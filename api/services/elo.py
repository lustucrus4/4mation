"""Calcul Elo pour les parties contre les bots."""

from __future__ import annotations

from typing import Tuple

# Elo de référence par niveau de bot (calibré pour progresser de façon lisible).
BOT_ELO: dict[str, int] = {
    "level_1": 800,
    "level_2": 1000,
    "level_3": 1200,
    "level_4": 1500,
    "level_5": 1800,
}

DEFAULT_BOT_ELO = 1200
K_FACTOR = 32


def bot_elo(bot_id: str) -> int:
    return BOT_ELO.get(bot_id, DEFAULT_BOT_ELO)


def bot_level(bot_id: str) -> int:
    if bot_id.startswith("level_"):
        try:
            return int(bot_id.split("_", 1)[1])
        except ValueError:
            pass
    return 3


def expected_score(player_elo: int, opponent_elo: int) -> float:
    return 1.0 / (1.0 + 10 ** ((opponent_elo - player_elo) / 400.0))


def update_elo(player_elo: int, opponent_elo: int, score: float) -> Tuple[int, int]:
    """score: 1.0 victoire, 0.5 nul, 0.0 défaite. Retourne (nouveau_elo, delta)."""
    exp = expected_score(player_elo, opponent_elo)
    delta = round(K_FACTOR * (score - exp))
    return player_elo + delta, delta


def human_score(winner: int | None, human_color: int) -> float:
    if winner is None:
        return 0.5
    if winner == human_color:
        return 1.0
    return 0.0


def result_label(winner: int | None, human_color: int) -> str:
    if winner is None:
        return "draw"
    if winner == human_color:
        return "win"
    return "loss"
