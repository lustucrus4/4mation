"""Game Review — analyse rétroactive d'une partie enregistrée."""

from __future__ import annotations

import logging
from typing import Any, Dict, Iterator, List, Optional, Tuple

from api.services.game_review_insights import (
    accuracy_by_phase,
    build_summary,
    key_moments,
    move_verdict,
    nature_of,
    outcome_status,
    phase_for,
    proven_stats,
)
from api.services.tablebase_lookup import get_tablebase_lookup
from game.game_engine import GameEngine
from game_tree.mcts_advisor import MCTSAdvisor
from solver.position_hasher import HASHER

logger = logging.getLogger(__name__)

# Seuils de perte de taux de victoire (perspective du joueur au trait) → classification.
_CLASS_THRESHOLDS = (
    ("best", 0.01),
    ("excellent", 0.03),
    ("good", 0.08),
    ("inaccuracy", 0.15),
    ("mistake", 0.30),
)

_ERROR_CLASSIFICATIONS = ("mistake", "blunder")

_NATURE_LABELS = {"proven": "Prouvé", "estimated": "Estimé", "unknown": "Non analysé"}

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
    best_move = analysis.get("best_move")
    if isinstance(best_move, (list, tuple)) and len(best_move) == 2:
        best = (int(best_move[0]), int(best_move[1]))
    else:
        best = None

    # Référence = meilleur taux atteignable dans la position. On la lit dans
    # ``position_win_rate`` (valeur prouvée quand ``exact=True``) plutôt que dans le
    # premier élément de ``moves`` : sur le livre exact, un coup peut porter une
    # estimation d'enfant fractionnaire incohérente avec la valeur prouvée de la
    # position, ce qui ferait passer un coup perdant pour « meilleur ».
    pwr = analysis.get("position_win_rate")
    if pwr is not None:
        best_wr = float(pwr)
    else:
        best_wr = float(moves[0]["win_rate"]) if moves else 0.5

    played_wr = None
    for m in moves:
        if int(m["row"]) == row and int(m["col"]) == col:
            played_wr = float(m["win_rate"])
            break

    if played_wr is None:
        played_wr = best_wr if best == (row, col) else 0.0

    is_best = played_wr >= best_wr - 0.001
    return played_wr, is_best, best


def _find_move_info(analysis: Dict[str, Any], row: int, col: int) -> Optional[Dict[str, Any]]:
    for m in analysis.get("moves") or []:
        if int(m.get("row", -1)) == row and int(m.get("col", -1)) == col:
            return m
    return None


def _played_value_exact(exact: bool, info: Optional[Dict[str, Any]]) -> bool:
    """La valeur du coup joué est-elle prouvée ?

    L'analyse peut être ``exact=True`` (position prouvée) tout en donnant, pour un coup
    précis, la valeur d'un enfant **estimé** (cas du livre d'ouverture : coups prouvés et
    coups estimés cohabitent). Dans ce cas on refuse d'attribuer une faute « prouvée ».
    """
    if not exact:
        return False
    if info is None:
        return True
    if "exact" in info:
        return bool(info["exact"])
    if "proven_move" in info or "proven" in info:
        proven = str(info.get("proven") or "")
        return bool(info.get("proven_move")) or proven in ("gain", "perte", "nulle")
    # Analyse exacte sans information par coup (tablebase rétrograde) : valeur prouvée.
    return True


def iter_build_game_review(
    history: List[Dict[str, Any]],
    *,
    human_color: int = 1,
) -> Iterator[Dict[str, Any]]:
    """
    Rejoue la partie et classifie chaque coup.
    Émet des événements ``progress`` puis ``complete`` avec la revue finale.

    Chaque coup porte une ``nature`` explicite : ``proven`` quand l'analyse est
    ``exact=True`` (valeur prouvée : tablebase ou mat forcé), ``estimated`` sinon
    (estimation bornée par un budget, non reproductible). Les agrégats — précision
    par phase, moments clés, résumé — conservent toujours cette séparation.
    """
    engine = GameEngine()
    engine.reset()

    moves_out: List[Dict[str, Any]] = []
    graph: List[Dict[str, Any]] = [{"move_index": 0, "win_rate_p1": 0.5}]
    accuracies_by_player: Dict[int, List[float]] = {1: [], 2: []}
    total = len(history)

    for entry in history:
        idx = int(entry.get("index", len(moves_out) + 1))
        player = int(entry["player"])
        row, col = int(entry["row"]), int(entry["col"])

        phase = phase_for(HASHER.empty_cells(engine.get_state().board))

        analysis = _analyze_at(engine, player)
        analyzed = analysis is not None
        classification = "unknown"
        win_rate_before = 0.5
        win_rate_played = 0.5
        win_rate_best = 0.5
        best_move = None
        source = ""
        exact = False
        accuracy = None
        nature = "unknown"
        verdict = "Non analysé"
        position_status_before = "unknown"
        played_outcome = "unknown"
        missed_forced_win = False
        proven_error = False
        value_exact = False
        win_rate_loss: Optional[float] = None
        mate_in = None
        played_mate_in = None

        if analysis is not None:
            source = str(analysis.get("source") or "")
            exact = bool(analysis.get("exact"))
            pwr = analysis.get("position_win_rate")
            if pwr is None:
                mv = analysis.get("moves") or []
                pwr = float(mv[0]["win_rate"]) if mv else 0.5
            win_rate_before = float(pwr)

            played_wr, is_best, best = _win_rate_for_move(analysis, row, col, player)
            win_rate_played = played_wr
            # La meilleure valeur atteignable est la valeur de la position elle-même.
            win_rate_best = win_rate_before
            best_move = list(best) if best else None

            loss = max(0.0, win_rate_best - win_rate_played)
            win_rate_loss = loss
            classification = _classify(loss, is_best)
            accuracy = _move_accuracy(loss, is_best)
            accuracies_by_player.setdefault(player, []).append(accuracy)

            info = _find_move_info(analysis, row, col)
            value_exact = _played_value_exact(exact, info)
            nature = nature_of(analyzed=True, exact=(exact and value_exact))
            position_status_before = str(
                analysis.get("position_status") or ("proven" if exact else "estimated")
            )
            played_outcome = outcome_status(win_rate_played, exact=(exact and value_exact))
            missed_forced_win = bool(
                exact
                and value_exact
                and win_rate_best >= 0.995
                and win_rate_played < 0.995
            )
            proven_error = bool(
                exact and value_exact and classification in _ERROR_CLASSIFICATIONS
            )
            mate_in = analysis.get("mate_in") if exact else None
            if info is not None and exact:
                played_mate_in = info.get("mate_in")
            verdict = move_verdict(
                analyzed=True,
                classification=classification,
                nature=nature,
                missed_forced_win=missed_forced_win,
                played_outcome=played_outcome,
            )

        engine.step((row, col))

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
            "value_exact": value_exact,
            "is_human": player == human_color,
            "nature": nature,
            "nature_label": _NATURE_LABELS.get(nature, "Non analysé"),
            "verdict": verdict,
            "phase": phase,
            "win_rate_loss": round(win_rate_loss, 4) if win_rate_loss is not None else None,
            "position_status_before": position_status_before,
            "played_outcome": played_outcome,
            "missed_forced_win": missed_forced_win,
            "proven_error": proven_error,
            "mate_in": mate_in,
            "played_mate_in": played_mate_in,
        })

        yield {
            "type": "progress",
            "current": len(moves_out),
            "total": total,
        }

    def _mean(values: List[float]) -> Optional[float]:
        return round(sum(values) / len(values), 1) if values else None

    human_accuracy = _mean(accuracies_by_player.get(human_color, []))
    bot_color = 2 if human_color == 1 else 1
    bot_accuracy = _mean(accuracies_by_player.get(bot_color, []))

    acc_by_phase = accuracy_by_phase(moves_out, human_color)
    moments = key_moments(moves_out, human_color, limit=5)
    summary = build_summary(
        moves_out,
        human_color,
        acc_by_phase,
        {"human": human_accuracy, "bot": bot_accuracy},
    )

    review = {
        "human_color": human_color,
        "human_accuracy": human_accuracy,
        "bot_accuracy": bot_accuracy,
        "moves": moves_out,
        "graph": graph,
        "move_count": len(moves_out),
        "accuracy_by_phase": acc_by_phase,
        "key_moments": moments,
        "summary": summary,
        "proven_stats": proven_stats(moves_out),
    }
    yield {"type": "complete", "review": review}


def build_game_review(
    history: List[Dict[str, Any]],
    *,
    human_color: int = 1,
) -> Dict[str, Any]:
    """Rejoue la partie et classifie chaque coup (bloquant, sans progression)."""
    review: Optional[Dict[str, Any]] = None
    for event in iter_build_game_review(history, human_color=human_color):
        if event.get("type") == "complete":
            review = event["review"]
    assert review is not None
    return review
