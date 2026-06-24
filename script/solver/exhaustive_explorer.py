"""
Exploration exhaustive de l'espace de positions 4mation (7×7, adjacence last_move).

- BFS avant depuis la position initiale
- Génération rétrograde de parents (coup annulé)
- Phases progressives selon max_empty
"""

from __future__ import annotations

from collections import deque
from typing import Deque, Iterator, List, Optional, Set, Tuple

import numpy as np

from game_tree.optimized_minimax import OptimizedMinimaxAdvisor
from solver.position_hasher import HASHER

Position = Tuple[np.ndarray, int, Optional[Tuple[int, int]]]

# Niveaux progressifs de cases vides (fin de partie → ouverture complète)
MAX_EMPTY_LEVELS: List[int] = [12, 20, 30, 40, 49]


def phase_for_max_empty(max_empty: int) -> str:
    """Libellé de phase pour l'UI et la progression."""
    if max_empty <= 12:
        return "endgame"
    if max_empty <= 20:
        return "midgame"
    if max_empty < 49:
        return "opening"
    return "complet"


def estimate_state_space(max_empty: int) -> Optional[int]:
    """
    Estimation grossière du nombre de positions atteignables avec ≤ max_empty cases vides.
    Ordre de grandeur pour affichage uniquement (non garanti exact).
    """
    # Fin de partie : combinatoire des placements avec contrainte frontier — ~10^5–10^6
    estimates = {
        12: 800_000,
        20: 5_000_000,
        30: 25_000_000,
        40: 80_000_000,
        49: 150_000_000,
    }
    for threshold, est in sorted(estimates.items()):
        if max_empty <= threshold:
            return est
    return estimates[49]


def is_terminal(advisor: OptimizedMinimaxAdvisor, board: np.ndarray, last_move, player: int) -> bool:
    if advisor._check_winner(board) is not None:
        return True
    if np.all(board != 0):
        return True
    return not advisor._get_frontier_moves(board, last_move, player)


def _expand_children(
    advisor: OptimizedMinimaxAdvisor,
    board: np.ndarray,
    player: int,
    last_move: Optional[Tuple[int, int]],
    out_queue: Deque[Position],
    visit_seen: Set[str],
) -> None:
    """Ajoute les enfants BFS non encore visités."""
    if is_terminal(advisor, board, last_move, player):
        return
    for move in advisor._get_frontier_moves(board, last_move, player):
        nb = board.copy()
        nb[move[0], move[1]] = player
        opp = 3 - player
        h = HASHER.hash_key(nb, opp, move)
        if h in visit_seen:
            continue
        visit_seen.add(h)
        out_queue.append((nb, opp, move))


def _parent_last_moves(
    advisor: OptimizedMinimaxAdvisor,
    board: np.ndarray,
    player: int,
    target_move: Tuple[int, int],
) -> List[Optional[Tuple[int, int]]]:
    """Tous les last_move possibles du parent où target_move est légal pour player."""
    if np.count_nonzero(board) == 0:
        return [None]

    found: List[Optional[Tuple[int, int]]] = []
    height, width = board.shape
    for row in range(height):
        for col in range(width):
            if board[row, col] == 0:
                continue
            lm = (row, col)
            moves = advisor._get_frontier_moves(board, lm, player)
            if target_move in moves:
                found.append(lm)

    # Règle de secours : last_move peut être absent si secours utilisé
    moves_fallback = advisor._get_frontier_moves(board, None, player)
    if target_move in moves_fallback and None not in found:
        found.append(None)

    return found


def generate_parents(
    advisor: OptimizedMinimaxAdvisor,
    board: np.ndarray,
    current_player: int,
    last_move: Optional[Tuple[int, int]],
    max_empty: int,
) -> List[Position]:
    """
    Génère les positions parentes en annulant le coup qui a mené à l'état courant.
    L'état courant = après que l'adversaire (3 - P) a joué sur last_move.
    """
    parents: List[Position] = []
    if last_move is None:
        return parents

    lr, lc = last_move
    mover = int(board[lr, lc])
    if mover != 3 - current_player or mover == 0:
        return parents

    board_parent = board.copy()
    board_parent[lr, lc] = 0
    parent_player = mover

    if HASHER.empty_cells(board_parent) > max_empty:
        return parents

    for plm in _parent_last_moves(advisor, board_parent, parent_player, last_move):
        parents.append((board_parent.copy(), parent_player, plm))

    return parents


def enumerate_terminals(advisor: OptimizedMinimaxAdvisor) -> List[Position]:
    """BFS depuis l'ouverture — retourne toutes les positions terminales atteignables."""
    start: Position = (np.zeros((7, 7), dtype=np.int8), 1, None)
    queue: Deque[Position] = deque([start])
    seen: Set[str] = set()
    terminals: List[Position] = []

    while queue:
        board, player, last_move = queue.popleft()
        h = HASHER.hash_key(board, player, last_move)
        if h in seen:
            continue
        seen.add(h)

        if is_terminal(advisor, board, last_move, player):
            terminals.append((board.copy(), player, last_move))
            continue

        _expand_children(advisor, board, player, last_move, queue, seen)

    return terminals


def forward_bfs_unsolved(
    advisor: OptimizedMinimaxAdvisor,
    max_empty: int,
    known_hashes: Set[str],
    bfs_seen: Set[str],
) -> Iterator[Position]:
    """
    Parcours BFS exhaustif depuis l'ouverture.
    Yield les positions avec ≤ max_empty cases vides absentes de known_hashes.
  """
    start: Position = (np.zeros((7, 7), dtype=np.int8), 1, None)
    sh = HASHER.hash_key(*start)
    queue: Deque[Position] = deque()

    if sh not in bfs_seen:
        bfs_seen.add(sh)
        queue.append(start)
    else:
        queue.append(start)

    while queue:
        board, player, last_move = queue.popleft()
        h = HASHER.hash_key(board, player, last_move)

        if HASHER.empty_cells(board) <= max_empty and h not in known_hashes:
            yield (board.copy(), player, last_move)

        if is_terminal(advisor, board, last_move, player):
            continue

        for move in advisor._get_frontier_moves(board, last_move, player):
            nb = board.copy()
            nb[move[0], move[1]] = player
            opp = 3 - player
            ch = HASHER.hash_key(nb, opp, move)
            if ch in bfs_seen:
                continue
            bfs_seen.add(ch)
            queue.append((nb, opp, move))


def retrograde_unsolved_parents(
    advisor: OptimizedMinimaxAdvisor,
    max_empty: int,
    known_hashes: Set[str],
    seed_positions: List[Position],
    retro_seen: Set[str],
) -> Iterator[Position]:
    """
    Vague rétrograde : depuis des positions résolues, remonte vers les parents non encore connus.
    """
    queue: Deque[Position] = deque()

    for pos in seed_positions:
        board, player, last_move = pos
        for parent in generate_parents(advisor, board, player, last_move, max_empty):
            h = HASHER.hash_key(*parent)
            if h in known_hashes or h in retro_seen:
                continue
            retro_seen.add(h)
            queue.append(parent)

    while queue:
        board, player, last_move = queue.popleft()
        h = HASHER.hash_key(board, player, last_move)

        if h in known_hashes:
            continue

        if HASHER.empty_cells(board) <= max_empty:
            yield (board.copy(), player, last_move)

        for parent in generate_parents(advisor, board, player, last_move, max_empty):
            ph = HASHER.hash_key(*parent)
            if ph in known_hashes or ph in retro_seen:
                continue
            retro_seen.add(ph)
            queue.append(parent)


def load_seed_positions_from_db(conn, limit: int = 5000) -> List[Position]:
    """Charge des positions résolues pour amorcer la vague rétrograde."""
    import json

    rows = conn.execute(
        """
        SELECT board_json, current_player, pos_last_move_row, pos_last_move_col
        FROM positions
        WHERE board_json IS NOT NULL
        ORDER BY depth_remaining ASC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()

    out: List[Position] = []
    for row in rows:
        try:
            board = np.array(json.loads(row[0]), dtype=np.int8)
        except (json.JSONDecodeError, TypeError, ValueError):
            continue
        player = int(row[1] or 1)
        lm = None
        if row[2] is not None and int(row[2]) >= 0:
            lm = (int(row[2]), int(row[3]))
        out.append((board, player, lm))
    return out
