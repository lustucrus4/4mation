"""
IA Minimax ultra-optimisée pour 4Mation
Implémente NegaMax, hash Zobrist, génération de coups optimisée, et évaluation adaptée
"""

import numpy as np
from typing import Dict, List, Tuple, Optional
from pathlib import Path
import sys
from collections import OrderedDict
import random
import time

# Ajouter le répertoire parent au path pour les imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from game.game_engine import GameEngine


class OptimizedMinimaxAdvisor:
    """
    IA Minimax ultra-optimisée avec:
    - NegaMax + alpha-beta
    - Hash Zobrist pour table de transposition
    - Génération de coups optimisée (frontier-based)
    - Ordre des coups intelligent (win/block/menace)
    - Évaluation adaptée (fenêtres de 4 + mobilité)
    - Iterative deepening
    - Quiescence search
    """
    
    # Flags pour le cache de transposition
    EXACT = 0
    LOWER = 1  # Score <= valeur réelle (coupure beta)
    UPPER = 2  # Score >= valeur réelle (coupure alpha)
    
    # Directions pour les alignements
    DIRECTIONS = [(0, 1), (1, 0), (1, 1), (1, -1)]
    
    # Poids pour les fenêtres de 4
    WINDOW_WEIGHTS = {0: 0, 1: 1, 2: 10, 3: 100, 4: 10000}
    
    def __init__(self, depth: int = 8, cache_size: int = 50000, use_iterative_deepening: bool = True,
                 time_budget_ms: Optional[int] = None):
        """
        Args:
            depth: Profondeur maximale de recherche
            cache_size: Taille maximale du cache (LRU)
            use_iterative_deepening: Utiliser iterative deepening
            time_budget_ms: Budget temps max (ms) pour iterative deepening
        """
        self.max_depth = depth
        self.cache_size = cache_size
        self.use_iterative_deepening = use_iterative_deepening
        self.time_budget_ms = time_budget_ms
        self._search_deadline: Optional[float] = None
        
        # Cache de transposition: {hash: (score, depth, flag, best_move)}
        self.transposition_cache = OrderedDict()
        self.cache_hits = 0
        self.cache_misses = 0
        
        # Hash Zobrist: clés aléatoires pour chaque (case, couleur)
        self._init_zobrist()
        
        # Pré-calcul des segments de 4
        self._init_segments()
        
        # Statistiques
        self.nodes_searched = 0
        self.quiescence_nodes = 0
        
        self.engine = GameEngine()

    def _time_exceeded(self) -> bool:
        return self._search_deadline is not None and time.perf_counter() >= self._search_deadline

    def _begin_search(self) -> None:
        self._search_deadline = None
        if self.time_budget_ms:
            self._search_deadline = time.perf_counter() + self.time_budget_ms / 1000.0
    
    def _init_zobrist(self):
        """Initialise les clés Zobrist pour le hash"""
        # Clés pour chaque case et chaque joueur (0=vide, 1=joueur1, 2=joueur2)
        self.zobrist_keys = {}
        random.seed(42)  # Seed fixe pour reproductibilité
        
        for row in range(7):
            for col in range(7):
                for player in [0, 1, 2]:
                    # Générer une clé aléatoire 64 bits
                    key = random.getrandbits(64)
                    self.zobrist_keys[(row, col, player)] = key
        
        # Clé pour le joueur courant
        self.zobrist_player_keys = {
            1: random.getrandbits(64),
            2: random.getrandbits(64)
        }
    
    def _init_segments(self):
        """Pré-calcule tous les segments de 4 cases (fenêtres)"""
        self.segments = []
        height, width = 7, 7
        
        # Horizontal
        for row in range(height):
            for col in range(width - 3):
                self.segments.append([(row, col + i) for i in range(4)])
        
        # Vertical
        for row in range(height - 3):
            for col in range(width):
                self.segments.append([(row + i, col) for i in range(4)])
        
        # Diagonale \
        for row in range(height - 3):
            for col in range(width - 3):
                self.segments.append([(row + i, col + i) for i in range(4)])
        
        # Diagonale /
        for row in range(height - 3):
            for col in range(3, width):
                self.segments.append([(row + i, col - i) for i in range(4)])
    
    def _zobrist_hash(self, board: np.ndarray, current_player: int, last_move: Optional[Tuple[int, int]] = None) -> int:
        """
        Calcule le hash Zobrist pour la position
        
        Args:
            board: Plateau de jeu
            current_player: Joueur actuel
            last_move: Dernier coup joué (pour différencier les positions avec mêmes pions mais règles différentes)
        
        Returns:
            Hash 64 bits
        """
        h = 0
        
        # Hash du plateau
        for row in range(7):
            for col in range(7):
                player = int(board[row, col])
                h ^= self.zobrist_keys[(row, col, player)]
        
        # Hash du joueur courant
        h ^= self.zobrist_player_keys[current_player]
        
        # Hash du dernier coup (important pour différencier les positions avec mêmes pions)
        if last_move:
            move_idx = int(last_move[0]) * 7 + int(last_move[1])
            h ^= move_idx << 32
        
        return h & ((1 << 64) - 1)
    
    def _get_frontier_moves(self, board: np.ndarray, last_move: Optional[Tuple[int, int]], 
                            current_player: int) -> List[Tuple[int, int]]:
        """
        Génère les coups valides de manière optimisée via frontier
        
        Args:
            board: Plateau de jeu
            last_move: Dernier coup joué (pour la règle principale)
            current_player: Joueur actuel
        
        Returns:
            Liste des coups valides
        """
        opponent = 3 - current_player
        valid_moves = set()
        height, width = board.shape
        
        # Si premier coup (plateau vide), toutes les cases sont valides
        if np.count_nonzero(board) == 0:
            for row in range(height):
                for col in range(width):
                    valid_moves.add((row, col))
            return list(valid_moves)
        
        # Cas 1: Règle principale - adjacents au dernier coup adverse
        if last_move:
            lr, lc = last_move
            for dr in [-1, 0, 1]:
                for dc in [-1, 0, 1]:
                    if dr == 0 and dc == 0:
                        continue
                    r, c = lr + dr, lc + dc
                    if 0 <= r < height and 0 <= c < width and board[r, c] == 0:
                        valid_moves.add((r, c))
        
        # Cas 2: Règle de secours - cases adjacentes à au moins un pion adverse
        if not valid_moves:
            # Trouver toutes les cases adjacentes aux pions adverses
            for row in range(height):
                for col in range(width):
                    if board[row, col] == opponent:
                        # Ajouter les voisins vides
                        for dr in [-1, 0, 1]:
                            for dc in [-1, 0, 1]:
                                if dr == 0 and dc == 0:
                                    continue
                                r, c = row + dr, col + dc
                                if 0 <= r < height and 0 <= c < width and board[r, c] == 0:
                                    valid_moves.add((r, c))
        
        return list(valid_moves)
    
    def _is_winning_move(self, board: np.ndarray, move: Tuple[int, int], player: int) -> bool:
        """Vérifie si un coup crée un alignement gagnant (4)"""
        row, col = move
        height, width = board.shape
        
        # Simuler le coup
        test_board = board.copy()
        test_board[row, col] = player
        
        # Vérifier dans toutes les directions
        for dr, dc in self.DIRECTIONS:
            count = 1  # Le pion qu'on vient de placer
            
            # Compter dans les deux directions
            for step in [1, -1]:
                r, c = row, col
                for _ in range(3):
                    r += dr * step
                    c += dc * step
                    if 0 <= r < height and 0 <= c < width and test_board[r, c] == player:
                        count += 1
                    else:
                        break
            
            if count >= 4:
                return True
        
        return False
    
    def _is_blocking_move(self, board: np.ndarray, move: Tuple[int, int], 
                         current_player: int) -> bool:
        """Vérifie si un coup bloque une victoire immédiate adverse"""
        opponent = 3 - current_player
        return self._is_winning_move(board, move, opponent)
    
    def _count_threats(self, board: np.ndarray, move: Tuple[int, int], player: int) -> int:
        """Compte les menaces (3 alignés ouverts) créées par un coup"""
        row, col = move
        height, width = board.shape
        threats = 0
        
        # Simuler le coup
        test_board = board.copy()
        test_board[row, col] = player
        
        # Vérifier chaque direction
        for dr, dc in self.DIRECTIONS:
            count = 1
            open_ends = 0
            
            # Compter dans les deux directions
            for step in [1, -1]:
                r, c = row, col
                for _ in range(3):
                    r += dr * step
                    c += dc * step
                    if 0 <= r < height and 0 <= c < width:
                        if test_board[r, c] == player:
                            count += 1
                        elif test_board[r, c] == 0:
                            open_ends += 1
                            break
                        else:
                            break
                    else:
                        break
            
            # Menace si 3 alignés avec au moins une extrémité ouverte
            if count == 3 and open_ends > 0:
                threats += 1
        
        return threats
    
    def _order_moves(self, board: np.ndarray, moves: List[Tuple[int, int]], 
                    current_player: int, last_move: Optional[Tuple[int, int]]) -> List[Tuple[int, int]]:
        """
        Trie les coups par ordre d'importance (win > block > threat > center > other)
        
        Returns:
            Liste de coups triés
        """
        if not moves:
            return []
        
        move_scores = []
        
        for move in moves:
            score = 0
            
            # 1. Coup gagnant immédiat (priorité maximale)
            if self._is_winning_move(board, move, current_player):
                score += 1000000
            # 2. Coup qui bloque une victoire adverse
            elif self._is_blocking_move(board, move, current_player):
                score += 500000
            # 3. Menaces (3 alignés)
            else:
                threats = self._count_threats(board, move, current_player)
                score += threats * 1000
                
                # 4. Bonus centre (souvent bon sur 7x7)
                row, col = move
                center_dist = abs(row - 3) + abs(col - 3)
                score += (7 - center_dist) * 10
                
                # 5. Évaluation rapide des fenêtres
                score += self._quick_window_eval(board, move, current_player) * 5
            
            move_scores.append((move, score))
        
        # Trier par score décroissant
        move_scores.sort(key=lambda x: x[1], reverse=True)
        return [move for move, _ in move_scores]
    
    def _quick_window_eval(self, board: np.ndarray, move: Tuple[int, int], player: int) -> float:
        """Évaluation rapide des fenêtres de 4 pour un coup"""
        row, col = move
        test_board = board.copy()
        test_board[row, col] = player
        
        score = 0.0
        opponent = 3 - player
        
        # Évaluer les segments qui contiennent ce coup
        for segment in self.segments:
            if (row, col) not in segment:
                continue
            
            # Compter les pions dans le segment
            my_count = 0
            opp_count = 0
            empty_count = 0
            
            for r, c in segment:
                cell = test_board[r, c]
                if cell == player:
                    my_count += 1
                elif cell == opponent:
                    opp_count += 1
                else:
                    empty_count += 1
            
            # Segment pollué (les deux joueurs) = 0
            if my_count > 0 and opp_count > 0:
                continue
            
            # Bonus pour mes segments
            if my_count > 0:
                score += self.WINDOW_WEIGHTS.get(my_count, 0)
            # Malus pour les segments adverses
            if opp_count > 0:
                score -= self.WINDOW_WEIGHTS.get(opp_count, 0) * 0.8
        
        return score
    
    def _evaluate_windows(self, board: np.ndarray, player: int) -> float:
        """
        Évalue la position en analysant toutes les fenêtres de 4
        
        Returns:
            Score heuristique
        """
        opponent = 3 - player
        score = 0.0
        
        for segment in self.segments:
            my_count = 0
            opp_count = 0
            empty_count = 0
            
            for row, col in segment:
                cell = board[row, col]
                if cell == player:
                    my_count += 1
                elif cell == opponent:
                    opp_count += 1
                else:
                    empty_count += 1
            
            # Segment pollué = 0
            if my_count > 0 and opp_count > 0:
                continue
            
            # Bonus pour mes segments
            if my_count > 0:
                score += self.WINDOW_WEIGHTS.get(my_count, 0)
            # Malus pour les segments adverses
            if opp_count > 0:
                score -= self.WINDOW_WEIGHTS.get(opp_count, 0) * 0.8
        
        return score
    
    def _evaluate_mobility(self, board: np.ndarray, last_move: Optional[Tuple[int, int]], 
                          current_player: int) -> float:
        """
        Évalue la mobilité (nombre de coups légaux)
        Bonus si l'adversaire a peu de coups, malus si on aura peu de coups
        """
        opponent = 3 - current_player
        
        # Coups légaux pour l'adversaire (après notre coup)
        opp_moves = self._get_frontier_moves(board, last_move, opponent)
        opp_mobility = len(opp_moves)
        
        # Estimer nos coups futurs (approximation)
        # On prend le dernier coup comme référence
        my_mobility = len(self._get_frontier_moves(board, last_move, current_player))
        
        # Bonus si adversaire a peu de coups, malus si on a peu de coups
        mobility_score = (opp_mobility * -0.1) + (my_mobility * 0.05)
        
        return mobility_score
    
    def _evaluate_position(self, board: np.ndarray, last_move: Optional[Tuple[int, int]], 
                          current_player: int, ply: int = 0) -> float:
        """
        Évalue une position avec heuristique adaptée à 4Mation
        
        Args:
            board: Plateau de jeu
            last_move: Dernier coup joué
            current_player: Joueur pour lequel on évalue
            ply: Profondeur (pour préférer gagner vite / perdre tard)
        
        Returns:
            Score heuristique (du point de vue de current_player)
        """
        opponent = 3 - current_player
        
        # Vérifier victoire/défaite
        winner = self._check_winner(board)
        if winner == current_player:
            return 100000 - ply  # Gagner vite
        elif winner == opponent:
            return -100000 + ply  # Perdre tard
        elif winner == 0:  # Égalité
            return 0
        
        # Vérifier si pas de coups légaux
        my_moves = self._get_frontier_moves(board, last_move, current_player)
        opp_moves = self._get_frontier_moves(board, last_move, opponent)
        
        if not my_moves:
            return -50000 + ply  # Pas de coups = perdre tard
        if not opp_moves:
            return 50000 - ply  # Adversaire sans coups = gagner vite
        
        # Évaluation principale
        score = 0.0
        
        # 1. Fenêtres de 4
        window_score = self._evaluate_windows(board, current_player)
        score += window_score
        
        # 2. Mobilité
        mobility_score = self._evaluate_mobility(board, last_move, current_player)
        score += mobility_score
        
        return score
    
    def _check_winner(self, board: np.ndarray) -> Optional[int]:
        """Vérifie s'il y a un gagnant"""
        height, width = board.shape
        
        for row in range(height):
            for col in range(width):
                player = board[row, col]
                if player == 0:
                    continue
                
                # Vérifier dans toutes les directions
                for dr, dc in self.DIRECTIONS:
                    count = 1
                    for step in [1, -1]:
                        r, c = row, col
                        for _ in range(3):
                            r += dr * step
                            c += dc * step
                            if 0 <= r < height and 0 <= c < width and board[r, c] == player:
                                count += 1
                            else:
                                break
                    
                    if count >= 4:
                        return player
        
        return None
    
    def _get_cache_entry(self, zobrist_hash: int, depth: int) -> Optional[Tuple[float, int, Optional[Tuple[int, int]]]]:
        """Récupère une entrée du cache"""
        cache_key = (zobrist_hash, depth)
        
        if cache_key in self.transposition_cache:
            entry = self.transposition_cache.pop(cache_key)
            self.transposition_cache[cache_key] = entry  # LRU: déplacer en fin
            self.cache_hits += 1
            return entry
        else:
            self.cache_misses += 1
            return None
    
    def _store_cache_entry(self, zobrist_hash: int, depth: int, score: float, 
                          flag: int, best_move: Optional[Tuple[int, int]] = None):
        """Stocke une entrée dans le cache (LRU)"""
        cache_key = (zobrist_hash, depth)
        
        # Si le cache est plein, supprimer l'entrée la plus ancienne
        if len(self.transposition_cache) >= self.cache_size:
            self.transposition_cache.popitem(last=False)
        
        self.transposition_cache[cache_key] = (score, flag, best_move)
    
    def _nega_max(self, board: np.ndarray, last_move: Optional[Tuple[int, int]], 
                  current_player: int, depth: int, alpha: float, beta: float, 
                  ply: int = 0) -> float:
        """
        Algorithme NegaMax avec alpha-beta et optimisations
        
        Returns:
            Score du point de vue du joueur qui maximise (current_player)
        """
        self.nodes_searched += 1
        if self.nodes_searched % 256 == 0 and self._time_exceeded():
            raise TimeoutError("budget temps Minimax dépassé")
        
        # Hash Zobrist
        zobrist_hash = self._zobrist_hash(board, current_player, last_move)
        
        # Vérifier le cache
        cache_entry = self._get_cache_entry(zobrist_hash, depth)
        if cache_entry:
            cached_score, flag, _ = cache_entry
            if flag == self.EXACT:
                return cached_score
            elif flag == self.LOWER and cached_score >= beta:
                return cached_score
            elif flag == self.UPPER and cached_score <= alpha:
                return cached_score
        
        # Évaluation terminale ou feuille
        winner = self._check_winner(board)
        if winner:
            score = 100000 - ply if winner == current_player else -100000 + ply
            self._store_cache_entry(zobrist_hash, depth, score, self.EXACT)
            return score
        
        # Vérifier coups légaux
        moves = self._get_frontier_moves(board, last_move, current_player)
        if not moves:
            score = -50000 + ply  # Pas de coups = perdre tard
            self._store_cache_entry(zobrist_hash, depth, score, self.EXACT)
            return score
        
        # Condition d'arrêt
        if depth <= 0:
            # Quiescence: continuer si position instable (menaces)
            return self._quiescence_search(board, last_move, current_player, alpha, beta, ply)
        
        # Trier les coups
        ordered_moves = self._order_moves(board, moves, current_player, last_move)
        
        best_score = float('-inf')
        best_move = None
        flag = self.UPPER
        
        for move in ordered_moves:
            # Créer nouvelle position
            new_board = board.copy()
            new_board[move[0], move[1]] = current_player
            
            # Vérifier victoire immédiate
            if self._is_winning_move(board, move, current_player):
                score = 100000 - ply
                self._store_cache_entry(zobrist_hash, depth, score, self.EXACT, move)
                return score
            
            # Récursion NegaMax (inverser alpha/beta et négater)
            opponent = 3 - current_player
            score = -self._nega_max(new_board, move, opponent, depth - 1, -beta, -alpha, ply + 1)
            
            if score > best_score:
                best_score = score
                best_move = move
                flag = self.EXACT
            
            alpha = max(alpha, score)
            if alpha >= beta:
                flag = self.LOWER
                break  # Coupure alpha-beta
        
        # Stocker dans le cache
        self._store_cache_entry(zobrist_hash, depth, best_score, flag, best_move)
        return best_score
    
    def _quiescence_search(self, board: np.ndarray, last_move: Optional[Tuple[int, int]], 
                          current_player: int, alpha: float, beta: float, ply: int, 
                          q_depth: int = 2) -> float:
        """
        Recherche de quiescence: continue la recherche dans les positions instables
        """
        self.quiescence_nodes += 1
        
        # Évaluation statique
        stand_pat = self._evaluate_position(board, last_move, current_player, ply)
        
        if stand_pat >= beta:
            return beta
        if stand_pat > alpha:
            alpha = stand_pat
        
        # Arrêt si profondeur quiescence atteinte
        if q_depth <= 0:
            return stand_pat
        
        # Continuer seulement si position instable (menaces)
        moves = self._get_frontier_moves(board, last_move, current_player)
        has_threat = False
        
        for move in moves:
            if self._is_winning_move(board, move, current_player) or \
               self._is_blocking_move(board, move, current_player) or \
               self._count_threats(board, move, current_player) > 0:
                has_threat = True
                break
        
        if not has_threat:
            return stand_pat
        
        # Explorer les coups menaçants
        ordered_moves = self._order_moves(board, moves, current_player, last_move)
        
        for move in ordered_moves[:5]:  # Limiter à 5 coups les plus menaçants
            if not (self._is_winning_move(board, move, current_player) or 
                   self._is_blocking_move(board, move, current_player) or
                   self._count_threats(board, move, current_player) > 0):
                continue
            
            new_board = board.copy()
            new_board[move[0], move[1]] = current_player
            
            opponent = 3 - current_player
            score = -self._quiescence_search(new_board, move, opponent, -beta, -alpha, 
                                            ply + 1, q_depth - 1)
            
            if score >= beta:
                return beta
            if score > alpha:
                alpha = score
        
        return alpha
    
    def _iterative_deepening(self, board: np.ndarray, last_move: Optional[Tuple[int, int]], 
                            current_player: int) -> Tuple[Optional[Tuple[int, int]], float]:
        """
        Iterative deepening: cherche de profondeur 1 à max_depth
        
        Returns:
            (meilleur_coup, meilleur_score)
        """
        best_move = None
        best_score = float('-inf')
        moves = self._get_frontier_moves(board, last_move, current_player)
        
        if not moves:
            return None, float('-inf')
        
        # Trier les coups une fois
        ordered_moves = self._order_moves(board, moves, current_player, last_move)
        
        for depth in range(1, self.max_depth + 1):
            if self._time_exceeded():
                break
            try:
                current_best_move = None
                current_best_score = float('-inf')
                
                # Explorer les coups dans l'ordre
                for move in ordered_moves:
                    if self._time_exceeded():
                        break
                    new_board = board.copy()
                    new_board[move[0], move[1]] = current_player
                    opponent = 3 - current_player
                    
                    score = -self._nega_max(new_board, move, opponent, depth - 1,
                                           float('-inf'), float('inf'), 1)
                    
                    if score > current_best_score:
                        current_best_score = score
                        current_best_move = move
                
                # Mettre à jour le meilleur global
                if current_best_score > best_score:
                    best_score = current_best_score
                    best_move = current_best_move
                
                # Utiliser le meilleur coup pour ordonner les prochaines itérations
                if best_move and best_move in ordered_moves:
                    ordered_moves.remove(best_move)
                    ordered_moves.insert(0, best_move)
                    
            except TimeoutError:
                break
            except Exception as e:
                print(f"[WARNING] Erreur à profondeur {depth}: {e}")
                break
        
        return best_move, best_score
    
    def _find_tactical_move(self, board: np.ndarray, valid_moves: List[Tuple[int, int]],
                            current_player: int,
                            last_move: Optional[Tuple[int, int]] = None) -> Optional[Tuple[int, int]]:
        """
        Détecte victoire en 1 ou blocage obligatoire parmi les coups légaux
        (respecte l'adjacence via valid_moves dérivés de last_move).
        """
        if not valid_moves:
            return None

        for move in valid_moves:
            if self._is_winning_move(board, move, current_player):
                return move

        blocking = [m for m in valid_moves if self._is_blocking_move(board, m, current_player)]
        if blocking:
            ordered = self._order_moves(board, blocking, current_player, last_move)
            return ordered[0]

        return None

    def evaluate_move(self, board: np.ndarray, move: Tuple[int, int], 
                     current_player: int, depth: int = None,
                     last_move: Optional[Tuple[int, int]] = None) -> float:
        """
        Évalue un coup avec minimax optimisé
        
        Args:
            board: État actuel du plateau
            move: Coup à évaluer (row, col)
            current_player: Joueur qui joue (1 ou 2)
            depth: Profondeur de recherche (None = self.max_depth)
            last_move: Dernier coup joué (requis pour coups légaux adjacents)
        
        Returns:
            Score de -1 (perdant) à 1 (gagnant) pour le joueur actuel
        """
        if depth is None:
            depth = self.max_depth
        
        # Vérifier si le coup est valide (avec adjacence correcte)
        moves = self._get_frontier_moves(board, last_move, current_player)
        if move not in moves:
            return -1.0
        
        # Appliquer le coup
        new_board = board.copy()
        new_board[move[0], move[1]] = current_player
        
        # Vérifier victoire immédiate
        if self._is_winning_move(board, move, current_player):
            return 1.0
        
        # Évaluer avec NegaMax
        opponent = 3 - current_player
        score = -self._nega_max(new_board, move, opponent, depth - 1, 
                               float('-inf'), float('inf'), 1)
        
        # Normaliser entre -1 et 1
        return max(-1.0, min(1.0, score / 100000.0))
    
    def analyze_position(self, board: np.ndarray, current_player: int = 1, 
                        last_move: Tuple[int, int] = None,
                        include_move_scores: bool = True) -> Dict:
        """
        Analyse une position et retourne les probabilités pour chaque coup
        
        Args:
            board: État actuel du plateau (7x7 numpy array)
            current_player: Joueur qui doit jouer (1 ou 2)
            last_move: Position du dernier coup joué (row, col) ou None si premier coup
        
        Returns:
            Dictionnaire avec:
            - 'moves': Liste de dicts avec 'move', 'score', 'win_probability'
            - 'best_move': Meilleur coup
            - 'board': État du plateau
        """
        # Réinitialiser les statistiques
        self.nodes_searched = 0
        self.quiescence_nodes = 0
        self._begin_search()
        
        # Obtenir les coups valides
        valid_moves = self._get_frontier_moves(board, last_move, current_player)
        
        if not valid_moves:
            return {
                'moves': [],
                'best_move': None,
                'board': board.tolist(),
                'current_player': current_player,
                'valid_moves_count': 0
            }

        # Tactiques immédiates (victoire en 1 / blocage obligatoire)
        tactical_move = self._find_tactical_move(board, valid_moves, current_player, last_move)
        if tactical_move is not None:
            move_scores = []
            for move in valid_moves:
                if move == tactical_move:
                    score = 1.0 if self._is_winning_move(board, move, current_player) else 0.9
                else:
                    score = -0.5
                move_scores.append({
                    'move': move,
                    'row': move[0],
                    'col': move[1],
                    'score': score,
                    'win_probability': (score + 1) / 2,
                    'estimated_score': score,
                })
            move_scores.sort(key=lambda x: x['score'], reverse=True)
            return {
                'moves': move_scores,
                'best_move': tactical_move,
                'board': board.tolist(),
                'current_player': current_player,
                'valid_moves_count': len(valid_moves),
                'tactical': True,
            }
        
        # Utiliser iterative deepening si activé
        best_move = None
        best_score = float('-inf')
        if self.use_iterative_deepening:
            best_move, best_score = self._iterative_deepening(board, last_move, current_player)
        else:
            # Sinon, chercher à profondeur max
            for move in self._order_moves(board, valid_moves, current_player, last_move):
                if self._time_exceeded():
                    break
                new_board = board.copy()
                new_board[move[0], move[1]] = current_player
                opponent = 3 - current_player
                score = -self._nega_max(new_board, move, opponent, self.max_depth - 1,
                                      float('-inf'), float('inf'), 1)
                if score > best_score:
                    best_score = score
                    best_move = move

        if not include_move_scores:
            return {
                'moves': [],
                'best_move': best_move,
                'board': board.tolist(),
                'current_player': current_player,
                'valid_moves_count': len(valid_moves),
            }
        
        # Évaluer tous les coups (score estimé heuristique, pas un vrai % victoire)
        move_scores = []
        for move in valid_moves:
            score = self.evaluate_move(board, move, current_player, last_move=last_move)
            win_probability = (score + 1) / 2
            
            move_scores.append({
                'move': move,
                'row': move[0],
                'col': move[1],
                'score': score,
                'win_probability': win_probability,
                'estimated_score': score,
            })
        
        # Trier par score décroissant
        move_scores.sort(key=lambda x: x['score'], reverse=True)
        
        return {
            'moves': move_scores,
            'best_move': best_move,
            'board': board.tolist(),
            'current_player': current_player,
            'valid_moves_count': len(valid_moves)
        }
    
    def get_cache_stats(self) -> Dict:
        """Retourne les statistiques du cache et de la recherche"""
        total = self.cache_hits + self.cache_misses
        hit_rate = (self.cache_hits / total * 100) if total > 0 else 0.0
        return {
            'hits': self.cache_hits,
            'misses': self.cache_misses,
            'hit_rate': hit_rate,
            'size': len(self.transposition_cache),
            'max_size': self.cache_size,
            'nodes_searched': self.nodes_searched,
            'quiescence_nodes': self.quiescence_nodes
        }
    
    def clear_cache(self):
        """Vide le cache"""
        self.transposition_cache.clear()
        self.cache_hits = 0
        self.cache_misses = 0
        self.nodes_searched = 0
        self.quiescence_nodes = 0
