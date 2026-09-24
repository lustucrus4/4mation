"""Compare le coup choisi par le moteur selon la profondeur et le mode de racine.

Le bot de niveau 6 joue avec `exact=False` (fenêtre rétrécie, élagage des symétries à la
racine, coupe dès qu'un gain est prouvé) ; l'analyse du site demande `exact=True`
(fenêtre pleine sur tous les coups de la racine). Si les deux ne désignent pas le même
meilleur coup, le bot joue autre chose que ce que le site lui prête dans ses propres
analyses — un écart invisible pour l'utilisateur et impossible à diagnostiquer à l'œil.

Le script rejoue une position à plusieurs profondeurs, dans les deux modes, et affiche
le coup retenu, le score, le temps et le taux de victoire des coups surveillés.

    python scripts/check_engine_root_modes.py --json _tmp_partie_diag.json
    python scripts/check_engine_root_modes.py --board 0000000/0000100/0002132/0002210/... 
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
for path in (str(ROOT), str(ROOT / "script")):
    if path not in sys.path:
        sys.path.insert(0, path)

from api.services.engine_client import EngineClient  # noqa: E402

DEPTHS = [14, 16, 18, 20, 22, 24]


def position_from_diag(path: Path, ply: int) -> Dict[str, Any]:
    """Extrait la position d'un demi-coup donné du journal de diagnostic."""
    data = json.loads(path.read_text(encoding="utf-8"))
    for entry in data["game"]["moves"]:
        if entry["ply"] == ply:
            return {
                "board": np.array(entry["board"], dtype=np.int8),
                "player": int(entry["player"]),
                "last_move": tuple(entry["last_move"]) if entry["last_move"] else None,
                "played": tuple(entry["move"]),
            }
    raise SystemExit(f"ply {ply} absent de {path}")


def scan(
    client: EngineClient,
    board: np.ndarray,
    player: int,
    last: Optional[Tuple[int, int]],
    exact: bool,
    watched: List[Tuple[int, int]],
    time_ms: int,
) -> None:
    mode = "exact (fenêtre pleine)" if exact else "rapide (fenêtre rétrécie)"
    print()
    print(f"Mode {mode}")
    header = (
        f"  {'visé':>5} {'atteint':>8} {'coup':>8} {'score':>7} {'état':>12} "
        f"{'temps':>8} {'nœuds':>12}  "
    )
    print(header + "  ".join(f"({r},{c})" for r, c in watched))
    for depth in DEPTHS:
        start = time.perf_counter()
        response = client.analyze(
            board, player, last, depth=depth, time_ms=time_ms, exact=exact
        )
        elapsed = time.perf_counter() - start
        if not response:
            print(f"  {depth:>5}  aucune réponse")
            continue
        best = response.get("best_move")
        best_txt = f"({best[0]},{best[1]})" if best else "—"
        scores: Dict[Tuple[int, int], int] = {}
        for m in response.get("moves") or []:
            move = m.get("move")
            if move is None:
                move = (m["row"], m["col"])
            scores[(int(move[0]), int(move[1]))] = int(m["score"])
        watched_txt = "  ".join(
            f"{scores.get(m, 0):>5}" if m in scores else "    —" for m in watched
        )
        etat = str(response.get("proven") or "—")
        if response.get("truncated"):
            etat += " tronqué"
        if response.get("mate_in"):
            etat += f" mat{response['mate_in']}"
        print(
            f"  {depth:>5} {int(response.get('depth') or 0):>8} {best_txt:>8} "
            f"{int(response.get('score') or 0):>7} {etat:>12} "
            f"{elapsed * 1000:>6.0f} ms {int(response.get('nodes') or 0):>12}  {watched_txt}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Comparaison des modes de racine du moteur")
    parser.add_argument("--json", default="_tmp_partie_diag.json")
    parser.add_argument("--ply", type=int, default=9)
    parser.add_argument("--time-ms", type=int, default=2500)
    parser.add_argument(
        "--watch",
        default=None,
        help="Coups à surveiller, au format r,c (défaut : le coup joué et le meilleur coup)",
    )
    parser.add_argument(
        "--modes",
        choices=["rapid", "exact", "both"],
        default="both",
        help="Modes de racine à mesurer (chacun dans un processus moteur neuf)",
    )
    args = parser.parse_args()

    diag = Path(args.json)
    if diag.exists():
        pos = position_from_diag(diag, args.ply)
        board, player, last = pos["board"], pos["player"], pos["last_move"]
        played = pos["played"]
        print(f"Position du ply {args.ply} de {diag.name} — joueur {player} au trait")
    else:
        raise SystemExit(f"Journal introuvable : {diag}")

    print("Plateau :")
    for row in board:
        print("  " + " ".join({0: ".", 1: "X", 2: "O"}[int(v)] for v in row))
    print(f"Dernier coup : {last}")

    client = EngineClient()
    if not client.is_available():
        raise SystemExit(f"Moteur introuvable : {client.binary}")
    client.close()

    if args.watch:
        watched = [tuple(int(x) for x in part.split(",")) for part in args.watch.split()]
    else:
        watched = [played]

    modes = {"rapid": [False], "exact": [True], "both": [False, True]}[args.modes]
    for exact in modes:
        # Un processus neuf par mode : la table de transposition est partagée entre
        # les requêtes d'un même processus, et un passage en fenêtre rétrécie y
        # laisse des bornes qui fausseraient la mesure du mode suivant.
        fresh = EngineClient()
        try:
            scan(fresh, board, player, last, exact, watched, args.time_ms)
        finally:
            fresh.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
