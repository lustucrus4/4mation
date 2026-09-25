"""Analyse de position par le moteur Rust, au format attendu par l'API.

`TablebaseLookup.analyze_position` est le point d'entrée unique de toute l'analyse du
site : coach, revue de partie, puzzles, explorateur d'ouvertures. Ce module fournit la
brique qui remplace, pour les positions **non prouvées**, l'ancienne estimation
(remontée depuis les enfants du livre, ou MCTS) par l'analyse du moteur.

Ce qui distingue les deux sources :

- ``exact=True`` : la valeur de la position est **prouvée** (mat forcé trouvé par la
  recherche, ou lecture de la tablebase). Le taux de victoire vaut alors exactement
  1,0 / 0,5 / 0,0 — ce n'est pas une estimation.
- ``exact=False`` : **estimation**. Le score du moteur n'est pas un taux de victoire,
  c'est une évaluation heuristique (une menace immédiate vaut 60 points, une ligne
  potentielle 1, le centre 3). On le convertit par une sigmoïde dont l'échelle a été
  calibrée sur les finales exactes de la tablebase par
  ``script/solver/calibrate_engine_scale.py`` (voir ``engine_scale.json``).

La distinction est essentielle pour la revue de partie : un coup qui manque un mat est
un « blunder » certain, alors qu'un écart entre deux estimations n'est qu'un indice.
"""

from __future__ import annotations

import json
import logging
import math
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from api.services.engine_client import EngineClient, get_engine_client

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCALE_FILE = REPO_ROOT / "script" / "solver" / "data" / "engine_scale.json"
# Nom explicite pour les scripts qui veulent lire le calibrage (constructeur du livre).
ENGINE_SCALE_FILE = SCALE_FILE

# Échelle par défaut si le calibrage n'a pas été exécuté. 120 est la valeur
# historiquement utilisée par le constructeur du livre ; le calibrage mesuré sur les
# finales donne un ordre de grandeur plus large (~280), c'est-à-dire des taux moins
# tranchés à score égal.
DEFAULT_SCALE = 120.0

# Scores de mat du moteur (voir `engine.rs`) : au-delà de `MATE_MARGIN`, le score
# décrit un mat forcé et non une estimation.
WIN = 100_000

# Bornes de sécurité sur la profondeur et le budget d'analyse du site.
MIN_DEPTH, MAX_DEPTH = 4, 30
MAX_TIME_MS = 6000


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "").strip() or default)
    except ValueError:
        return default


def analyze_depth() -> int:
    return max(MIN_DEPTH, min(MAX_DEPTH, _env_int("ENGINE_ANALYZE_DEPTH", 14)))


def analyze_time_ms() -> int:
    return max(50, min(MAX_TIME_MS, _env_int("ENGINE_ANALYZE_TIME_MS", 700)))


class _ScaleCache:
    """Lit `engine_scale.json` une fois, et le relit s'il change sur le disque."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._scale = DEFAULT_SCALE
        self._meta: Dict[str, Any] = {}
        self._mtime = 0.0
        self._load()

    def _load(self) -> None:
        try:
            if not self.path.exists():
                return
            mtime = self.path.stat().st_mtime
            if mtime == self._mtime:
                return
            data = json.loads(self.path.read_text(encoding="utf-8"))
            scale = float(data.get("scale") or 0)
            if scale > 0:
                self._scale = scale
                self._meta = data
                self._mtime = mtime
                logger.info(
                    "Échelle de score du moteur : %.1f (calibrée, %s positions, Brier %.4f)",
                    scale,
                    data.get("samples"),
                    float(data.get("brier") or 0.0),
                )
        except Exception:
            logger.warning("engine_scale.json illisible — échelle par défaut", exc_info=True)

    @property
    def scale(self) -> float:
        self._load()
        return self._scale

    @property
    def meta(self) -> Dict[str, Any]:
        self._load()
        return self._meta


_scale_cache: Optional[_ScaleCache] = None


def get_scale_cache() -> _ScaleCache:
    global _scale_cache
    if _scale_cache is None:
        _scale_cache = _ScaleCache(SCALE_FILE)
    return _scale_cache


def score_to_win_rate(score: float, scale: Optional[float] = None) -> float:
    """Taux de victoire estimé pour un score heuristique (sigmoïde)."""
    s = float(scale if scale is not None else get_scale_cache().scale)
    z = max(-60.0, min(60.0, float(score) / s))
    return 1.0 / (1.0 + math.exp(-z))


def result_for(score: float, proven: Optional[str] = None) -> Tuple[str, float, bool]:
    """(résultat, taux de victoire, exact) pour un score et un verdict du moteur.

    ``proven`` vaut ``gain`` / ``perte`` / ``nulle`` quand le moteur a la preuve
    (mat forcé ou tablebase), ``aucune preuve`` sinon.
    """
    if proven == "gain":
        return "W", 1.0, True
    if proven == "perte":
        return "L", 0.0, True
    if proven == "nulle":
        return "D", 0.5, True
    return _estimate_result(score), score_to_win_rate(score), False


def _estimate_result(score: float) -> str:
    if score > 0:
        return "W"
    if score < 0:
        return "L"
    return "D"


def _move_label(proven: str) -> Optional[str]:
    """Verdict du moteur pour une estimation de coup."""
    if proven in ("gain", "perte", "nulle"):
        return proven
    return None


def _mate_in_moves(score: float, proven: str) -> Optional[int]:
    """Convertit un score de mat en « nombre de coups » lisibles (demi-coups → coups)."""
    if proven not in ("gain", "perte"):
        return None
    half = int(abs(WIN - abs(float(score))))
    return max(1, (half + 1) // 2)


def build_analysis(
    board: Any,
    current_player: int,
    last_move: Optional[Sequence[int]],
    response: Dict[str, Any],
    *,
    elapsed_ms: Optional[int] = None,
    depth: Optional[int] = None,
) -> Dict[str, Any]:
    """Convertit une réponse du moteur en analyse au format de l'API.

    Le format est celui que produisent ``TablebaseLookup._opening_book_analysis`` et
    ``_build_mcts_analysis`` : ``moves`` (avec ``row``/``col``/``win_rate``/``result``),
    ``best_move``, ``position_win_rate``, ``source``, ``exact``, ``label``,
    ``coverage_percent``. Les consommateurs existants (revue, coach, puzzles,
    explorateur) continuent donc de fonctionner sans modification.
    """
    scale = get_scale_cache().scale
    proven = str(response.get("proven") or "aucune preuve")
    pos_result, pos_wr, pos_exact = result_for(float(response.get("score") or 0), proven)
    position_mate = _mate_in_moves(float(response.get("score") or 0), proven)

    moves_out: List[Dict[str, Any]] = []
    for m in response.get("moves") or []:
        score = float(m.get("score") or 0)
        move_proven = str(m.get("proven") or "aucune preuve")
        result, wr, is_proven_move = result_for(score, _move_label(move_proven))
        moves_out.append(
            {
                "move": (int(m["row"]), int(m["col"])),
                "row": int(m["row"]),
                "col": int(m["col"]),
                "win_rate": wr,
                "result": result,
                "score": int(score),
                "proven": move_proven,
                "proven_move": is_proven_move,
                "mate_in": _mate_in_moves(score, move_proven),
            }
        )

    moves_out.sort(key=lambda x: x["win_rate"], reverse=True)
    best_move = None
    raw_best = response.get("best_move")
    if isinstance(raw_best, (list, tuple)) and len(raw_best) >= 2:
        best_move = (int(raw_best[0]), int(raw_best[1]))
    elif moves_out:
        best_move = moves_out[0]["move"]

    valid_count = int(response.get("valid_moves_count") or len(moves_out))
    coverage = 100.0 * len(moves_out) / valid_count if valid_count else 100.0
    truncated = bool(response.get("truncated"))

    if pos_exact:
        if proven == "nulle":
            label = "Nulle exacte (moteur)"
        elif proven == "gain":
            label = f"Mat forcé en {position_mate} coup(s)" if position_mate else "Gain exact (moteur)"
        else:
            label = f"Perte forcée en {position_mate} coup(s)" if position_mate else "Perte exacte (moteur)"
    elif truncated:
        label = "Estimation (moteur, recherche interrompue)"
    else:
        label = f"Estimation (moteur, profondeur {response.get('depth')})"

    if pos_wr <= 0.005:
        pos_result = "L"
    elif pos_wr >= 0.995:
        pos_result = "W"

    analysis: Dict[str, Any] = {
        "moves": moves_out,
        "best_move": best_move,
        "current_player": int(current_player),
        "valid_moves_count": valid_count,
        "elapsed_ms": int(elapsed_ms if elapsed_ms is not None else response.get("elapsed_ms") or 0),
        "source": "engine",
        "exact": pos_exact,
        "label": label,
        "position_win_rate": pos_wr,
        "position_result": pos_result,
        "coverage_percent": coverage,
        "truncated": truncated,
        "engine_depth": int(response.get("depth") or depth or 0),
        "engine_nodes": int(response.get("nodes") or 0),
        "engine_scale": scale,
        "mate_in": position_mate if pos_exact else None,
        "last_move": list(last_move) if last_move is not None else None,
    }
    return analysis


def engine_analysis(
    board: Any,
    current_player: int,
    last_move: Optional[Sequence[int]] = None,
    *,
    depth: Optional[int] = None,
    time_ms: Optional[int] = None,
    client: Optional[EngineClient] = None,
    exact: bool = True,
) -> Optional[Dict[str, Any]]:
    """Analyse d'une position par le moteur, ou ``None`` s'il est indisponible.

    ``exact=True`` demande la fenêtre pleine sur chaque coup de la racine : sans cela
    les scores des coups non joués ne sont que des bornes (un coup perdant peut
    s'afficher à −147 au lieu de « perte forcée »). C'est indispensable pour analyser,
    superflu pour un bot qui ne joue que son meilleur coup.
    """
    cli = client or get_engine_client()
    if not cli.is_available():
        return None
    d = depth if depth is not None else analyze_depth()
    t = time_ms if time_ms is not None else analyze_time_ms()
    started = time.perf_counter()
    response = cli.analyze(
        board, current_player, last_move, depth=d, time_ms=t, exact=exact
    )
    if not response or response.get("error"):
        if response and response.get("error"):
            logger.warning("Moteur : %s", response["error"])
        return None
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    return build_analysis(
        board, current_player, last_move, response, elapsed_ms=elapsed_ms, depth=d
    )
