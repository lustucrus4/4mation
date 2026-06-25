"""Game Review — analyse rétroactive d'une partie enregistrée."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from api.services.tablebase_lookup import get_tablebase_lookup
from game.game_engine import GameEngine
from game_tree.mcts_advisor import MCTSAdvisor

logger = logging.getLogger(__name__)

# Seuils de perte de taux de victoire (perspective du joueur au trait) → classification.
_CLASS_THRESHOLDS = (
    ("best", 0.01),
    ("excellent", 0.03),
    ("good", 0.08),
    ("inaccuracy", 0.15),
    ("mistake", 0.30),
)

_MCTS = MCTSAdvisor(time_budget_ms=350)


def _classify(win_rate_loss: float, is_best: bool) -> str:
    if is_best:
        return "best"
    for label, max_loss in _CLASS_THRESHOLDS:
        if win_rate_loss <= max_loss:
            return label
    return "blunder"


def _move_accuracy(win_rate_loss: float, is_best: bool) -> float:
    if is_best:
        return 100.0
    # Perte 0 → 100 %, perte ≥ 0.5 → 0 % (approximation lisible type chess.com).
    return max(0.0, min(100.0, 100.0 - win_rate_loss * 200.0))


def _last_move_from_engine(engine: GameEngine) -> Optional[Tuple[int, int]]:
    state = engine.get_state()
    if state.action_history:
        _, r, c = state.action_history[-1]
        return (int(r), int(c))
    return None


def _analyze_at(
    engine: GameEngine,
    player: int,
) -> Optional[Dict[str, Any]]:
    state = engine.get_state()
    if state.is_terminal:
        return None
    last = _last_move_from_engine(engine)
    board = state.board

    tb = get_tablebase_lookup()
    analysis = tb.analyze_position(board, current_player=player, last_move=last)
    if analysis is not None:
        return analysis

    try:
        mcts = _MCTS.analyze_position(board, current_player=player, last_move=last)
        mcts["source"] = "mcts"
        mcts["exact"] = False
        mcts["label"] = "Estimé (MCTS)"
        return mcts
    except Exception:
        logger.debug("Analyse MCTS indisponible pour review", exc_info=True)
        return None


def _win_rate_for_move(
    analysis: Dict[str, Any],
    row: int,
    col: int,
    player: int,
) -> Tuple[float, bool, Optional[Tuple[int, int]]]:
    moves = analysis.get("moves") or []
    best_wr = float(moves[0]["win_rate"]) if moves else 0.5
    best_move = analysis.get("best_move")
    if isinstance(best_move, (list, tuple)) and len(best_move) == 2:
        best = (int(best_move[0]), int(best_move[1]))
    else:
        best = None

    played_wr = None
    for m in moves:
        if int(m["row"]) == row and int(m["col"]) == col:
            played_wr = float(m["win_rate"])
            break

    if played_wr is None:
        played_wr = best_wr if best == (row, col) else 0.0

    is_best = best == (row, col) if best else played_wr >= best_wr - 0.001
    return played_wr, is_best, best


def build_game_review(
    history: List[Dict[str, Any]],
    *,
    human_color: int = 1,
) -> Dict[str, Any]:
    """
    Rejoue la partie et classifie chaque coup.
    `history` : liste { index, player, row, col }.
    """
    engine = GameEngine()
    engine.reset()

    moves_out: List[Dict[str, Any]] = []
    graph: List[Dict[str, Any]] = [{"move_index": 0, "win_rate_p1": 0.5}]
    human_accs: List[float] = []

    for entry in history:
        idx = int(entry.get("index", len(moves_out) + 1))
        player = int(entry["player"])
        row, col = int(entry["row"]), int(entry["col"])

        analysis = _analyze_at(engine, player)
        classification = "unknown"
        win_rate_before = 0.5
        win_rate_played = 0.5
        win_rate_best = 0.5
        best_move = None
        source = ""
        exact = False
        accuracy = None

        if analysis is not None:
            source = str(analysis.get("source") or "")
            exact = bool(analysis.get("exact"))
            cp = int(analysis.get("current_player") or player)
            pwr = analysis.get("position_win_rate")
            if pwr is None:
                mv = analysis.get("moves") or []
                pwr = float(mv[0]["win_rate"]) if mv else 0.5
            win_rate_before = float(pwr)

            played_wr, is_best, best = _win_rate_for_move(analysis, row, col, player)
            win_rate_played = played_wr
            mv = analysis.get("moves") or []
            win_rate_best = float(mv[0]["win_rate"]) if mv else played_wr
            best_move = list(best) if best else None

            # Perte = différence entre le meilleur coup et le coup joué (perspective joueur au trait).
            loss = max(0.0, win_rate_best - win_rate_played)
            classification = _classify(loss, is_best)
            if player == human_color:
                accuracy = _move_accuracy(loss, is_best)
                human_accs.append(accuracy)

        engine.step((row, col))

        state = engine.get_state()
        wr_p1 = win_rate_before if player == 1 else 1.0 - win_rate_before
        graph.append({
            "move_index": idx,
            "win_rate_p1": round(wr_p1, 4),
            "player": player,
        })

        moves_out.append({
            "index": idx,
            "player": player,
            "row": row,
            "col": col,
            "classification": classification,
            "win_rate_before": round(win_rate_before, 4),
            "win_rate_played": round(win_rate_played, 4),
            "win_rate_best": round(win_rate_best, 4),
            "best_move": best_move,
            "accuracy": round(accuracy, 1) if accuracy is not None else None,
            "source": source,
            "exact": exact,
            "is_human": player == human_color,
        })

    human_accuracy = round(sum(human_accs) / len(human_accs), 1) if human_accs else None

    return {
        "human_color": human_color,
        "human_accuracy": human_accuracy,
        "bot_accuracy": None,
        "moves": moves_out,
        "graph": graph,
        "move_count": len(moves_out),
    }
