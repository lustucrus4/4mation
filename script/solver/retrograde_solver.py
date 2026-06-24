"""
Solveur rétrograde pour positions fin de partie (≤ N cases vides).

Résout W/L/D pour le joueur au trait, best_move et win_rate exact.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np

from game_tree.optimized_minimax import OptimizedMinimaxAdvisor
from solver.position_hasher import HASHER

logger = logging.getLogger(__name__)

RESULT_WIN = "W"
RESULT_LOSS = "L"
RESULT_DRAW = "D"

RESULT_TO_WIN_RATE = {RESULT_WIN: 1.0, RESULT_LOSS: 0.0, RESULT_DRAW: 0.5}


@dataclass
class SolvedPosition:
    hash_key: str
    result: str
    win_rate: float
    best_move: Optional[Tuple[int, int]]
    depth_remaining: int


class RetrogradeSolver:
    """Résolution à rebours depuis les positions terminales."""

    def __init__(self, max_empty: int = 12) -> None:
        self.max_empty = max_empty
        self._advisor = OptimizedMinimaxAdvisor(depth=4, use_iterative_deepening=False)
        self._cache: Dict[str, SolvedPosition] = {}

    def should_solve(self, board: np.ndarray) -> bool:
        return HASHER.empty_cells(board) <= self.max_empty

    def _legal_moves(
        self,
        board: np.ndarray,
        last_move: Optional[Tuple[int, int]],
        player: int,
    ) -> List[Tuple[int, int]]:
        return self._advisor._get_frontier_moves(board, last_move, player)

    def _apply_move(
        self,
        board: np.ndarray,
        move: Tuple[int, int],
        player: int,
    ) -> Tuple[np.ndarray, Tuple[int, int]]:
        nb = board.copy()
        nb[move[0], move[1]] = player
        return nb, move

    def _terminal_result(
        self,
        board: np.ndarray,
        last_move: Optional[Tuple[int, int]],
        current_player: int,
    ) -> Optional[SolvedPosition]:
        winner = self._advisor._check_winner(board)
        if winner is not None:
            if winner == 0:
                result, wr = RESULT_DRAW, 0.5
            elif winner == current_player:
                result, wr = RESULT_WIN, 1.0
            else:
                result, wr = RESULT_LOSS, 0.0
            h = HASHER.hash_key(board, current_player, last_move)
            return SolvedPosition(h, result, wr, None, 0)

        if np.all(board != 0):
            h = HASHER.hash_key(board, current_player, last_move)
            return SolvedPosition(h, RESULT_DRAW, 0.5, None, 0)

        moves = self._legal_moves(board, last_move, current_player)
        if not moves:
            h = HASHER.hash_key(board, current_player, last_move)
            return SolvedPosition(h, RESULT_LOSS, 0.0, None, 0)

        return None

    def solve_position(
        self,
        board: np.ndarray,
        current_player: int,
        last_move: Optional[Tuple[int, int]] = None,
    ) -> Optional[SolvedPosition]:
        """Résout une position si ≤ max_empty cases vides."""
        if not self.should_solve(board):
            return None

        h = HASHER.hash_key(board, current_player, last_move)
        if h in self._cache:
            return self._cache[h]

        terminal = self._terminal_result(board, last_move, current_player)
        if terminal is not None:
            self._cache[h] = terminal
            return terminal

        moves = self._legal_moves(board, last_move, current_player)
        child_results: List[Tuple[Tuple[int, int], SolvedPosition]] = []

        for move in moves:
            nb, lm = self._apply_move(board, move, current_player)
            opponent = 3 - current_player

            if self._advisor._is_winning_move(board, move, current_player):
                child = SolvedPosition(
                    HASHER.hash_key(nb, opponent, lm),
                    RESULT_LOSS,
                    0.0,
                    None,
                    0,
                )
            else:
                child = self.solve_position(nb, opponent, lm)
                if child is None:
                    return None

            child_results.append((move, child))

        best_move: Optional[Tuple[int, int]] = None
        best_wr = -1.0
        has_win = False
        all_loss = True

        for move, child in child_results:
            opp_wr = child.win_rate
            my_wr = 1.0 - opp_wr if child.result != RESULT_DRAW else 0.5

            if child.result == RESULT_LOSS:
                my_result = RESULT_WIN
                my_wr = 1.0
            elif child.result == RESULT_WIN:
                my_result = RESULT_LOSS
                my_wr = 0.0
            else:
                my_result = RESULT_DRAW
                my_wr = 0.5

            if my_result == RESULT_WIN:
                has_win = True
                all_loss = False
                if my_wr > best_wr:
                    best_wr = my_wr
                    best_move = move
            elif my_result == RESULT_DRAW:
                all_loss = False
                if not has_win and my_wr > best_wr:
                    best_wr = my_wr
                    best_move = move
            else:
                if not has_win and best_move is None:
                    best_wr = my_wr
                    best_move = move

        if has_win:
            result = RESULT_WIN
            win_rate = 1.0
        elif all_loss:
            result = RESULT_LOSS
            win_rate = 0.0
            best_move = child_results[0][0]
        else:
            result = RESULT_DRAW
            win_rate = 0.5
            if best_move is None:
                best_move = child_results[0][0]

        depth = 1 + max(c.depth_remaining for _, c in child_results)
        solved = SolvedPosition(h, result, win_rate, best_move, depth)
        self._cache[h] = solved
        return solved

    def analyze_moves(
        self,
        board: np.ndarray,
        current_player: int,
        last_move: Optional[Tuple[int, int]] = None,
    ) -> Optional[dict]:
        """
        Analyse exacte de tous les coups légaux via résolution rétrograde.
        Retourne None si une sous-position n'est pas résoluble.
        """
        moves = self._legal_moves(board, last_move, current_player)
        if not moves:
            return None

        for move in moves:
            if self._advisor._is_winning_move(board, move, current_player):
                moves_out = []
                for m in moves:
                    wr = 1.0 if m == move else 0.0
                    moves_out.append({
                        "move": m,
                        "row": m[0],
                        "col": m[1],
                        "win_rate": wr,
                        "result": RESULT_WIN if m == move else RESULT_LOSS,
                    })
                moves_out.sort(key=lambda m: m["win_rate"], reverse=True)
                return {
                    "moves": moves_out,
                    "best_move": move,
                    "current_player": current_player,
                    "valid_moves_count": len(moves),
                    "elapsed_ms": 0,
                    "source": "tablebase",
                    "exact": True,
                    "label": "Exact (tablebase)",
                    "tactical": True,
                }

        if not self.should_solve(board):
            return None

        moves_out = []
        for move in moves:
            nb, lm = self._apply_move(board, move, current_player)
            child = self.solve_position(nb, 3 - current_player, lm)
            if child is None:
                return None

            if child.result == RESULT_WIN:
                wr, res = 0.0, RESULT_LOSS
            elif child.result == RESULT_LOSS:
                wr, res = 1.0, RESULT_WIN
            else:
                wr, res = 0.5, RESULT_DRAW

            moves_out.append({
                "move": move,
                "row": move[0],
                "col": move[1],
                "win_rate": wr,
                "result": res,
            })

        moves_out.sort(key=lambda m: m["win_rate"], reverse=True)
        best = moves_out[0]["move"] if moves_out else None
        pos = self.solve_position(board, current_player, last_move)

        return {
            "moves": moves_out,
            "best_move": best,
            "current_player": current_player,
            "valid_moves_count": len(moves),
            "elapsed_ms": 0,
            "source": "tablebase",
            "exact": True,
            "position_result": pos.result if pos else None,
            "position_win_rate": pos.win_rate if pos else None,
        }

    def clear_cache(self) -> None:
        self._cache.clear()
