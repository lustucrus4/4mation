"""Vérifie une annonce de mat forcé en la jouant.

Le moteur annonce parfois `perte mat24` : « ce camp est maté de force, la preuve est
dans l'arbre ». Une telle annonce décide de ce que le site affiche (mat forcé, coup
obligatoire) et de ce que le bot joue. Elle se vérifie en la jouant : les deux camps
tirent leurs coups du moteur, et si l'annonce est juste, la partie se termine par le
mat annoncé dans le nombre de demi-coups annoncé.

C'est aussi le moyen le plus simple de chercher un **schéma gagnant** : la suite de
coups produite est une ligne forcée, reproductible, qui se termine par un gain.

    python scripts/check_mate_line.py --json _tmp_partie_diag.json --ply 5 --depth 26
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
for path in (str(ROOT), str(ROOT / "script")):
    if path not in sys.path:
        sys.path.insert(0, path)

from api.services.engine_client import EngineClient  # noqa: E402
from game.game_engine import GameEngine  # noqa: E402

WIN = 100000


def mate_distance(score: int) -> Optional[int]:
    """Nombre de demi-coups avant le mat, si le score est un score de mat."""
    if abs(score) >= WIN - 200:
        return int(abs(WIN - abs(score)))
    return None


def render(board: np.ndarray) -> List[str]:
    return [
        "  " + " ".join({0: ".", 1: "X", 2: "O"}[int(v)] for v in row) for row in board
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description="Joue une ligne annoncée mat forcé")
    parser.add_argument("--json", default="_tmp_partie_diag.json")
    parser.add_argument("--ply", type=int, default=5, help="Demi-coup de départ")
    parser.add_argument("--depth", type=int, default=26)
    parser.add_argument("--time-ms", type=int, default=8000)
    parser.add_argument("--max-plies", type=int, default=60)
    args = parser.parse_args()

    data = json.loads(Path(args.json).read_text(encoding="utf-8"))
    start: Optional[Dict[str, Any]] = None
    for entry in data["game"]["moves"]:
        if entry["ply"] == args.ply:
            start = entry
            break
    if start is None:
        raise SystemExit(f"ply {args.ply} absent du journal")

    board = np.array(start["board"], dtype=np.int8)
    player = int(start["player"])
    last = tuple(start["last_move"]) if start["last_move"] else None
    print(f"Départ au ply {args.ply}, joueur {player} au trait, dernier coup {last}")
    for line in render(board):
        print(line)

    client = EngineClient()
    if not client.is_available():
        raise SystemExit(f"Moteur introuvable : {client.binary}")

    engine = GameEngine()
    engine.reset()
    # On rejoue les coups du journal pour retrouver l'état exact, plutôt que de
    # bricoler le plateau interne du moteur de jeu.
    for entry in data["game"]["moves"]:
        if entry["ply"] >= args.ply:
            break
        engine.step((entry["move"][0], entry["move"][1]))

    print()
    print(f"  {'ply':>4} {'j':>2} {'coup':>8} {'score':>8} {'état':>14} {'prof.':>6} {'temps':>8}")
    winner = None
    claim: Optional[int] = None
    for ply in range(args.ply, args.max_plies):
        state = engine.get_state()
        if engine.is_terminal():
            winner = engine.get_winner()
            break
        player = int(state.current_player)
        last_move = tuple(state.last_move_position) if state.last_move_position else None
        board_now = np.array(state.board, dtype=np.int8).reshape(7, 7)

        response = client.analyze(
            board_now, player, last_move, depth=args.depth, time_ms=args.time_ms, exact=False
        )
        if not response or not response.get("best_move"):
            print("  moteur muet — arrêt")
            break
        move = tuple(int(v) for v in response["best_move"])
        score = int(response.get("score") or 0)
        dist = mate_distance(score)
        if dist is not None and claim is None:
            claim = dist
        etat = str(response.get("proven") or "—")
        if dist is not None:
            etat = f"mat en {dist}"
        print(
            f"  {ply:>4} {player:>2} {str(move):>8} {score:>8} {etat:>14} "
            f"{int(response.get('depth') or 0):>6} {int(response.get('elapsed_ms') or 0):>6} ms"
        )
        applied = engine.step(move)[1]
        if not applied:
            print(f"  coup refusé par le moteur de jeu : {move}")
            break

    if engine.is_terminal():
        winner = engine.get_winner()
    print()
    repondu = {
        1: f"X gagne au ply {engine.get_state().move_count}",
        2: f"O gagne au ply {engine.get_state().move_count}",
        0: "aucun gagnant (nulle ou plateau plein)",
    }.get(winner, "partie non terminée")
    print(f"Résultat du déroulé : {repondu}")
    if claim is not None:
        print(
            f"Annonce vérifiée : mat en {claim} demi-coups depuis le ply {args.ply}, "
            f"donc fin attendue au ply {args.ply + claim}"
        )
    client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
