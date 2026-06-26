"""Puzzles tactiques (1 coup) et pack de victoires forcées (multi-coups)."""

from __future__ import annotations

import json
import random
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from api.services.tablebase_lookup import get_tablebase_lookup
from game.game_engine import GameEngine

HUMAN = 1
PACK_PATH = Path(__file__).resolve().parent.parent / "data" / "puzzles.json"


def _engine_from_history(history: List[Dict[str, int]]) -> GameEngine:
    engine = GameEngine()
    engine.reset()
    for h in history:
        engine.step((int(h["row"]), int(h["col"])))
    return engine


def _history_moves(engine: GameEngine) -> List[Dict[str, int]]:
    return [
        {"player": int(e["player"]), "row": int(e["row"]), "col": int(e["col"])}
        for e in engine.get_move_history()
    ]


def _move_key(move: Dict[str, int]) -> Tuple[int, int, int]:
    return (int(move["player"]), int(move["row"]), int(move["col"]))


@lru_cache(maxsize=1)
def _load_pack_raw() -> List[Dict[str, Any]]:
    if not PACK_PATH.is_file():
        return []
    return json.loads(PACK_PATH.read_text(encoding="utf-8"))


def reload_puzzle_pack() -> None:
    _load_pack_raw.cache_clear()


def list_pack_puzzles() -> List[Dict[str, Any]]:
    return [
        {
            "id": p["id"],
            "difficulty": p["difficulty"],
            "human_moves": p["human_moves"],
            "title": p["title"],
            "theme": p.get("theme", "Victoire forcée"),
        }
        for p in _load_pack_raw()
    ]


def get_pack_puzzle(puzzle_id: str, *, include_line: bool = False) -> Optional[Dict[str, Any]]:
    for p in _load_pack_raw():
        if p["id"] != puzzle_id:
            continue
        out: Dict[str, Any] = {
            "id": p["id"],
            "difficulty": p["difficulty"],
            "human_moves": p["human_moves"],
            "title": p["title"],
            "theme": p.get("theme", "Victoire forcée"),
            "history": p["history"],
            "player_to_move": int(p.get("player_to_move", HUMAN)),
        }
        if include_line:
            out["line"] = p["line"]
        return out
    return None


def _normalize_history(history: List[Dict[str, int]]) -> List[Dict[str, int]]:
    return [
        {"player": int(h["player"]), "row": int(h["row"]), "col": int(h["col"])}
        for h in history
    ]


def check_pack_puzzle_move(
    puzzle_id: str,
    history: List[Dict[str, int]],
    row: int,
    col: int,
) -> Dict[str, Any]:
    """Valide un coup humain et renvoie la réponse adverse automatique si besoin."""
    puzzle = get_pack_puzzle(puzzle_id, include_line=True)
    if puzzle is None:
        return {"correct": False, "reason": "Puzzle introuvable"}

    setup = _normalize_history(puzzle["history"])
    line: List[Dict[str, int]] = _normalize_history(puzzle["line"])
    history = _normalize_history(history)
    setup_len = len(setup)

    if len(history) < setup_len:
        return {"correct": False, "reason": "Historique incomplet"}

    if history[:setup_len] != setup:
        return {"correct": False, "reason": "Position de départ invalide"}

    played = history[setup_len:]
    engine = _engine_from_history(history)
    if engine.is_terminal():
        return {"correct": False, "reason": "Partie terminée", "solved": True}

    if int(engine.get_current_player()) != HUMAN:
        return {"correct": False, "reason": "Ce n'est pas votre tour"}

    step = len(played)
    if step >= len(line):
        return {"correct": False, "reason": "Puzzle déjà résolu"}

    expected = line[step]
    if int(expected["player"]) != HUMAN:
        return {"correct": False, "reason": "Étape invalide"}

    played_move = {"player": HUMAN, "row": int(row), "col": int(col)}
    if _move_key(played_move) != _move_key(expected):
        return {
            "correct": False,
            "reason": "Ce n'est pas le bon coup",
            "expected_step": sum(1 for m in played if int(m["player"]) == HUMAN) + 1,
            "human_moves": puzzle["human_moves"],
        }

    new_history = list(history) + [played_move]
    engine = _engine_from_history(new_history)

    opponent_move: Optional[Dict[str, int]] = None
    solved = False

    if engine.is_terminal():
        solved = engine.get_winner() == HUMAN
    elif step + 1 < len(line):
        opp = line[step + 1]
        if int(opp["player"]) != 2:
            return {"correct": False, "reason": "Ligne de solution invalide"}
        opponent_move = {
            "player": 2,
            "row": int(opp["row"]),
            "col": int(opp["col"]),
        }
        new_history.append(opponent_move)
        engine = _engine_from_history(new_history)
        if engine.is_terminal():
            solved = engine.get_winner() == HUMAN
    elif step + 1 == len(line):
        solved = engine.is_terminal() and engine.get_winner() == HUMAN

    human_done = sum(1 for m in new_history[setup_len:] if int(m["player"]) == HUMAN)

    return {
        "correct": True,
        "history": new_history,
        "opponent_move": opponent_move,
        "solved": solved,
        "step": human_done,
        "human_moves": puzzle["human_moves"],
        "player_to_move": int(engine.get_current_player()) if not solved else HUMAN,
    }


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
