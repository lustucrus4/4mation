#!/usr/bin/env python3
"""
Générateur de positions pour la file work_queue (BFS + rétrograde).

Alimente work_queue avec des hash absents de positions et de la queue.
À lancer sur le VPS (cron ou conteneur solver).

Usage:
    python script/solver/work_queue_filler.py --db PATH [--max-empty 12] [--batch 200]
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Optional, Set, Tuple

import numpy as np

ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = ROOT / "script"
if str(SCRIPT) not in sys.path:
    sys.path.insert(0, str(SCRIPT))

from game_tree.optimized_minimax import OptimizedMinimaxAdvisor
from solver.db_schema import init_db
from solver.exhaustive_explorer import (
    MAX_EMPTY_LEVELS,
    forward_bfs_unsolved,
    load_seed_positions_from_db,
    retrograde_unsolved_parents,
)
from solver.position_hasher import HASHER
from solver.solver_status import board_to_list

DEFAULT_DB = SCRIPT / "solver" / "data" / "tablebase.db"
CHECKPOINT_FILE = "filler_checkpoint.json"
DEFAULT_BATCH = 5000
DEFAULT_SLEEP_SEC = 0.0
DEFAULT_MIN_PENDING = 10000
TURBO_BATCH_CAP = 50000
CHECKPOINT_EVERY_TURBO = 200
IDLE_ROUNDS_BEFORE_RESET = 1
SEED_LIMIT = 20000
INSERT_CHUNK = 2000
KNOWN_REFRESH_SEC = 45.0
PROGRESS_EVERY_TURBO = 15
CHECKPOINT_TAIL = 25000
INSERT_SQL = """
INSERT OR IGNORE INTO work_queue
(hash, board_json, player, last_move_row, last_move_col, status)
VALUES (?, ?, ?, ?, ?, 'pending')
"""

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("work_queue_filler")


def _load_checkpoint(db_path: Path) -> dict:
    cp = db_path.parent / CHECKPOINT_FILE
    if not cp.exists():
        return {}
    try:
        return json.loads(cp.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _tune_sqlite(conn) -> None:
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=-128000")
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute("PRAGMA mmap_size=268435456")


def _save_checkpoint(
    db_path: Path,
    *,
    bfs_seen: Set[str],
    retro_seen: Set[str],
    max_empty_level: int,
    exploration_mode: str,
) -> None:
    cp = db_path.parent / CHECKPOINT_FILE
    tail_bfs = list(bfs_seen)[-CHECKPOINT_TAIL:]
    tail_retro = list(retro_seen)[-CHECKPOINT_TAIL:]
    cp.write_text(
        json.dumps(
            {
                "bfs_seen_tail": tail_bfs,
                "retro_seen_tail": tail_retro,
                "max_empty_level": max_empty_level,
                "exploration_mode": exploration_mode,
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def _known_hashes(conn, *, full: bool = True) -> Set[str]:
    known: Set[str] = set()
    for row in conn.execute("SELECT hash FROM positions"):
        known.add(str(row[0]).lower())
    if full:
        for row in conn.execute(
            "SELECT hash FROM work_queue WHERE status IN ('pending', 'in_progress', 'done')"
        ):
            known.add(str(row[0]).lower())
    else:
        for row in conn.execute(
            "SELECT hash FROM work_queue WHERE status IN ('pending', 'in_progress')"
        ):
            known.add(str(row[0]).lower())
    return known


def _incremental_known_refresh(conn, known: Set[str], last_refresh: float) -> float:
    """Ajoute les hashes résolus récemment sans recharger toute la base."""
    now = time.monotonic()
    if now - last_refresh < KNOWN_REFRESH_SEC:
        return last_refresh
    for row in conn.execute(
        "SELECT hash FROM positions WHERE solved_at > datetime('now', '-120 seconds')"
    ):
        known.add(str(row[0]).lower())
    for row in conn.execute(
        """
        SELECT hash FROM work_queue
        WHERE status = 'done' AND created_at > datetime('now', '-120 seconds')
        """
    ):
        known.add(str(row[0]).lower())
    return now


def _resolve_level_index(max_empty: int, checkpoint: dict) -> int:
    if "max_empty_level" in checkpoint:
        return int(checkpoint["max_empty_level"])
    for i, level in enumerate(MAX_EMPTY_LEVELS):
        if level >= max_empty:
            return i
    return len(MAX_EMPTY_LEVELS) - 1


def _effective_batch(batch_size: int, pending: int, min_pending: int) -> int:
    if min_pending <= 0 or pending >= min_pending:
        return batch_size
    if pending < min_pending // 5:
        mult = 5
    elif pending < min_pending // 3:
        mult = 4
    elif pending < min_pending // 2:
        mult = 3
    else:
        mult = 2
    return min(batch_size * mult, TURBO_BATCH_CAP)


def fill_queue(
    db_path: Path,
    max_empty_start: int = 12,
    batch_size: int = DEFAULT_BATCH,
    sleep_sec: float = DEFAULT_SLEEP_SEC,
    min_pending: int = DEFAULT_MIN_PENDING,
    once: bool = False,
) -> None:
    conn = init_db(db_path)
    _tune_sqlite(conn)
    checkpoint = _load_checkpoint(db_path)
    level_idx = _resolve_level_index(max_empty_start, checkpoint)
    max_empty = MAX_EMPTY_LEVELS[min(level_idx, len(MAX_EMPTY_LEVELS) - 1)]

    advisor = OptimizedMinimaxAdvisor(depth=2, use_iterative_deepening=False)
    known = _known_hashes(conn)
    bfs_seen: Set[str] = set(checkpoint.get("bfs_seen_tail") or [])
    retro_seen: Set[str] = set(checkpoint.get("retro_seen_tail") or [])
    # Ne pas fusionner known dans bfs_seen/retro_seen : sinon le parcours ne découvre
    # plus de nouvelles branches à travers des positions déjà résolues.

    exploration_mode = checkpoint.get("exploration_mode") or "retrograde"
    work_iter = None
    idle_rounds = 0
    turbo_rounds = 0
    known_refresh_at = time.monotonic()

    logger.info(
        "Filler démarré — max_empty=%d, known=%d, mode=%s, batch=%d, min_pending=%d",
        max_empty,
        len(known),
        exploration_mode,
        batch_size,
        min_pending,
    )

    while True:
        inserted = 0
        pending_now = conn.execute(
            "SELECT COUNT(*) FROM work_queue WHERE status = 'pending'"
        ).fetchone()[0]
        turbo = min_pending > 0 and pending_now < min_pending
        target_batch = _effective_batch(batch_size, pending_now, min_pending)
        known_refresh_at = _incremental_known_refresh(conn, known, known_refresh_at)
        if work_iter is None:
            if exploration_mode == "forward":
                work_iter = forward_bfs_unsolved(advisor, max_empty, known, bfs_seen)
            else:
                seeds = load_seed_positions_from_db(conn, limit=SEED_LIMIT)
                work_iter = retrograde_unsolved_parents(
                    advisor, max_empty, known, seeds, retro_seen
                )

        rows_buffer: list[tuple] = []
        try:
            while inserted < target_batch:
                board, player, last_move = next(work_iter)
                h = HASHER.hash_key(board, player, last_move)
                if h in known:
                    continue
                known.add(h)
                board_json = json.dumps(board_to_list(board))
                lmr, lmc = (-1, -1)
                if last_move is not None:
                    lmr, lmc = last_move
                rows_buffer.append((h, board_json, player, lmr, lmc))
                if len(rows_buffer) >= INSERT_CHUNK:
                    before = conn.total_changes
                    conn.executemany(INSERT_SQL, rows_buffer)
                    inserted += conn.total_changes - before
                    rows_buffer.clear()
                    if inserted >= target_batch:
                        break
            if rows_buffer and inserted < target_batch:
                before = conn.total_changes
                conn.executemany(INSERT_SQL, rows_buffer)
                inserted += conn.total_changes - before
                rows_buffer.clear()
        except StopIteration:
            work_iter = None
            if exploration_mode == "retrograde":
                exploration_mode = "forward"
                logger.info("Bascule filler → mode forward (max_empty=%d)", max_empty)
            elif level_idx + 1 < len(MAX_EMPTY_LEVELS):
                level_idx += 1
                max_empty = MAX_EMPTY_LEVELS[level_idx]
                exploration_mode = "retrograde"
                logger.info("Niveau filler suivant — max_empty=%d", max_empty)
            else:
                logger.info(
                    "Passe exploration terminée (max_empty=%d) — recyclage niveau 0",
                    max_empty,
                )
                level_idx = 0
                max_empty = MAX_EMPTY_LEVELS[0]
                exploration_mode = "retrograde"
                work_iter = None
                bfs_seen.clear()
                retro_seen.clear()
                known = _known_hashes(conn, full=True)
                known_refresh_at = time.monotonic()
                if once:
                    break
                if sleep_sec > 0 and not turbo:
                    time.sleep(sleep_sec)
                continue

        if turbo and inserted > 0:
            pending = pending_now + inserted
        else:
            pending = conn.execute(
                "SELECT COUNT(*) FROM work_queue WHERE status = 'pending'"
            ).fetchone()[0]
        if not turbo or turbo_rounds % PROGRESS_EVERY_TURBO == 0:
            conn.execute(
                """
                INSERT INTO solver_progress (id, total_queued, updated_at)
                VALUES (1, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(id) DO UPDATE SET total_queued = excluded.total_queued, updated_at = CURRENT_TIMESTAMP
                """,
                (pending,),
            )
        conn.commit()

        turbo_rounds = turbo_rounds + 1 if turbo else 0
        if not turbo or turbo_rounds % CHECKPOINT_EVERY_TURBO == 0 or inserted == 0:
            _save_checkpoint(
                db_path,
                bfs_seen=bfs_seen,
                retro_seen=retro_seen,
                max_empty_level=level_idx,
                exploration_mode=exploration_mode,
            )

        if inserted:
            idle_rounds = 0
            tag = " [turbo]" if turbo else ""
            logger.info("+%d positions en queue (pending=%d)%s", inserted, pending, tag)
        else:
            idle_rounds += 1
            if idle_rounds >= IDLE_ROUNDS_BEFORE_RESET:
                logger.warning(
                    "Filler bloqué (%d tours sans insertion) — avance niveau ou reset exploration",
                    idle_rounds,
                )
                work_iter = None
                idle_rounds = 0
                bfs_seen.clear()
                retro_seen.clear()
                if exploration_mode == "retrograde":
                    exploration_mode = "forward"
                elif level_idx + 1 < len(MAX_EMPTY_LEVELS):
                    level_idx += 1
                    max_empty = MAX_EMPTY_LEVELS[level_idx]
                    exploration_mode = "retrograde"
                    logger.info("Niveau filler forcé — max_empty=%d", max_empty)
                else:
                    exploration_mode = "retrograde"
                    level_idx = 0
                    max_empty = MAX_EMPTY_LEVELS[0]
                    known = _known_hashes(conn, full=True)
                    known_refresh_at = time.monotonic()
                    logger.info("Recyclage exploration depuis niveau %d", max_empty)

        if once:
            break
        if min_pending > 0 and pending < min_pending:
            continue
        time.sleep(sleep_sec)


def main() -> None:
    parser = argparse.ArgumentParser(description="Alimente work_queue pour workers distribués")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--max-empty", type=int, default=12)
    parser.add_argument("--batch", type=int, default=DEFAULT_BATCH)
    parser.add_argument("--sleep", type=float, default=DEFAULT_SLEEP_SEC)
    parser.add_argument(
        "--min-pending",
        type=int,
        default=DEFAULT_MIN_PENDING,
        help="Cible de tampon : pas de pause tant que pending < cette valeur (turbo x2–x5 selon niveau)",
    )
    parser.add_argument("--once", action="store_true", help="Un seul lot puis sortie")
    args = parser.parse_args()

    fill_queue(
        args.db,
        max_empty_start=args.max_empty,
        batch_size=args.batch,
        sleep_sec=args.sleep,
        min_pending=max(0, args.min_pending),
        once=args.once,
    )


if __name__ == "__main__":
    main()
