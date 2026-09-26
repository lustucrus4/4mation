"""Calculs dérivés de la revue de partie : phases, moments clés, résumés.

Ce module ne parle pas au moteur : il transforme des coups déjà analysés par
``game_review`` en statistiques et en libellés lisibles.

Règle de confiance (appliquée sans exception) :
- ``exact=True``  → ``nature = "proven"``   : valeur **prouvée** (tablebase ou mat forcé) ;
- ``exact=False`` → ``nature = "estimated"``: valeur **estimée**, bornée par un budget.

Aucun agrégat ne mélange les deux familles : les compteurs sont toujours séparés, et
un coup non analysé garde ``nature = "unknown"``.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

PHASES: tuple[str, ...] = ("opening", "middlegame", "endgame")

PHASE_LABELS: Dict[str, str] = {
    "opening": "Ouverture",
    "middlegame": "Milieu de partie",
    "endgame": "Finale",
}

CLASS_LABELS: Dict[str, str] = {
    "best": "Meilleur coup",
    "excellent": "Excellent",
    "good": "Bon coup",
    "inaccuracy": "Imprécision",
    "mistake": "Erreur",
    "blunder": "Gaffe",
    "unknown": "—",
}

ERROR_CLASSIFICATIONS = ("mistake", "blunder")

# Bornes de phase, alignées sur les seuils d'analyse : le livre couvre les 12 premiers
# demi-coups (ouverture), la tablebase exacte les finales à ≤ 12 cases vides.
_OPENING_MIN_EMPTY = 37
_ENDGAME_MAX_EMPTY = 12

# En dessous de ce delta, un coup n'est pas retenu comme « moment clé ».
_MIN_MOMENT_LOSS = 0.03


def phase_for(empty_cells: int) -> str:
    """Phase d'après le nombre de cases vides de la position *avant* le coup."""
    if empty_cells <= _ENDGAME_MAX_EMPTY:
        return "endgame"
    if empty_cells >= _OPENING_MIN_EMPTY:
        return "opening"
    return "middlegame"


def nature_of(*, analyzed: bool, exact: bool) -> str:
    """``proven`` / ``estimated`` / ``unknown`` — jamais un mélange."""
    if not analyzed:
        return "unknown"
    return "proven" if exact else "estimated"


def outcome_status(win_rate: float, *, exact: bool) -> str:
    """Valeur de la position atteinte par le coup, dans la même règle de confiance."""
    if not exact:
        return "estimated"
    if win_rate >= 0.995:
        return "proven_win"
    if win_rate <= 0.005:
        return "proven_loss"
    if abs(win_rate - 0.5) < 0.01:
        return "proven_draw"
    return "proven_unknown"


def move_verdict(
    *,
    analyzed: bool,
    classification: str,
    nature: str,
    missed_forced_win: bool,
    played_outcome: str,
) -> str:
    """Libellé clair qui dit explicitement si la faute est prouvée ou estimée."""
    if not analyzed or nature == "unknown":
        return "Non analysé"
    label = CLASS_LABELS.get(classification, classification)
    if nature == "estimated":
        return f"{label} (estimation)"
    if missed_forced_win:
        if played_outcome == "proven_draw":
            return "Mat forcé manqué — nulle prouvée"
        if played_outcome == "proven_loss":
            return "Faute prouvée — position perdante"
        return "Mat forcé manqué (prouvé)"
    if classification in ERROR_CLASSIFICATIONS:
        return f"{label} prouvée"
    if classification == "inaccuracy":
        return "Imprécision prouvée"
    return f"{label} (prouvé)"


def accuracy_by_phase(moves: Sequence[Dict[str, Any]], human_color: int) -> Dict[str, Any]:
    """Précision moyenne par phase, séparément pour l'humain et le bot."""
    buckets: Dict[str, Dict[str, List[float]]] = {
        "human": {p: [] for p in PHASES},
        "bot": {p: [] for p in PHASES},
    }
    for m in moves:
        acc = m.get("accuracy")
        if acc is None:
            continue
        phase = m.get("phase")
        if phase not in PHASES:
            continue
        who = "human" if int(m.get("player", 0)) == human_color else "bot"
        buckets[who][phase].append(float(acc))

    def mean(values: List[float]) -> Optional[float]:
        return round(sum(values) / len(values), 1) if values else None

    return {
        "human": {p: mean(buckets["human"][p]) for p in PHASES},
        "bot": {p: mean(buckets["bot"][p]) for p in PHASES},
        "counts": {
            "human": {p: len(buckets["human"][p]) for p in PHASES},
            "bot": {p: len(buckets["bot"][p]) for p in PHASES},
        },
    }


def proven_stats(moves: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Compteurs séparés prouvé / estimé : preuve que les deux ne sont pas mélangés."""
    by_phase = {
        p: {"proven": 0, "estimated": 0, "unknown": 0} for p in PHASES
    }
    counts = {"proven": 0, "estimated": 0, "unknown": 0}
    proven_errors = 0
    estimated_errors = 0
    missed_forced_wins = 0
    for m in moves:
        nature = str(m.get("nature") or "unknown")
        if nature not in counts:
            nature = "unknown"
        counts[nature] += 1
        phase = m.get("phase")
        if phase in by_phase:
            by_phase[phase][nature] += 1
        if m.get("proven_error"):
            proven_errors += 1
        if nature == "estimated" and m.get("classification") in ERROR_CLASSIFICATIONS:
            estimated_errors += 1
        if m.get("missed_forced_win"):
            missed_forced_wins += 1
    return {
        "proven_moves": counts["proven"],
        "estimated_moves": counts["estimated"],
        "unknown_moves": counts["unknown"],
        "proven_errors": proven_errors,
        "estimated_errors": estimated_errors,
        "missed_forced_wins": missed_forced_wins,
        "by_phase": by_phase,
        "mixed": False,
    }


def _player_label(move: Dict[str, Any]) -> str:
    return "Vous" if move.get("is_human") else "Coach"


def _delta_p1(move: Dict[str, Any]) -> float:
    """Variation du taux de victoire du joueur 1 due au coup (négatif = perte)."""
    before = float(move.get("win_rate_before") or 0.5)
    played = float(move.get("win_rate_played") or 0.5)
    delta = played - before
    if int(move.get("player", 1)) == 2:
        delta = -delta
    return round(delta, 4)


def describe_key_moment(move: Dict[str, Any], loss: float) -> Dict[str, Any]:
    nature = str(move.get("nature") or "unknown")
    nature_txt = {"proven": "prouvée", "estimated": "estimée"}.get(nature, "non analysée")
    best = move.get("best_move")
    if isinstance(best, (list, tuple)) and len(best) == 2:
        best_txt = f"meilleur coup conseillé ({int(best[0])},{int(best[1])})"
    else:
        best_txt = "aucun meilleur coup disponible"

    played_pct = round(float(move.get("win_rate_played") or 0.0) * 100)
    best_pct = round(float(move.get("win_rate_best") or 0.0) * 100)
    loss_pct = round(loss * 100)
    mate = move.get("mate_in")
    mate_txt = ""
    if move.get("missed_forced_win") and mate:
        mate_txt = f" (mat forcé en {int(mate)} coup(s) manqué)"

    description = (
        f"Coup #{move.get('index')} ({_player_label(move)}) : "
        f"{move.get('verdict')}{mate_txt} — {loss_pct} points de taux de victoire perdus "
        f"({played_pct} % joué contre {best_pct} % au mieux), {best_txt}."
    )
    return {
        "index": move.get("index"),
        "player": move.get("player"),
        "is_human": bool(move.get("is_human")),
        "row": move.get("row"),
        "col": move.get("col"),
        "phase": move.get("phase"),
        "classification": move.get("classification"),
        "nature": nature,
        "win_rate_loss": round(loss, 4),
        "delta_p1": _delta_p1(move),
        "best_move": list(best) if isinstance(best, (list, tuple)) else None,
        "description": description,
    }


def key_moments(
    moves: Sequence[Dict[str, Any]],
    human_color: int,
    *,
    limit: int = 5,
) -> List[Dict[str, Any]]:
    """Les ``limit`` plus gros retournements, du pire au moindre."""
    scored = []
    for m in moves:
        loss = m.get("win_rate_loss")
        if loss is None:
            continue
        loss = float(loss)
        if loss >= _MIN_MOMENT_LOSS:
            scored.append((loss, m))
    scored.sort(key=lambda t: t[0], reverse=True)
    return [describe_key_moment(m, loss) for loss, m in scored[: max(0, limit)]]


def _class_counts(moves: Sequence[Dict[str, Any]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for m in moves:
        c = str(m.get("classification") or "unknown")
        counts[c] = counts.get(c, 0) + 1
    return counts


def _summary_for_player(
    moves: Sequence[Dict[str, Any]],
    who: str,
    accuracy_by_phase_map: Dict[str, Any],
    accuracy: Optional[float],
) -> Dict[str, Any]:
    counts = _class_counts(moves)
    strengths = counts.get("best", 0) + counts.get("excellent", 0)
    proven_errors = sum(1 for m in moves if m.get("proven_error"))
    estimated_errors = sum(
        1
        for m in moves
        if m.get("nature") == "estimated" and m.get("classification") in ERROR_CLASSIFICATIONS
    )

    decisive = None
    for m in moves:
        loss = m.get("win_rate_loss")
        if loss is None:
            continue
        if decisive is None or float(loss) > float(decisive.get("win_rate_loss") or 0.0):
            decisive = m
    if decisive is not None and float(decisive.get("win_rate_loss") or 0.0) < _MIN_MOMENT_LOSS:
        decisive = None

    losses_by_phase: Dict[str, float] = {p: 0.0 for p in PHASES}
    for m in moves:
        phase = m.get("phase")
        if phase in losses_by_phase and m.get("win_rate_loss") is not None:
            losses_by_phase[phase] += float(m["win_rate_loss"])
    decisive_phase = None
    if any(v >= _MIN_MOMENT_LOSS for v in losses_by_phase.values()):
        decisive_phase = max(losses_by_phase, key=lambda p: losses_by_phase[p])

    errors_total = proven_errors + estimated_errors
    if errors_total == 0:
        weakness = "aucune erreur majeure"
    else:
        weakness = f"{errors_total} erreur(s) dont {proven_errors} prouvée(s) et {estimated_errors} estimée(s)"

    if decisive is None:
        decisive_txt = "aucune faute décisive"
    else:
        decisive_txt = (
            f"coup #{decisive.get('index')} ({decisive.get('verdict')}, "
            f"-{round(float(decisive.get('win_rate_loss') or 0.0) * 100)} %)"
        )

    phase_txt = PHASE_LABELS.get(decisive_phase or "", "—")
    acc_txt = f"{accuracy} %" if accuracy is not None else "non calculée"
    text = (
        f"{who} : {acc_txt} de précision. "
        f"Points forts : {strengths} coup(s) excellent(s) ou meilleur(s). "
        f"Points faibles : {weakness}. "
        f"Faute décisive : {decisive_txt}. "
        f"Phase décisive : {phase_txt}."
    )

    return {
        "accuracy": accuracy,
        "counts": counts,
        "strengths": strengths,
        "errors": {"total": errors_total, "proven": proven_errors, "estimated": estimated_errors},
        "decisive_move": (
            {
                "index": decisive.get("index"),
                "classification": decisive.get("classification"),
                "nature": decisive.get("nature"),
                "verdict": decisive.get("verdict"),
                "win_rate_loss": round(float(decisive.get("win_rate_loss") or 0.0), 4),
                "phase": decisive.get("phase"),
            }
            if decisive is not None
            else None
        ),
        "decisive_phase": decisive_phase,
        "text": text,
    }


def build_summary(
    moves: Sequence[Dict[str, Any]],
    human_color: int,
    accuracy_by_phase_map: Dict[str, Any],
    accuracies: Dict[str, Optional[float]],
) -> Dict[str, Any]:
    """Résumé textuel court par joueur (points forts/faibles, faute et phase décisives)."""
    human_moves = [m for m in moves if int(m.get("player", 0)) == human_color]
    bot_color = 2 if human_color == 1 else 1
    bot_moves = [m for m in moves if int(m.get("player", 0)) == bot_color]

    human = _summary_for_player(
        human_moves, "Vous", accuracy_by_phase_map.get("human", {}), accuracies.get("human")
    )
    bot = _summary_for_player(
        bot_moves, "Le bot", accuracy_by_phase_map.get("bot", {}), accuracies.get("bot")
    )
    return {"human": human, "bot": bot}
