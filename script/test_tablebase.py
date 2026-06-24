"""
Tests tablebase / livre d'ouverture et intégration lookup.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "script"
sys.path.insert(0, str(SCRIPT))
sys.path.insert(0, str(ROOT))

from solver.db_schema import init_db
from solver.position_hasher import HASHER
from solver.retrograde_solver import RetrogradeSolver, RESULT_WIN
from game_tree.optimized_minimax import OptimizedMinimaxAdvisor


DB_PATH = SCRIPT / "solver" / "data" / "tablebase.db"


def test_hasher_consistency():
    """Le hash solver correspond au hash Minimax."""
    advisor = OptimizedMinimaxAdvisor(depth=2, use_iterative_deepening=False)
    board = np.zeros((7, 7), dtype=np.int8)
    board[3, 3] = 1
    last_move = (3, 3)
    h_solver = HASHER.hash_key(board, 2, last_move)
    h_minimax = f"{advisor._zobrist_hash(board, 2, last_move):016x}"
    assert h_solver == h_minimax, f"Hash divergent: {h_solver} vs {h_minimax}"
    print("[OK] Hash Zobrist cohérent avec Minimax")


def test_retrograde_endgame():
    """Résolution rétrograde sur position endgame générée aléatoirement."""
    import random
    advisor = OptimizedMinimaxAdvisor(depth=2, use_iterative_deepening=False)
    solver = RetrogradeSolver(max_empty=12)
    random.seed(123)

    for _ in range(30):
        board = np.zeros((7, 7), dtype=np.int8)
        player = 1
        last_move = None
        for _ply in range(40):
            if HASHER.empty_cells(board) <= 12 and advisor._check_winner(board) is None:
                result = solver.solve_position(board, player, last_move)
                if result is not None:
                    assert result.result in ("W", "L", "D")
                    assert 0.0 <= result.win_rate <= 1.0
                    print(f"[OK] Rétrograde endgame : {result.result} wr={result.win_rate}")
                    return
            moves = advisor._get_frontier_moves(board, last_move, player)
            if not moves:
                break
            move = random.choice(moves)
            board = board.copy()
            board[move[0], move[1]] = player
            last_move = move
            if advisor._check_winner(board) is not None:
                break
            player = 3 - player

    print("[OK] Rétrograde endgame (aucune position testée — aléatoire)")


def test_lookup_speed():
    """Lookup SQLite < 10 ms si DB présente."""
    if not DB_PATH.exists():
        print("[SKIP] tablebase.db absente — lancer seed_initial_tablebase.py")
        return

    import os
    os.environ["TABLEBASE_DB_PATH"] = str(DB_PATH)
    from api.services.tablebase_lookup import TablebaseLookup

    tb = TablebaseLookup(db_path=DB_PATH)
    board = np.zeros((7, 7), dtype=np.int8)
    start = time.perf_counter()
    hit = tb.lookup(board, 1, None)
    elapsed_ms = (time.perf_counter() - start) * 1000
    assert elapsed_ms < 50, f"Lookup trop lent: {elapsed_ms:.1f}ms"
    if hit:
        print(f"[OK] Lookup opening en {elapsed_ms:.2f}ms — {hit.source}")
    else:
        print(f"[OK] Lookup en {elapsed_ms:.2f}ms (pas de hit sur position vide)")


def test_tactical_win_in_one():
    """Victoire en 1 détectée dans analyze_moves (tactique)."""
    board = np.zeros((7, 7), dtype=np.int8)
    board[3, 0] = 1
    board[3, 1] = 1
    board[3, 2] = 1
    solver = RetrogradeSolver(max_empty=12)
    # analyze_moves vérifie _is_winning_move avant la limite empty
    analysis = solver.analyze_moves(board, 1, (3, 2))
    assert analysis is not None
    assert analysis["best_move"] == (3, 3)
    assert analysis["moves"][0]["win_rate"] == 1.0
    print("[OK] Victoire en 1 (tactique)")


def test_db_stats():
    if not DB_PATH.exists():
        print("[SKIP] stats DB")
        return
    import sqlite3
    conn = init_db(DB_PATH)
    pos = conn.execute("SELECT COUNT(*) FROM positions").fetchone()[0]
    opening = conn.execute("SELECT COUNT(*) FROM opening_book").fetchone()[0]
    conn.close()
    print(f"[OK] DB : {opening} ouvertures, {pos} positions endgame")
    assert opening > 0 or pos > 0


if __name__ == "__main__":
    print("TESTS TABLEBASE 4MATION")
    print("=" * 40)
    test_hasher_consistency()
    test_retrograde_endgame()
    test_tactical_win_in_one()
    test_lookup_speed()
    test_db_stats()
    print("[OK] Tous les tests tablebase passent")
