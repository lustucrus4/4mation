"""
Wrapper pour utiliser Minimax comme adversaire dans l'environnement
"""

import numpy as np
import gymnasium as gym
from typing import Optional, Tuple, Dict
from game_tree.optimized_minimax import OptimizedMinimaxAdvisor
from game.game_engine import GameEngine


class MinimaxOpponentWrapper(gym.Wrapper):
    """
    Wrapper qui remplace l'adversaire aléatoire par Minimax.
    Supporte la profondeur progressive pour le curriculum learning.
    """
    
    def __init__(self, env, minimax_depth: int = 4):
        """
        Args:
            env: Environnement FourMationEnv à envelopper
            minimax_depth: Profondeur initiale de Minimax
        """
        super().__init__(env)
        self.minimax_depth = minimax_depth
        self.minimax_advisor = OptimizedMinimaxAdvisor(depth=minimax_depth)
        
        # S'assurer que l'environnement n'a pas d'adversaire automatique
        # (on le gère nous-mêmes)
        if hasattr(env, 'opponent_type'):
            self.original_opponent_type = env.opponent_type
            env.opponent_type = "none"  # Désactiver l'adversaire automatique
        else:
            self.original_opponent_type = "none"
    
    def set_minimax_depth(self, depth: int):
        """Change la profondeur de Minimax (pour curriculum learning)"""
        if depth != self.minimax_depth:
            self.minimax_depth = depth
            self.minimax_advisor = OptimizedMinimaxAdvisor(depth=depth)
            print(f"📊 Profondeur Minimax mise à jour: {depth}")
    
    def reset(self, **kwargs):
        """Réinitialise l'environnement"""
        obs, info = self.env.reset(**kwargs)
        return obs, info
    
    def step(self, action: int) -> Tuple[np.ndarray, float, bool, bool, Dict]:
        """
        Exécute l'action de l'agent, puis fait jouer Minimax comme adversaire.
        """
        # Décoder l'action de l'agent
        row = action // self.env.engine.board_width
        col = action % self.env.engine.board_width
        action_pos = (row, col)
        
        # Vérifier si l'action est valide
        valid_actions = self.env.engine.get_valid_actions()
        if action_pos not in valid_actions:
            reward = -10.0
            terminated = True
            truncated = False
            info = {"invalid_action": True, "valid_actions": valid_actions}
            return self.env.current_observation, reward, terminated, truncated, info
        
        # Exécuter l'action du joueur 1 (l'agent)
        state, success, winner = self.env.engine.step(action_pos)
        
        if not success:
            reward = -10.0
            terminated = True
            truncated = False
            info = {"action_failed": True}
            return self.env.current_observation, reward, terminated, truncated, info
        
        # Vérifier si l'agent a gagné
        if winner == 1:
            reward = 10.0
            terminated = True
            truncated = False
            info = {"winner": 1}
            self.env.current_observation = self.env._get_observation()
            return self.env.current_observation, reward, terminated, truncated, info
        
        # Vérifier égalité
        if winner == 0:
            reward = 0.0
            terminated = True
            truncated = False
            info = {"winner": 0}
            self.env.current_observation = self.env._get_observation()
            return self.env.current_observation, reward, terminated, truncated, info
        
        # Si la partie continue, Minimax (joueur 2) joue
        if not self.env.engine.is_terminal():
            # Obtenir le meilleur coup de Minimax
            board = state.board
            last_move = state.last_move_position
            
            # Minimax joue le joueur 2
            analysis = self.minimax_advisor.analyze_position(
                board=board,
                current_player=2,
                last_move=last_move
            )
            
            if analysis['best_move'] is None:
                # Pas de coup valide, égalité
                reward = 0.0
                terminated = True
                truncated = False
                info = {"winner": 0, "minimax_no_move": True}
                self.env.current_observation = self.env._get_observation()
                return self.env.current_observation, reward, terminated, truncated, info
            
            minimax_move = analysis['best_move']
            
            # Exécuter le coup de Minimax
            state, success, winner = self.env.engine.step(minimax_move)
            
            if not success:
                # Minimax a joué un coup invalide (ne devrait pas arriver)
                reward = 0.0
                terminated = True
                truncated = False
                info = {"minimax_invalid_move": True}
                self.env.current_observation = self.env._get_observation()
                return self.env.current_observation, reward, terminated, truncated, info
            
            # Vérifier si Minimax a gagné
            if winner == 2:
                reward = -10.0
                terminated = True
                truncated = False
                info = {"winner": 2, "minimax_won": True}
                self.env.current_observation = self.env._get_observation()
                return self.env.current_observation, reward, terminated, truncated, info
            
            # Vérifier égalité après le coup de Minimax
            if winner == 0:
                reward = 0.0
                terminated = True
                truncated = False
                info = {"winner": 0}
                self.env.current_observation = self.env._get_observation()
                return self.env.current_observation, reward, terminated, truncated, info
        
        # Partie en cours: calculer une récompense intelligente
        reward = self.env._calculate_smart_reward(state, action_pos)
        terminated = False
        truncated = False
        info = {
            "current_player": self.env.engine.get_current_player(),
            "valid_actions": self.env.engine.get_valid_actions(),
            "minimax_depth": self.minimax_depth
        }
        
        self.env.current_observation = self.env._get_observation()
        return self.env.current_observation, reward, terminated, truncated, info

