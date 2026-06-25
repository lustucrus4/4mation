"""
Symétries du plateau 7×7 (groupe diédral D₄ : 4 rotations × miroir).

Forme canonique = représentant de hash Zobrist minimal parmi les 8 images.
"""

from __future__ import annotations

from enum import IntEnum
from typing import Optional, Tuple

import numpy as np

BOARD_SIZE = 7
N = BOARD_SIZE
Move = Tuple[int, int]
Board = np.ndarray


class Symmetry(IntEnum):
    ID = 0
    R90 = 1
    R180 = 2
    R270 = 3
    FLIP_H = 4
    FLIP_H_R90 = 5
    FLIP_H_R180 = 6
    FLIP_H_R270 = 7


ALL_SYMMETRIES = list(Symmetry)


def _rot90_cell(r: int, c: int) -> Move:
    return c, N - 1 - r


def _rot180_cell(r: int, c: int) -> Move:
    return N - 1 - r, N - 1 - c


def _rot270_cell(r: int, c: int) -> Move:
    return N - 1 - c, r


def _flip_h_cell(r: int, c: int) -> Move:
    return r, N - 1 - c


def transform_cell(r: int, c: int, sym: Symmetry) -> Move:
    if sym == Symmetry.ID:
        return r, c
    if sym == Symmetry.R90:
        return _rot90_cell(r, c)
    if sym == Symmetry.R180:
        return _rot180_cell(r, c)
    if sym == Symmetry.R270:
        return _rot270_cell(r, c)
    fr, fc = _flip_h_cell(r, c)
    if sym == Symmetry.FLIP_H:
        return fr, fc
    if sym == Symmetry.FLIP_H_R90:
        return _rot90_cell(fr, fc)
    if sym == Symmetry.FLIP_H_R180:
        return _rot180_cell(fr, fc)
    return _rot270_cell(fr, fc)


def apply_symmetry(
    board: Board,
    last_move: Optional[Move],
    sym: Symmetry,
) -> Tuple[Board, Optional[Move]]:
    out = np.zeros((N, N), dtype=np.int8)
    for r in range(N):
        for c in range(N):
            nr, nc = transform_cell(r, c, sym)
            out[nr, nc] = board[r, c]
    lm = None if last_move is None else transform_cell(last_move[0], last_move[1], sym)
    return out, lm


def canonical_position(
    board: Board,
    current_player: int,
    last_move: Optional[Move],
) -> Tuple[Board, int, Optional[Move]]:
    """Retourne la forme canonique (Zobrist brut minimal)."""
    from solver.position_hasher import HASHER

    best: Optional[Tuple[Board, Optional[Move], int]] = None
    for sym in ALL_SYMMETRIES:
        b, lm = apply_symmetry(board, last_move, sym)
        key = HASHER.raw_zobrist_int(b, current_player, lm)
        if best is None or key < best[2]:
            best = (b, lm, key)
    assert best is not None
    b, lm, _ = best
    return b, current_player, lm
