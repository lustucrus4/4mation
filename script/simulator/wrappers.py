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
    Utile pour éviter que l'agent choisisse des colonnes pleines.
    """
    
    def __init__(self, env):
        super().__init__(env)
        # Ajouter un espace d'observation pour le masque d'actions
        # On concatène le masque à l'observation
        original_obs_size = env.observation_space.shape[0]
        self.observation_space = spaces.Box(
            low=0, high=1,
            shape=(original_obs_size + env.action_space.n,),
            dtype=np.float32
        )
    
    def observation(self, obs):
        """
        Ajoute le masque d'actions à l'observation.
        """
        valid_actions = self.env.engine.get_valid_actions()
        action_mask = np.zeros(self.env.action_space.n, dtype=np.float32)
        for action in valid_actions:
            action_mask[action] = 1.0
        
        return np.concatenate([obs, action_mask])
    
    def action(self, action):
        """
        S'assure que l'action est valide.
        Si invalide, retourne la première action valide.
        """
        valid_actions = self.env.engine.get_valid_actions()
        if action in valid_actions:
            return action
        elif valid_actions:
            return valid_actions[0]
        else:
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

