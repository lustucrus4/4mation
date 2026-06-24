"""
Logique et règles du jeu 4mation
"""

import numpy as np
from typing import Optional, Tuple, List
from .game_state import GameState


class GameLogic:
    """
    Implémente les règles et la logique du jeu 4mation.
    
    Note: Les règles sont actuellement basées sur un style Connect 4.
    Adaptez cette classe selon les règles spécifiques de 4mation.
    """
    
    def __init__(self, board_width: int = 7, board_height: int = 7, win_length: int = 4):
        """
        Initialise la logique du jeu.
        
        Args:
            board_width: Largeur du plateau
            board_height: Hauteur du plateau
            win_length: Nombre de pièces à aligner pour gagner
        """
        self.board_width = board_width
        self.board_height = board_height
        self.win_length = win_length
    
    def is_valid_action(self, state: GameState, action) -> bool:
        """
        Vérifie si une action est valide.
        
        Args:
            state: État actuel du jeu
            action: Position (row, col) ou tuple (row, col)
        
        Returns:
            True si l'action est valide, False sinon
        """
        # Convertir l'action en (row, col) si nécessaire
        if isinstance(action, int):
            # Compatibilité avec l'ancien format (colonne)
            # Pour le premier coup, on peut accepter une colonne
            if state.last_move_position is None:
                col = action
                # Trouver la première case vide dans la colonne
                for row in range(self.board_height):
                    if state.board[row, col] == 0:
                        action = (row, col)
                        break
                else:
                    return False
            else:
                return False
        elif not isinstance(action, tuple) or len(action) != 2:
            return False
        
        row, col = action
        
        # Vérifier que la position est dans les limites
        if not (0 <= row < self.board_height and 0 <= col < self.board_width):
            return False
        
        # Vérifier que la case est vide
        if state.board[row, col] != 0:
            return False
        
        # Premier coup : n'importe quelle case vide est valide
        if state.last_move_position is None:
            return True
        
        # Coups suivants : vérifier d'abord les cases adjacentes au dernier coup
        last_row, last_col = state.last_move_position
        dr = abs(row - last_row)
        dc = abs(col - last_col)
        is_adjacent_to_last = dr <= 1 and dc <= 1 and (dr > 0 or dc > 0)
        
        if is_adjacent_to_last:
            # Si c'est adjacent au dernier coup et vide, c'est valide
            return True
        
        # Si ce n'est pas adjacent au dernier coup, vérifier si toutes les cases
        # adjacentes au dernier coup sont pleines
        all_adjacent_full = True
        for dr in [-1, 0, 1]:
            for dc in [-1, 0, 1]:
                if dr == 0 and dc == 0:
                    continue
                r = last_row + dr
                c = last_col + dc
                if (0 <= r < self.board_height and 
                    0 <= c < self.board_width and 
                    state.board[r, c] == 0):
                    all_adjacent_full = False
                    break
            if not all_adjacent_full:
                break
        
        # Si toutes les cases adjacentes au dernier coup sont pleines,
        # on peut jouer sur une case adjacente à l'adversaire
        if all_adjacent_full:
            opponent = 2 if state.current_player == 1 else 1
            # Vérifier si cette case est adjacente à au moins une case de l'adversaire
            for dr in [-1, 0, 1]:
                for dc in [-1, 0, 1]:
                    if dr == 0 and dc == 0:
                        continue
                    r = row + dr
                    c = col + dc
                    if (0 <= r < self.board_height and 
                        0 <= c < self.board_width and 
                        state.board[r, c] == opponent):
                        return True
        
        return False
    
    def apply_action(self, state: GameState, action) -> bool:
        """
        Applique une action au jeu (place une pièce à une position).
        
        Args:
            state: État du jeu à modifier
            action: Position (row, col) ou tuple (row, col)
        
        Returns:
            True si l'action a été appliquée avec succès, False sinon
        """
        if not self.is_valid_action(state, action):
            return False
        
        # Convertir l'action en (row, col) si nécessaire
        if isinstance(action, int):
            # Compatibilité avec l'ancien format (colonne) pour le premier coup
            if state.last_move_position is None:
                col = action
                # Trouver la première case vide dans la colonne
                for row in range(self.board_height):
                    if state.board[row, col] == 0:
                        action = (row, col)
                        break
                else:
                    return False
            else:
                return False
        
        row, col = action
        
        # Placer la pièce
        state.board[row, col] = state.current_player
        state.action_history.append((state.current_player, row, col))
        state.last_move_position = (row, col)
        state.move_count += 1
        
        # Vérifier si la partie est terminée
        winner = self.check_winner(state, row, col)
        if winner:
            state.is_terminal = True
            state.winner = winner
        elif self.is_board_full(state):
            state.is_terminal = True
            state.winner = 0  # Égalité
        
        # Passer au joueur suivant
        if not state.is_terminal:
            state.current_player = (state.current_player % state.num_players) + 1
        
        return True
    
    def check_winner(self, state: GameState, row: int, col: int) -> Optional[int]:
        """
        Vérifie si le dernier coup a créé un alignement gagnant.
        
        Args:
            state: État du jeu
            row: Ligne où la pièce a été placée
            col: Colonne où la pièce a été placée
        
        Returns:
            Numéro du joueur gagnant, ou None si personne n'a gagné
        """
        player = state.board[row, col]
        
        # Directions à vérifier: horizontal, vertical, diagonales
        directions = [
            (0, 1),   # horizontal
            (1, 0),   # vertical
            (1, 1),   # diagonale \
            (1, -1)   # diagonale /
        ]
        
        for dr, dc in directions:
            count = 1  # Compter la pièce qu'on vient de placer
            
            # Vérifier dans une direction
            for step in [1, -1]:
                r, c = row, col
                for _ in range(self.win_length - 1):
                    r += dr * step
                    c += dc * step
                    
                    if (0 <= r < self.board_height and 
                        0 <= c < self.board_width and 
                        state.board[r, c] == player):
                        count += 1
                    else:
                        break
            
            if count >= self.win_length:
                return player
        
        return None
    
    def is_board_full(self, state: GameState) -> bool:
        """
        Vérifie si le plateau est plein (égalité).
        
        Args:
            state: État du jeu
        
        Returns:
            True si le plateau est plein, False sinon
        """
        return np.all(state.board != 0)
    
    def get_valid_actions(self, state: GameState) -> List[int]:
        """
        Retourne la liste des actions valides.
        
        Args:
            state: État du jeu
        
        Returns:
            Liste des indices de colonnes valides
        """
        return state.get_valid_actions()
    
    def calculate_reward(self, state: GameState, player: int) -> float:
        """
        Calcule la récompense pour un joueur donné.
        
        Args:
            state: État du jeu
            player: Numéro du joueur (1-indexed)
        
        Returns:
            Récompense (positive pour victoire, négative pour défaite, 0 sinon)
        """
        if not state.is_terminal:
            return 0.0
        
        if state.winner == 0:  # Égalité
            return 0.0
        elif state.winner == player:  # Victoire
            return 1.0
        else:  # Défaite
            return -1.0

