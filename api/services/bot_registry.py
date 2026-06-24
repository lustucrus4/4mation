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
    """Joueur Minimax optimisé à profondeur fixe."""

    def __init__(self, depth: int):
        self.depth = depth
        self._advisor = OptimizedMinimaxAdvisor(
            depth=depth,
            use_iterative_deepening=True,
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
            "description": "Minimax optimisé, recherche peu profonde",
        },
        "minimax_d4": {
            "name": "Minimax (profondeur 4)",
            "description": "Minimax optimisé, niveau débutant",
        },
        "minimax_d6": {
            "name": "Minimax (profondeur 6)",
            "description": "Minimax optimisé, niveau intermédiaire",
        },
        "minimax_d8": {
            "name": "Minimax (profondeur 8)",
            "description": "Minimax optimisé, niveau avancé",
        },
    }

    def __init__(self) -> None:
        self._random_bot = RandomBot()
        self._minimax_bots: Dict[int, MinimaxBot] = {}

    def list_bots(self) -> List[Dict[str, str]]:
        return [
            {"id": bot_id, **meta}
            for bot_id, meta in self._BOT_META.items()
        ]

    def is_valid_bot(self, bot_id: str) -> bool:
        return bot_id in self._BOT_META

    def _get_minimax_bot(self, depth: int) -> MinimaxBot:
        if depth not in self._minimax_bots:
            self._minimax_bots[depth] = MinimaxBot(depth=depth)
        return self._minimax_bots[depth]

    def choose_move(self, bot_id: str, engine: GameEngine) -> Optional[Tuple[int, int]]:
        if bot_id == "random":
            return self._random_bot.choose_move(engine)

        depth_map = {
            "minimax_d2": 2,
            "minimax_d4": 4,
            "minimax_d6": 6,
            "minimax_d8": 8,
        }
        if bot_id not in depth_map:
            raise ValueError(f"Bot inconnu: {bot_id}")

        return self._get_minimax_bot(depth_map[bot_id]).choose_move(engine)
