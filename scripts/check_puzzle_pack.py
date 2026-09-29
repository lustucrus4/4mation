"""Verifie l'integrite de l'arbre de solution du pack de puzzles.

Pour chaque noeud de l'arbre precalcule :

- chaque coup liste est accepte par `check_pack_puzzle_move` ;
- sa reponse adverse est celle du noeud enfant, qui existe bien ;
- un coup legal non liste est refuse, et n'est jamais annonce comme une defaite ;
- en suivant les premiers coups acceptes depuis la racine, le puzzle se resout.

Usage:
    cd 4mation
    set PYTHONPATH=.;script
    python scripts/check_puzzle_pack.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "script"))

from api.services.puzzle_service import check_pack_puzzle_move  # noqa: E402
from game.game_engine import GameEngine  # noqa: E402

HUMAN = 1
PACK_PATH = ROOT / "api" / "data" / "puzzles.json"


def _engine_from_history(history: List[Dict[str, int]]) -> GameEngine:
    engine = GameEngine()
    engine.reset()
    for h in history:
        engine.step((int(h["row"]), int(h["col"])))
    return engine


def _parse_cle(cle: str) -> List[Dict[str, int]]:
    moves: List[Dict[str, int]] = []
    for index, token in enumerate(t for t in cle.split(";") if t):
        row, col = token.split(",")
        moves.append({"player": HUMAN if index % 2 == 0 else 2, "row": int(row), "col": int(col)})
    return moves


def _cle_de(played: List[Dict[str, int]]) -> str:
    return ";".join(f"{int(m['row'])},{int(m['col'])}" for m in played)


def _verifier_puzzle(puzzle: Dict[str, Any], erreurs: List[str]) -> Tuple[int, int]:
    puzzle_id = puzzle["id"]
    setup = puzzle["history"]
    nodes = puzzle["nodes"]
    noeuds = 0
    coups = 0

    for cle, node in nodes.items():
        noeuds += 1
        played = _parse_cle(cle)
        history = setup + played
        engine = _engine_from_history(history)
        if engine.is_terminal():
            erreurs.append(f"{puzzle_id} [{cle or 'racine'}] : noeud terminal dans l'arbre")
            continue
        if int(engine.get_current_player()) != HUMAN:
            erreurs.append(f"{puzzle_id} [{cle or 'racine'}] : l'humain n'est pas au trait")
            continue

        acceptes = {f"{int(r)},{int(c)}": [int(r), int(c)] for r, c in node["moves"]}
        if not acceptes:
            erreurs.append(f"{puzzle_id} [{cle or 'racine'}] : aucun coup accepte")
            continue

        for move_key, move in acceptes.items():
            coups += 1
            res = check_pack_puzzle_move(puzzle_id, history, move[0], move[1])
            if not res.get("correct"):
                erreurs.append(
                    f"{puzzle_id} [{cle or 'racine'}] : coup {move_key} annonce gagnant mais refuse"
                )
                continue
            attendu = node["replies"].get(move_key)
            reponse = res.get("opponent_move")
            if attendu is None:
                if reponse is not None:
                    erreurs.append(
                        f"{puzzle_id} [{cle or 'racine'}] : reponse adverse inattendue {reponse}"
                    )
                if not res.get("solved"):
                    erreurs.append(
                        f"{puzzle_id} [{cle or 'racine'}] : coup final {move_key} non marque resolu"
                    )
                continue
            if reponse is None:
                erreurs.append(
                    f"{puzzle_id} [{cle or 'racine'}] : aucune reponse adverse pour {move_key}"
                )
                continue
            if [reponse["row"], reponse["col"]] != attendu:
                erreurs.append(
                    f"{puzzle_id} [{cle or 'racine'}] : reponse {reponse} au lieu de {attendu} "
                    f"pour {move_key}"
                )
            enfant = ";".join(
                p for p in (cle, move_key, f"{int(reponse['row'])},{int(reponse['col'])}") if p
            )
            if enfant not in nodes:
                erreurs.append(
                    f"{puzzle_id} [{cle or 'racine'}] : noeud enfant {enfant} absent"
                )

        refusables = [
            m
            for m in engine.get_valid_actions()
            if f"{int(m[0])},{int(m[1])}" not in acceptes
        ]
        if refusables:
            move = refusables[0]
            res = check_pack_puzzle_move(puzzle_id, history, int(move[0]), int(move[1]))
            if res.get("correct"):
                erreurs.append(
                    f"{puzzle_id} [{cle or 'racine'}] : coup non liste {move} accepte"
                )
            elif res.get("solved"):
                erreurs.append(
                    f"{puzzle_id} [{cle or 'racine'}] : coup refuse {move} annonce resolu"
                )
        elif not acceptes:
            erreurs.append(f"{puzzle_id} [{cle or 'racine'}] : tous les coups sont acceptes")

    # parcours complet en suivant le premier coup accepte
    played: List[Dict[str, int]] = []
    for _ in range(int(puzzle["human_moves"]) + 1):
        cle = _cle_de(played)
        node = nodes.get(cle)
        if node is None:
            erreurs.append(f"{puzzle_id} : parcours perdu au noeud {cle or 'racine'}")
            break
        move = node["moves"][0]
        res = check_pack_puzzle_move(puzzle_id, setup + played, int(move[0]), int(move[1]))
        if not res.get("correct"):
            erreurs.append(f"{puzzle_id} : le parcours s'arrete au noeud {cle or 'racine'}")
            break
        if res.get("solved"):
            break
        reponse = res["opponent_move"]
        played = played + [
            {"player": HUMAN, "row": int(move[0]), "col": int(move[1])},
            {"player": 2, "row": int(reponse["row"]), "col": int(reponse["col"])},
        ]
    else:
        erreurs.append(f"{puzzle_id} : parcours non resolu apres {puzzle['human_moves']} coups")

    return noeuds, coups


def main() -> int:
    puzzles = json.loads(PACK_PATH.read_text(encoding="utf-8"))
    erreurs: List[str] = []
    total_noeuds = 0
    total_coups = 0
    sans_arbre: List[str] = []

    for puzzle in puzzles:
        if not puzzle.get("nodes"):
            sans_arbre.append(puzzle["id"])
            continue
        noeuds, coups = _verifier_puzzle(puzzle, erreurs)
        total_noeuds += noeuds
        total_coups += coups

    print(f"puzzles : {len(puzzles)}")
    print(f"noeuds verifies : {total_noeuds}")
    print(f"coups acceptes verifies : {total_coups}")
    print(f"puzzles sans arbre : {len(sans_arbre)} {sans_arbre or ''}")
    if erreurs:
        print(f"\n{len(erreurs)} ERREURS :")
        for erreur in erreurs:
            print(f"  - {erreur}")
        return 1
    print("\nOK — arbre coherent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
