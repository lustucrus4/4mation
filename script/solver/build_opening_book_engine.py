#!/usr/bin/env python3
"""Livre d'ouverture évalué par le moteur Rust `4mation-engine`.

Même parcours, mêmes clés et mêmes lignes que `build_opening_book.py` — mais
l'estimation ne passe plus par le Minimax Python et le MCTS : elle vient du moteur.

Deux natures d'entrées, distinguées par la colonne ``exact`` :

- ``exact=1`` : le moteur a **prouvé** la valeur (mat forcé, ou verdict lu dans la
  tablebase). ``win_rate`` vaut alors exactement 1,0 / 0,5 / 0,0.
- ``exact=0`` : **estimation**. Le score du moteur est une évaluation heuristique
  dont l'unité est la menace immédiate (voir ``evaluate`` dans ``engine.rs`` : une
  menace vaut 60 points, une ligne potentielle 1 point, le centre 3 points). Il est
  converti en taux de victoire par une sigmoïde d'échelle ``--score-scale``, le
  signe donnant le résultat. C'est une estimation assumée, pas une mesure : la
  constante est réglable et devra être calibrée sur les positions exactes de la
  tablebase.

Usage :
    python script/solver/build_opening_book_engine.py --max-ply 4 --max-positions 500
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path
from typing import Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent.parent
for _p in (str(ROOT), str(ROOT / "script")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from api.services.engine_client import EngineClient  # noqa: E402
from api.services.engine_analysis import ENGINE_SCALE_FILE, DEFAULT_SCALE  # noqa: E402
from game_tree.optimized_minimax import OptimizedMinimaxAdvisor  # noqa: E402
from solver.build_opening_book import (  # noqa: E402
    DEFAULT_DB,
    _collect_positions,
    _store_opening,
    _try_exact,
)
from solver.db_schema import init_db  # noqa: E402
from solver.retrograde_solver import RESULT_DRAW, RESULT_LOSS, RESULT_WIN  # noqa: E402


def calibrated_scale() -> float:
    """Échelle score → taux de victoire, lue dans le fichier de calibrage.

    Le livre et l'API doivent parler la même langue : une entrée écrite avec une
    échelle et relue avec une autre donnerait des taux de victoire incohérents d'une
    couche à l'autre. Si le calibrage n'a pas été exécuté, on retombe sur la constante
    historique.
    """
    try:
        if ENGINE_SCALE_FILE.exists():
            data = json.loads(ENGINE_SCALE_FILE.read_text(encoding="utf-8"))
            scale = float(data.get("scale") or 0)
            if scale > 0:
                return scale
    except Exception:
        pass
    return DEFAULT_SCALE


# Échelle de la sigmoïde quand le calibrage n'a pas tourné : un écart d'une « menace
# immédiate » (60 points d'évaluation) fait alors passer le taux de 50 % à 62 %.
DEFAULT_SCORE_SCALE = 120.0


def _budget(ply: int) -> Tuple[int, int]:
    """(profondeur, budget ms) du moteur selon le ply.

    Les tout premiers coups sont peu nombreux mais très consultés : on y investit.
    Mesuré : sur le plateau vide, la profondeur 20 en 4 s donne (3,3) avec un score
    stable, alors qu'un budget de 200 ms renvoie une réponse tronquée donc fausse.
    En profondeur, la recherche devient trop nombreuse pour être payée à ce prix.
    """
    if ply <= 1:
        return 20, 4000
    if ply == 2:
        return 18, 2500
    if ply <= 6:
        return 14, 1000
    return 12, 500


def map_score(
    score: int, proven: Optional[str], scale: float = DEFAULT_SCORE_SCALE
) -> Tuple[str, float, bool]:
    """(résultat, taux de victoire, exact) pour une évaluation du moteur.

    ``proven`` est le verdict du moteur : ``gain`` / ``perte`` / ``nulle`` quand il a
    la preuve (mat ou tablebase), ``aucune preuve`` sinon.
    """
    if proven == "gain":
        return RESULT_WIN, 1.0, True
    if proven == "perte":
        return RESULT_LOSS, 0.0, True
    if proven == "nulle":
        return RESULT_DRAW, 0.5, True

    win_rate = 1.0 / (1.0 + math.exp(-score / scale))
    if score >= scale:
        return RESULT_WIN, win_rate, False
    if score <= -scale:
        return RESULT_LOSS, win_rate, False
    return RESULT_DRAW, win_rate, False


def build(
    db_path: Path,
    *,
    max_ply: int,
    max_positions: int,
    score_scale: float,
    quality: str = "full",
    min_depth: Optional[int] = None,
    min_time_ms: Optional[int] = None,
    budget_factor: float = 1.0,
    verbose: bool = True,
) -> Tuple[int, int]:
    """Parcourt le livre et remplace chaque estimation par celle du moteur.

    Renvoie (entrées écrites, dont exactes).
    """
    conn = init_db(db_path)
    advisor = OptimizedMinimaxAdvisor(depth=1, use_iterative_deepening=False)
    client = EngineClient(
        default_depth=min_depth or 20, default_time_ms=min_time_ms or 4000
    )
    if not client.is_available():
        raise SystemExit(
            f"Moteur introuvable : {client.binary}\n"
            "Compiler avec : cd script/solver_rust && cargo build --release"
        )

    positions = _collect_positions(advisor, max_ply, max_positions, quality=quality)
    # Plus profond d'abord : les entrées exactes écrites pour un enfant peuvent
    # prouver son parent dans la foulée.
    positions.sort(key=lambda p: p[3], reverse=True)

    if verbose:
        print(f"{len(positions)} positions collectées (ply <= {max_ply}).")

    written = 0
    n_exact = 0
    n_engine_exact = 0
    n_estimated = 0
    started = time.perf_counter()

    for i, (board, player, last_move, ply, h) in enumerate(positions):
        exact = _try_exact(conn, advisor, board, player, last_move)
        if exact is not None:
            result, win_rate, best = exact
            _store_opening(
                conn,
                h,
                result,
                win_rate,
                best,
                ply,
                exact=1,
                board=board,
                current_player=player,
                last_move=last_move,
                store_board=True,
            )
            written += 1
            n_exact += 1
        else:
            depth, time_ms = _budget(ply)
            if min_depth is not None:
                depth = max(depth, min_depth)
            if min_time_ms is not None:
                time_ms = max(time_ms, min_time_ms)
            time_ms = int(time_ms * budget_factor)
            analysis = client.analyze(
                board, player, last_move, depth=depth, time_ms=time_ms, exact=False
            )
            if not analysis:
                continue
            best_move = analysis.get("best_move")
            if not best_move:
                continue
            result, win_rate, proven = map_score(
                int(analysis.get("score") or 0), analysis.get("proven"), score_scale
            )
            _store_opening(
                conn,
                h,
                result,
                win_rate,
                (int(best_move[0]), int(best_move[1])),
                ply,
                exact=1 if proven else 0,
                board=board,
                current_player=player,
                last_move=last_move,
                store_board=True,
            )
            written += 1
            if proven:
                n_engine_exact += 1
            else:
                n_estimated += 1

        if (i + 1) % 10 == 0:
            conn.commit()
            if verbose:
                elapsed = max(time.perf_counter() - started, 0.001)
                print(
                    f"  {i + 1}/{len(positions)} | {written} écrites "
                    f"({n_exact} tablebase + {n_engine_exact} prouvées moteur, "
                    f"{n_estimated} estimées) | {written / elapsed:.2f}/s"
                )

    conn.commit()
    conn.close()
    client.close()

    if verbose:
        print(
            f"Terminé : {written} entrées écrites — {n_exact} promues exactes depuis la "
            f"tablebase, {n_engine_exact} prouvées par le moteur, "
            f"{n_estimated} estimées par le moteur."
        )
    return written, n_exact + n_engine_exact


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Livre d'ouverture évalué par le moteur Rust 4mation-engine"
    )
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--max-ply", type=int, default=4)
    parser.add_argument("--max-positions", type=int, default=500)
    parser.add_argument(
        "--score-scale",
        type=float,
        default=None,
        help="Échelle de la sigmoïde score → taux de victoire (défaut: le calibrage mesuré)",
    )
    parser.add_argument(
        "--budget-factor",
        type=float,
        default=1.0,
        help="Multiplie le budget temps par position (0.25 = exploration rapide)",
    )
    parser.add_argument("--min-depth", type=int, default=None)
    parser.add_argument("--min-time-ms", type=int, default=None)
    args = parser.parse_args()

    scale = args.score_scale if args.score_scale is not None else calibrated_scale()
    origin = "argument" if args.score_scale is not None else "calibrage mesuré"
    print(
        f"Livre d'ouverture par le moteur — ply <= {args.max_ply}, "
        f"{args.max_positions} positions max, échelle {scale:g} ({origin})"
    )
    build(
        Path(args.db),
        max_ply=args.max_ply,
        max_positions=args.max_positions,
        score_scale=scale,
        budget_factor=args.budget_factor,
        min_depth=args.min_depth,
        min_time_ms=args.min_time_ms,
    )


if __name__ == "__main__":
    main()
