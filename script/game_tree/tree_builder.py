"""
Construction de l'arbre de jeu pour les N premiers coups
"""

import numpy as np
from typing import Dict, List, Tuple, Optional
from collections import deque
import hashlib

try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False
    # Fallback si tqdm n'est pas disponible
    class tqdm:
        def __init__(self, *args, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def update(self, n=1):
            pass
        def set_postfix(self, **kwargs):
            pass

from game.game_state import GameState
from game.game_logic import GameLogic


class GameTreeBuilder:
    """
    Construit l'arbre de jeu en explorant toutes les positions possibles
    jusqu'à un nombre maximum de coups.
    """
    
    def __init__(self, max_moves: int = 8, board_width: int = 7, board_height: int = 7):
        self.max_moves = max_moves
        self.board_width = board_width
        self.board_height = board_height
        self.logic = GameLogic(board_width, board_height, win_length=4)
        
        # Table de transposition pour éviter les doublons
        self.transposition_table: Dict[str, str] = {}
        
        # Structure de l'arbre : {node_id: node_data}
        self.tree: Dict[str, dict] = {}
        
    def board_to_hash(self, board: np.ndarray, current_player: int, move_count: int) -> str:
        """
        Crée un hash unique pour une position.
        
        Args:
            board: Plateau de jeu
            current_player: Joueur actuel
            move_count: Nombre de coups joués
        
        Returns:
            Hash string unique
        """
        # Inclure le plateau, le joueur actuel et le nombre de coups
        data = board.tobytes() + bytes([current_player, move_count])
        return hashlib.md5(data).hexdigest()
    
    def build_tree(self) -> Dict[str, dict]:
        """
        Construit l'arbre de jeu complet.
        
        Returns:
            Dictionnaire contenant tous les nœuds de l'arbre
        """
        print(f"🌳 Construction de l'arbre de jeu pour les {self.max_moves} premiers coups...")
        print("⚠️  Cela peut prendre du temps selon votre CPU")
        print()
        
        # État initial
        initial_state = GameState(self.board_width, self.board_height, num_players=2)
        root_id = self.board_to_hash(
            initial_state.board, 
            initial_state.current_player, 
            initial_state.move_count
        )
        
        # Queue pour exploration BFS
        queue = deque([(initial_state, root_id, None, None)])  # (state, node_id, parent_id, action)
        self.transposition_table[root_id] = root_id
        
        nodes_processed = 0
        total_nodes = 0
        
        # Progress bar
        with tqdm(desc="Exploration de l'arbre", unit=" nœuds") as pbar:
            while queue:
                state, node_id, parent_id, action = queue.popleft()
                
                # Vérifier si on a déjà traité ce nœud
                if node_id in self.tree:
                    continue
                
                # Créer le nœud
                node_data = {
                    'node_id': node_id,
                    'board': state.board.copy(),
                    'move_count': state.move_count,
                    'current_player': state.current_player,
                    'is_terminal': state.is_terminal,
                    'winner': state.winner,
                    'last_move': action,  # Coup qui a mené à cette position
                    'parent_id': parent_id,
                    'children': []
                }
                
                # Si la partie est terminée ou on a atteint max_moves, pas d'enfants
                if state.is_terminal or state.move_count >= self.max_moves:
                    self.tree[node_id] = node_data
                    nodes_processed += 1
                    pbar.update(1)
                    continue
                
                # Explorer tous les coups possibles
                valid_actions = state.get_valid_actions()
                
                for action in valid_actions:
                    # Créer un nouvel état pour ce coup
                    new_state = state.copy()
                    if self.logic.apply_action(new_state, action):
                        # Créer l'ID pour ce nouvel état
                        child_id = self.board_to_hash(
                            new_state.board,
                            new_state.current_player,
                            new_state.move_count
                        )
                        
                        # Vérifier si on a déjà vu cette position
                        if child_id not in self.transposition_table:
                            self.transposition_table[child_id] = child_id
                            queue.append((new_state, child_id, node_id, action))
                            total_nodes += 1
                        
                        # Ajouter l'enfant au nœud
                        node_data['children'].append({
                            'action': action,
                            'node_id': child_id
                        })
                
                self.tree[node_id] = node_data
                nodes_processed += 1
                pbar.update(1)
                
                # Mettre à jour la barre de progression avec le total estimé
                if total_nodes > 0:
                    pbar.set_postfix({
                        'traité': nodes_processed,
                        'queue': len(queue)
                    })
        
        print(f"\n✅ Arbre construit : {len(self.tree)} nœuds uniques")
        return self.tree
    
    def get_tree_stats(self) -> dict:
        """
        Retourne des statistiques sur l'arbre construit.
        
        Returns:
            Dictionnaire avec les statistiques
        """
        stats = {
            'total_nodes': len(self.tree),
            'terminal_nodes': 0,
            'ongoing_nodes': 0,
            'winning_nodes_p1': 0,
            'winning_nodes_p2': 0,
            'draw_nodes': 0,
            'max_children': 0,
            'avg_children': 0
        }
        
        total_children = 0
        for node in self.tree.values():
            if node['is_terminal']:
                stats['terminal_nodes'] += 1
                if node['winner'] == 1:
                    stats['winning_nodes_p1'] += 1
                elif node['winner'] == 2:
                    stats['winning_nodes_p2'] += 1
                elif node['winner'] == 0:
                    stats['draw_nodes'] += 1
            else:
                stats['ongoing_nodes'] += 1
            
            num_children = len(node['children'])
            total_children += num_children
            stats['max_children'] = max(stats['max_children'], num_children)
        
        if len(self.tree) > 0:
            stats['avg_children'] = total_children / len(self.tree)
        
        return stats

