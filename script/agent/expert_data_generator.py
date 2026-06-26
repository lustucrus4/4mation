"""
Générateur de données expert pour l'imitation learning
Génère des parties jouées par Minimax pour entraîner le PPO
"""

import gc
import numpy as np
from typing import List, Dict, Tuple, Optional
from game_tree.optimized_minimax import OptimizedMinimaxAdvisor
from game.game_engine import GameEngine
from utils.config import config


class ExpertDataGenerator:
    """
    Génère des parties jouées par Minimax (expert demonstrations)
    pour l'apprentissage par imitation.
    """
    
    def __init__(self, minimax_depth: int = 6, cache_size: int = 10000):
        """
        Args:
            minimax_depth: Profondeur de Minimax pour générer les données expert
            cache_size: Taille max du cache de transposition (réduit vs jeu live)
        """
        self.minimax_depth = minimax_depth
        self.minimax_advisor = OptimizedMinimaxAdvisor(
            depth=minimax_depth,
            cache_size=cache_size,
            use_iterative_deepening=False,
        )
        self.engine = GameEngine(
            board_width=config.game.board_width,
            board_height=config.game.board_height,
            num_players=config.game.num_players,
            win_length=config.game.win_length
        )
    
    def _board_to_observation(self, board: np.ndarray) -> np.ndarray:
        """
        Convertit un plateau en observation (format PPO).
        
        Args:
            board: Plateau 7x7
            
        Returns:
            Observation aplatie (147 valeurs: 7*7*3)
        """
        observation = np.zeros(
            (config.game.board_height, config.game.board_width, config.game.num_players),
            dtype=np.float32
        )
        
        for row in range(config.game.board_height):
            for col in range(config.game.board_width):
                player = board[row, col]
                if player > 0:
                    observation[row, col, player - 1] = 1.0
        
        return observation.flatten()
    
    def _action_to_int(self, move: Tuple[int, int]) -> int:
        """Convertit un coup (row, col) en action entière"""
        return move[0] * config.game.board_width + move[1]
    
    def generate_game(self, player1_minimax: bool = True, player2_minimax: bool = True) -> List[Dict]:
        """
        Génère une partie complète jouée par Minimax.
        
        Args:
            player1_minimax: Si True, le joueur 1 est Minimax
            player2_minimax: Si True, le joueur 2 est Minimax
            
        Returns:
            Liste de transitions (observation, action, reward, next_observation, done)
        """
        self.engine.reset()
        transitions = []
        
        # Pour l'apprentissage par imitation, on veut que Minimax joue le joueur 1
        # (l'agent PPO apprendra à imiter Minimax)
        current_player = 1
        last_move = None
        
        while not self.engine.is_terminal():
            board = self.engine.get_state().board
            observation = self._board_to_observation(board)
            
            # Déterminer qui joue
            use_minimax = (current_player == 1 and player1_minimax) or \
                         (current_player == 2 and player2_minimax)
            
            if use_minimax:
                # Minimax joue
                analysis = self.minimax_advisor.analyze_position(
                    board=board,
                    current_player=current_player,
                    last_move=last_move
                )
                
                if analysis['best_move'] is None:
                    # Pas de coup valide, fin de partie
                    break
                
                move = analysis['best_move']
            else:
                # Joueur aléatoire (pour diversité)
                valid_actions = self.engine.get_valid_actions()
                if not valid_actions:
                    break
                import random
                move = random.choice(valid_actions)
            
            # Exécuter le coup
            state, success, winner = self.engine.step(move)
            
            if not success:
                break
            
            # Calculer la récompense
            if winner == current_player:
                reward = 10.0
                done = True
            elif winner == 0:
                reward = 0.0
                done = True
            else:
                # Partie continue
                reward = 0.01  # Petite récompense pour continuer
                done = False
            
            # Observation suivante
            next_board = state.board
            next_observation = self._board_to_observation(next_board)
            
            # Encoder l'action
            action = self._action_to_int(move)
            
            # Sauvegarder la transition (seulement pour le joueur 1 si on apprend à imiter Minimax)
            if current_player == 1 and player1_minimax:
                transitions.append({
                    'observation': observation,
                    'action': action,
                    'reward': reward,
                    'next_observation': next_observation,
                    'done': done,
                    'move': move
                })
            
            # Mettre à jour pour le prochain coup
            last_move = move
            current_player = 3 - current_player  # Alterner entre 1 et 2
            
            if done:
                break
        
        return transitions
    
    def generate(self, num_games: int = 150, player1_minimax: bool = True) -> List[Dict]:
        """
        Génère plusieurs parties et retourne toutes les transitions.
        
        Args:
            num_games: Nombre de parties à générer
            player1_minimax: Si True, Minimax joue le joueur 1 (pour imitation learning)
            
        Returns:
            Liste de toutes les transitions de toutes les parties
        """
        all_transitions = []
        
        print(f"Génération de {num_games} parties expert avec Minimax (profondeur {self.minimax_depth})...")
        
        for i in range(num_games):
            if (i + 1) % 100 == 0:
                print(f"  Parties générées: {i + 1}/{num_games}")
            
            transitions = self.generate_game(player1_minimax=player1_minimax, player2_minimax=False)
            all_transitions.extend(transitions)
            del transitions
            self.minimax_advisor.clear_cache()
            gc.collect()
        
        print(f"✅ {len(all_transitions)} transitions expert générées")
        
        return all_transitions
    
    def save_to_file(self, transitions: List[Dict], filepath: str):
        """Sauvegarde les transitions dans un fichier"""
        import pickle
        with open(filepath, 'wb') as f:
            pickle.dump(transitions, f)
        print(f"💾 Données expert sauvegardées: {filepath}")
    
    def load_from_file(self, filepath: str) -> List[Dict]:
        """Charge les transitions depuis un fichier"""
        import pickle
        with open(filepath, 'rb') as f:
            transitions = pickle.load(f)
        print(f"📂 Données expert chargées: {filepath} ({len(transitions)} transitions)")
        return transitions

