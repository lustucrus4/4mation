"""
MCTS root-only pour analyser tous les coups légaux (mode coach 4mation).
"""

from __future__ import annotations

import random
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

from game_tree.optimized_minimax import OptimizedMinimaxAdvisor


@dataclass
class _MCTSNode:
    visits: int = 0
    wins: float = 0.0
    children: Dict[Tuple[int, int], "_MCTSNode"] = field(default_factory=dict)


class MCTSAdvisor:
    """
    Monte Carlo Tree Search limité à la racine :
    chaque coup légal reçoit des simulations jusqu'au budget temps/nombre.
    """

    def __init__(
        self,
        time_budget_ms: int = 2000,
        simulations_per_move: Optional[int] = None,
        rollout_depth: int = 2,
        cache_size: int = 200,
        exploration: float = 1.41,
    ):
        self.time_budget_ms = time_budget_ms
        self.simulations_per_move = simulations_per_move
        self.rollout_depth = rollout_depth
        self.exploration = exploration
        self._rollout_advisor = OptimizedMinimaxAdvisor(
            depth=rollout_depth,
            use_iterative_deepening=False,
            cache_size=5000,
        )
        self._minimax = OptimizedMinimaxAdvisor(depth=6, use_iterative_deepening=True)
        self._analysis_cache: OrderedDict[int, Dict] = OrderedDict()
        self._cache_size = cache_size

    def _position_hash(self, board: np.ndarray, current_player: int,
                       last_move: Optional[Tuple[int, int]]) -> int:
        return self._minimax._zobrist_hash(board, current_player, last_move)

    def _cache_get(self, key: int) -> Optional[Dict]:
        if key not in self._analysis_cache:
            return None
        self._analysis_cache.move_to_end(key)
        return self._analysis_cache[key]

    def _cache_put(self, key: int, value: Dict) -> None:
        if key in self._analysis_cache:
            self._analysis_cache.move_to_end(key)
        self._analysis_cache[key] = value
        while len(self._analysis_cache) > self._cache_size:
            self._analysis_cache.popitem(last=False)

    def _terminal_winner(self, board: np.ndarray) -> Optional[int]:
        return self._minimax._check_winner(board)

    def _legal_moves(self, board: np.ndarray, last_move: Optional[Tuple[int, int]],
                     player: int) -> List[Tuple[int, int]]:
        return self._minimax._get_frontier_moves(board, last_move, player)

    def _apply_move(self, board: np.ndarray, move: Tuple[int, int], player: int) -> np.ndarray:
        nb = board.copy()
        nb[move[0], move[1]] = player
        return nb

    def _rollout(self, board: np.ndarray, last_move: Optional[Tuple[int, int]],
                 current_player: int, root_player: int) -> float:
        """Simulation rapide jusqu'à fin de partie ou profondeur limite."""
        b = board.copy()
        lm = last_move
        cp = current_player
        depth = 0
        max_depth = 40

        while depth < max_depth:
            winner = self._terminal_winner(b)
            if winner is not None:
                if winner == root_player:
                    return 1.0
                if winner == 0:
                    return 0.5
                return 0.0

            moves = self._legal_moves(b, lm, cp)
            if not moves:
                return 0.0 if cp == root_player else 1.0

            if depth < self.rollout_depth and len(moves) <= 12:
                analysis = self._rollout_advisor.analyze_position(b, cp, lm)
                move = analysis.get("best_move") or random.choice(moves)
            else:
                move = random.choice(moves)

            b = self._apply_move(b, move, cp)
            lm = move
            cp = 3 - cp
            depth += 1

        eval_score = self._minimax._evaluate_position(b, lm, root_player)
        return max(0.0, min(1.0, (eval_score / 100000.0 + 1.0) / 2.0))

    def analyze_position(
        self,
        board: np.ndarray,
        current_player: int = 1,
        last_move: Optional[Tuple[int, int]] = None,
    ) -> Dict:
        """
        Analyse MCTS de tous les coups légaux.

        Returns:
            Dict avec moves[{move, win_rate, visits, ...}], best_move, elapsed_ms
        """
        pos_hash = self._position_hash(board, current_player, last_move)
        cached = self._cache_get(pos_hash)
        if cached is not None:
            return {**cached, "cached": True}

        valid_moves = self._legal_moves(board, last_move, current_player)
        if not valid_moves:
            return {
                "moves": [],
                "best_move": None,
                "current_player": current_player,
                "valid_moves_count": 0,
                "elapsed_ms": 0,
            }

        tactical = self._minimax._find_tactical_move(
            board, valid_moves, current_player, last_move
        )
        if tactical is not None:
            is_win = self._minimax._is_winning_move(board, tactical, current_player)
            moves_out = []
            for move in valid_moves:
                if move == tactical:
                    wr = 1.0 if is_win else 0.95
                else:
                    wr = 0.05
                moves_out.append({
                    "move": move,
                    "row": move[0],
                    "col": move[1],
                    "win_rate": wr,
                    "visits": 0,
                    "tactical": True,
                })
            moves_out.sort(key=lambda m: m["win_rate"], reverse=True)
            result = {
                "moves": moves_out,
                "best_move": tactical,
                "current_player": current_player,
                "valid_moves_count": len(valid_moves),
                "elapsed_ms": 0,
                "tactical": True,
            }
            self._cache_put(pos_hash, result)
            return result

        nodes: Dict[Tuple[int, int], _MCTSNode] = {
            m: _MCTSNode() for m in valid_moves
        }
        total_sims = 0
        start = time.perf_counter()
        deadline = start + self.time_budget_ms / 1000.0

        def budget_reached() -> bool:
            if self.simulations_per_move is not None:
                return all(n.visits >= self.simulations_per_move for n in nodes.values())
            return time.perf_counter() >= deadline

        while not budget_reached():
            for move in valid_moves:
                if self.simulations_per_move is not None and nodes[move].visits >= self.simulations_per_move:
                    continue
                if self.simulations_per_move is None and time.perf_counter() >= deadline:
                    break

                nb = self._apply_move(board, move, current_player)
                opponent = 3 - current_player
                outcome = self._rollout(nb, move, opponent, current_player)
                node = nodes[move]
                node.visits += 1
                node.wins += outcome
                total_sims += 1

        elapsed_ms = int((time.perf_counter() - start) * 1000)
        moves_out = []
        for move in valid_moves:
            node = nodes[move]
            win_rate = node.wins / node.visits if node.visits > 0 else 0.0
            moves_out.append({
                "move": move,
                "row": move[0],
                "col": move[1],
                "win_rate": round(win_rate, 4),
                "visits": node.visits,
            })

        moves_out.sort(key=lambda m: (m["win_rate"], m["visits"]), reverse=True)
        best_move = moves_out[0]["move"] if moves_out else None

        result = {
            "moves": moves_out,
            "best_move": best_move,
            "current_player": current_player,
            "valid_moves_count": len(valid_moves),
            "elapsed_ms": elapsed_ms,
            "total_simulations": total_sims,
        }
        self._cache_put(pos_hash, result)
        return result

    def clear_cache(self) -> None:
        self._analysis_cache.clear()
