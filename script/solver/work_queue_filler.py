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


def _save_checkpoint(
    db_path: Path,
    *,
    bfs_seen: Set[str],
    retro_seen: Set[str],
    max_empty_level: int,
    exploration_mode: str,
) -> None:
    cp = db_path.parent / CHECKPOINT_FILE
    tail_bfs = list(bfs_seen)[-50000:]
    tail_retro = list(retro_seen)[-50000:]
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


def _known_hashes(conn) -> Set[str]:
    known: Set[str] = set()
    for row in conn.execute("SELECT hash FROM positions"):
        known.add(str(row[0]).lower())
    for row in conn.execute(
        "SELECT hash FROM work_queue WHERE status IN ('pending', 'in_progress', 'done')"
    ):
        known.add(str(row[0]).lower())
    return known


def _resolve_level_index(max_empty: int, checkpoint: dict) -> int:
    if "max_empty_level" in checkpoint:
        return int(checkpoint["max_empty_level"])
    for i, level in enumerate(MAX_EMPTY_LEVELS):
        if level >= max_empty:
            return i
    return len(MAX_EMPTY_LEVELS) - 1


def fill_queue(
    db_path: Path,
    max_empty_start: int = 12,
    batch_size: int = 200,
    sleep_sec: float = 2.0,
    once: bool = False,
) -> None:
    conn = init_db(db_path)
    checkpoint = _load_checkpoint(db_path)
    level_idx = _resolve_level_index(max_empty_start, checkpoint)
    max_empty = MAX_EMPTY_LEVELS[min(level_idx, len(MAX_EMPTY_LEVELS) - 1)]

    advisor = OptimizedMinimaxAdvisor(depth=2, use_iterative_deepening=False)
    known = _known_hashes(conn)
    bfs_seen: Set[str] = set(checkpoint.get("bfs_seen_tail") or [])
    retro_seen: Set[str] = set(checkpoint.get("retro_seen_tail") or [])
    bfs_seen |= known
    retro_seen |= known

    exploration_mode = checkpoint.get("exploration_mode") or "retrograde"
    work_iter = None

    logger.info(
        "Filler démarré — max_empty=%d, known=%d, mode=%s",
        max_empty,
        len(known),
        exploration_mode,
    )

    while True:
        inserted = 0
        if work_iter is None:
            if exploration_mode == "forward":
                work_iter = forward_bfs_unsolved(advisor, max_empty, known, bfs_seen)
            else:
                seeds = load_seed_positions_from_db(conn, limit=3000)
                work_iter = retrograde_unsolved_parents(
                    advisor, max_empty, known, seeds, retro_seen
                )

        try:
            while inserted < batch_size:
                board, player, last_move = next(work_iter)
                h = HASHER.hash_key(board, player, last_move)
                if h in known:
                    continue
                known.add(h)
                board_json = json.dumps(board_to_list(board))
                lmr, lmc = (-1, -1)
                if last_move is not None:
                    lmr, lmc = last_move
                before = conn.total_changes
                conn.execute(
                    """
                    INSERT OR IGNORE INTO work_queue
                    (hash, board_json, player, last_move_row, last_move_col, status)
                    VALUES (?, ?, ?, ?, ?, 'pending')
                    """,
                    (h, board_json, player, lmr, lmc),
                )
                if conn.total_changes > before:
                    inserted += 1
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
                logger.info("Filler terminé — espace exploré pour tous les niveaux")
                if once:
                    break
                time.sleep(30)
                known = _known_hashes(conn)
                continue

        pending = conn.execute(
            "SELECT COUNT(*) FROM work_queue WHERE status = 'pending'"
        ).fetchone()[0]
        conn.execute(
            """
            INSERT INTO solver_progress (id, total_queued, updated_at)
            VALUES (1, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(id) DO UPDATE SET total_queued = excluded.total_queued, updated_at = CURRENT_TIMESTAMP
            """,
            (pending,),
        )
        conn.commit()

        _save_checkpoint(
            db_path,
            bfs_seen=bfs_seen,
            retro_seen=retro_seen,
            max_empty_level=level_idx,
            exploration_mode=exploration_mode,
        )

        if inserted:
            logger.info("+%d positions en queue (pending=%d)", inserted, pending)

        if once:
            break
        time.sleep(sleep_sec)


def main() -> None:
    parser = argparse.ArgumentParser(description="Alimente work_queue pour workers distribués")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--max-empty", type=int, default=12)
    parser.add_argument("--batch", type=int, default=200)
    parser.add_argument("--sleep", type=float, default=2.0)
    parser.add_argument("--once", action="store_true", help="Un seul lot puis sortie")
    args = parser.parse_args()

    fill_queue(
        args.db,
        max_empty_start=args.max_empty,
        batch_size=args.batch,
        sleep_sec=args.sleep,
        once=args.once,
    )


if __name__ == "__main__":
    main()
