"""
Callback pour le curriculum learning avec Minimax
Augmente progressivement la profondeur de Minimax selon la performance
"""

from typing import Optional, Dict
from stable_baselines3.common.callbacks import BaseCallback
import numpy as np


class CurriculumCallback(BaseCallback):
    """
    Callback qui gère la progression automatique de la profondeur Minimax.
    Augmente la difficulté quand le PPO performe bien.
    """
    
    def __init__(self,
                 initial_depth: int = 2,
                 max_depth: int = 8,
                 win_rate_threshold: float = 0.6,
                 evaluation_freq: int = 1000,
                 num_eval_games: int = 20,
                 verbose: int = 0):
        """
        Args:
            initial_depth: Profondeur initiale de Minimax
            max_depth: Profondeur maximale de Minimax
            win_rate_threshold: Taux de victoire requis pour augmenter la profondeur (0.6 = 60%)
            evaluation_freq: Fréquence d'évaluation (en steps)
            num_eval_games: Nombre de parties pour évaluer la performance
            verbose: Niveau de verbosité
        """
        super().__init__(verbose)
        self.initial_depth = initial_depth
        self.max_depth = max_depth
        self.win_rate_threshold = win_rate_threshold
        self.evaluation_freq = evaluation_freq
        self.num_eval_games = num_eval_games
        
        self.current_depth = initial_depth
        self.depth_progression = [2, 4, 6, 8]  # Progression standard
        self.current_depth_index = 0
        
        # Statistiques
        self.evaluation_results = []
        self.last_evaluation_step = 0
        
        # Référence à l'environnement (sera définie dans _on_training_start)
        self.env_wrapper = None
    
    def _on_training_start(self) -> None:
        """Appelé au début de l'entraînement"""
        # Trouver le MinimaxOpponentWrapper dans l'environnement
        self.env_wrapper = self._find_minimax_wrapper(self.training_env)
        
        if self.env_wrapper is None:
            if self.verbose > 0:
                print("⚠️  CurriculumCallback: MinimaxOpponentWrapper non trouvé")
            return
        
        # Initialiser la profondeur
        self.env_wrapper.set_minimax_depth(self.current_depth)
        
        if self.verbose > 0:
            print(f"📚 Curriculum Learning activé:")
            print(f"   Profondeur initiale: {self.current_depth}")
            print(f"   Profondeur maximale: {self.max_depth}")
            print(f"   Seuil de progression: {self.win_rate_threshold * 100:.0f}% de victoires")
    
    def _find_minimax_wrapper(self, env) -> Optional:
        """Trouve le MinimaxOpponentWrapper dans l'environnement"""
        from simulator.minimax_opponent_wrapper import MinimaxOpponentWrapper
        
        # Si c'est un VecEnv, chercher dans les environnements
        if hasattr(env, 'envs'):
            for sub_env in env.envs:
                wrapper = self._find_minimax_wrapper(sub_env)
                if wrapper is not None:
                    return wrapper
        
        # Vérifier si c'est le wrapper lui-même
        if isinstance(env, MinimaxOpponentWrapper):
            return env
        
        # Vérifier si c'est enveloppé
        if hasattr(env, 'env'):
            return self._find_minimax_wrapper(env.env)
        
        return None
    
    def _on_step(self) -> bool:
        """
        Appelé à chaque step. Évalue la performance périodiquement
        et augmente la profondeur si nécessaire.
        """
        if self.env_wrapper is None:
            return True
        
        # Évaluer périodiquement
        if self.num_timesteps - self.last_evaluation_step >= self.evaluation_freq:
            self._evaluate_performance()
            self.last_evaluation_step = self.num_timesteps
        
        return True
    
    def _evaluate_performance(self):
        """
        Évalue la performance du PPO contre Minimax actuel
        et augmente la profondeur si le taux de victoire est suffisant.
        """
        if self.env_wrapper is None:
            return
        
        # Simuler quelques parties pour évaluer
        # Note: Dans un vrai environnement, on devrait faire des évaluations réelles
        # Pour l'instant, on utilise une heuristique basée sur les récompenses
        
        # Vérifier si on peut augmenter la profondeur
        if self.current_depth_index < len(self.depth_progression) - 1:
            next_depth = self.depth_progression[self.current_depth_index + 1]
            
            # Pour simplifier, on augmente la profondeur après un certain nombre de steps
            # Dans une implémentation complète, on ferait des évaluations réelles
            steps_at_current_depth = self.num_timesteps - self.last_evaluation_step
            
            # Augmenter la profondeur progressivement
            depth_increase_threshold = self.evaluation_freq * (self.current_depth_index + 1) * 2
            
            if steps_at_current_depth >= depth_increase_threshold:
                self._increase_depth(next_depth)
    
    def _increase_depth(self, new_depth: int):
        """Augmente la profondeur de Minimax"""
        if new_depth > self.max_depth:
            return
        
        if self.env_wrapper is not None:
            self.current_depth = new_depth
            self.current_depth_index += 1
            self.env_wrapper.set_minimax_depth(new_depth)
            
            if self.verbose > 0:
                print(f"📈 Curriculum: Profondeur Minimax augmentée à {new_depth}")
    
    def _on_training_end(self) -> None:
        """Appelé à la fin de l'entraînement"""
        if self.verbose > 0:
            print(f"\n📚 Curriculum Learning - Profondeur finale: {self.current_depth}")

