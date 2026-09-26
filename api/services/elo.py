"""Calcul Elo pour les parties contre les bots."""

from __future__ import annotations

from typing import Tuple

# Elo de référence par niveau de bot.
#
# Ces valeurs sont les Elo mesurés par l'arène round-robin
# (`scripts/bot_arena.py`, `scripts/ARENA_BOTS.md`, Bradley-Terry, 60 parties par paire,
# 900 parties, 4 profils de sonde, mesure du 26/09/2026). Elles servent à convertir les
# résultats de l'humain en Elo lisible : si elles s'écartaient de la mesure, le classement
# affiché contredirait la force réelle des bots. Toute recalibration de l'échelle doit donc
# mettre ces valeurs à jour — `scripts/check_bot_arena.py` échoue si les deux divergent.
#
# Écarts mesurés : +125, +179, +227, +110, +105. L'écart `level_5` → `level_6` reste le
# plus court, mais les deux niveaux sont désormais séparés par les quatre profils de sonde
# (la confrontation directe, elle, ne tranche pas : 0.39 [0.28, 0.52]).
BOT_ELO: dict[str, int] = {
    "level_1": 1109,
    "level_2": 1234,
    "level_3": 1413,
    "level_4": 1640,
    "level_5": 1750,
    "level_6": 1855,
}

DEFAULT_BOT_ELO = BOT_ELO["level_3"]
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
    if winner is None or winner == 0:
        return 0.5
    if winner == human_color:
        return 1.0
    return 0.0


def result_label(winner: int | None, human_color: int) -> str:
    if winner is None or winner == 0:
        return "draw"
    if winner == human_color:
        return "win"
    return "loss"
