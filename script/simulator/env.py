"""
Environnement Gymnasium pour le jeu 4mation
"""

import numpy as np
import gymnasium as gym
from gymnasium import spaces
from typing import Optional, Tuple, Dict, Any

from game.game_engine import GameEngine
from utils.config import config


class FourMationEnv(gym.Env):
    """
    Environnement Gymnasium pour entraîner une IA à jouer à 4mation.
    
    L'agent contrôle le joueur 1. Le joueur 2 peut être:
    - Un autre agent (self-play)
    - Un joueur aléatoire
    - Un joueur avec stratégie fixe
    """
    
    metadata = {"render_modes": ["human", "rgb_array"], "render_fps": 4}
    
    def __init__(self, render_mode: Optional[str] = None, 
                 opponent_type: str = "random"):
        """
        Initialise l'environnement.
        
        Args:
            render_mode: Mode de rendu ("human", "rgb_array", ou None)
            opponent_type: Type d'adversaire ("random", "self", ou "none")
        """
        super().__init__()
        
        self.render_mode = render_mode
        self.opponent_type = opponent_type
        
        # Initialiser le moteur de jeu
        game_cfg = config.game
        self.engine = GameEngine(
            board_width=game_cfg.board_width,
            board_height=game_cfg.board_height,
            num_players=game_cfg.num_players,
            win_length=game_cfg.win_length
        )
        
        # Espace d'observation: plateau + dernier coup + masque d'actions
        board_channels = game_cfg.board_width * game_cfg.board_height * game_cfg.num_players
        last_move_dims = 2
        action_mask_dims = game_cfg.board_width * game_cfg.board_height
        observation_size = board_channels + last_move_dims + action_mask_dims
        self._board_channels = board_channels
        self._last_move_dims = last_move_dims
        self._action_mask_dims = action_mask_dims
        self.observation_space = spaces.Box(
            low=-1, high=1,
            shape=(observation_size,),
            dtype=np.float32
        )
        
        # Espace d'action: choix de position (row, col) encodé comme un seul entier
        # action = row * board_width + col
        self.action_space = spaces.Discrete(game_cfg.board_width * game_cfg.board_height)
        
        # État interne
        self.current_observation = None
    
    def _encode_last_move(self, state) -> np.ndarray:
        """Encode la position du dernier coup (normalisée) ou (-1, -1) si absent."""
        if state.last_move_position is None:
            return np.array([-1.0, -1.0], dtype=np.float32)
        row, col = state.last_move_position
        max_row = max(self.engine.board_height - 1, 1)
        max_col = max(self.engine.board_width - 1, 1)
        return np.array([row / max_row, col / max_col], dtype=np.float32)

    def _encode_action_mask(self) -> np.ndarray:
        """Masque binaire des actions légales (index = row * width + col)."""
        mask = np.zeros(self._action_mask_dims, dtype=np.float32)
        for row, col in self.engine.get_valid_actions():
            mask[row * self.engine.board_width + col] = 1.0
        return mask

    def _get_observation(self) -> np.ndarray:
        """
        Construit l'observation à partir de l'état du jeu.
        
        Returns:
            Tableau numpy représentant l'état
        """
        state = self.engine.get_state()
        board = state.board
        
        # Encoder le plateau avec des canaux séparés pour chaque joueur
        observation = np.zeros(
            (self.engine.board_height, self.engine.board_width, self.engine.num_players),
            dtype=np.float32
        )
        
        for row in range(self.engine.board_height):
            for col in range(self.engine.board_width):
                player = board[row, col]
                if player > 0:
                    observation[row, col, player - 1] = 1.0
        
        board_flat = observation.flatten()
        last_move = self._encode_last_move(state)
        action_mask = self._encode_action_mask()
        return np.concatenate([board_flat, last_move, action_mask])
    
    def reset(self, seed: Optional[int] = None, options: Optional[Dict] = None) -> Tuple[np.ndarray, Dict]:
        """
        Réinitialise l'environnement.
        
        Args:
            seed: Graine aléatoire
            options: Options supplémentaires
        
        Returns:
            Tuple (observation, info)
        """
        super().reset(seed=seed)
        
        self.engine.reset()
        self.current_observation = self._get_observation()
        
        info = {
            "current_player": self.engine.get_current_player(),
            "valid_actions": self.engine.get_valid_actions()
        }
        
        return self.current_observation, info
    
    def step(self, action: int) -> Tuple[np.ndarray, float, bool, bool, Dict]:
        """
        Exécute une action dans l'environnement.
        
        Args:
            action: Action à exécuter (encodé comme row * width + col)
        
        Returns:
            Tuple (observation, reward, terminated, truncated, info)
        """
        # Décoder l'action en (row, col)
        row = action // self.engine.board_width
        col = action % self.engine.board_width
        action_pos = (row, col)
        
        # Vérifier si l'action est valide
        valid_actions = self.engine.get_valid_actions()
        if action_pos not in valid_actions:
            # Action invalide: pénalité et fin de l'épisode
            reward = -10.0
            terminated = True
            truncated = False
            info = {
                "invalid_action": True,
                "valid_actions": valid_actions
            }
            return self.current_observation, reward, terminated, truncated, info
        
        # Exécuter l'action du joueur 1 (l'agent)
        state, success, winner = self.engine.step(action_pos)
        
        if not success:
            reward = -10.0
            terminated = True
            truncated = False
            info = {"action_failed": True}
            return self.current_observation, reward, terminated, truncated, info
        
        # Vérifier si l'agent a gagné
        if winner == 1:
            reward = 10.0
            terminated = True
            truncated = False
            info = {"winner": 1}
            self.current_observation = self._get_observation()
            return self.current_observation, reward, terminated, truncated, info
        
        # Vérifier égalité
        if winner == 0:
            reward = 0.0
            terminated = True
            truncated = False
            info = {"winner": 0}
            self.current_observation = self._get_observation()
            return self.current_observation, reward, terminated, truncated, info
        
        # Si la partie continue, l'adversaire joue
        if self.opponent_type == "random" and not self.engine.is_terminal():
            opponent_action = self._get_opponent_action()
            state, success, winner = self.engine.step(opponent_action)
            
            # Vérifier si l'adversaire a gagné
            if winner == 2:
                reward = -10.0
                terminated = True
                truncated = False
                info = {"winner": 2}
                self.current_observation = self._get_observation()
                return self.current_observation, reward, terminated, truncated, info
            
            # Vérifier égalité après le coup de l'adversaire
            if winner == 0:
                reward = 0.0
                terminated = True
                truncated = False
                info = {"winner": 0}
                self.current_observation = self._get_observation()
                return self.current_observation, reward, terminated, truncated, info
        
        # Partie en cours: calculer une récompense intelligente
        # On passe aussi la position du dernier coup pour détecter les menaces
        reward = self._calculate_smart_reward(state, action_pos)
        terminated = False
        truncated = False
        info = {
            "current_player": self.engine.get_current_player(),
            "valid_actions": self.engine.get_valid_actions()
        }
        
        self.current_observation = self._get_observation()
        return self.current_observation, reward, terminated, truncated, info
    
    def _calculate_smart_reward(self, state, last_action: Tuple[int, int] = None) -> float:
        """
        Calcule une récompense intelligente basée sur la position.
        Encourage les bonnes stratégies :
        - Créer des alignements (2, 3 pièces)
        - Bloquer les alignements de l'adversaire
        - Éviter de créer des opportunités de victoire pour l'adversaire
        - Se positionner stratégiquement
        """
        reward = 0.0
        board = state.board
        player = 1  # L'agent est toujours le joueur 1
        opponent = 2
        
        # Analyser les alignements du joueur et de l'adversaire
        my_alignments = self._count_alignments(board, player)
        opponent_alignments = self._count_alignments(board, opponent)
        
        # Récompenser les alignements du joueur
        reward += my_alignments[2] * 1   # 2 pièces alignées = +0.1
        reward += my_alignments[3] * 4   # 3 pièces alignées = +0.5 (menace de victoire)
        reward += my_alignments[4] * 50   # 4 pièces alignées = +1.0 (victoire)
        
        # Récompenser le blocage des alignements adverses
        reward += opponent_alignments[2] * 2  # Bloquer 2 pièces = +0.05
        reward += opponent_alignments[3] * 5  # Bloquer 3 pièces = +0.3 (empêcher la défaite)
        reward += opponent_alignments[4] * 15  # Bloquer 4 pièces = +0.5 (empêcher la victoire)
        # Récompenser les positions centrales (plus stratégiques)
        center_bonus = self._calculate_center_bonus(board, player)
        reward += center_bonus * 0.02
        
        # Pénaliser les positions isolées (moins stratégiques)
        isolation_penalty = self._calculate_isolation_penalty(board, player)
        reward -= isolation_penalty * 0.01
        
        # Pénalité de -0.02 à chaque coup joué (encourage les parties rapides)
        reward -= 0.02
        
        return reward
    
    def _count_alignments(self, board: np.ndarray, player: int) -> dict:
        """
        Compte les alignements de différentes longueurs pour un joueur.
        
        Returns:
            Dict avec clés 2, 3, 4 (longueur d'alignement) et valeurs (nombre d'alignements)
        """
        alignments = {2: 0, 3: 0, 4: 0}
        height, width = board.shape
        
        # Directions à vérifier
        directions = [(0, 1), (1, 0), (1, 1), (1, -1)]
        
        for row in range(height):
            for col in range(width):
                if board[row, col] != player:
                    continue
                
                for dr, dc in directions:
                    # Compter les pièces alignées dans cette direction
                    count = 1
                    for step in [1, -1]:
                        r, c = row, col
                        for _ in range(3):  # Maximum 3 dans chaque direction
                            r += dr * step
                            c += dc * step
                            if (0 <= r < height and 0 <= c < width and 
                                board[r, c] == player):
                                count += 1
                            else:
                                break
                    
                    # Enregistrer l'alignement (on compte chaque direction une fois)
                    if count >= 2:
                        # On compte seulement depuis la première pièce pour éviter les doublons
                        if step == 1:  # Seulement dans une direction pour éviter les doublons
                            if count >= 4:
                                alignments[4] += 1
                            elif count >= 3:
                                alignments[3] += 1
                            elif count >= 2:
                                alignments[2] += 1
        
        return alignments
    
    def _calculate_center_bonus(self, board: np.ndarray, player: int) -> float:
        """
        Récompense les positions proches du centre du plateau.
        """
        height, width = board.shape
        center_row = height // 2
        center_col = width // 2
        bonus = 0.0
        
        for row in range(height):
            for col in range(width):
                if board[row, col] == player:
                    # Distance au centre (plus proche = plus de bonus)
                    dist_row = abs(row - center_row)
                    dist_col = abs(col - center_col)
                    dist = (dist_row + dist_col) / (height + width)
                    bonus += (1.0 - dist)  # Plus proche = plus de bonus
        
        return bonus
    
    def _calculate_isolation_penalty(self, board: np.ndarray, player: int) -> float:
        """
        Pénalise les pièces isolées (sans voisins).
        """
        height, width = board.shape
        isolated = 0
        
        for row in range(height):
            for col in range(width):
                if board[row, col] != player:
                    continue
                
                # Vérifier les 8 voisins
                has_neighbor = False
                for dr in [-1, 0, 1]:
                    for dc in [-1, 0, 1]:
                        if dr == 0 and dc == 0:
                            continue
                        r, c = row + dr, col + dc
                        if (0 <= r < height and 0 <= c < width and 
                            board[r, c] == player):
                            has_neighbor = True
                            break
                    if has_neighbor:
                        break
                
                if not has_neighbor:
                    isolated += 1
        
        return isolated
    
    def _calculate_threat_penalty(self, board: np.ndarray, last_action: Tuple[int, int], 
                                   player: int, opponent: int) -> float:
        """
        Calcule une pénalité si le dernier coup crée une opportunité de victoire pour l'adversaire.
        
        Détecte si le dernier coup est adjacent à une case où l'adversaire pourrait gagner
        (3 pièces alignées avec une case vide pour compléter).
        
        Returns:
            Pénalité (plus élevée = plus dangereux)
        """
        penalty = 0.0
        last_row, last_col = last_action
        height, width = board.shape
        win_length = self.engine.win_length
        
        # Vérifier les 8 cases adjacentes au dernier coup
        for dr in [-1, 0, 1]:
            for dc in [-1, 0, 1]:
                if dr == 0 and dc == 0:
                    continue
                adj_row = last_row + dr
                adj_col = last_col + dc
                
                # Vérifier que la case adjacente est dans les limites et vide
                if not (0 <= adj_row < height and 0 <= adj_col < width):
                    continue
                if board[adj_row, adj_col] != 0:
                    continue
                
                # Simuler un coup de l'adversaire sur cette case adjacente
                # et vérifier si cela créerait une menace de victoire
                threat_score = self._check_threat_at_position(board, adj_row, adj_col, opponent, win_length)
                if threat_score > 0:
                    # Pénalité proportionnelle à la menace
                    # Si l'adversaire peut gagner en jouant là, pénalité très forte
                    penalty += threat_score * 2.0
        
        return penalty
    
    def _check_threat_at_position(self, board: np.ndarray, row: int, col: int, 
                                   player: int, win_length: int) -> float:
        """
        Vérifie si jouer à la position (row, col) créerait une menace de victoire pour le joueur.
        
        Returns:
            Score de menace (0 = pas de menace, >0 = menace détectée)
        """
        height, width = board.shape
        directions = [(0, 1), (1, 0), (1, 1), (1, -1)]
        max_threat = 0.0
        
        for dr, dc in directions:
            # Compter les pièces alignées dans cette direction
            count = 1  # La pièce qu'on placerait
            empty_spaces = 0
            
            # Vérifier dans les deux directions
            for step in [1, -1]:
                r, c = row, col
                for _ in range(win_length - 1):
                    r += dr * step
                    c += dc * step
                    
                    if (0 <= r < height and 0 <= c < width):
                        if board[r, c] == player:
                            count += 1
                        elif board[r, c] == 0:
                            empty_spaces += 1
                        else:
                            break
                    else:
                        break
            
            # Si on a presque assez de pièces pour gagner
            if count >= win_length - 1 and empty_spaces > 0:
                # Menace critique : l'adversaire peut gagner au prochain coup
                threat_level = count / win_length
                max_threat = max(max_threat, threat_level)
        
        return max_threat
    
    def _get_opponent_action(self):
        """
        Obtient l'action de l'adversaire.
        
        Returns:
            Action de l'adversaire (row, col)
        """
        valid_actions = self.engine.get_valid_actions()
        if not valid_actions:
            return (0, 0)  # Action par défaut
        
        if self.opponent_type == "random":
            return self.np_random.choice(valid_actions)
        else:
            # Par défaut, action aléatoire
            return self.np_random.choice(valid_actions)
    
    def render(self):
        """
        Affiche l'état actuel du jeu.
        """
        if self.render_mode == "human":
            print(self.engine.get_state())
        elif self.render_mode == "rgb_array":
            # Pour l'instant, retourner None
            # On pourrait implémenter un rendu graphique ici
            return None

