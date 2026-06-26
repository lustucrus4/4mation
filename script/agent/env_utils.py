"""
Utilitaires pour créer et envelopper l'environnement d'entraînement (obs 149 dims).
"""

from __future__ import annotations

import numpy as np
import gymnasium as gym

from simulator.env import FourMationEnv
from simulator.wrappers import ActionMaskWrapper
from utils.config import config

# sb3-contrib (MaskablePPO) — optionnel
try:
    from sb3_contrib import MaskablePPO  # noqa: F401
    from sb3_contrib.common.wrappers import ActionMasker

    HAS_MASKABLE_PPO = True
except ImportError:
    HAS_MASKABLE_PPO = False
    ActionMasker = None  # type: ignore


def observation_dim() -> int:
    """Taille de l'observation : board + last_move + action_mask."""
    g = config.game
    return (
        g.board_width * g.board_height * g.num_players
        + 2
        + g.board_width * g.board_height
    )


OBSERVATION_DIM = observation_dim()
LEGACY_OBSERVATION_DIM = 98


def _unwrap_to_engine_env(env: gym.Env) -> FourMationEnv:
    """Remonte les wrappers jusqu'à FourMationEnv."""
    current = env
    while hasattr(current, "env"):
        if isinstance(current, FourMationEnv):
            return current
        current = current.env
    if isinstance(current, FourMationEnv):
        return current
    raise TypeError("FourMationEnv introuvable dans la pile de wrappers")


def get_action_mask(env: gym.Env) -> np.ndarray:
    """Masque booléen des actions légales pour MaskablePPO."""
    base = _unwrap_to_engine_env(env)
    width = base.engine.board_width
    mask = np.zeros(base.action_space.n, dtype=bool)
    for row, col in base.engine.get_valid_actions():
        mask[row * width + col] = True
    return mask


def wrap_env_for_ppo(env: gym.Env) -> gym.Env:
    """
    Enveloppe l'environnement pour l'entraînement PPO.

    - MaskablePPO (sb3-contrib) : ActionMasker
    - PPO standard : ActionMaskWrapper (filtre les actions invalides)
    """
    if HAS_MASKABLE_PPO:
        return ActionMasker(env, get_action_mask)
    return ActionMaskWrapper(env)


def make_base_env(opponent_type: str = "random") -> FourMationEnv:
    """Crée un FourMationEnv nu (obs 149 dims intégrée)."""
    return FourMationEnv(opponent_type=opponent_type)


def make_training_env(
    opponent_type: str = "random",
    track_games: bool = True,
) -> gym.Env:
    """Factory : env de base + tracking optionnel + wrapper masque d'actions."""
    env = make_base_env(opponent_type=opponent_type)
    if track_games:
        from simulator.game_tracker_wrapper import GameTrackerWrapper

        env = GameTrackerWrapper(env)
    return wrap_env_for_ppo(env)


def ppo_algorithm_name() -> str:
    return "MaskablePPO" if HAS_MASKABLE_PPO else "PPO"
