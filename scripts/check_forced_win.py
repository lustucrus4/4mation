#!/usr/bin/env python3
"""Contre-vérification d'une ligne de gain forcée, sans faire confiance au moteur.

`extract_forced_win.py` produit une ligne de mat forcé en s'appuyant sur le moteur. Un bug
du moteur (coups légaux trop restrictifs, preuve interrompue) produirait une ligne
« prouvée » qui ne l'est pas. Ce script rejoue la ligne avec **le moteur de jeu Python**,
qui fait autorité sur les règles, et contrôle :

1. **légalité** de chaque coup joué, et surtout **égalité du nombre de coups légaux**
   entre le moteur et le moteur de jeu à chaque position — un moteur qui oublierait un
   coup de défense croirait à tort à une perte forcée ;
2. **décroissance du mat** : la distance annoncée doit diminuer d'exactement 1 par
   demi-coup, en alternant les camps ;
3. **tous les coups de défense perdent** (preuve indépendante d'une faute adverse) ;
4. **conclusion** : la ligne se termine sur un alignement de quatre du camp annoncé ;
5. **tablebase** : pour les positions qu'elle couvre (≤ 12 cases vides), le verdict
   stocké ne doit jamais contredire la ligne.

    python scripts/check_forced_win.py script/solver/forced_win_33.json

Note : la tablebase s'arrête à 12 cases vides, alors qu'une partie gagnée en 29 demi-coups
en laisse encore une vingtaine. La couverture est donc nulle pour une ligne d'ouverture :
ce contrôle porte sur les règles et la cohérence, pas sur la base.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT), str(ROOT / "script"), str(ROOT / "script" / "solver")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from game_tree.optimized_minimax import OptimizedMinimaxAdvisor  # noqa: E402
from solver.position_hasher import HASHER  # noqa: E402

DB = ROOT / "script" / "solver" / "data" / "tablebase.db"
ADVISOR = OptimizedMinimaxAdvisor()


def stored(conn: sqlite3.Connection, board: np.ndarray, player: int, last):
    row = conn.execute(
        "SELECT result, depth_remaining FROM positions WHERE hash=?",
        (HASHER.hash_key(board, player, last),),
    ).fetchone()
    if row is None:
        return None
    return str(row["result"]), int(row["depth_remaining"] or 0)


def legal(board: np.ndarray, last, player: int) -> List[Tuple[int, int]]:
    return [(int(r), int(c)) for r, c in ADVISOR._get_frontier_moves(board, last, player)]


def check(payload: Dict[str, Any], conn: sqlite3.Connection) -> int:
    plies = payload["plies"]
    opening = tuple(payload["opening"])
    winner = payload["winner"]
    if winner is None:
        print("La ligne ne se conclut pas : rien à vérifier.")
        return 1

    board = np.zeros((7, 7), dtype=np.int8)
    board[opening] = 1
    last: Optional[Tuple[int, int]] = opening
    player = 2
    faults = 0
    covered = 0
    checked = 0
    expected_mate = None
    print(f"Ligne : {len(plies) - 1} demi-coups, vainqueur annoncé : joueur {winner}.")
    print()
    for entry in plies[1:]:
        move = tuple(entry["move"])
        moves = legal(board, last, player)
        nb = board.copy()
        nb[move[0], move[1]] = player
        four = ADVISOR._check_winner(nb)
        child = stored(conn, nb, 3 - player, move)
        problems: List[str] = []

        if move not in moves:
            problems.append("coup illégal")
        if entry.get("legal") != len(moves):
            problems.append(f"moteur {entry.get('legal')} coups légaux, règles {len(moves)}")

        mate = entry.get("mate_in")
        if four:
            if mate != 1:
                problems.append(f"alignement final mais mat annoncé {mate}")
        else:
            if mate is None:
                problems.append("aucune distance de mat annoncée")
            elif expected_mate is not None and mate != expected_mate:
                problems.append(f"mat {mate} au lieu de {expected_mate}")
            expected_mate = None if mate is None else mate - 1

        if player != winner:
            # C'est la défense qui joue : aucun de ses coups ne doit sauver la partie.
            res = entry.get("resistance") or {}
            if not res.get("all_lose"):
                problems.append("un coup de défense ne perd pas")

        if child is not None:
            covered += 1
            expected = "L" if player == winner else "W"
            if child[0] != expected and not four:
                problems.append(f"tablebase {child[0]} au lieu de {expected}")

        tag = "X" if player == 1 else "O"
        print(
            f"  {'ok    ' if not problems else 'FAUTE '} {entry['ply']:>2} {tag}{move} "
            f"| moteur {entry['proven']:<10} mat {mate} | légaux {entry.get('legal')}"
            f"/{len(moves)} | tablebase {'—' if child is None else child[0]}"
            + (f" | {', '.join(problems)}" if problems else "")
        )
        faults += len(problems)
        checked += 1
        board = nb
        player = 3 - player
        last = move

    if ADVISOR._check_winner(board) != winner:
        print("ANOMALIE : la ligne ne se termine pas par la victoire annoncée")
        faults += 1

    print()
    print(
        f"{checked} demi-coups rejoués, {covered} couverts par la tablebase, "
        f"{faults} anomalie(s)."
    )
    return faults


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        return 1 if check(payload, conn) else 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
