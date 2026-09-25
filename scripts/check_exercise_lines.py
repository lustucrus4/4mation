#!/usr/bin/env python3
"""Contrôle des exercices de finales : rejoue chaque ligne et vérifie chaque demi-coup.

Un rapport d'exercices peut être faux de trois façons : coup illégal, ligne qui s'arrête
sans conclusion, ou camp gagnant qui joue un coup perdant parce que la base a un trou.
Ce contrôle rejoue la ligne annoncée depuis la position de départ et vérifie, à chaque
étape, la légalité du coup, la valeur stockée de la position obtenue et le rôle des camps.
Il sert de test de non-régression sur le format des exercices produits par
`mine_final_patterns.py`.

Usage :
    python scripts/check_exercise_lines.py script/solver/final_patterns.json
    python scripts/check_exercise_lines.py script/solver/final_patterns.json 7 9
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT), str(ROOT / "script"), str(ROOT / "script" / "solver")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from game_tree.optimized_minimax import OptimizedMinimaxAdvisor  # noqa: E402
from solver.position_hasher import HASHER  # noqa: E402

DB = ROOT / "script" / "solver" / "data" / "tablebase.db"
ADVISOR = OptimizedMinimaxAdvisor()


def legal(board: np.ndarray, last, player: int):
    return [(int(r), int(c)) for r, c in ADVISOR._get_frontier_moves(board, last, player)]


def stored(conn: sqlite3.Connection, board: np.ndarray, player: int, last):
    row = conn.execute(
        "SELECT result, depth_remaining, pos_last_move_row, pos_last_move_col "
        "FROM positions WHERE hash=?",
        (HASHER.hash_key(board, player, last),),
    ).fetchone()
    if row is None:
        return None
    return (
        str(row["result"]),
        int(row["depth_remaining"] or 0),
        (row["pos_last_move_row"], row["pos_last_move_col"]),
    )


def check(puzzle: dict, conn: sqlite3.Connection) -> int:
    """Contrôle un exercice ; renvoie le nombre d'anomalies trouvées."""
    board = np.array(puzzle["plateau"], dtype=np.int8)
    player = int(puzzle["camp"])
    last = tuple(puzzle["dernier_coup"]) if puzzle["dernier_coup"] else None
    faults = 0
    start = stored(conn, board, player, last)
    print(f"--- Exercice {puzzle['numero']} : {puzzle['cellules_vides']} vides, trait {player}")
    print(f"    valeur de la position : {start}")
    if start is None or start[0] != "W":
        print("    ANOMALIE : l'exercice ne part pas d'une position gagnante connue")
        faults += 1
    if ADVISOR._check_winner(board) is not None:
        print("    ANOMALIE : un alignement de quatre est déjà sur le plateau")
        faults += 1

    for step in puzzle["ligne"]:
        mv = tuple(step["coup"])
        moves = legal(board, last, player)
        nb = board.copy()
        nb[mv[0], mv[1]] = player
        four = ADVISOR._check_winner(nb)
        child = stored(conn, nb, 3 - player, mv)
        problems = []
        if mv not in moves:
            problems.append("coup illégal")
        if not four and child is None:
            problems.append("enfant absent de la base")
        if not four and child is not None:
            expected = "L" if player == puzzle["camp"] else "W"
            if child[0] != expected:
                problems.append(f"enfant {child[0]} au lieu de {expected}")
        faults += len(problems)
        print(
            f"    {'ok     ' if not problems else 'FAUTE  '} "
            f"{'X' if player == 1 else 'O'}{mv} | quatre={four} | enfant={child} | "
            f"légaux={len(moves)}"
            + (f" | {', '.join(problems)}" if problems else "")
        )
        if problems and mv not in moves:
            print(f"           coups légaux : {moves[:12]}")
        board = nb
        player = 3 - player
        last = mv

    if not puzzle["ligne"] or not puzzle["ligne"][-1]["alignement"]:
        print("    ANOMALIE : la ligne ne se termine pas sur un alignement de quatre")
        faults += 1
    return faults


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    wanted = {int(x) for x in sys.argv[2:]} if len(sys.argv) > 2 else None
    faults = 0
    checked = 0
    for puzzle in payload["puzzles"]:
        if wanted and puzzle["numero"] not in wanted:
            continue
        checked += 1
        faults += check(puzzle, conn)
    conn.close()
    print()
    print(f"{checked} exercice(s) contrôlé(s), {faults} anomalie(s).")
    return 1 if faults else 0


if __name__ == "__main__":
    raise SystemExit(main())
