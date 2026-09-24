#!/usr/bin/env python3
"""Inscrit dans le livre d'ouverture les positions d'une ligne **prouvée**.

Le livre d'ouverture (`opening_book`) est construit par estimation : au premier coup, le
moteur ne prouve rien dans le budget imparti et le site affiche « nulle à 58 % » là où le
jeu est en réalité **gagné de force**. Une fois la preuve extraite
(`scripts/extract_forced_win.py`), il faut donc la reporter dans le livre.

Le script marque :

- la position racine (plateau vide, premier joueur au trait) : `W`, meilleur coup = le
  premier coup prouvé ;
- chaque position de la ligne : `W` pour le camp qui gagne, `L` pour l'autre, avec pour
  meilleur coup celui de la ligne (mat le plus court, ou résistance la plus longue).

Toutes ces entrées passent en `exact=1` : elles remplacent les estimations du même `hash`.

Les positions *voisines* (autres coups de défense, prouvés perdants eux aussi) ne sont pas
marquées : on ne connaît pas leur meilleur coup, et une ligne de livre avec un meilleur coup
inventé serait pire que pas de ligne du tout. Le moteur les prouve de toute façon à la volée.

    python script/solver/mark_proven_lines.py --line script/solver/forced_win_33.json
    python script/solver/mark_proven_lines.py --line ... --dry-run
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
for _p in (str(ROOT), str(ROOT / "script"), str(ROOT / "script" / "solver")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from solver.build_opening_book import _store_opening  # noqa: E402
from solver.position_hasher import HASHER  # noqa: E402
from solver.retrograde_solver import RESULT_LOSS, RESULT_WIN  # noqa: E402

DEFAULT_DB = ROOT / "script" / "solver" / "data" / "tablebase.db"


def rows_for_line(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Entrées de livre à écrire pour une ligne prouvée (racine incluse).

    Pour la position qui suit le demi-coup `k`, le meilleur coup à inscrire n'est pas le
    demi-coup `k` (il appartient au passé) mais le demi-coup `k+1`, celui du joueur
    au trait. La position finale (après le dernier demi-coup) est terminale : elle n'a pas
    de meilleur coup et n'est donc pas inscrite.
    """
    plies = payload["plies"]
    winner = payload["winner"]
    if winner is None or len(plies) < 2:
        raise SystemExit("La ligne n'est pas une partie gagnée : rien à marquer.")

    rows: List[Dict[str, Any]] = []
    board = np.zeros((7, 7), dtype=np.int8)
    opening = plies[0]["move"]
    rows.append(
        {
            "board": board.copy(),
            "player": 1,
            "last": None,
            "ply": 0,
            "result": RESULT_WIN,
            "win_rate": 1.0,
            "best": (int(opening[0]), int(opening[1])),
            "desc": "racine (plateau vide)",
        }
    )

    for index in range(len(plies) - 1):
        played = plies[index]
        following = plies[index + 1]
        move = played["move"]
        mover = int(played["player"])
        board = board.copy()
        board[move[0], move[1]] = mover
        last = (int(move[0]), int(move[1]))
        won = mover == winner
        rows.append(
            {
                "board": board.copy(),
                "player": 3 - mover,
                "last": last,
                "ply": int(played["ply"]),
                "result": RESULT_LOSS if won else RESULT_WIN,
                "win_rate": 0.0 if won else 1.0,
                "best": (int(following["move"][0]), int(following["move"][1])),
                "desc": f"après {'X' if mover == 1 else 'O'} {move[0]},{move[1]}",
            }
        )
    return rows


def mark(db_path: Path, rows: List[Dict[str, Any]], dry_run: bool) -> int:
    conn = sqlite3.connect(str(db_path), timeout=60)
    conn.row_factory = sqlite3.Row
    written = 0
    try:
        for row in rows:
            key = HASHER.hash_key(row["board"], row["player"], row["last"])
            before = conn.execute(
                "SELECT result, win_rate, exact FROM opening_book WHERE hash=?", (key,)
            ).fetchone()
            state = (
                "absente"
                if before is None
                else f"{before['result']} {before['win_rate']:.3f} exact={before['exact']}"
            )
            print(
                f"  ply {row['ply']:>2} | {row['desc']:<18} | trait {row['player']} "
                f"| {row['result']} {row['win_rate']:.1f} | avant : {state}"
            )
            if dry_run:
                continue
            _store_opening(
                conn,
                key,
                row["result"],
                row["win_rate"],
                row["best"],
                row["ply"],
                exact=1,
                board=row["board"],
                current_player=row["player"],
                last_move=row["last"],
                store_board=True,
            )
            written += 1
        if not dry_run:
            conn.commit()
    finally:
        conn.close()
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description="Marque une ligne prouvée dans le livre")
    parser.add_argument("--line", action="append", required=True, help="JSON de ligne prouvée")
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    total = 0
    for path_txt in args.line:
        payload = json.loads(Path(path_txt).read_text(encoding="utf-8"))
        rows = rows_for_line(payload)
        print(f"--- {path_txt} ({len(rows)} positions)")
        total += mark(Path(args.db), rows, args.dry_run)
    print()
    print(f"{total} position(s) marquée(s) exactes{' (simulation)' if args.dry_run else ''}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
