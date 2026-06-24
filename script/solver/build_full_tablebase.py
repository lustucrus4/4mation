#!/usr/bin/env python3

"""

Solveur complet progressif avec checkpoint/reprise (Phase C — serveur background).



Parcourt l'espace de positions par BFS rétrograde depuis les terminales,

écrit au fur et à mesure dans tablebase.db et publie solver_status.json.



Usage:

    python script/solver/build_full_tablebase.py [--db PATH] [--max-empty 20] [--batch 500]

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

from typing import Optional, Set, Tuple



import numpy as np



ROOT = Path(__file__).resolve().parent.parent.parent

SCRIPT = ROOT / "script"

if str(SCRIPT) not in sys.path:

    sys.path.insert(0, str(SCRIPT))



from game_tree.optimized_minimax import OptimizedMinimaxAdvisor

from solver.db_schema import init_db

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

PHASE = "full"



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

    total_target: int,

    progress_percent: float,

    solver_running: bool,

) -> None:

    conn.execute(

        """

        INSERT INTO solver_progress

        (id, total_queued, total_solved, last_hash, started_at, current_phase,

         solver_running, total_target, progress_percent, updated_at)

        VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)

        ON CONFLICT(id) DO UPDATE SET

            total_queued=excluded.total_queued,

            total_solved=excluded.total_solved,

            last_hash=excluded.last_hash,

            started_at=COALESCE(solver_progress.started_at, excluded.started_at),

            current_phase=excluded.current_phase,

            solver_running=excluded.solver_running,

            total_target=excluded.total_target,

            progress_percent=excluded.progress_percent,

            updated_at=CURRENT_TIMESTAMP

        """,

        (

            queued,

            solved,

            last_hash,

            started_at,

            PHASE,

            1 if solver_running else 0,

            total_target,

            progress_percent,

        ),

    )





def _load_checkpoint(db_path: Path) -> Set[str]:

    cp = db_path.parent / CHECKPOINT_FILE

    if not cp.exists():

        return set()

    try:

        data = json.loads(cp.read_text(encoding="utf-8"))

        return set(data.get("processed", []))

    except (json.JSONDecodeError, OSError):

        return set()





def _save_checkpoint(db_path: Path, processed: Set[str]) -> None:

    cp = db_path.parent / CHECKPOINT_FILE

    cp.write_text(

        json.dumps({"processed": list(processed)[-10000:], "count": len(processed)}),

        encoding="utf-8",

    )





def _known_hashes_from_db(conn) -> Set[str]:
    rows = conn.execute("SELECT hash FROM positions").fetchall()
    return {str(r[0]) for r in rows}


def _enumerate_seed_positions(

    advisor: OptimizedMinimaxAdvisor,

    max_empty: int,

    num_games: int = 500,

    exclude: Optional[Set[str]] = None,

) -> deque:

    """Génère des positions candidates via parties aléatoires."""

    import random



    queue: deque = deque()

    seen: Set[str] = set(exclude or ())

    skip = exclude or set()



    for _ in range(num_games):

        board = np.zeros((7, 7), dtype=np.int8)

        player = 1

        last_move = None

        for _ply in range(49):

            if HASHER.empty_cells(board) <= max_empty:

                h = HASHER.hash_key(board, player, last_move)

                if h not in seen and h not in skip:

                    seen.add(h)

                    queue.append((board.copy(), player, last_move))

            if advisor._check_winner(board) is not None:

                break

            moves = advisor._get_frontier_moves(board, last_move, player)

            if not moves:

                break

            move = random.choice(moves)

            board = board.copy()

            board[move[0], move[1]] = player

            last_move = move

            if advisor._check_winner(board) is not None or np.all(board != 0):

                break

            player = 3 - player



    return queue





def _sort_queue_by_difficulty(queue: deque) -> deque:
    """Traite d'abord les positions avec le moins de cases vides."""
    items = list(queue)
    items.sort(key=lambda item: HASHER.empty_cells(item[0]))
    return deque(items)





def _publish_live_status(

    *,

    total_solved: int,

    total_target: int,

    queued: int,

    started_at: str,

    started_mono: float,

    batch_solved: int,

    batch_elapsed: float,

    last_hash: str,

    recent: list,

    board: np.ndarray,

    current_player: int,

    last_move: Optional[Tuple[int, int]],

    solved: SolvedPosition,

    solver_running: bool,

) -> list:

    rate = batch_solved / batch_elapsed if batch_elapsed > 0 else 0.0

    elapsed = max(time.monotonic() - started_mono, 0.001)

    overall_rate = total_solved / elapsed if total_solved else rate

    use_rate = rate if rate > 0 else overall_rate

    remaining = max(total_target - total_solved, 0)

    eta = int(remaining / use_rate) if use_rate > 0 and remaining > 0 else None

    progress = min(100.0, 100.0 * total_solved / max(total_target, 1))



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



    write_status({

        "solver_running": solver_running,

        "started_at": started_at,

        "last_update": entry["solved_at"],

        "current_phase": PHASE,

        "total_positions_solved": total_solved,

        "total_positions_target": total_target,

        "total_queued": queued,

        "progress_percent": round(progress, 4),

        "positions_per_second": round(use_rate, 2),

        "eta_seconds": eta,

        "recent_positions": recent,

    })

    return recent





def _flush_progress(
    conn,
    *,
    total_solved: int,
    total_target: int,
    queued: int,
    last_hash: str,
    started_at: str,
    started_mono: float,
    recent: list,
    solver: RetrogradeSolver,
    solver_running: bool,
    force_json: bool = False,
    board: Optional[np.ndarray] = None,
    current_player: int = 1,
    last_move: Optional[Tuple[int, int]] = None,
    solved: Optional[SolvedPosition] = None,
    batch_solved: int = 0,
    batch_elapsed: float = 0.0,
) -> list:
    """Écrit progression DB + JSON (heartbeat même sans batch complet)."""
    progress = min(100.0, 100.0 * total_solved / max(total_target, 1))
    _update_progress(
        conn,
        solved=total_solved,
        queued=queued,
        last_hash=last_hash,
        started_at=started_at,
        total_target=total_target,
        progress_percent=progress,
        solver_running=solver_running,
    )
    conn.commit()
    if solved is not None:
        recent = _publish_live_status(
            total_solved=total_solved,
            total_target=total_target,
            queued=queued,
            started_at=started_at,
            started_mono=started_mono,
            batch_solved=batch_solved,
            batch_elapsed=max(batch_elapsed, 0.001),
            last_hash=last_hash,
            recent=recent,
            board=board if board is not None else np.zeros((7, 7), dtype=np.int8),
            current_player=current_player,
            last_move=last_move,
            solved=solved,
            solver_running=solver_running,
        )
    elif force_json:
        elapsed = max(time.monotonic() - started_mono, 0.001)
        rate = total_solved / elapsed if total_solved else 0.0
        progress = min(100.0, 100.0 * total_solved / max(total_target, 1))
        write_status({
            "solver_running": solver_running,
            "started_at": started_at,
            "last_update": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "current_phase": PHASE,
            "total_positions_solved": total_solved,
            "total_positions_target": total_target,
            "total_queued": queued,
            "progress_percent": round(progress, 4),
            "positions_per_second": round(rate, 2),
            "eta_seconds": None,
            "recent_positions": recent,
        })
    solver.clear_cache()
    return recent


def _refill_queue(
    conn,
    advisor: OptimizedMinimaxAdvisor,
    max_empty: int,
    *,
    num_games: int,
    known: Set[str],
) -> deque:
    """Génère une file de positions absentes de la base."""
    raw = _enumerate_seed_positions(
        advisor, max_empty, num_games=num_games, exclude=known,
    )
    fresh: deque = deque()
    for board, player, last_move in raw:
        h = HASHER.hash_key(board, player, last_move)
        if h in known:
            continue
        fresh.append((board, player, last_move))
    return _sort_queue_by_difficulty(fresh)


def run_full_solver(
    db_path: Path,
    max_empty: int = 12,
    batch_size: int = 25,
    progress_every: int = 1,
    progress_interval_sec: float = 15.0,
    sleep_between_batches: float = 0.05,
    position_timeout_sec: float = 30.0,
    continuous: bool = True,
    refill_sleep_sec: float = 5.0,
    max_refill_games: int = 8000,
) -> None:

    conn = init_db(db_path)

    solver = RetrogradeSolver(max_empty=max_empty, position_timeout_sec=position_timeout_sec)

    advisor = OptimizedMinimaxAdvisor(depth=2, use_iterative_deepening=False)

    checkpoint_processed = _load_checkpoint(db_path)

    total_solved = conn.execute("SELECT COUNT(*) FROM positions").fetchone()[0]

    known = _known_hashes_from_db(conn)
    num_games = 500
    queue = _refill_queue(conn, advisor, max_empty, num_games=num_games, known=known)

    # Cible = file initiale + déjà résolu (sans gonfler via checkpoint)
    total_target = max(total_solved + len(queue), total_solved + 50, total_solved, 1)



    started_mono = time.monotonic()

    prev_status = read_status()

    started_at = prev_status.get("started_at") or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    recent: list = list(prev_status.get("recent_positions") or [])



    logger.info(

        "Démarrage solveur complet — max_empty=%d, déjà %d positions, file=%d, cible ~%d",

        max_empty,

        total_solved,

        len(queue),

        total_target,

    )



    _update_progress(

        conn,

        solved=total_solved,

        queued=len(queue),

        last_hash="",

        started_at=started_at,

        total_target=total_target,

        progress_percent=100.0 * total_solved / total_target,

        solver_running=True,

    )

    conn.commit()



    write_status({

        "solver_running": True,

        "started_at": started_at,

        "last_update": started_at,

        "current_phase": PHASE,

        "total_positions_solved": total_solved,

        "total_positions_target": total_target,

        "total_queued": len(queue),

        "progress_percent": round(100.0 * total_solved / total_target, 2),

        "positions_per_second": 0.0,

        "eta_seconds": None,

        "recent_positions": recent,

    })



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
    shared_state = {
        "total_solved": total_solved,
        "queued": len(queue),
        "last_hash": "",
        "last_progress_mono": time.monotonic(),
    }

    def _heartbeat_loop() -> None:
        while not heartbeat_stop.wait(progress_interval_sec):
            with heartbeat_lock:
                if heartbeat_stop.is_set():
                    break
                now = time.monotonic()
                if (now - shared_state["last_progress_mono"]) < progress_interval_sec:
                    continue
                try:
                    _flush_progress(
                        conn,
                        total_solved=shared_state["total_solved"],
                        total_target=total_target,
                        queued=shared_state["queued"],
                        last_hash=shared_state["last_hash"],
                        started_at=started_at,
                        started_mono=started_mono,
                        recent=recent,
                        solver=solver,
                        solver_running=True,
                        force_json=True,
                    )
                    shared_state["last_progress_mono"] = now
                except Exception as exc:
                    logger.warning("Heartbeat progression échoué: %s", exc)

    heartbeat_thread = threading.Thread(target=_heartbeat_loop, daemon=True)
    heartbeat_thread.start()

    processed: Set[str] = set(known) | checkpoint_processed
    refill_attempts = 0
    max_refill_attempts = 12

    try:
        while True:
            if not queue:
                if not continuous:
                    break
                known = _known_hashes_from_db(conn)
                if refill_attempts >= max_refill_attempts:
                    logger.warning(
                        "File vide après %d tentatives de rechargement — arrêt",
                        refill_attempts,
                    )
                    break
                refill_attempts += 1
                num_games = min(num_games * 2, max_refill_games)
                logger.info(
                    "Rechargement file — %d positions connues, essai %d (%d parties simulées)",
                    len(known),
                    refill_attempts,
                    num_games,
                )
                queue = _refill_queue(
                    conn, advisor, max_empty, num_games=num_games, known=known,
                )
                total_target = max(total_solved + len(queue), total_solved + 50, total_solved, 1)
                with heartbeat_lock:
                    shared_state["queued"] = len(queue)
                _flush_progress(
                    conn,
                    total_solved=total_solved,
                    total_target=total_target,
                    queued=len(queue),
                    last_hash=last_hash,
                    started_at=started_at,
                    started_mono=started_mono,
                    recent=recent,
                    solver=solver,
                    solver_running=True,
                    force_json=True,
                )
                if not queue:
                    logger.info(
                        "Aucune position inédite trouvée — pause %.0fs avant nouvel essai",
                        refill_sleep_sec,
                    )
                    time.sleep(refill_sleep_sec)
                    continue
                refill_attempts = 0
                num_games = 500

            board, player, last_move = queue.popleft()

            h = HASHER.hash_key(board, player, last_move)

            if h in processed:

                continue

            processed.add(h)



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
                        "Position ignorée (timeout %.0fs ou limite nœuds) — hash=%s, vides=%d",
                        position_timeout_sec,
                        h[:12],
                        HASHER.empty_cells(board),
                    )
                continue



            _store_position(conn, solved, board, player, last_move)

            total_solved += 1
            known.add(h)
            refill_attempts = 0
            batch_count += 1
            last_hash = h
            last_board = board
            last_player = player
            last_move_saved = last_move
            last_solved = solved
            with heartbeat_lock:
                shared_state["total_solved"] = total_solved
                shared_state["queued"] = len(queue)
                shared_state["last_hash"] = last_hash

            now_mono = time.monotonic()
            should_flush = (
                batch_count >= batch_size
                or batch_count >= progress_every
                or (now_mono - last_progress_mono) >= progress_interval_sec
            )

            if should_flush:

                batch_elapsed = max(now_mono - batch_start_mono, 0.001)
                progress = min(100.0, 100.0 * total_solved / max(total_target, 1))
                recent = _flush_progress(
                    conn,
                    total_solved=total_solved,
                    total_target=total_target,
                    queued=len(queue),
                    last_hash=last_hash,
                    started_at=started_at,
                    started_mono=started_mono,
                    recent=recent,
                    solver=solver,
                    solver_running=True,
                    board=last_board,
                    current_player=last_player,
                    last_move=last_move_saved,
                    solved=last_solved,
                    batch_solved=total_solved - batch_start_solved,
                    batch_elapsed=batch_elapsed,
                )
                _save_checkpoint(db_path, processed)
                logger.info(
                    "Progression : %d/%d (%.2f%%) — %.2f pos/s, file=%d",
                    total_solved,
                    total_target,
                    progress,
                    (total_solved - batch_start_solved) / batch_elapsed,
                    len(queue),
                )
                batch_count = 0
                batch_start_mono = time.monotonic()
                batch_start_solved = total_solved
                last_progress_mono = time.monotonic()
                with heartbeat_lock:
                    shared_state["last_progress_mono"] = last_progress_mono
                time.sleep(sleep_between_batches)

    finally:
        heartbeat_stop.set()
        heartbeat_thread.join(timeout=2.0)

    if skipped_timeouts:
        logger.info("%d positions ignorées (timeout)", skipped_timeouts)



    conn.commit()

    progress = 100.0 if total_solved >= total_target else 100.0 * total_solved / max(total_target, 1)

    _update_progress(

        conn,

        solved=total_solved,

        queued=0,

        last_hash=last_hash,

        started_at=started_at,

        total_target=total_target,

        progress_percent=progress,

        solver_running=False,

    )

    conn.commit()

    _save_checkpoint(db_path, processed)



    final = read_status()

    final["solver_running"] = False

    final["total_positions_solved"] = total_solved

    final["total_queued"] = 0

    final["progress_percent"] = round(progress, 2)

    final["last_update"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    write_status(final)



    conn.close()

    logger.info("Solveur terminé — %d positions au total", total_solved)





def main() -> None:

    parser = argparse.ArgumentParser(description="Solveur complet progressif 4mation")

    parser.add_argument("--db", default=str(DEFAULT_DB))

    parser.add_argument("--max-empty", type=int, default=12)

    parser.add_argument("--batch", type=int, default=25)
    parser.add_argument("--progress-every", type=int, default=1)
    parser.add_argument("--progress-interval", type=float, default=15.0)
    parser.add_argument("--position-timeout", type=float, default=30.0)
    parser.add_argument(
        "--continuous",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Boucle jusqu'à épuisement des positions inédites (défaut: oui)",
    )
    parser.add_argument("--refill-sleep", type=float, default=5.0)

    args = parser.parse_args()



    run_full_solver(
        Path(args.db),
        args.max_empty,
        args.batch,
        args.progress_every,
        args.progress_interval,
        position_timeout_sec=args.position_timeout,
        continuous=args.continuous,
        refill_sleep_sec=args.refill_sleep,
    )





if __name__ == "__main__":

    main()


