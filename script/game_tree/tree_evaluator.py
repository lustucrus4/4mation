"""
Évaluation et classification des positions de l'arbre de jeu
"""

import numpy as np
from typing import Dict, Optional, Tuple
from multiprocessing import Pool, cpu_count
from functools import partial

# Détection GPU
try:
    import torch
    HAS_TORCH = True
    if torch.cuda.is_available():
        HAS_CUDA = True
        DEVICE = torch.device("cuda")
    else:
        HAS_CUDA = False
        DEVICE = torch.device("cpu")
except ImportError:
    HAS_TORCH = False
    HAS_CUDA = False
    DEVICE = None

try:
    import torch
    HAS_TORCH = True
    if torch.cuda.is_available():
        DEVICE = torch.device("cuda")
        HAS_CUDA = True
    else:
        DEVICE = torch.device("cpu")
        HAS_CUDA = False
except ImportError:
    HAS_TORCH = False
    HAS_CUDA = False
    DEVICE = None

try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False
    # Fallback si tqdm n'est pas disponible
    class tqdm:
        def __init__(self, *args, **kwargs):
            self.total = kwargs.get('total', 0)
            self.n = 0
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def update(self, n=1):
            self.n += n
            if self.total > 0 and self.n % max(1, self.total // 100) == 0:
                print(f"Progression: {self.n}/{self.total} ({100*self.n//self.total}%)")
        def set_postfix(self, **kwargs):
            pass

from game.game_state import GameState
from game.game_logic import GameLogic


# Fonctions standalone pour la parallélisation (doivent être au niveau module)
def _count_alignments_standalone(board: np.ndarray, player: int) -> dict:
    """Compte les alignements (version standalone pour multiprocessing)"""
    alignments = {2: 0, 3: 0, 4: 0}
    height, width = board.shape
    directions = [(0, 1), (1, 0), (1, 1), (1, -1)]
    
    for row in range(height):
        for col in range(width):
            if board[row, col] != player:
                continue
            
            for dr, dc in directions:
                count = 1
                for step in [1, -1]:
                    r, c = row, col
                    for _ in range(3):
                        r += dr * step
                        c += dc * step
                        if (0 <= r < height and 0 <= c < width and 
                            board[r, c] == player):
                            count += 1
                        else:
                            break
                
                if count >= 2:
                    if step == 1:  # Éviter les doublons
                        if count >= 4:
                            alignments[4] += 1
                        elif count >= 3:
                            alignments[3] += 1
                        elif count >= 2:
                            alignments[2] += 1
    
    return alignments


def _evaluate_heuristic_standalone(state: GameState) -> float:
    """Évaluation heuristique standalone"""
    board = state.board
    player = 1
    opponent = 2
    
    score = 0.0
    
    # Compter les alignements
    my_alignments = _count_alignments_standalone(board, player)
    opp_alignments = _count_alignments_standalone(board, opponent)
    
    # Bonus pour alignements
    score += my_alignments[2] * 0.1
    score += my_alignments[3] * 0.3
    score += my_alignments[4] * 1.0
    
    # Pénalité pour alignements adverses
    score -= opp_alignments[2] * 0.1
    score -= opp_alignments[3] * 0.3
    score -= opp_alignments[4] * 1.0
    
    # Normaliser entre -1 et 1
    score = max(-1.0, min(1.0, score / 10.0))
    
    return score


def _minimax_evaluate_standalone(state: GameState, logic: GameLogic, 
                                 depth: int, alpha: float, beta: float,
                                 maximizing: bool, player: int) -> float:
    """Minimax standalone pour multiprocessing"""
    if state.is_terminal or depth == 0:
        if state.is_terminal:
            if state.winner == player:
                return 1.0
            elif state.winner == 0:
                return 0.0
            else:
                return -1.0
        else:
            return _evaluate_heuristic_standalone(state)
    
    valid_actions = state.get_valid_actions()
    if not valid_actions:
        return _evaluate_heuristic_standalone(state)
    
    if maximizing:
        max_eval = float('-inf')
        for action in valid_actions:
            new_state = state.copy()
            if logic.apply_action(new_state, action):
                eval_score = _minimax_evaluate_standalone(
                    new_state, logic, depth - 1, alpha, beta, False, player
                )
                max_eval = max(max_eval, eval_score)
                alpha = max(alpha, eval_score)
                if beta <= alpha:
                    break
        return max_eval
    else:
        min_eval = float('inf')
        for action in valid_actions:
            new_state = state.copy()
            if logic.apply_action(new_state, action):
                eval_score = _minimax_evaluate_standalone(
                    new_state, logic, depth - 1, alpha, beta, True, player
                )
                min_eval = min(min_eval, eval_score)
                beta = min(beta, eval_score)
                if beta <= alpha:
                    break
        return min_eval


def _evaluate_single_node_worker(args):
    """
    Fonction worker pour évaluer un nœud (doit être au niveau module pour multiprocessing).
    
    Args:
        args: Tuple (node_id, node_data, board_width, board_height)
    
    Returns:
        Tuple (node_id, node_data_with_evaluation, stats)
    """
    node_id, node_data, board_width, board_height = args
    
    # Créer un GameState à partir des données du nœud
    state = GameState(board_width, board_height)
    state.board = node_data['board'].copy()
    state.current_player = node_data['current_player']
    state.move_count = node_data['move_count']
    state.is_terminal = node_data['is_terminal']
    state.winner = node_data['winner']
    
    # Créer une instance locale de GameLogic pour ce processus
    logic = GameLogic(board_width, board_height, win_length=4)
    
    # Évaluer la position
    stats = {'terminal': 0, 'heuristic': 0, 'minimax': 0}
    
    if state.is_terminal:
        # Partie terminée : score clair
        stats['terminal'] = 1
        if state.winner == 1:
            evaluation = 1.0
        elif state.winner == 2:
            evaluation = -1.0
        else:
            evaluation = 0.0
    else:
        # Partie en cours : utiliser minimax limité ou heuristique
        if node_data['move_count'] >= 6:  # Proche de la fin
            # Utiliser minimax avec profondeur limitée
            stats['minimax'] = 1
            evaluation = _minimax_evaluate_standalone(
                state, logic, depth=5, 
                alpha=float('-inf'), 
                beta=float('inf'),
                maximizing=(state.current_player == 1),
                player=1
            )
        else:
            # Utiliser heuristique simple
            stats['heuristic'] = 1
            evaluation = _evaluate_heuristic_standalone(state)
    
    # Copier le nœud avec l'évaluation
    new_node = node_data.copy()
    new_node['evaluation'] = evaluation
    
    return (node_id, new_node, stats)


class TreeEvaluator:
    """
    Évalue les positions de l'arbre et classe les branches
    comme gagnantes, perdantes, ou en cours.
    """
    
    def __init__(self, board_width: int = 7, board_height: int = 7, num_workers: int = None, 
                 use_gpu: bool = True, silent: bool = False):
        self.board_width = board_width
        self.board_height = board_height
        self.logic = GameLogic(board_width, board_height, win_length=4)
        # Utiliser tous les cœurs disponibles par défaut, ou le nombre spécifié
        if num_workers is None:
            self.num_workers = cpu_count()
        else:
            self.num_workers = num_workers
        
        # Configuration GPU (pour les évaluations heuristiques batchées)
        self.use_gpu = use_gpu and HAS_CUDA
        if self.use_gpu:
            self.device = DEVICE
            if not silent:
                print(f"GPU detecte: {torch.cuda.get_device_name(0)}")
                print(f"   Note: Le GPU sera utilise pour les evaluations heuristiques batchées")
                print(f"   Le minimax reste sur CPU (sequentiel)")
                print(f"Parallellisation CPU: {self.num_workers} processus + GPU")
        else:
            self.device = None
            if not silent:
                if use_gpu and not HAS_CUDA:
                    print(f"GPU demande mais non disponible (PyTorch sans CUDA)")
                print(f"Parallellisation CPU: {self.num_workers} processus")
    
    def evaluate_position(self, state: GameState, player: int = 1) -> float:
        """
        Évalue une position pour un joueur donné.
        
        Args:
            state: État du jeu
            player: Joueur pour lequel évaluer (1 ou 2)
        
        Returns:
            Score : 1.0 (victoire), -1.0 (défaite), 0.0 (égalité),
            ou score heuristique entre -1 et 1 si partie en cours
        """
        # Si partie terminée, retourner le résultat
        if state.is_terminal:
            if state.winner == player:
                return 1.0
            elif state.winner == 0:
                return 0.0
            else:
                return -1.0
        
        # Partie en cours : utiliser heuristique
        return self._evaluate_heuristic(state, player)
    
    def _evaluate_heuristic(self, state: GameState, player: int) -> float:
        """
        Évalue une position en cours avec une heuristique.
        
        Returns:
            Score entre -1 et 1 (1 = très favorable pour player, -1 = défavorable)
        """
        board = state.board
        opponent = 2 if player == 1 else 1
        
        score = 0.0
        
        # Compter les alignements
        my_alignments = self._count_alignments(board, player)
        opp_alignments = self._count_alignments(board, opponent)
        
        # Bonus pour alignements
        score += my_alignments[2] * 0.1  # 2 pièces alignées
        score += my_alignments[3] * 0.3  # 3 pièces alignées (menace)
        score += my_alignments[4] * 1.0  # 4 pièces alignées (victoire)
        
        # Pénalité pour alignements adverses
        score -= opp_alignments[2] * 0.1
        score -= opp_alignments[3] * 0.3
        score -= opp_alignments[4] * 1.0
        
        # Normaliser entre -1 et 1
        score = max(-1.0, min(1.0, score / 10.0))
        
        return score
    
    def _count_alignments(self, board: np.ndarray, player: int) -> dict:
        """
        Compte les alignements de différentes longueurs.
        
        Returns:
            Dict avec clés 2, 3, 4 et valeurs (nombre d'alignements)
        """
        alignments = {2: 0, 3: 0, 4: 0}
        height, width = board.shape
        directions = [(0, 1), (1, 0), (1, 1), (1, -1)]
        
        for row in range(height):
            for col in range(width):
                if board[row, col] != player:
                    continue
                
                for dr, dc in directions:
                    count = 1
                    for step in [1, -1]:
                        r, c = row, col
                        for _ in range(3):
                            r += dr * step
                            c += dc * step
                            if (0 <= r < height and 0 <= c < width and 
                                board[r, c] == player):
                                count += 1
                            else:
                                break
                    
                    if count >= 2:
                        if step == 1:  # Éviter les doublons
                            if count >= 4:
                                alignments[4] += 1
                            elif count >= 3:
                                alignments[3] += 1
                            elif count >= 2:
                                alignments[2] += 1
        
        return alignments
    
    def minimax_evaluate(self, state: GameState, depth: int, 
                         alpha: float, beta: float, 
                         maximizing: bool, player: int) -> float:
        """
        Évalue une position avec minimax et élagage alpha-beta.
        
        Args:
            state: État du jeu
            depth: Profondeur restante
            alpha: Valeur alpha pour élagage
            beta: Valeur beta pour élagage
            maximizing: True si on maximise pour player
            player: Joueur pour lequel on évalue
        
        Returns:
            Score de la position
        """
        # Condition d'arrêt
        if state.is_terminal or depth == 0:
            return self.evaluate_position(state, player)
        
        valid_actions = state.get_valid_actions()
        if not valid_actions:
            return self.evaluate_position(state, player)
        
        if maximizing:
            max_eval = float('-inf')
            for action in valid_actions:
                new_state = state.copy()
                if self.logic.apply_action(new_state, action):
                    eval_score = self.minimax_evaluate(
                        new_state, depth - 1, alpha, beta, False, player
                    )
                    max_eval = max(max_eval, eval_score)
                    alpha = max(alpha, eval_score)
                    if beta <= alpha:
                        break  # Élagage
            return max_eval
        else:
            min_eval = float('inf')
            for action in valid_actions:
                new_state = state.copy()
                if self.logic.apply_action(new_state, action):
                    eval_score = self.minimax_evaluate(
                        new_state, depth - 1, alpha, beta, True, player
                    )
                    min_eval = min(min_eval, eval_score)
                    beta = min(beta, eval_score)
                    if beta <= alpha:
                        break  # Élagage
            return min_eval
    
    
    def evaluate_tree(self, tree: Dict[str, dict]) -> Dict[str, dict]:
        """
        Évalue toutes les positions de l'arbre (parallélisé).
        
        Args:
            tree: Arbre de jeu construit
        
        Returns:
            Arbre avec évaluations ajoutées
        """
        if self.use_gpu:
            print("Evaluation des positions (parallellisee CPU + GPU)...")
        else:
            print("Evaluation des positions (parallellisee CPU)...")
        
        total_nodes = len(tree)
        
        # Préparer les données pour la parallélisation
        node_items = list(tree.items())
        
        # Compteurs pour les statistiques
        terminal_count = 0
        heuristic_count = 0
        minimax_count = 0
        
        evaluated_tree = {}
        
        # Préparer les arguments pour les workers
        worker_args = [
            (node_id, node_data, self.board_width, self.board_height)
            for node_id, node_data in node_items
        ]
        
        # Utiliser multiprocessing pour paralléliser
        with Pool(processes=self.num_workers) as pool:
            # Barre de progression avec traitement par chunks
            with tqdm(total=total_nodes, desc="Évaluation", unit=" nœuds") as pbar:
                # Traiter par chunks pour la barre de progression
                chunk_size = max(1, total_nodes // (self.num_workers * 4))
                for i in range(0, total_nodes, chunk_size):
                    chunk = worker_args[i:i + chunk_size]
                    chunk_results = pool.map(_evaluate_single_node_worker, chunk)
                    
                    for node_id, new_node, stats in chunk_results:
                        evaluated_tree[node_id] = new_node
                        terminal_count += stats['terminal']
                        heuristic_count += stats['heuristic']
                        minimax_count += stats['minimax']
                        pbar.update(1)
                    
                    pbar.set_postfix({
                        'terminaux': terminal_count,
                        'heuristique': heuristic_count,
                        'minimax': minimax_count
                    })
        
        print("Evaluation terminee")
        print(f"   - Nœuds terminaux: {terminal_count}")
        print(f"   - Évaluations heuristiques: {heuristic_count}")
        print(f"   - Évaluations minimax: {minimax_count}")
        return evaluated_tree
    
    def classify_branches(self, tree: Dict[str, dict]) -> Dict[str, dict]:
        """
        Classe les branches comme gagnantes, perdantes, ou en cours.
        
        Args:
            tree: Arbre évalué
        
        Returns:
            Arbre avec classification ajoutée
        """
        print("Classification des branches...")
        
        classified_tree = {}
        classification_cache = {}  # Cache pour éviter les recalculs
        total_nodes = len(tree)
        
        def classify_node(node_id: str) -> str:
            """
            Classe récursivement un nœud en fonction de ses enfants.
            
            Returns:
                "winning", "losing", "draw", ou "ongoing"
            """
            # Vérifier le cache
            if node_id in classification_cache:
                return classification_cache[node_id]
            
            node = tree[node_id]
            
            # Si partie terminée, classification directe
            if node['is_terminal']:
                if node['winner'] == 1:
                    result = "winning"
                elif node['winner'] == 2:
                    result = "losing"
                else:
                    result = "draw"
                classification_cache[node_id] = result
                return result
            
            # Si pas d'enfants (devrait pas arriver normalement)
            if not node['children']:
                # Utiliser l'évaluation pour classifier
                eval_score = node.get('evaluation', 0.0)
                if eval_score > 0.5:
                    result = "winning"
                elif eval_score < -0.5:
                    result = "losing"
                elif abs(eval_score) < 0.1:
                    result = "draw"
                else:
                    result = "ongoing"
                classification_cache[node_id] = result
                return result
            
            # Classifier en fonction des enfants
            child_classifications = []
            for child in node['children']:
                child_id = child['node_id']
                if child_id in tree:
                    child_class = classify_node(child_id)
                    child_classifications.append(child_class)
            
            if not child_classifications:
                # Pas d'enfants classifiés, utiliser évaluation
                eval_score = node.get('evaluation', 0.0)
                if eval_score > 0.5:
                    result = "winning"
                elif eval_score < -0.5:
                    result = "losing"
                else:
                    result = "ongoing"
                classification_cache[node_id] = result
                return result
            
            # Logique de classification
            # Si c'est le tour du joueur 1, on cherche une branche gagnante
            # Si c'est le tour du joueur 2, on évite les branches perdantes
            if node['current_player'] == 1:
                # Joueur 1 : gagnant si au moins un enfant est gagnant
                if "winning" in child_classifications:
                    result = "winning"
                elif all(c == "losing" for c in child_classifications):
                    result = "losing"
                elif "draw" in child_classifications and not any(c == "winning" for c in child_classifications):
                    result = "draw"
                else:
                    result = "ongoing"
            else:
                # Joueur 2 : perdant si tous les enfants sont perdants pour joueur 1
                # (c'est-à-dire gagnants pour joueur 2)
                if all(c == "losing" for c in child_classifications):
                    result = "winning"  # Gagnant pour joueur 1 = perdant pour joueur 2
                elif "winning" in child_classifications:
                    result = "losing"
                elif "draw" in child_classifications:
                    result = "draw"
                else:
                    result = "ongoing"
            
            classification_cache[node_id] = result
            return result
        
        # Classifier tous les nœuds (en partant des feuilles)
        # On doit traiter les nœuds dans l'ordre inverse (feuilles d'abord)
        nodes_by_depth = {}
        for node_id, node in tree.items():
            depth = node['move_count']
            if depth not in nodes_by_depth:
                nodes_by_depth[depth] = []
            nodes_by_depth[depth].append(node_id)
        
        # Traiter de la profondeur max à 0
        max_depth = max(nodes_by_depth.keys()) if nodes_by_depth else 0
        
        # Compter le total pour la barre de progression
        total_to_process = sum(len(nodes_by_depth[d]) for d in nodes_by_depth.keys())
        processed = 0
        
        # Barre de progression
        with tqdm(total=total_to_process, desc="Classification", unit=" nœuds") as pbar:
            for depth in range(max_depth, -1, -1):
                if depth in nodes_by_depth:
                    for node_id in nodes_by_depth[depth]:
                        classification = classify_node(node_id)
                        new_node = tree[node_id].copy()
                        new_node['classification'] = classification
                        classified_tree[node_id] = new_node
                        processed += 1
                        pbar.update(1)
                        
                        # Afficher des stats périodiquement
                        if processed % max(1, total_to_process // 20) == 0:
                            winning = sum(1 for n in classified_tree.values() if n.get('classification') == 'winning')
                            losing = sum(1 for n in classified_tree.values() if n.get('classification') == 'losing')
                            draw = sum(1 for n in classified_tree.values() if n.get('classification') == 'draw')
                            pbar.set_postfix({
                                'gagnantes': winning,
                                'perdantes': losing,
                                'égalités': draw
                            })
        
        print("Classification terminee")
        return classified_tree

