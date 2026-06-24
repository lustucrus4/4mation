"""
Hash Zobrist pour positions 4mation (plateau 7×7 + last_move + joueur au trait).

Compatible avec OptimizedMinimaxAdvisor (seed 42).
"""

from __future__ import annotations

import random
from typing import Optional, Tuple

import numpy as np

BOARD_SIZE = 7
NO_LAST_MOVE = (-1, -1)


class PositionHasher:
    """Calcule des clés stables pour indexation tablebase / livre d'ouverture."""

    def __init__(self) -> None:
        self._zobrist_keys: dict[tuple[int, int, int], int] = {}
        self._zobrist_player_keys: dict[int, int] = {}
        self._init_keys()

    def _init_keys(self) -> None:
        random.seed(42)
        for row in range(BOARD_SIZE):
            for col in range(BOARD_SIZE):
                for player in (0, 1, 2):
                    self._zobrist_keys[(row, col, player)] = random.getrandbits(64)
        self._zobrist_player_keys = {
            1: random.getrandbits(64),
            2: random.getrandbits(64),
        }

    def zobrist_int(
        self,
        board: np.ndarray,
        current_player: int,
        last_move: Optional[Tuple[int, int]] = None,
    ) -> int:
        h = 0
        for row in range(BOARD_SIZE):
            for col in range(BOARD_SIZE):
                player = int(board[row, col])
                h ^= self._zobrist_keys[(row, col, player)]
        h ^= self._zobrist_player_keys[current_player]
        if last_move is not None:
            h ^= (last_move[0] * BOARD_SIZE + last_move[1]) << 32
        return h

    def hash_key(
        self,
        board: np.ndarray,
        current_player: int,
        last_move: Optional[Tuple[int, int]] = None,
    ) -> str:
        """Clé hexadécimale pour SQLite."""
        return f"{self.zobrist_int(board, current_player, last_move):016x}"

    def empty_cells(self, board: np.ndarray) -> int:
        return int(np.count_nonzero(board == 0))

    def move_count(self, board: np.ndarray) -> int:
        return int(np.count_nonzero(board != 0))


# Instance partagée (même seed → mêmes clés que Minimax)
HASHER = PositionHasher()
