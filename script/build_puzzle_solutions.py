"""Precalcule l'arbre de solution des puzzles du pack.

Le pack ne stockait qu'un **deroule** (`line`) : une seule variante ou l'adversaire
coopere. Le controle de coup comparait le coup joue a ce deroule au coup pres, donc
il refusait les autres coups gagnants et validait parfois des coups qui ne gagnent pas.

Ce script remplace ce mecanisme par un arbre precalcule, stocke sous `nodes` :

    "nodes": {
      "": {
        "moves": [[0,4], ...],            # coups humains qui forcent encore la victoire
        "replies": {"0,4": [1,5], ...}    # reponse adverse la plus tenace, par coup
      },
      "0,4;1,5": { ... }                  # noeud suivant (cle = coups joues)
    }

Une cle de noeud est la suite des coups joues depuis la position de depart, au format
"ligne,colonne" separes par ";". `replies` vaut `null` quand le coup humain termine
la partie.

Usage:
    cd 4mation
    set PYTHONPATH=.;script
    python script/build_puzzle_solutions.py
    python script/build_puzzle_solutions.py --only hard-01 --dry-run
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "script"))

from game.game_engine import GameEngine  # noqa: E402
import build_puzzle_pack as pack_builder  # noqa: E402

HUMAN = 1
PACK_PATH = ROOT / "api" / "data" / "puzzles.json"
INFINI = 99
CAP_NOEUDS = 20000


def _engine_from_history(history: List[Dict[str, int]]) -> GameEngine:
    engine = GameEngine()
    engine.reset()
    for h in history:
        engine.step((int(h["row"]), int(h["col"])))
    return engine


def _copie(engine: GameEngine) -> GameEngine:
    return GameEngine.from_snapshot(engine.to_snapshot())


def _gagne(engine: GameEngine, budget: int) -> bool:
    """La victoire forcee tient-elle en `budget` coups humains ?

    `_human_can_force_win` fait avancer le moteur qu'on lui passe : on lui donne une copie.
    """
    work = _copie(engine)
    if work.is_terminal():
        return work.get_winner() == HUMAN
    if budget <= 0:
        return False
    return pack_builder._human_can_force_win(work, budget)


def _distance(engine: GameEngine, plafond: int) -> int:
    """Plus petit budget (coups humains) qui gagne, ou INFINI si aucun jusqu'a `plafond`."""
    for budget in range(0, plafond + 1):
        if _gagne(engine, budget):
            return budget
    return INFINI


def _cle(move: Tuple[int, int]) -> str:
    return f"{int(move[0])},{int(move[1])}"


def _lire_cle(cle: str) -> Tuple[int, int]:
    row, col = cle.split(",")
    return int(row), int(col)


def _construire(
    chemin: str,
    engine: GameEngine,
    budget: int,
    nodes: Dict[str, Any],
    compteur: List[int],
) -> None:
    """Remplit `nodes` pour la position `engine` (humain au trait, `budget` coups restants)."""
    compteur[0] += 1
    if compteur[0] > CAP_NOEUDS:
        raise RuntimeError(f"plus de {CAP_NOEUDS} noeuds")

    base = engine.to_snapshot()
    moves: List[List[int]] = []
    replies: Dict[str, Optional[List[int]]] = {}
    enfants: List[Tuple[str, Tuple[int, int]]] = []

    for move in engine.get_valid_actions():
        apres = GameEngine.from_snapshot(base)
        _, ok, _ = apres.step(move)
        if not ok:
            continue
        cle_move = _cle(move)

        if apres.is_terminal():
            if apres.get_winner() == HUMAN:
                moves.append([int(move[0]), int(move[1])])
                replies[cle_move] = None
            continue

        if budget - 1 < 0:
            continue
        reponses = apres.get_valid_actions()
        if not reponses:
            continue

        pire = -1
        meilleure: Optional[Tuple[int, int]] = None
        gagnant = True
        snap = apres.to_snapshot()
        for reponse in reponses:
            suivant = GameEngine.from_snapshot(snap)
            _, ok_rep, _ = suivant.step(reponse)
            if not ok_rep:
                gagnant = False
                break
            d = _distance(suivant, budget - 1)
            if d == INFINI:
                gagnant = False
                break
            if d > pire:
                pire = d
                meilleure = (int(reponse[0]), int(reponse[1]))

        if not gagnant or meilleure is None:
            continue

        moves.append([int(move[0]), int(move[1])])
        replies[cle_move] = [meilleure[0], meilleure[1]]
        enfants.append((cle_move, meilleure))

    nodes[chemin] = {"moves": moves, "replies": replies}

    for cle_move, reponse in enfants:
        suivant = GameEngine.from_snapshot(base)
        suivant.step(_lire_cle(cle_move))
        suivant.step(reponse)
        enfant_chemin = ";".join(
            [p for p in (chemin, cle_move, _cle(reponse)) if p]
        )
        _construire(enfant_chemin, suivant, budget - 1, nodes, compteur)


def _resoudre(puzzle: Dict[str, Any]) -> Dict[str, Any]:
    engine = _engine_from_history(puzzle["history"])
    if engine.is_terminal() or int(engine.get_current_player()) != HUMAN:
        raise RuntimeError("position de depart invalide")

    budget = int(puzzle["human_moves"])
    nodes: Dict[str, Any] = {}
    compteur = [0]
    _construire("", engine, budget, nodes, compteur)

    racine = nodes[""]
    if not racine["moves"]:
        raise RuntimeError("aucun coup gagnant a la racine")

    distance_min = _distance(engine, budget)
    return {"nodes": nodes, "min_moves": distance_min, "nb_noeuds": compteur[0]}


def _ligne_principale(nodes: Dict[str, Any]) -> Optional[List[Dict[str, int]]]:
    """Variante de reference extraite de l'arbre : 1er coup gagnant, puis la defense la plus tenace.

    L'ancien champ `line` etait un deroule ou l'adversaire coopere : il ne correspondait a
    aucune suite reellement gagnante. On le regenere depuis l'arbre pour qu'il reste utilisable
    comme repli.
    """
    chemin = ""
    line: List[Dict[str, int]] = []

    while True:
        node = nodes.get(chemin)
        if node is None:
            return None
        if not node["moves"]:
            return line
        move = node["moves"][0]
        move_key = _cle(move)
        line.append({"player": HUMAN, "row": int(move[0]), "col": int(move[1])})

        reponse = node["replies"].get(move_key)
        if reponse is None:
            return line

        line.append({"player": 2, "row": int(reponse[0]), "col": int(reponse[1])})
        chemin = ";".join(p for p in (chemin, move_key, _cle(reponse)) if p)


def add_solutions(pack: List[Dict[str, Any]], *, verbose: bool = True) -> List[str]:
    """Calcule et stocke `nodes` / `min_moves` / `line` pour chaque puzzle du pack."""
    pack_builder.memo_force.clear()
    echecs: List[str] = []

    for puzzle in pack:
        debut = time.perf_counter()
        try:
            resultat = _resoudre(puzzle)
        except RuntimeError as exc:
            echecs.append(f"{puzzle['id']} : {exc}")
            if verbose:
                print(f"{puzzle['id']:<10} ECHEC  {exc}", flush=True)
            continue

        line = _ligne_principale(resultat["nodes"])
        if line is None:
            echecs.append(f"{puzzle['id']} : variante de reference introuvable dans l'arbre")
            if verbose:
                print(f"{puzzle['id']:<10} ECHEC  variante de reference introuvable", flush=True)
            continue

        elapsed = time.perf_counter() - debut
        puzzle["nodes"] = resultat["nodes"]
        puzzle["min_moves"] = resultat["min_moves"]
        puzzle["line"] = line
        if verbose:
            racine = resultat["nodes"][""]
            coups_line = sum(1 for m in line if int(m["player"]) == HUMAN)
            print(
                f"{puzzle['id']:<10} coups acceptes des le depart={len(racine['moves'])}  "
                f"noeuds={resultat['nb_noeuds']}  min_moves={resultat['min_moves']}  "
                f"line={coups_line}  annonce={puzzle['human_moves']}  {elapsed:.1f} s",
                flush=True,
            )

    return echecs


def main() -> int:
    parser = argparse.ArgumentParser(description="Precalcule l'arbre de solution des puzzles")
    parser.add_argument("--only", action="append", help="Limiter a un ou plusieurs id")
    parser.add_argument("--dry-run", action="store_true", help="Ne pas ecrire le pack")
    args = parser.parse_args()

    pack: List[Dict[str, Any]] = json.loads(PACK_PATH.read_text(encoding="utf-8"))
    if args.only:
        pack = [p for p in pack if p["id"] in args.only]
        if not pack:
            print("Aucun puzzle ne correspond a --only")
            return 1

    echecs = add_solutions(pack)

    if echecs:
        print("\nPuzzles non resolus :")
        for ligne in echecs:
            print(f"  - {ligne}")

    if args.dry_run:
        print("\nMode --dry-run : pack non ecrit")
        return 0

    PACK_PATH.write_text(json.dumps(pack, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nOK — {len(pack)} puzzles ecrits dans {PACK_PATH} ({PACK_PATH.stat().st_size} octets)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
