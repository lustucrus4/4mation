"""Registre des bots IA disponibles pour 4mation."""

from __future__ import annotations

import random
from typing import Any, Dict, List, Optional, Tuple

from game.game_engine import GameEngine
from game_tree.optimized_minimax import OptimizedMinimaxAdvisor


class RandomBot:
    """Joueur aléatoire parmi les coups valides."""

    def choose_move(self, engine: GameEngine) -> Optional[Tuple[int, int]]:
        valid_actions = engine.get_valid_actions()
        if not valid_actions:
            return None
        return random.choice(valid_actions)


class MinimaxBot:
    """Joueur Minimax optimisé avec budget temps."""

    def __init__(self, depth: int, time_budget_ms: int = 400):
        self.depth = depth
        self.time_budget_ms = time_budget_ms
        self._advisor = OptimizedMinimaxAdvisor(
            depth=depth,
            use_iterative_deepening=True,
            time_budget_ms=time_budget_ms,
        )

    def choose_move(self, engine: GameEngine) -> Optional[Tuple[int, int]]:
        state = engine.get_state()
        last_move = None
        if state.action_history:
            _, last_row, last_col = state.action_history[-1]
            last_move = (int(last_row), int(last_col))

        analysis = self._advisor.analyze_position(
            state.board,
            current_player=int(state.current_player),
            last_move=last_move,
        )
        best_move = analysis.get("best_move")
        if best_move:
            return (int(best_move[0]), int(best_move[1]))

        valid_actions = engine.get_valid_actions()
        return valid_actions[0] if valid_actions else None


class BotRegistry:
    """Catalogue et instanciation des bots configurés."""

    DEFAULT_BOT_ID = "minimax_d4"

    _BOT_META: Dict[str, Dict[str, str]] = {
        "random": {
            "name": "Aléatoire",
            "description": "Joue un coup valide au hasard",
        },
        "minimax_d2": {
            "name": "Minimax (profondeur 2)",
            "description": "Minimax rapide (~200 ms)",
        },
        "minimax_d4": {
            "name": "Minimax (profondeur 4)",
            "description": "Minimax optimisé, niveau débutant (~400 ms)",
        },
        "minimax_d6": {
            "name": "Minimax (profondeur 6)",
            "description": "Minimax optimisé, niveau intermédiaire (~500 ms)",
        },
        "minimax_d8": {
            "name": "Minimax (profondeur 8)",
            "description": "Minimax optimisé, niveau avancé (~800 ms)",
        },
    }

    _DEPTH_CONFIG: Dict[str, Tuple[int, int]] = {
        "minimax_d2": (2, 200),
        "minimax_d4": (4, 400),
        "minimax_d6": (6, 500),
        "minimax_d8": (8, 800),
    }

    def __init__(self) -> None:
        self._random_bot = RandomBot()
        self._minimax_bots: Dict[str, MinimaxBot] = {}

    def list_bots(self) -> List[Dict[str, str]]:
        return [
            {"id": bot_id, **meta}
            for bot_id, meta in self._BOT_META.items()
        ]

    def is_valid_bot(self, bot_id: str) -> bool:
        return bot_id in self._BOT_META

    def _get_minimax_bot(self, bot_id: str) -> MinimaxBot:
        if bot_id not in self._minimax_bots:
            depth, budget = self._DEPTH_CONFIG[bot_id]
            self._minimax_bots[bot_id] = MinimaxBot(depth=depth, time_budget_ms=budget)
        return self._minimax_bots[bot_id]

    def choose_move(self, bot_id: str, engine: GameEngine) -> Optional[Tuple[int, int]]:
        if bot_id == "random":
            return self._random_bot.choose_move(engine)

        if bot_id not in self._DEPTH_CONFIG:
            raise ValueError(f"Bot inconnu: {bot_id}")

        return self._get_minimax_bot(bot_id).choose_move(engine)
