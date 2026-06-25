"""Génération de puzzles tactiques (positions à coup décisif)."""

from __future__ import annotations

import random
from typing import Any, Dict, List, Optional, Tuple

from api.services.tablebase_lookup import get_tablebase_lookup
from game.game_engine import GameEngine


def _last_move(engine: GameEngine) -> Optional[Tuple[int, int]]:
    state = engine.get_state()
    if state.action_history:
        _, r, c = state.action_history[-1]
        return (int(r), int(c))
    return None


def _try_puzzle_at_engine(engine: GameEngine) -> Optional[Dict[str, Any]]:
    if engine.is_terminal():
        return None
    state = engine.get_state()
    last = _last_move(engine)
    tb = get_tablebase_lookup()
    analysis = tb.analyze_position(state.board, int(state.current_player), last)
    if not analysis:
        return None

    moves = analysis.get("moves") or []
    if not moves:
        return None

    best = moves[0]
    best_wr = float(best.get("win_rate", 0))
    second_wr = float(moves[1]["win_rate"]) if len(moves) > 1 else 0.0
    gap = best_wr - second_wr

    # Puzzle = un coup nettement supérieur (tactique).
    if best_wr < 0.55 or gap < 0.12:
        return None

    solution = (int(best["row"]), int(best["col"]))
    history = engine.get_move_history()

    return {
        "history": history,
        "player_to_move": int(state.current_player),
        "solution": {"row": solution[0], "col": solution[1]},
        "win_rate": best_wr,
        "gap": round(gap, 3),
        "exact": bool(analysis.get("exact")),
        "label": analysis.get("label", ""),
        "theme": "tactique",
    }


def random_puzzle(*, max_attempts: int = 40) -> Optional[Dict[str, Any]]:
    """Marche aléatoire puis vérifie qu'il existe un coup nettement meilleur."""
    for _ in range(max_attempts):
        engine = GameEngine()
        engine.reset()
        plies = random.randint(3, 9)
        for _ in range(plies):
            if engine.is_terminal():
                break
            valid = engine.get_valid_actions()
            if not valid:
                break
            move = random.choice(valid)
            engine.step(move)

        puzzle = _try_puzzle_at_engine(engine)
        if puzzle is not None:
            puzzle["id"] = f"gen-{random.randint(100000, 999999)}"
            return puzzle

    # Fallback : position de départ (premier coup)
    engine = GameEngine()
    engine.reset()
    puzzle = _try_puzzle_at_engine(engine)
    if puzzle:
        puzzle["id"] = "gen-root"
    return puzzle


def check_puzzle_solution(
    history: List[Dict[str, int]],
    player: int,
    row: int,
    col: int,
) -> Dict[str, Any]:
    """Vérifie si le coup joué est correct (meilleur ou équivalent gagnant)."""
    engine = GameEngine()
    engine.reset()
    for h in history:
        engine.step((int(h["row"]), int(h["col"])))
    if engine.is_terminal():
        return {"correct": False, "reason": "Partie terminée"}

    state = engine.get_state()
    if int(state.current_player) != int(player):
        return {"correct": False, "reason": "Ce n'est pas votre tour"}

    last = _last_move(engine)
    tb = get_tablebase_lookup()
    analysis = tb.analyze_position(state.board, int(state.current_player), last)
    if not analysis:
        return {"correct": False, "reason": "Analyse indisponible"}

    moves = analysis.get("moves") or []
    if not moves:
        return {"correct": False, "reason": "Aucun coup analysé"}

    best = moves[0]
    best_key = (int(best["row"]), int(best["col"]))
    played = (int(row), int(col))

    if played == best_key:
        return {"correct": True, "win_rate": float(best["win_rate"])}

    played_wr = next(
        (float(m["win_rate"]) for m in moves if int(m["row"]) == row and int(m["col"]) == col),
        None,
    )
    if played_wr is not None and float(best["win_rate"]) - played_wr < 0.05:
        return {"correct": True, "win_rate": played_wr, "note": "acceptable"}

    return {
        "correct": False,
        "solution": {"row": best_key[0], "col": best_key[1]},
        "win_rate": float(best["win_rate"]),
    }
