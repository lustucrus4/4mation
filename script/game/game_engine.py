"""
Moteur principal du jeu 4mation
"""

from typing import Dict, Optional, List, Tuple
from .game_state import GameState
from .game_logic import GameLogic


class GameEngine:
    """
    Orchestre le jeu 4mation.
    Gère le tour par tour et l'historique des actions.
    """
    
    def __init__(self, board_width: int = 7, board_height: int = 7, 
                 num_players: int = 2, win_length: int = 4):
        """
        Initialise le moteur de jeu.
        
        Args:
            board_width: Largeur du plateau
            board_height: Hauteur du plateau
            num_players: Nombre de joueurs
            win_length: Nombre de pièces à aligner pour gagner
        """
        self.board_width = board_width
        self.board_height = board_height
        self.num_players = num_players
        self.win_length = win_length
        
        self.logic = GameLogic(board_width, board_height, win_length)
        self.state = GameState(board_width, board_height, num_players)
        self.history = []
    
    def reset(self) -> GameState:
        """
        Réinitialise le jeu à un état initial.
        
        Returns:
            Nouvel état de jeu
        """
        self.state = GameState(self.board_width, self.board_height, self.num_players)
        self.history = []
        return self.state
    
    def step(self, action) -> Tuple[GameState, bool, Optional[int]]:
        """
        Exécute une action dans le jeu.
        
        Args:
            action: Position (row, col) ou tuple (row, col)
        
        Returns:
            Tuple (nouvel état, action_valide, gagnant)
            - nouvel état: État du jeu après l'action
            - action_valide: True si l'action a été appliquée
            - gagnant: Numéro du joueur gagnant (ou None)
        """
        if self.state.is_terminal:
            return self.state, False, self.state.winner
        
        # Sauvegarder l'état avant l'action
        prev_state = self.state.copy()
        
        # Appliquer l'action
        success = self.logic.apply_action(self.state, action)
        
        if success:
            self.history.append({
                'player': prev_state.current_player,
                'action': action,
                'state_before': prev_state,
                'state_after': self.state.copy()
            })
        
        winner = self.state.winner if self.state.is_terminal else None
        
        return self.state, success, winner
    
    def get_current_player(self) -> int:
        """
        Retourne le numéro du joueur actuel.
        
        Returns:
            Numéro du joueur (1-indexed)
        """
        return self.state.current_player
    
    def get_valid_actions(self) -> List:
        """
        Retourne la liste des actions valides.
        
        Returns:
            Liste des positions valides (row, col)
        """
        return self.logic.get_valid_actions(self.state)
    
    def is_terminal(self) -> bool:
        """
        Vérifie si la partie est terminée.
        
        Returns:
            True si la partie est terminée, False sinon
        """
        return self.state.is_terminal
    
    def get_winner(self) -> Optional[int]:
        """
        Retourne le gagnant de la partie.
        
        Returns:
            Numéro du joueur gagnant, 0 pour égalité, ou None si pas terminé
        """
        return self.state.winner
    
    def get_state(self) -> GameState:
        """
        Retourne l'état actuel du jeu.
        
        Returns:
            État actuel du jeu
        """
        return self.state

    def undo(self, count: int = 1) -> bool:
        """Annule les `count` derniers coups."""
        if count < 1 or count > len(self.history):
            return False
        for _ in range(count):
            self.history.pop()
        if self.history:
            self.state = self.history[-1]["state_after"].copy()
        else:
            self.reset()
        return True

    def undo_to(self, move_index: int) -> bool:
        """
        Revient à l'état après `move_index` coups joués (0 = début de partie).
        """
        if move_index < 0 or move_index > len(self.history):
            return False
        while len(self.history) > move_index:
            self.history.pop()
        if move_index == 0:
            self.reset()
        else:
            self.state = self.history[move_index - 1]["state_after"].copy()
        return True

    def get_move_history(self) -> List[Dict]:
        """Historique des coups pour la timeline frontend."""
        return [
            {
                "index": i + 1,
                "player": int(entry["player"]),
                "row": int(entry["action"][0]),
                "col": int(entry["action"][1]),
            }
            for i, entry in enumerate(self.history)
        ]

    def to_snapshot(self) -> Dict:
        """Sérialise l'état du moteur pour persistance."""
        state = self.state
        last = state.last_move_position
        return {
            "board": state.board.tolist(),
            "current_player": int(state.current_player),
            "action_history": [
                [int(p), int(r), int(c)] for p, r, c in state.action_history
            ],
            "last_move_position": [int(last[0]), int(last[1])] if last else None,
            "is_terminal": bool(state.is_terminal),
            "winner": int(state.winner) if state.winner is not None else None,
            "move_count": int(state.move_count),
            "history": [
                {"player": int(e["player"]), "action": [int(e["action"][0]), int(e["action"][1])]}
                for e in self.history
            ],
        }

    @classmethod
    def from_snapshot(cls, data: Dict) -> "GameEngine":
        """Restaure un moteur depuis un snapshot."""
        engine = cls()
        engine.reset()
        for entry in data.get("history", []):
            action = tuple(entry["action"])
            engine.step(action)
        return engine

