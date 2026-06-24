#!/usr/bin/env python3
"""
Solveur exhaustif progressif Phase C — couvre TOUT l'espace atteignable.

Stratégie :
  1. BFS avant depuis l'ouverture (toutes positions ≤ max_empty)
  2. Vague rétrograde depuis positions déjà résolues (parents par coup annulé)
  3. max_empty progressif : 12 → 20 → 30 → 40 → 49
  4. Boucle continue sans plafond de lot ; checkpoint/reprise

Usage:
    python script/solver/build_full_tablebase.py [--db PATH] [--max-empty 12]
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import threading
import time
from collections import deque
from pathlib import Path
from typing import Deque, Optional, Set, Tuple

import numpy as np

ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = ROOT / "script"
if str(SCRIPT) not in sys.path:
    sys.path.insert(0, str(SCRIPT))

from game_tree.optimized_minimax import OptimizedMinimaxAdvisor
from solver.db_schema import init_db
from solver.exhaustive_explorer import (
    MAX_EMPTY_LEVELS,
    estimate_state_space,
    forward_bfs_unsolved,
    load_seed_positions_from_db,
    phase_for_max_empty,
    retrograde_unsolved_parents,
)
from solver.position_hasher import HASHER
from solver.retrograde_solver import RetrogradeSolver, SolvedPosition
from solver.solver_status import (
    append_recent,
    board_to_list,
    position_entry,
    read_status,
    write_status,
)

DEFAULT_DB = SCRIPT / "solver" / "data" / "tablebase.db"
CHECKPOINT_FILE = "solver_checkpoint.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("full_tablebase")


def _store_position(
    conn,
    solved: SolvedPosition,
    board: np.ndarray,
    current_player: int,
    last_move: Optional[Tuple[int, int]],
) -> None:
    br, bc = (-1, -1)
    if solved.best_move:
        br, bc = solved.best_move
    lmr, lmc = (-1, -1)
    if last_move is not None:
        lmr, lmc = last_move
    conn.execute(
        """
        INSERT OR REPLACE INTO positions
        (hash, result, win_rate, best_move_row, best_move_col, depth_remaining,
         board_json, current_player, pos_last_move_row, pos_last_move_col, solved_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """,
        (
            solved.hash_key,
            solved.result,
            solved.win_rate,
            br,
            bc,
            solved.depth_remaining,
            json.dumps(board_to_list(board)),
            current_player,
            lmr,
            lmc,
        ),
    )


def _update_progress(
    conn,
    *,
    solved: int,
    queued: int,
    last_hash: str,
    started_at: str,
    current_phase: str,
    solver_running: bool,
    progress_percent: Optional[float],
    max_empty: int,
) -> None:
    conn.execute(
        """
        INSERT INTO solver_progress
        (id, total_queued, total_solved, last_hash, started_at, current_phase,
         solver_running, total_target, progress_percent, updated_at)
        VALUES (1, ?, ?, ?, ?, ?, ?, NULL, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(id) DO UPDATE SET
            total_queued=excluded.total_queued,
            total_solved=excluded.total_solved,
            last_hash=excluded.last_hash,
            started_at=COALESCE(solver_progress.started_at, excluded.started_at),
            current_phase=excluded.current_phase,
            solver_running=excluded.solver_running,
            total_target=NULL,
            progress_percent=excluded.progress_percent,
            updated_at=CURRENT_TIMESTAMP
        """,
        (
            queued,
            solved,
            last_hash,
            started_at,
            current_phase,
            1 if solver_running else 0,
            progress_percent,
        ),
    )


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
    cp.write_text(
        json.dumps({
            "bfs_seen_count": len(bfs_seen),
            "bfs_seen_tail": list(bfs_seen)[-5000:],
            "retro_seen_count": len(retro_seen),
            "retro_seen_tail": list(retro_seen)[-5000:],
            "max_empty_level": max_empty_level,
            "exploration_mode": exploration_mode,
            "saved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }),
        encoding="utf-8",
    )


def _known_hashes_from_db(conn) -> Set[str]:
    rows = conn.execute("SELECT hash FROM positions").fetchall()
    return {str(r[0]) for r in rows}


def _compute_progress_percent(solved: int, max_empty: int) -> Optional[float]:
    est = estimate_state_space(max_empty)
    if est is None or est <= 0:
        return None
    return min(99.9, 100.0 * solved / est)


def _publish_status(
    *,
    total_solved: int,
    queued: int,
    started_at: str,
    started_mono: float,
    recent: list,
    current_phase: str,
    max_empty: int,
    solver_running: bool,
    batch_solved: int = 0,
    batch_elapsed: float = 0.0,
    board: Optional[np.ndarray] = None,
    current_player: int = 1,
    last_move: Optional[Tuple[int, int]] = None,
    solved: Optional[SolvedPosition] = None,
) -> list:
    rate = batch_solved / batch_elapsed if batch_elapsed > 0 else 0.0
    elapsed = max(time.monotonic() - started_mono, 0.001)
    overall_rate = total_solved / elapsed if total_solved else rate
    use_rate = rate if rate > 0 else overall_rate

    progress = _compute_progress_percent(total_solved, max_empty)
    est = estimate_state_space(max_empty)
    eta = None
    if progress is not None and use_rate > 0 and est and total_solved < est:
        eta = int((est - total_solved) / use_rate)

    payload = {
        "solver_running": solver_running,
        "started_at": started_at,
        "last_update": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "current_phase": current_phase,
        "max_empty": max_empty,
        "total_positions_solved": total_solved,
        "total_positions_target": est,
        "total_queued": queued,
        "progress_percent": round(progress, 4) if progress is not None else None,
        "progress_unknown": progress is None,
        "positions_per_second": round(use_rate, 2),
        "eta_seconds": eta,
        "recent_positions": recent,
    }

    if solved is not None and board is not None:
        entry = position_entry(
            hash_key=solved.hash_key,
            board=board,
            current_player=current_player,
            last_move=last_move,
            best_move=solved.best_move,
            result=solved.result,
            win_rate=solved.win_rate,
        )
        recent = append_recent(recent, entry)
        payload["recent_positions"] = recent
        payload["last_update"] = entry["solved_at"]

    write_status(payload)
    return recent


def _flush(
    conn,
    *,
    total_solved: int,
    queued: int,
    last_hash: str,
    started_at: str,
    started_mono: float,
    recent: list,
    solver: RetrogradeSolver,
    current_phase: str,
    max_empty: int,
    solver_running: bool,
    force_json: bool = False,
    board: Optional[np.ndarray] = None,
    current_player: int = 1,
    last_move: Optional[Tuple[int, int]] = None,
    solved: Optional[SolvedPosition] = None,
    batch_solved: int = 0,
    batch_elapsed: float = 0.0,
) -> list:
    progress = _compute_progress_percent(total_solved, max_empty)
    _update_progress(
        conn,
        solved=total_solved,
        queued=queued,
        last_hash=last_hash,
        started_at=started_at,
        current_phase=current_phase,
        solver_running=solver_running,
        progress_percent=progress,
        max_empty=max_empty,
    )
    conn.commit()

    if solved is not None:
        recent = _publish_status(
            total_solved=total_solved,
            queued=queued,
            started_at=started_at,
            started_mono=started_mono,
            recent=recent,
            current_phase=current_phase,
            max_empty=max_empty,
            solver_running=solver_running,
            batch_solved=batch_solved,
            batch_elapsed=max(batch_elapsed, 0.001),
            board=board,
            current_player=current_player,
            last_move=last_move,
            solved=solved,
        )
    elif force_json:
        recent = _publish_status(
            total_solved=total_solved,
            queued=queued,
            started_at=started_at,
            started_mono=started_mono,
            recent=recent,
            current_phase=current_phase,
            max_empty=max_empty,
            solver_running=solver_running,
        )

    solver.clear_cache()
    return recent


def _resolve_level_index(max_empty: int, checkpoint: dict) -> int:
    if "max_empty_level" in checkpoint:
        return int(checkpoint["max_empty_level"])
    for i, level in enumerate(MAX_EMPTY_LEVELS):
        if level >= max_empty:
            return i
    return len(MAX_EMPTY_LEVELS) - 1


def _fill_queue_forward(
    advisor: OptimizedMinimaxAdvisor,
    max_empty: int,
    known: Set[str],
    bfs_seen: Set[str],
    limit: int = 50_000,
) -> Deque[Tuple]:
    q: Deque[Tuple] = deque()
    for pos in forward_bfs_unsolved(advisor, max_empty, known, bfs_seen):
        q.append(pos)
        if len(q) >= limit:
            break
    return q


def _fill_queue_retrograde(
    conn,
    advisor: OptimizedMinimaxAdvisor,
    max_empty: int,
    known: Set[str],
    retro_seen: Set[str],
    limit: int = 50_000,
) -> Deque[Tuple]:
    seeds = load_seed_positions_from_db(conn, limit=2000)
    q: Deque[Tuple] = deque()
    for pos in retrograde_unsolved_parents(advisor, max_empty, known, seeds, retro_seen):
        q.append(pos)
        if len(q) >= limit:
            break
    return q


def run_full_solver(
    db_path: Path,
    max_empty_start: int = 12,
    batch_size: int = 25,
    progress_interval_sec: float = 15.0,
    position_timeout_sec: float = 30.0,
    sleep_between_batches: float = 0.02,
) -> None:
    conn = init_db(db_path)
    checkpoint = _load_checkpoint(db_path)

    level_idx = _resolve_level_index(max_empty_start, checkpoint)
    if level_idx < len(MAX_EMPTY_LEVELS):
        max_empty = MAX_EMPTY_LEVELS[level_idx]
    else:
        max_empty = MAX_EMPTY_LEVELS[-1]

    solver = RetrogradeSolver(max_empty=max_empty, position_timeout_sec=position_timeout_sec)
    advisor = OptimizedMinimaxAdvisor(depth=2, use_iterative_deepening=False)

    known = _known_hashes_from_db(conn)
    bfs_seen: Set[str] = set(checkpoint.get("bfs_seen_tail") or [])
    retro_seen: Set[str] = set(checkpoint.get("retro_seen_tail") or [])
    bfs_seen |= known
    retro_seen |= known

    total_solved = conn.execute("SELECT COUNT(*) FROM positions").fetchone()[0]
    started_mono = time.monotonic()
    prev_status = read_status()
    started_at = prev_status.get("started_at") or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    recent: list = list(prev_status.get("recent_positions") or [])

    exploration_mode = "forward"
    queue: Deque[Tuple] = _fill_queue_forward(advisor, max_empty, known, bfs_seen)
    if not queue:
        exploration_mode = "retrograde"
        queue = _fill_queue_retrograde(conn, advisor, max_empty, known, retro_seen)

    current_phase = phase_for_max_empty(max_empty)
    logger.info(
        "Solveur exhaustif — phase=%s, max_empty=%d, résolu=%d, file=%d, mode=%s",
        current_phase,
        max_empty,
        total_solved,
        len(queue),
        exploration_mode,
    )

    _flush(
        conn,
        total_solved=total_solved,
        queued=len(queue),
        last_hash="",
        started_at=started_at,
        started_mono=started_mono,
        recent=recent,
        solver=solver,
        current_phase=current_phase,
        max_empty=max_empty,
        solver_running=True,
        force_json=True,
    )

    batch_count = 0
    batch_start_mono = time.monotonic()
    batch_start_solved = total_solved
    last_progress_mono = time.monotonic()
    last_hash = ""
    last_board: Optional[np.ndarray] = None
    last_player = 1
    last_move_saved: Optional[Tuple[int, int]] = None
    last_solved: Optional[SolvedPosition] = None
    skipped_timeouts = 0

    heartbeat_stop = threading.Event()
    heartbeat_lock = threading.Lock()
    shared = {
        "total_solved": total_solved,
        "queued": len(queue),
        "last_hash": "",
        "last_progress_mono": time.monotonic(),
        "current_phase": current_phase,
        "max_empty": max_empty,
    }

    def _heartbeat() -> None:
        while not heartbeat_stop.wait(progress_interval_sec):
            with heartbeat_lock:
                if heartbeat_stop.is_set():
                    break
                now = time.monotonic()
                if (now - shared["last_progress_mono"]) < progress_interval_sec:
                    continue
                try:
                    _flush(
                        conn,
                        total_solved=shared["total_solved"],
                        queued=shared["queued"],
                        last_hash=shared["last_hash"],
                        started_at=started_at,
                        started_mono=started_mono,
                        recent=recent,
                        solver=solver,
                        current_phase=shared["current_phase"],
                        max_empty=shared["max_empty"],
                        solver_running=True,
                        force_json=True,
                    )
                    shared["last_progress_mono"] = now
                except Exception as exc:
                    logger.warning("Heartbeat échoué: %s", exc)

    heartbeat_thread = threading.Thread(target=_heartbeat, daemon=True)
    heartbeat_thread.start()

    try:
        while True:
            if not queue:
                known = _known_hashes_from_db(conn)

                if exploration_mode == "forward":
                    exploration_mode = "retrograde"
                    queue = _fill_queue_retrograde(conn, advisor, max_empty, known, retro_seen)
                    logger.info("Bascule rétrograde — file=%d", len(queue))
                else:
                    if level_idx + 1 < len(MAX_EMPTY_LEVELS):
                        level_idx += 1
                        max_empty = MAX_EMPTY_LEVELS[level_idx]
                        solver.max_empty = max_empty
                        current_phase = phase_for_max_empty(max_empty)
                        exploration_mode = "forward"
                        queue = _fill_queue_forward(advisor, max_empty, known, bfs_seen)
                        logger.info(
                            "Extension max_empty=%d (phase %s) — file=%d",
                            max_empty,
                            current_phase,
                            len(queue),
                        )
                    else:
                        exploration_mode = "forward"
                        bfs_seen.clear()
                        bfs_seen |= known
                        retro_seen.clear()
                        retro_seen |= known
                        queue = _fill_queue_forward(advisor, max_empty, known, bfs_seen)
                        logger.info("Nouvelle passe complète — file=%d", len(queue))

                with heartbeat_lock:
                    shared["queued"] = len(queue)
                    shared["current_phase"] = current_phase
                    shared["max_empty"] = max_empty

                _flush(
                    conn,
                    total_solved=total_solved,
                    queued=len(queue),
                    last_hash=last_hash,
                    started_at=started_at,
                    started_mono=started_mono,
                    recent=recent,
                    solver=solver,
                    current_phase=current_phase,
                    max_empty=max_empty,
                    solver_running=True,
                    force_json=True,
                )
                _save_checkpoint(
                    db_path,
                    bfs_seen=bfs_seen,
                    retro_seen=retro_seen,
                    max_empty_level=level_idx,
                    exploration_mode=exploration_mode,
                )

                if not queue:
                    logger.info("File vide — pause 30s avant nouvelle exploration")
                    time.sleep(30)
                    continue

            board, player, last_move = queue.popleft()
            h = HASHER.hash_key(board, player, last_move)

            if h in known:
                continue

            existing = conn.execute("SELECT 1 FROM positions WHERE hash=?", (h,)).fetchone()
            if existing:
                known.add(h)
                continue

            solver.begin_position()
            solved = solver.solve_position(board, player, last_move)

            if solved is None:
                if solver._timed_out:
                    skipped_timeouts += 1
                    logger.warning(
                        "Timeout %.0fs — hash=%s, vides=%d",
                        position_timeout_sec,
                        h[:12],
                        HASHER.empty_cells(board),
                    )
                continue

            _store_position(conn, solved, board, player, last_move)
            total_solved += 1
            known.add(h)
            batch_count += 1
            last_hash = h
            last_board = board
            last_player = player
            last_move_saved = last_move
            last_solved = solved

            with heartbeat_lock:
                shared["total_solved"] = total_solved
                shared["queued"] = len(queue)
                shared["last_hash"] = last_hash

            now_mono = time.monotonic()
            should_flush = (
                batch_count >= batch_size
                or (now_mono - last_progress_mono) >= progress_interval_sec
            )

            if should_flush:
                batch_elapsed = max(now_mono - batch_start_mono, 0.001)
                recent = _flush(
                    conn,
                    total_solved=total_solved,
                    queued=len(queue),
                    last_hash=last_hash,
                    started_at=started_at,
                    started_mono=started_mono,
                    recent=recent,
                    solver=solver,
                    current_phase=current_phase,
                    max_empty=max_empty,
                    solver_running=True,
                    board=last_board,
                    current_player=last_player,
                    last_move=last_move_saved,
                    solved=last_solved,
                    batch_solved=total_solved - batch_start_solved,
                    batch_elapsed=batch_elapsed,
                )
                _save_checkpoint(
                    db_path,
                    bfs_seen=bfs_seen,
                    retro_seen=retro_seen,
                    max_empty_level=level_idx,
                    exploration_mode=exploration_mode,
                )
                progress = _compute_progress_percent(total_solved, max_empty)
                pct_str = f"{progress:.2f}%" if progress is not None else "exploration"
                logger.info(
                    "Progression : %d positions (%s) — %.2f pos/s, file=%d, phase=%s",
                    total_solved,
                    pct_str,
                    (total_solved - batch_start_solved) / batch_elapsed,
                    len(queue),
                    current_phase,
                )
                batch_count = 0
                batch_start_mono = time.monotonic()
                batch_start_solved = total_solved
                last_progress_mono = time.monotonic()
                with heartbeat_lock:
                    shared["last_progress_mono"] = last_progress_mono
                time.sleep(sleep_between_batches)

    except KeyboardInterrupt:
        logger.info("Interruption — sauvegarde checkpoint")
    finally:
        heartbeat_stop.set()
        heartbeat_thread.join(timeout=2.0)
        _save_checkpoint(
            db_path,
            bfs_seen=bfs_seen,
            retro_seen=retro_seen,
            max_empty_level=level_idx,
            exploration_mode=exploration_mode,
        )
        conn.commit()
        conn.close()

    if skipped_timeouts:
        logger.info("%d positions ignorées (timeout)", skipped_timeouts)


def main() -> None:
    parser = argparse.ArgumentParser(description="Solveur exhaustif progressif 4mation")
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--max-empty", type=int, default=12)
    parser.add_argument("--batch", type=int, default=25)
    parser.add_argument("--progress-interval", type=float, default=15.0)
    parser.add_argument("--position-timeout", type=float, default=30.0)
    # Arguments hérités (ignorés — boucle continue intégrée)
    parser.add_argument("--progress-every", type=int, default=1, help=argparse.SUPPRESS)
    parser.add_argument("--continuous", action="store_true", default=True, help=argparse.SUPPRESS)
    parser.add_argument("--refill-sleep", type=float, default=5.0, help=argparse.SUPPRESS)
    args = parser.parse_args()

    run_full_solver(
        Path(args.db),
        max_empty_start=args.max_empty,
        batch_size=args.batch,
        progress_interval_sec=args.progress_interval,
        position_timeout_sec=args.position_timeout,
    )


if __name__ == "__main__":
    main()
