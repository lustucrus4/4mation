"""Verifie que le deroule `line` du pack reste compatible avec l'arbre `nodes`.

`line` n'est plus la source de verite du controle des coups (c'est `nodes`), mais il
sert encore de repli si un puzzle n'a pas d'arbre. Un `line` desynchronise ferait
resoudre le puzzle avec un deroule ou l'adversaire coopere, ou refuserait des coups
pourtant gagnants.

Pour chaque puzzle, on rejoue `line` et on verifie que :

- chaque coup humain figure dans les `moves` du noeud courant ;
- chaque reponse adverse est exactement celle attendue par `replies` ;
- la suite atteint bien un noeud terminal gagnant pour l'humain.

Usage:
    cd 4mation
    set PYTHONPATH=.;script
    python scripts/_puzzle_diag.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "script"))

from game.game_engine import GameEngine  # noqa: E402

HUMAN = 1
PACK = ROOT / "api" / "data" / "puzzles.json"


def _engine_from(history: List[Dict[str, int]]) -> GameEngine:
    engine = GameEngine()
    engine.reset()
    for h in history:
        engine.step((int(h["row"]), int(h["col"])))
    return engine


def _cle(move_key: str, reponse_key: str, chemin: str) -> str:
    return ";".join(p for p in (chemin, move_key, reponse_key) if p)


def verifier(puzzle: Dict[str, Any], erreurs: List[str]) -> int:
    puzzle_id = puzzle["id"]
    nodes = puzzle.get("nodes") or {}
    if not nodes:
        erreurs.append(f"{puzzle_id} : aucun arbre, impossible de valider `line`")
        return 0

    chemin = ""
    pas = 0
    moteur = _engine_from(puzzle["history"])
    line = puzzle["line"]

    index = 0
    while index < len(line):
        node = nodes.get(chemin)
        if node is None:
            erreurs.append(f"{puzzle_id} : noeud {chemin or 'racine'} absent de l'arbre")
            return pas
        if not node["moves"]:
            erreurs.append(f"{puzzle_id} : noeud {chemin or 'racine'} sans coup gagnant")
            return pas

        entry = line[index]
        move = (int(entry["row"]), int(entry["col"]))
        if int(entry["player"]) != HUMAN:
            erreurs.append(f"{puzzle_id} : l'humain n'est pas au trait dans `line`")
            return pas
        move_key = f"{move[0]},{move[1]}"
        if [move[0], move[1]] not in node["moves"]:
            erreurs.append(
                f"{puzzle_id} : le coup {move_key} de `line` n'est pas gagnant au noeud "
                f"{chemin or 'racine'} (gagnants : {node['moves']})"
            )
            return pas

        _, ok, _ = moteur.step(move)
        if not ok:
            erreurs.append(f"{puzzle_id} : coup {move_key} de `line` illegal")
            return pas
        pas += 1

        attendu = node["replies"].get(move_key)
        index += 1

        if attendu is None:
            if not moteur.is_terminal() or moteur.get_winner() != HUMAN:
                erreurs.append(f"{puzzle_id} : `line` s'arrete avant la victoire apres {move_key}")
            return pas

        if index >= len(line):
            erreurs.append(f"{puzzle_id} : reponse adverse manquante apres {move_key}")
            return pas
        reponse_entry = line[index]
        reponse = (int(reponse_entry["row"]), int(reponse_entry["col"]))
        if int(reponse_entry["player"]) == HUMAN:
            erreurs.append(f"{puzzle_id} : reponse adverse attendue apres {move_key}")
            return pas
        if [reponse[0], reponse[1]] != attendu:
            erreurs.append(
                f"{puzzle_id} : reponse {reponse} apres {move_key} au lieu de {attendu}"
            )
            return pas
        _, ok_rep, _ = moteur.step(reponse)
        if not ok_rep:
            erreurs.append(f"{puzzle_id} : reponse {reponse} illegale")
            return pas

        chemin = _cle(move_key, f"{reponse[0]},{reponse[1]}", chemin)
        index += 1

    if not moteur.is_terminal() or moteur.get_winner() != HUMAN:
        erreurs.append(f"{puzzle_id} : `line` ne se termine pas par une victoire de l'humain")
    return pas


def main() -> int:
    puzzles = json.loads(PACK.read_text(encoding="utf-8"))
    erreurs: List[str] = []
    total = 0

    for puzzle in puzzles:
        total += verifier(puzzle, erreurs)

    print(f"puzzles : {len(puzzles)}")
    print(f"coups humains rejoues depuis `line` : {total}")
    if erreurs:
        print(f"\n{len(erreurs)} ERREURS :")
        for erreur in erreurs:
            print(f"  - {erreur}")
        return 1
    print("\nOK — `line` coherent avec l'arbre pour les 21 puzzles")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
