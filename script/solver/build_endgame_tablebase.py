#!/usr/bin/env python3
"""
Génère la tablebase fin de partie (positions avec ≤ N cases vides).

Usage:
    python script/solver/build_endgame_tablebase.py [--db PATH] [--max-empty 12] [--games 200]
"""

from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = ROOT / "script"
if str(SCRIPT) not in sys.path:
    sys.path.insert(0, str(SCRIPT))

from game_tree.optimized_minimax import OptimizedMinimaxAdvisor
from solver.db_schema import init_db
from solver.position_hasher import HASHER
from solver.retrograde_solver import RetrogradeSolver, SolvedPosition

DEFAULT_DB = SCRIPT / "solver" / "data" / "tablebase.db"


def _store_position(conn, solved: SolvedPosition) -> None:
    br, bc = (-1, -1)
    if solved.best_move:
        br, bc = solved.best_move
    conn.execute(
        """
        INSERT OR REPLACE INTO positions
        (hash, result, win_rate, best_move_row, best_move_col, depth_remaining, solved_at)
        VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """,
        (solved.hash_key, solved.result, solved.win_rate, br, bc, solved.depth_remaining),
    )


def _play_random_game(advisor: OptimizedMinimaxAdvisor, max_moves: int = 49) -> list[tuple]:
    """Retourne la liste des états (board, player, last_move) rencontrés."""
    board = np.zeros((7, 7), dtype=np.int8)
    states = []
    current_player = 1
    last_move = None

    for _ in range(max_moves):
        states.append((board.copy(), current_player, last_move))
        if advisor._check_winner(board) is not None:
            break
        moves = advisor._get_frontier_moves(board, last_move, current_player)
        if not moves:
            break
        move = random.choice(moves)
        board = board.copy()
        board[move[0], move[1]] = current_player
        last_move = move
        if advisor._check_winner(board) is not None or np.all(board != 0):
            break
        current_player = 3 - current_player

    return states


def generate_endgame_tablebase(
    db_path: Path,
    max_empty: int = 12,
    num_games: int = 200,
    verbose: bool = True,
) -> int:
    conn = init_db(db_path)
    solver = RetrogradeSolver(max_empty=max_empty)
    advisor = OptimizedMinimaxAdvisor(depth=2, use_iterative_deepening=False)
    count = 0
    seen: set[str] = set()

    for g in range(num_games):
        states = _play_random_game(advisor)
        for board, player, last_move in states:
            if HASHER.empty_cells(board) > max_empty:
                continue
            h = HASHER.hash_key(board, player, last_move)
            if h in seen:
                continue
            seen.add(h)
            solved = solver.solve_position(board, player, last_move)
            if solved is None:
                continue
            _store_position(conn, solved)
            count += 1

        if verbose and (g + 1) % 50 == 0:
            conn.commit()
            print(f"  Jeux {g + 1}/{num_games} — {count} positions endgame")

    conn.commit()
    conn.close()
    if verbose:
        print(f"Tablebase endgame : {count} positions -> {db_path}")
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description="Génère la tablebase fin de partie 4mation")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="Chemin SQLite")
    parser.add_argument("--max-empty", type=int, default=12)
    parser.add_argument("--games", type=int, default=200)
    args = parser.parse_args()

    print(f"Génération endgame (max_empty={args.max_empty}, games={args.games})…")
    generate_endgame_tablebase(Path(args.db), args.max_empty, args.games)


if __name__ == "__main__":
    main()
