#!/usr/bin/env python3
"""
Construit le livre d'ouverture (8–12 premiers coups) via Minimax profondeur 10+.

Usage:
    python script/solver/build_opening_book.py [--db PATH] [--max-ply 12] [--depth 10]
"""

from __future__ import annotations

import argparse
import sys
from collections import deque
from pathlib import Path
from typing import Optional, Tuple

import numpy as np

ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = ROOT / "script"
if str(SCRIPT) not in sys.path:
    sys.path.insert(0, str(SCRIPT))

from game_tree.optimized_minimax import OptimizedMinimaxAdvisor
from solver.db_schema import init_db
from solver.position_hasher import HASHER
from solver.retrograde_solver import RESULT_DRAW, RESULT_LOSS, RESULT_WIN

DEFAULT_DB = SCRIPT / "solver" / "data" / "tablebase.db"


def _score_to_result(score: float) -> Tuple[str, float]:
    if score > 50000:
        return RESULT_WIN, 1.0
    if score < -50000:
        return RESULT_LOSS, 0.0
    if score > 1000:
        wr = min(0.95, 0.5 + score / 200000)
        return RESULT_WIN, wr
    if score < -1000:
        wr = max(0.05, 0.5 + score / 200000)
        return RESULT_LOSS, wr
    return RESULT_DRAW, 0.5


def _store_opening(conn, h: str, result: str, wr: float, best_move, ply: int) -> None:
    br, bc = (-1, -1)
    if best_move:
        br, bc = best_move
    conn.execute(
        """
        INSERT OR REPLACE INTO opening_book
        (hash, result, win_rate, best_move_row, best_move_col, ply, solved_at)
        VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """,
        (h, result, wr, br, bc, ply),
    )


def build_opening_book(
    db_path: Path,
    max_ply: int = 12,
    depth: int = 10,
    time_budget_ms: int = 2000,
    max_positions: int = 400,
    branch_factor: int = 4,
    verbose: bool = True,
) -> int:
    conn = init_db(db_path)
    advisor = OptimizedMinimaxAdvisor(
        depth=depth,
        use_iterative_deepening=True,
        time_budget_ms=time_budget_ms,
    )
    count = 0
    queue: deque = deque()
    board = np.zeros((7, 7), dtype=np.int8)
    queue.append((board.copy(), 1, None, 0))

    while queue and count < max_positions:
        board, player, last_move, ply = queue.popleft()
        if ply >= max_ply:
            continue

        h = HASHER.hash_key(board, player, last_move)
        existing = conn.execute("SELECT 1 FROM opening_book WHERE hash=?", (h,)).fetchone()
        if existing:
            moves = advisor._get_frontier_moves(board, last_move, player)
        elif ply == 0 and HASHER.move_count(board) == 0:
            best = (3, 3)
            _store_opening(conn, h, "D", 0.5, best, ply)
            count += 1
            moves = advisor._get_frontier_moves(board, last_move, player)
        else:
            ply_advisor = advisor
            if ply < 4:
                ply_advisor = OptimizedMinimaxAdvisor(
                    depth=2, use_iterative_deepening=False, time_budget_ms=500
                )
            try:
                analysis = ply_advisor.analyze_position(
                    board, player, last_move, include_move_scores=True
                )
            except (TimeoutError, Exception) as exc:
                if verbose:
                    print(f"  Skip ply={ply} : {exc}")
                moves = advisor._get_frontier_moves(board, last_move, player)
                continue
            best = analysis.get("best_move")
            moves_data = analysis.get("moves", [])
            best_score = moves_data[0].get("score", 0) if moves_data else 0
            result, wr = _score_to_result(best_score)
            _store_opening(conn, h, result, wr, best, ply)
            count += 1
            moves = advisor._get_frontier_moves(board, last_move, player)

            if verbose and count % 20 == 0:
                conn.commit()
                print(f"  {count} positions d'ouverture (ply<={max_ply})")

        if advisor._check_winner(board) is not None:
            continue

        ordered = advisor._order_moves(board, moves, player, last_move)
        for move in ordered[:branch_factor]:
            nb = board.copy()
            nb[move[0], move[1]] = player
            if advisor._check_winner(nb) is not None:
                continue
            queue.append((nb, 3 - player, move, ply + 1))

    conn.commit()
    conn.close()
    if verbose:
        print(f"Livre d'ouverture : {count} positions -> {db_path}")
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description="Génère le livre d'ouverture 4mation")
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--max-ply", type=int, default=12)
    parser.add_argument("--depth", type=int, default=10)
    parser.add_argument("--time-ms", type=int, default=2000)
    args = parser.parse_args()

    print(f"Construction livre d'ouverture (ply<={args.max_ply}, depth={args.depth})...")
    build_opening_book(
        Path(args.db),
        max_ply=args.max_ply,
        depth=args.depth,
        time_budget_ms=args.time_ms,
    )


if __name__ == "__main__":
    main()
