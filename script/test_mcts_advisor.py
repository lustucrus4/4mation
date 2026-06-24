"""
Tests MCTS advisor et endpoints tactiques.
"""

import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent / "script"))

from game_tree.mcts_advisor import MCTSAdvisor


def test_terminal_win_rate():
    """Position gagnante → win_rate ~100% pour le coup gagnant."""
    advisor = MCTSAdvisor(time_budget_ms=500, simulations_per_move=20)
    board = np.zeros((7, 7), dtype=np.int8)
    board[3, 3] = 1
    board[3, 4] = 1
    board[3, 5] = 1

    analysis = advisor.analyze_position(board, current_player=1, last_move=(3, 5))
    assert analysis["best_move"] == (3, 6)
    best = next(m for m in analysis["moves"] if m["move"] == (3, 6))
    assert best["win_rate"] >= 0.9, f"win_rate attendu >= 0.9, obtenu {best['win_rate']}"
    print(f"[OK] Victoire tactique: win_rate={best['win_rate']}")


def test_terminal_loss_rate():
    """Position perdante forcée → meilleur coup bloque."""
    advisor = MCTSAdvisor(time_budget_ms=500, simulations_per_move=20)
    board = np.zeros((7, 7), dtype=np.int8)
    board[3, 0] = 1
    board[3, 1] = 1
    board[3, 2] = 1

    analysis = advisor.analyze_position(board, current_player=2, last_move=(3, 2))
    assert analysis["best_move"] == (3, 3)
    print(f"[OK] Blocage tactique: {analysis['best_move']}")


def test_mcts_timing():
    """Analyse MCTS termine en moins de 5 secondes."""
    advisor = MCTSAdvisor(time_budget_ms=2000)
    board = np.zeros((7, 7), dtype=np.int8)
    board[3, 3] = 1
    board[3, 4] = 2

    start = time.perf_counter()
    analysis = advisor.analyze_position(board, current_player=1, last_move=(3, 4))
    elapsed = time.perf_counter() - start

    assert elapsed < 5.0, f"Trop lent: {elapsed:.2f}s"
    assert analysis["valid_moves_count"] > 0
    print(f"[OK] MCTS en {elapsed:.2f}s, {analysis.get('total_simulations', 0)} sims")


def main():
    print("=" * 60)
    print("TESTS MCTS ADVISOR")
    print("=" * 60)
    test_terminal_win_rate()
    test_terminal_loss_rate()
    test_mcts_timing()
    print("=" * 60)
    print("[OK] Tous les tests MCTS passent")
    print("=" * 60)


if __name__ == "__main__":
    main()
