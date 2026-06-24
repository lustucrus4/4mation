"""Sérialisation de l'état de partie pour l'API (sans calcul Minimax)."""

from __future__ import annotations

from typing import Any, Dict, Optional

from game.game_engine import GameEngine


def serialize_board_state(engine: GameEngine, mode: str = "standard") -> Dict[str, Any]:
    """Retourne l'état du plateau au format JSON, sans analyse IA."""
    state = engine.get_state()
    board = state.board.tolist()

    last_move_row = None
    last_move_col = None
    if state.action_history:
        _, last_row, last_col = state.action_history[-1]
        last_move_row = int(last_row)
        last_move_col = int(last_col)

    winner = None
    if state.is_terminal and state.winner is not None:
        winner = int(state.winner)

    return {
        "board": board,
        "current_player": int(state.current_player),
        "is_terminal": bool(state.is_terminal),
        "winner": winner,
        "move_count": int(state.move_count),
        "mode": mode,
        "valid_actions": [
            {"row": int(row), "col": int(col)}
            for row, col in engine.get_valid_actions()
        ],
        "last_move": (
            {"row": last_move_row, "col": last_move_col}
            if last_move_row is not None
            else None
        ),
        "history": engine.get_move_history(),
    }
