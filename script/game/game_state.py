"""
Représentation de l'état du jeu 4mation
"""

import numpy as np
from typing import Optional, Tuple
from copy import deepcopy


class GameState:
    """
    Représente l'état actuel du jeu.
    
    Le plateau est représenté comme une matrice numpy où:
    - 0 = case vide
    - 1 = pièce du joueur 1
    - 2 = pièce du joueur 2
    """
    
    def __init__(self, board_width: int = 7, board_height: int = 7, num_players: int = 2):
        """
        Initialise un nouvel état de jeu.
        
        Args:
            board_width: Largeur du plateau
            board_height: Hauteur du plateau
            num_players: Nombre de joueurs
        """
        self.board_width = board_width
        self.board_height = board_height
        self.num_players = num_players
        
        # Plateau de jeu (board_height x board_width)
        # 0 = vide, 1 = joueur 1, 2 = joueur 2, etc.
        self.board = np.zeros((board_height, board_width), dtype=np.int8)
        
        # Joueur actuel (1-indexed)
        self.current_player = 1
        
        # Historique des actions (liste de tuples (player, row, col))
        self.action_history = []
        
        # Position du dernier coup joué (pour déterminer les cases adjacentes valides)
        self.last_move_position = None  # (row, col) ou None si aucun coup joué
        
        # État de fin de partie
        self.is_terminal = False
        self.winner = None  # None, 1, 2, ou 0 pour égalité
        
        # Compteur de coups
        self.move_count = 0
    
    def copy(self) -> 'GameState':
        """
        Crée une copie profonde de l'état actuel.
        
        Returns:
            Nouvelle instance de GameState identique à l'actuelle
        """
        new_state = GameState(self.board_width, self.board_height, self.num_players)
        new_state.board = self.board.copy()
        new_state.current_player = self.current_player
        new_state.action_history = self.action_history.copy()
        new_state.last_move_position = self.last_move_position
        new_state.is_terminal = self.is_terminal
        new_state.winner = self.winner
        new_state.move_count = self.move_count
        return new_state
    
    def get_valid_actions(self) -> list:
        """
        Retourne la liste des actions valides (positions où on peut jouer).
        
        Pour le premier coup : toutes les cases vides
        Pour les coups suivants :
        1. Les 8 cases adjacentes à la dernière position jouée (si vides)
        2. Si toutes les cases adjacentes au dernier coup sont pleines,
           alors toutes les cases vides adjacentes à une case de l'adversaire
        
        Returns:
            Liste des positions valides (row, col)
        """
        valid_actions = []
        opponent = 2 if self.current_player == 1 else 1
        
        # Premier coup : toutes les cases vides
        if self.last_move_position is None:
            for row in range(self.board_height):
                for col in range(self.board_width):
                    if self.board[row, col] == 0:
                        valid_actions.append((row, col))
        else:
            # Coups suivants : d'abord les 8 cases adjacentes à la dernière position
            last_row, last_col = self.last_move_position
            adjacent_to_last = []
            all_adjacent_full = True
            
            for dr in [-1, 0, 1]:
                for dc in [-1, 0, 1]:
                    if dr == 0 and dc == 0:
                        continue  # Skip la case elle-même
                    row = last_row + dr
                    col = last_col + dc
                    # Vérifier que la case est dans les limites
                    if (0 <= row < self.board_height and 
                        0 <= col < self.board_width):
                        if self.board[row, col] == 0:
                            # Case vide adjacente au dernier coup
                            adjacent_to_last.append((row, col))
                            all_adjacent_full = False
            
            # Si on a trouvé des cases vides adjacentes au dernier coup, les utiliser
            if adjacent_to_last:
                valid_actions = adjacent_to_last
            else:
                # Toutes les cases adjacentes au dernier coup sont pleines
                # On peut jouer sur n'importe quelle case vide adjacente à l'adversaire
                for row in range(self.board_height):
                    for col in range(self.board_width):
                        # La case doit être vide
                        if self.board[row, col] != 0:
                            continue
                        
                        # Vérifier si cette case est adjacente à au moins une case de l'adversaire
                        has_adjacent_opponent = False
                        for dr in [-1, 0, 1]:
                            for dc in [-1, 0, 1]:
                                if dr == 0 and dc == 0:
                                    continue  # Skip la case elle-même
                                r = row + dr
                                c = col + dc
                                # Vérifier que la case adjacente est dans les limites
                                if (0 <= r < self.board_height and 
                                    0 <= c < self.board_width and 
                                    self.board[r, c] == opponent):
                                    has_adjacent_opponent = True
                                    break
                            if has_adjacent_opponent:
                                break
                        
                        if has_adjacent_opponent:
                            valid_actions.append((row, col))
        
        return valid_actions
    
    def get_observation(self) -> np.ndarray:
        """
        Retourne une représentation de l'état pour l'IA.
        
        Returns:
            Tableau numpy représentant l'état du jeu
        """
        # Retourne le plateau comme observation
        # On peut aussi ajouter des informations supplémentaires
        return self.board.flatten().astype(np.float32)
    
    def __str__(self) -> str:
        """Représentation textuelle de l'état"""
        lines = []
        lines.append("État du jeu:")
        lines.append(f"Joueur actuel: {self.current_player}")
        lines.append(f"Coup #{self.move_count}")
        lines.append("Plateau:")
        
        # Afficher le plateau (inversé pour avoir le bas en bas)
        for row in range(self.board_height):
            row_str = "|"
            for col in range(self.board_width):
                cell = self.board[row, col]
                if cell == 0:
                    row_str += " . "
                else:
                    row_str += f" {cell} "
            row_str += "|"
            lines.append(row_str)
        
        # Ligne de numéros de colonnes
        col_nums = "  "
        for col in range(self.board_width):
            col_nums += f" {col} "
        lines.append(col_nums)
        
        if self.is_terminal:
            if self.winner:
                lines.append(f"Partie terminée! Gagnant: Joueur {self.winner}")
            else:
                lines.append("Partie terminée! Égalité")
        
        return "\n".join(lines)

