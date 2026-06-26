"""
Wrappers pour améliorer l'apprentissage de l'IA
"""

import numpy as np
import gymnasium as gym
from gymnasium import spaces
from typing import Any, Dict, Tuple, Optional


class ActionMaskWrapper(gym.ActionWrapper):
    """
    Wrapper qui masque les actions invalides.
    Utile pour éviter que l'agent choisisse des coups hors frontière.
    """

    def __init__(self, env):
        super().__init__(env)
        obs_size = env.observation_space.shape[0]
        # Si l'env inclut déjà le masque, ne pas le dupliquer
        if hasattr(env, "_action_mask_dims") and obs_size > env._board_channels + env._last_move_dims:
            self._mask_in_obs = True
            self.observation_space = env.observation_space
        else:
            self._mask_in_obs = False
            self.observation_space = spaces.Box(
                low=-1, high=1,
                shape=(obs_size + env.action_space.n,),
                dtype=np.float32
            )

    @staticmethod
    def _pos_to_action(row: int, col: int, width: int) -> int:
        return row * width + col

    def _build_action_mask(self) -> np.ndarray:
        width = self.env.engine.board_width
        action_mask = np.zeros(self.env.action_space.n, dtype=np.float32)
        for row, col in self.env.engine.get_valid_actions():
            action_mask[self._pos_to_action(row, col, width)] = 1.0
        return action_mask

    def observation(self, obs):
        """Ajoute le masque d'actions à l'observation si absent."""
        if self._mask_in_obs:
            return obs
        action_mask = self._build_action_mask()
        return np.concatenate([obs, action_mask])

    def action(self, action):
        """S'assure que l'action est valide (index row * width + col)."""
        width = self.env.engine.board_width
        valid_actions = self.env.engine.get_valid_actions()
        valid_indices = {self._pos_to_action(r, c, width) for r, c in valid_actions}
        if action in valid_indices:
            return action
        if valid_indices:
            return min(valid_indices)
        return 0


class RewardShapingWrapper(gym.RewardWrapper):
    """
    Wrapper pour ajuster les récompenses (reward shaping).
    Peut encourager certains comportements.
    """
    
    def __init__(self, env, shaping_factor: float = 0.1):
        super().__init__(env)
        self.shaping_factor = shaping_factor
    
    def reward(self, reward):
        """
        Ajuste la récompense.
        """
        # On peut ajouter des récompenses intermédiaires ici
        # Par exemple, récompenser les positions avantageuses
        return reward * (1.0 + self.shaping_factor)


class NormalizeObservationWrapper(gym.ObservationWrapper):
    """
    Wrapper pour normaliser les observations.
    """
    
    def __init__(self, env):
        super().__init__(env)
        # Les observations sont déjà entre 0 et 1, donc pas besoin de normalisation
        # Mais on peut ajouter d'autres transformations ici
        pass
    
    def observation(self, obs):
        """
        Normalise l'observation.
        """
        # Les observations sont déjà normalisées (0-1)
        return obs.astype(np.float32)

