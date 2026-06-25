"""Explorateur d'ouvertures (livre d'ouverture + continuations)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from api.services.tablebase_lookup import get_tablebase_lookup
from game.game_engine import GameEngine


def _last_move(engine: GameEngine) -> Optional[Tuple[int, int]]:
    state = engine.get_state()
    if state.action_history:
        _, r, c = state.action_history[-1]
        return (int(r), int(c))
    return None


def explore_opening(moves: List[Tuple[int, int]]) -> Dict[str, Any]:
    """Rejoue `moves` depuis le début et renvoie stats livre + continuations."""
    engine = GameEngine()
    engine.reset()
    for row, col in moves:
        _, success, _ = engine.step((int(row), int(col)))
        if not success:
            break

    state = engine.get_state()
    last = _last_move(engine)
    tb = get_tablebase_lookup()
    hit = tb.lookup(state.board, int(state.current_player), last)

    analysis = tb.analyze_position(state.board, int(state.current_player), last)

    continuations: List[Dict[str, Any]] = []
    for row, col in engine.get_valid_actions():
        child_engine = GameEngine()
        child_engine.reset()
        for m in moves:
            child_engine.step(m)
        child_engine.step((row, col))
        cs = child_engine.get_state()
        cl = _last_move(child_engine)
        child_hit = tb.lookup(cs.board, int(cs.current_player), cl)
        entry: Dict[str, Any] = {
            "move": {"row": int(row), "col": int(col)},
            "in_book": child_hit is not None,
        }
        if child_hit:
            entry["win_rate"] = child_hit.win_rate
            entry["result"] = child_hit.result
            entry["exact"] = child_hit.exact
            entry["ply"] = child_hit.ply
        continuations.append(entry)

    # Enrichir avec l'analyse si disponible
    if analysis and analysis.get("moves"):
        rate_map = {
            (int(m["row"]), int(m["col"])): float(m["win_rate"])
            for m in analysis["moves"]
        }
        for c in continuations:
            key = (c["move"]["row"], c["move"]["col"])
            if key in rate_map:
                c["win_rate"] = rate_map[key]

    continuations.sort(key=lambda x: x.get("win_rate", 0), reverse=True)

    book_info = None
    if hit:
        book_info = {
            "result": hit.result,
            "win_rate": hit.win_rate,
            "best_move": list(hit.best_move) if hit.best_move else None,
            "exact": hit.exact,
            "ply": hit.ply,
            "source": hit.source,
        }

    return {
        "board": state.board.tolist(),
        "current_player": int(state.current_player),
        "move_count": int(state.move_count),
        "is_terminal": bool(state.is_terminal),
        "last_move": {"row": last[0], "col": last[1]} if last else None,
        "book": book_info,
        "analysis_label": analysis.get("label") if analysis else None,
        "best_move": analysis.get("best_move") if analysis else None,
        "continuations": continuations,
        "history": engine.get_move_history(),
    }
