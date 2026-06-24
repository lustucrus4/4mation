"""
Wrapper pour tracker les parties complètes pendant l'entraînement
"""

import numpy as np
import gymnasium as gym
from typing import Dict, List, Tuple, Optional


class GameTrackerWrapper(gym.Wrapper):
    """
    Wrapper qui track les parties complètes avec leurs récompenses
    """
    
    def __init__(self, env):
        super().__init__(env)
        self.current_episode_moves = []
        self.current_episode_boards = []
        self.current_episode_reward = 0.0
        self.current_episode_info = {}
        
    def reset(self, **kwargs):
        """Réinitialise et commence un nouvel épisode"""
        obs, info = self.env.reset(**kwargs)
        
        # Réinitialiser le tracking
        self.current_episode_moves = []
        self.current_episode_boards = []
        self.current_episode_reward = 0.0
        self.current_episode_info = {}
        
        # Sauvegarder le plateau initial
        board = self.env.engine.get_state().board.copy()
        self.current_episode_boards.append(board.tolist())
        
        return obs, info
    
    def step(self, action):
        """Exécute un step et track les données"""
        obs, reward, terminated, truncated, info = self.env.step(action)
        
        # Accumuler la récompense
        self.current_episode_reward += reward
        
        # Sauvegarder le coup (décoder l'action)
        row = action // self.env.engine.board_width
        col = action % self.env.engine.board_width
        self.current_episode_moves.append((int(row), int(col)))
        
        # Sauvegarder le plateau actuel
        board = self.env.engine.get_state().board.copy()
        self.current_episode_boards.append(board.tolist())
        
        # Si l'épisode est terminé, préparer les données
        if terminated or truncated:
            winner = self.env.engine.get_winner()
            self.current_episode_info = {
                'moves': self.current_episode_moves.copy(),
                'board_history': self.current_episode_boards.copy(),
                'final_board': board.tolist(),
                'winner': winner,
                'move_count': len(self.current_episode_moves),
                'reward': self.current_episode_reward,
                'terminated': terminated,
                'truncated': truncated
            }
        
        return obs, reward, terminated, truncated, info
    
    def get_episode_data(self) -> Optional[Dict]:
        """Retourne les données de l'épisode actuel si terminé"""
        if self.current_episode_info:
            return self.current_episode_info.copy()
        return None
    
    def reset_episode_tracking(self):
        """Réinitialise le tracking pour le prochain épisode"""
        self.current_episode_info = {}
        self.current_episode_reward = 0.0

