"""Registre des bots IA de 4mation — échelle de difficulté graduée.

Six niveaux, du plus facile au plus fort, jusqu'à un niveau « Impossible » qui
joue les lignes **prouvées** (tablebase exacte, gain forcé du centre) sans commettre
aucune erreur.

Trois leviers, appliqués de façon strictement croissante :

- ``depth`` / ``time_budget_ms`` : force de la recherche ;
- ``blunder_rate`` : probabilité de jouer un coup **au hasard** parmi les coups
  légaux. Réservé aux niveaux faibles : une telle faute est immédiatement
  exploitable, donc trop brutale pour graduer finement le haut de l'échelle ;
- ``inaccuracy_rate`` : probabilité de jouer un coup **un peu moins bon** (le 2ᵉ choix
  du moteur, strictement moins bien noté) au lieu du meilleur. C'est le levier de
  précision du haut de l'échelle : le bot reste fort mais laisse une ouverture ;
- ``use_tablebase`` (finales exactes + repli livre estimé) et ``proven_line``
  (raccourci sur les positions **prouvées** du livre / de la tablebase).

Le raccourci ``proven_line`` rend un bot **infaillible** : sur une position prouvée
(ouverture exacte du livre, finale exacte), il joue la preuve sans rechercher. Quand
``inaccuracy_rate`` se déclenche, le bot **renonce volontairement** à la preuve ce
coup-là : c'est ce qui rend « Difficile » battable là où « Impossible » ne l'est pas.

Conséquence de conception : à partir du niveau 4, deux bots jouent la **même** ligne
prouvée ; leur seule différence est le taux d'erreur graduée. Il doit donc être
franchement décroissant (0.16 → 0.04 → 0.00), sinon les niveaux deviennent
indiscernables en confrontation directe.

``use_engine`` branche le moteur Rust ``4mation-engine`` (processus persistant). Si
le binaire est absent, le niveau retombe automatiquement sur le chemin Minimax.

Limite honnête du niveau 6 : « Impossible » n'est infaillible que dans la zone
**résolue** (tablebase exacte + livre). L'ouverture du 4mation n'est pas résolue, et
là le bot redevient un moteur très fort mais faillible. Mesuré : un proxy humain de
profondeur 6 et 15 % d'erreurs marque encore 0.19 contre lui sur 96 parties, et 0.38
en profondeur 8 / 6 % d'erreurs. Augmenter la profondeur ne corrige pas ce taux
(mesuré : d34/6 s fait *moins* bien que d26/3 s), car le problème est la couverture de
la base, pas la vitesse de recherche.
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
        proven_line: bool = False,
        inaccuracy_rate: float = 0.0,
    ) -> None:
        self.depth = depth
        self.time_budget_ms = time_budget_ms
        self.use_tablebase = use_tablebase
        self.blunder_rate = blunder_rate
        self.use_engine = use_engine
        self.proven_line = proven_line
        self.inaccuracy_rate = inaccuracy_rate
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

    @staticmethod
    def _pick_worse(
        response: Dict[str, Any],
        valid_actions: List[Tuple[int, int]],
    ) -> Optional[Tuple[int, int]]:
        """Coup strictement moins bon que le meilleur, parmi les 2 plus proches.

        On se restreint aux coups dont le score est **strictement inférieur** à celui du
        meilleur : les coups à égalité sont d'excellents coups déguisés, les jouer ne
        serait pas une erreur. On prend les deux moins pénalisants pour rester crédible.
        """
        scored: List[Tuple[float, Tuple[int, int]]] = []
        for entry in response.get("moves") or []:
            try:
                row, col = int(entry["row"]), int(entry["col"])
                score = float(entry.get("score", 0.0))
            except (KeyError, TypeError, ValueError):
                continue
            move = (row, col)
            if move in valid_actions:
                scored.append((score, move))
        if len(scored) < 2:
            return None
        scored.sort(key=lambda item: item[0], reverse=True)
        best_score = scored[0][0]
        worse = [move for score, move in scored if score < best_score]
        if not worse:
            return None
        return random.choice(worse[:2])

    def _engine_play(
        self,
        state: Any,
        last_move: Optional[Tuple[int, int]],
        valid_actions: List[Tuple[int, int]],
        prefer_worse: bool,
    ) -> Optional[Tuple[int, int]]:
        """Coup du moteur Rust, ou None si indisponible / coup inutilisable.

        Si `prefer_worse`, joue volontairement le 2ᵉ meilleur coup (erreur graduée) ;
        c'est ce qui différencie « Difficile » de « Impossible ».
        """
        client = get_engine_client()
        if not client.is_available():
            return None
        try:
            response = client.analyze(
                state.board,
                int(state.current_player),
                last_move,
                depth=self.depth,
                time_ms=self.time_budget_ms,
                exact=False,
            )
        except Exception as exc:
            logger.warning("Moteur Rust en erreur : %s — repli Minimax", exc)
            return None

        if not response:
            return None

        if prefer_worse:
            alternative = self._pick_worse(response, valid_actions)
            if alternative is not None:
                return alternative

        move = response.get("best_move")
        if not (isinstance(move, (list, tuple)) and len(move) >= 2):
            return None
        best = (int(move[0]), int(move[1]))
        if best not in valid_actions:
            logger.warning("Moteur Rust propose un coup illégal %s — coup ignoré", best)
            return None
        return best

    def choose_move(self, engine: GameEngine) -> Optional[Tuple[int, int]]:
        valid_actions = engine.get_valid_actions()
        if not valid_actions:
            return None

        # Erreur franche : un coup au hasard (réservé aux niveaux faibles).
        if self.blunder_rate > 0.0 and random.random() < self.blunder_rate:
            return random.choice(valid_actions)

        state = engine.get_state()
        last_move = self._last_move(engine)

        # Erreur graduée : jouer un coup un peu moins bon, et surtout NE PAS se reposer
        # sur la preuve ce coup-là. C'est ce levier qui rend « Difficile » battable
        # alors que « Impossible » ne l'est pas.
        graded_error = self.inaccuracy_rate > 0.0 and random.random() < self.inaccuracy_rate

        # Preuve d'abord : une position dont la valeur est démontrée (tablebase exacte ou
        # livre prouvé) se joue sans chercher. Aucune recherche ne fera mieux, et cela
        # évite qu'un moteur profond joue un coup gagnant mais plus lent qu'un autre.
        if self.proven_line and not graded_error:
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
            engine_move = self._engine_play(state, last_move, valid_actions, graded_error)
            if engine_move is not None:
                return engine_move

        # Preuve en secours si le moteur est absent (on ne peut pas faire mieux).
        if self.proven_line and graded_error:
            proven = get_tablebase_lookup().choose_move(
                state.board,
                int(state.current_player),
                last_move,
                valid_actions,
                require_exact=True,
            )
            if proven is not None:
                return proven

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

    # Échelle de difficulté : chaque niveau est strictement plus fort que le précédent.
    # Niveaux 1-3 : faiblesse franche par `blunder_rate` (coups au hasard) et recherche
    # courte. Niveaux 4-6 : même ligne prouvée, donc leur SEULE différence est
    # `inaccuracy_rate` (erreur graduée), qui doit rester franchement décroissant sinon
    # ils deviennent indiscernables. `proven_line` + `inaccuracy_rate = 0` = infaillible.
    #
    # Réglages mesurés (voir scripts/ARENA_BOTS.md).
    # Score du proxy humain en siège 1, 96 parties/niveau/profil, budgets réduits (--fast) :
    #   niveau   novice   débutant   moyen   avancé
    #     1        0.99     0.94       1.00    1.00
    #     2        0.91     0.80       0.96    0.98
    #     3        0.77     0.60       0.91    0.98
    #     4        0.61     0.29       0.72    0.87
    #     5        0.26     0.14       0.51    0.56
    #     6        0.01     0.03       0.17    0.28
    # Verdict (scripts/bot_arena.py) : les 5 paires adjacentes sont validées, chacune
    # démontrée par les QUATRE profils de sonde ; la confrontation directe (sièges alternés,
    # 60 parties/paire) démontre en plus les 4 premières paires (le score du plus faible
    # reste sous 0.50, IC exclu). Aucune inversion, aucune paire indiscernable.
    #   score du plus faible en direct : 0.34 / 0.33 / 0.27 / 0.35 / 0.39 (L5→L6 : IC à
    #   0.50, paire démontrée par les sondes uniquement).
    #
    # Réglage de `level_5` — mesuré, pas deviné. Avec 4 % d'écarts et une profondeur 16, le
    # niveau 5 collait tellement à la ligne théorique qu'il devenait PLUS PRÉVISIBLE, donc
    # plus facile à battre que le niveau 4 pour un adversaire fort (0.89 contre 0.77 pour la
    # sonde « avancé ») : une inversion de difficulté ressentie, alors que la force restait
    # correctement ordonnée. Passer à 8 % d'écarts avec une profondeur 18 fait s'écarter le
    # bot plus souvent, mais en choisissant mieux ses écarts : la courbe de sonde redevient
    # strictement décroissante sur les 4 profils (0.87 → 0.56 pour « avancé ») sans casser
    # la séparation directe avec `level_4` (0.35 [0.24, 0.48]).
    # `scripts/check_bot_arena.py` échoue si l'une de ces deux propriétés régresse.
    _LEVELS: Dict[str, Dict[str, Any]] = {
        "level_1": {
            "name": "Niveau 1 — Très facile",
            "description": "Joue presque au hasard : un débutant gagne quasiment à tous les coups",
            "level": 1,
            "depth": 1,
            "time_budget_ms": 60,
            "use_tablebase": False,
            "proven_line": False,
            "use_engine": True,
            "blunder_rate": 0.95,
            "inaccuracy_rate": 0.0,
        },
        "level_2": {
            "name": "Niveau 2 — Facile",
            "description": "Joue au hasard près de trois coups sur quatre : on gagne souvent",
            "level": 2,
            "depth": 2,
            "time_budget_ms": 120,
            "use_tablebase": False,
            "proven_line": False,
            "use_engine": True,
            "blunder_rate": 0.70,
            "inaccuracy_rate": 0.0,
        },
        "level_3": {
            "name": "Niveau 3 — Moyen",
            "description": "Voit quelques coups d'avance mais laisse encore de vraies ouvertures",
            "level": 3,
            "depth": 4,
            "time_budget_ms": 300,
            "use_tablebase": False,
            "proven_line": False,
            "use_engine": True,
            "blunder_rate": 0.40,
            "inaccuracy_rate": 0.0,
        },
        "level_4": {
            "name": "Niveau 4 — Difficile",
            "description": "Joue la preuve en ouverture et en finale, mais se relâche encore souvent",
            "level": 4,
            "depth": 8,
            "time_budget_ms": 1200,
            "use_tablebase": True,
            "proven_line": True,
            "use_engine": True,
            "blunder_rate": 0.0,
            "inaccuracy_rate": 0.16,
        },
        "level_5": {
            "name": "Niveau 5 — Très difficile",
            "description": "Recherche très profonde, lignes prouvées, erreurs rares",
            "level": 5,
            "depth": 18,
            "time_budget_ms": 2000,
            "use_tablebase": True,
            "proven_line": True,
            "use_engine": True,
            "blunder_rate": 0.0,
            "inaccuracy_rate": 0.08,
        },
        "level_6": {
            "name": "Niveau 6 — Impossible",
            "description": "Joue les lignes prouvées sans jamais se tromper (gagne de force)",
            "level": 6,
            "depth": 26,
            "time_budget_ms": 3000,
            "use_tablebase": True,
            "proven_line": True,
            "use_engine": True,
            "blunder_rate": 0.0,
            "inaccuracy_rate": 0.0,
        },
    }

    def __init__(self) -> None:
        self._bots: Dict[str, DifficultyBot] = {}

    def list_bots(self) -> List[Dict[str, Any]]:
        """Les six niveaux, triés du plus facile au plus dur.

        Le tri est explicite (et non l'ordre d'insertion du dictionnaire) : l'API ne doit
        jamais présenter l'échelle dans un autre ordre, sinon le joueur choisirait un
        « adversaire » sans repère de difficulté. `scripts/check_bot_arena.py` verrouille
        cette propriété.
        """
        return [
            {
                "id": bot_id,
                "name": meta["name"],
                "description": meta["description"],
                "level": meta["level"],
            }
            for bot_id, meta in sorted(
                self._LEVELS.items(), key=lambda item: item[1]["level"]
            )
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
                proven_line=cfg.get("proven_line", False),
                inaccuracy_rate=cfg.get("inaccuracy_rate", 0.0),
            )
        return self._bots[bot_id]

    def choose_move(self, bot_id: str, engine: GameEngine) -> Optional[Tuple[int, int]]:
        if bot_id not in self._LEVELS:
            raise ValueError(f"Bot inconnu: {bot_id}")
        return self._get_bot(bot_id).choose_move(engine)
