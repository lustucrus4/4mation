"""Registre des bots IA de 4mation — 6 niveaux de difficulté réels.

Les niveaux 1 à 5 sont des bots Minimax paramétrés :
- depth / time_budget_ms : force de la recherche ;
- use_tablebase : consulte la tablebase exacte (coups parfaits en finale) ;
- blunder_rate : probabilité de jouer un coup au hasard (erreurs « humaines »),
  ce qui rend les niveaux faibles réellement battables sans être stupides.

Le niveau 6 est branché sur le moteur Rust `4mation-engine` (processus persistant,
recherche alpha-bêta + tablebase). Si le binaire n'est pas disponible, le niveau 6
retombe automatiquement sur le chemin Minimax des niveaux 5.
"""

from __future__ import annotations

import logging
import random
from typing import Any, Dict, List, Optional, Tuple

from api.services.engine_client import get_engine_client
from api.services.tablebase_lookup import get_tablebase_lookup
from game.game_engine import GameEngine
from game_tree.optimized_minimax import OptimizedMinimaxAdvisor

logger = logging.getLogger(__name__)


class DifficultyBot:
    """Bot dont la force est calibrée par un niveau de difficulté.

    Deux moteurs possibles : le Minimax Python historique, ou le moteur Rust
    (`use_engine`) quand il est compilé et disponible.
    """

    def __init__(
        self,
        depth: int,
        time_budget_ms: int,
        use_tablebase: bool,
        blunder_rate: float,
        use_engine: bool = False,
    ) -> None:
        self.depth = depth
        self.time_budget_ms = time_budget_ms
        self.use_tablebase = use_tablebase
        self.blunder_rate = blunder_rate
        self.use_engine = use_engine
        self._advisor = OptimizedMinimaxAdvisor(
            depth=depth,
            use_iterative_deepening=True,
            time_budget_ms=time_budget_ms,
        )

    @staticmethod
    def _last_move(engine: GameEngine) -> Optional[Tuple[int, int]]:
        state = engine.get_state()
        if state.action_history:
            _, last_row, last_col = state.action_history[-1]
            return (int(last_row), int(last_col))
        return None

    def _engine_move(
        self,
        state: Any,
        last_move: Optional[Tuple[int, int]],
        valid_actions: List[Tuple[int, int]],
    ) -> Optional[Tuple[int, int]]:
        """Coup du moteur Rust, ou None si indisponible / coup inutilisable."""
        client = get_engine_client()
        if not client.is_available():
            return None
        try:
            move = client.best_move(
                state.board,
                int(state.current_player),
                last_move,
                depth=self.depth,
                time_ms=self.time_budget_ms,
            )
        except Exception as exc:
            logger.warning("Moteur Rust en erreur : %s — repli Minimax", exc)
            return None

        if move is None:
            return None
        if move not in valid_actions:
            logger.warning("Moteur Rust propose un coup illégal %s — coup ignoré", move)
            return None
        return move

    def choose_move(self, engine: GameEngine) -> Optional[Tuple[int, int]]:
        valid_actions = engine.get_valid_actions()
        if not valid_actions:
            return None

        # Erreur « humaine » : un coup au hasard (surtout aux niveaux faibles).
        if self.blunder_rate > 0.0 and random.random() < self.blunder_rate:
            return random.choice(valid_actions)

        state = engine.get_state()
        last_move = self._last_move(engine)

        # Preuve d'abord : une position dont la valeur est démontrée (tablebase exacte ou
        # livre prouvé) se joue sans chercher. Aucune recherche ne fera mieux, et cela
        # évite qu'un moteur profond joue un coup gagnant mais plus lent qu'un autre.
        if self.use_tablebase:
            proven = get_tablebase_lookup().choose_move(
                state.board,
                int(state.current_player),
                last_move,
                valid_actions,
                require_exact=True,
            )
            if proven is not None:
                return proven

        # Moteur Rust : recherche profonde, tablebase gérée de son côté.
        if self.use_engine:
            engine_move = self._engine_move(state, last_move, valid_actions)
            if engine_move is not None:
                return engine_move

        # Estimations du livre (non prouvées) : seulement si la recherche n'a rien donné.
        if self.use_tablebase:
            tb_move = get_tablebase_lookup().choose_move(
                state.board,
                int(state.current_player),
                last_move,
                valid_actions,
            )
            if tb_move is not None:
                return tb_move

        try:
            analysis = self._advisor.analyze_position(
                state.board,
                current_player=int(state.current_player),
                last_move=last_move,
                include_move_scores=False,
            )
            best_move = analysis.get("best_move")
            if best_move:
                move = (int(best_move[0]), int(best_move[1]))
                if move in valid_actions:
                    return move
        except Exception as exc:
            logger.warning(
                "Minimax niveau (d%d, %d ms) erreur : %s — coup fallback",
                self.depth,
                self.time_budget_ms,
                exc,
            )

        return valid_actions[0]


class BotRegistry:
    """Catalogue et instanciation des 6 niveaux de difficulté."""

    DEFAULT_BOT_ID = "level_3"

    _LEVELS: Dict[str, Dict[str, Any]] = {
        "level_1": {
            "name": "Niveau 1 — Débutant",
            "description": "Joue vite et commet beaucoup d'erreurs",
            "level": 1,
            "depth": 1,
            "time_budget_ms": 120,
            "use_tablebase": False,
            "blunder_rate": 0.55,
        },
        "level_2": {
            "name": "Niveau 2 — Facile",
            "description": "Repère les menaces immédiates, se trompe encore souvent",
            "level": 2,
            "depth": 2,
            "time_budget_ms": 250,
            "use_tablebase": False,
            "blunder_rate": 0.30,
        },
        "level_3": {
            "name": "Niveau 3 — Intermédiaire",
            "description": "Calcule plusieurs coups à l'avance",
            "level": 3,
            "depth": 4,
            "time_budget_ms": 600,
            "use_tablebase": False,
            "blunder_rate": 0.12,
        },
        "level_4": {
            "name": "Niveau 4 — Avancé",
            "description": "Recherche profonde et finales parfaites (tablebase)",
            "level": 4,
            "depth": 6,
            "time_budget_ms": 1000,
            "use_tablebase": True,
            "blunder_rate": 0.0,
        },
        "level_5": {
            "name": "Niveau 5 — Expert",
            "description": "Jeu quasi parfait : recherche maximale + tablebase",
            "level": 5,
            "depth": 10,
            "time_budget_ms": 1600,
            "use_tablebase": True,
            "blunder_rate": 0.0,
        },
        "level_6": {
            "name": "Niveau 6 — Maître",
            "description": "Moteur Rust : recherche profonde et finales exactes",
            "level": 6,
            "depth": 22,
            "time_budget_ms": 2500,
            "use_tablebase": True,
            "blunder_rate": 0.0,
            "use_engine": True,
        },
    }

    def __init__(self) -> None:
        self._bots: Dict[str, DifficultyBot] = {}

    def list_bots(self) -> List[Dict[str, Any]]:
        return [
            {
                "id": bot_id,
                "name": meta["name"],
                "description": meta["description"],
                "level": meta["level"],
            }
            for bot_id, meta in self._LEVELS.items()
        ]

    def is_valid_bot(self, bot_id: str) -> bool:
        return bot_id in self._LEVELS

    def _get_bot(self, bot_id: str) -> DifficultyBot:
        if bot_id not in self._bots:
            cfg = self._LEVELS[bot_id]
            self._bots[bot_id] = DifficultyBot(
                depth=cfg["depth"],
                time_budget_ms=cfg["time_budget_ms"],
                use_tablebase=cfg["use_tablebase"],
                blunder_rate=cfg["blunder_rate"],
                use_engine=cfg.get("use_engine", False),
            )
        return self._bots[bot_id]

    def choose_move(self, bot_id: str, engine: GameEngine) -> Optional[Tuple[int, int]]:
        if bot_id not in self._LEVELS:
            raise ValueError(f"Bot inconnu: {bot_id}")
        return self._get_bot(bot_id).choose_move(engine)
