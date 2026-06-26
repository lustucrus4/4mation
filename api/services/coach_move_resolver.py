"""Résolution des coups coach : livre d'ouverture, tablebase, secours Minimax 6 plies."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Set, Tuple

import numpy as np

from game_tree.mcts_advisor import MCTSAdvisor
from game_tree.optimized_minimax import OptimizedMinimaxAdvisor

from api.services.tablebase_lookup import get_tablebase_lookup

logger = logging.getLogger(__name__)

BACKUP_DEPTH = 6
BACKUP_TIME_MS = 1200

_backup_minimax: Optional[OptimizedMinimaxAdvisor] = None
_mcts_fallback = MCTSAdvisor(time_budget_ms=600)


def _get_backup_minimax() -> OptimizedMinimaxAdvisor:
    global _backup_minimax
    if _backup_minimax is None:
        _backup_minimax = OptimizedMinimaxAdvisor(
            depth=BACKUP_DEPTH,
            cache_size=30000,
            use_iterative_deepening=True,
            time_budget_ms=BACKUP_TIME_MS,
        )
    return _backup_minimax


def _normalize_move(raw: Any) -> Optional[Tuple[int, int]]:
    if raw is None:
        return None
    if isinstance(raw, (list, tuple)) and len(raw) >= 2:
        return (int(raw[0]), int(raw[1]))
    if isinstance(raw, dict) and "row" in raw and "col" in raw:
        return (int(raw["row"]), int(raw["col"]))
    return None


def _resolve_from_analysis(
    analysis: Dict[str, Any],
    valid_set: Set[Tuple[int, int]],
) -> Optional[Tuple[int, int]]:
    best = _normalize_move(analysis.get("best_move"))
    if best is not None and best in valid_set:
        return best
    for m in analysis.get("moves") or []:
        action = _normalize_move(m.get("move", m))
        if action is not None and action in valid_set:
            return action
    return None


def backup_minimax_move(
    board: np.ndarray,
    current_player: int,
    last_move: Optional[Tuple[int, int]],
    valid_set: Set[Tuple[int, int]],
) -> Optional[Tuple[int, int]]:
    """Meilleur coup légal via Minimax rapide sur BACKUP_DEPTH plies."""
    advisor = _get_backup_minimax()
    advisor.max_depth = BACKUP_DEPTH
    advisor.time_budget_ms = BACKUP_TIME_MS

    best_move, _ = advisor._iterative_deepening(board, last_move, current_player)
    if best_move is not None and best_move in valid_set:
        return best_move

    analysis = advisor.analyze_position(board, current_player, last_move)
    return _resolve_from_analysis(analysis, valid_set)


def choose_coach_move(
    board: np.ndarray,
    current_player: int,
    last_move: Optional[Tuple[int, int]],
    valid_actions: list,
) -> Tuple[Optional[Tuple[int, int]], Dict[str, Any]]:
    """
    Choisit le coup du coach :
    1. Livre / table si le coup stocké est légal
    2. Analyse livre exacte (enfants) ou tablebase
    3. Secours Minimax 6 plies si la table propose un coup impossible
    4. MCTS puis premier coup légal
    Au tour suivant, le livre d'ouverture est consulté à nouveau s'il existe.
    """
    valid_set = set(valid_actions)
    if not valid_set:
        return None, {}

    tb = get_tablebase_lookup()
    hit = tb.lookup(board, current_player, last_move)
    table_move_rejected = False

    if hit is not None and hit.best_move is not None:
        if hit.best_move in valid_set:
            if hit.source == "opening_book":
                label = (
                    "Exact (livre d'ouverture)"
                    if hit.exact
                    else "Estimé (livre d'ouverture)"
                )
            else:
                label = "Exact (tablebase)"
            return hit.best_move, {
                "source": hit.source,
                "exact": hit.exact,
                "label": label,
            }
        table_move_rejected = True
        logger.warning(
            "Coach: coup table illégal %s source=%s → secours Minimax %d plies",
            hit.best_move,
            hit.source,
            BACKUP_DEPTH,
        )

    if hit is not None and hit.source == "opening_book" and hit.exact:
        book = tb.opening_book_coach_analysis(board, current_player, last_move, hit)
        action = _resolve_from_analysis(book, valid_set)
        if action is not None:
            return action, book

    skip_full_analysis = (
        table_move_rejected and hit is not None and hit.source == "opening_book"
    )
    if not skip_full_analysis:
        analysis = tb.analyze_position(board, current_player, last_move)
        if analysis:
            action = _resolve_from_analysis(analysis, valid_set)
            if action is not None:
                return action, analysis

    action = backup_minimax_move(board, current_player, last_move, valid_set)
    if action is not None:
        label = f"Secours Minimax ({BACKUP_DEPTH} plies)"
        if table_move_rejected:
            label += " — livre d'ouverture au prochain coup si disponible"
        return action, {
            "source": "backup_minimax",
            "exact": False,
            "label": label,
            "table_move_rejected": table_move_rejected,
        }

    analysis = _mcts_fallback.analyze_position(board, current_player, last_move)
    analysis["source"] = "mcts"
    analysis["exact"] = False
    analysis["label"] = "Estimé (MCTS)"
    action = _resolve_from_analysis(analysis, valid_set)
    if action is not None:
        return action, analysis

    logger.warning("Coach: fallback sur premier coup légal")
    return valid_actions[0], {
        "source": "fallback",
        "exact": False,
        "label": "Coup légal",
    }
