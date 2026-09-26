"""Réparation ciblée des valeurs périmées signalées par `4mation-local --verify`.

`--verify` relit chaque position, recalcule sa valeur depuis ses enfants et signale les
contradictions (« faux »). Pour les corriger, le répareteur de masse
(`4mation-local --sweep-from N --repair`) réécrit une couche entière : c'est le bon outil
pour une dérive systématique (289 lignes en couche 7, 616 en couche 8), mais il est
disproportionné pour quelques lignes isolées — et, sur les couches hautes, il a un coût
caché : il insère aussi les positions manquantes de la couche suivante, ce qui peut faire
grossir la base de plusieurs gigaoctets.

Ce script corrige **uniquement** les hashes demandés, à partir des enfants déjà présents
dans la base :

    python repair_stale_positions.py 099f04b0a8c243bc --dry-run
    python repair_stale_positions.py 099f04b0a8c243bc

Il recalcule valeur, taux et meilleur coup avec `RetrogradeSolver`, donc avec exactement
les mêmes règles que l'analyse servie par l'API. Une position dont un enfant manque est
dite « indécidable » et laissée intacte : la corriger reviendrait à inventer une valeur.

`depth_remaining` n'est pas modifié : c'est un indicateur de distance au gain, sans effet
sur le coup joué, et le recalculer demanderait une résolution complète de la position.
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path
from typing import Optional, Sequence

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from solver.db_schema import board_from_blob  # noqa: E402
from solver.retrograde_solver import RetrogradeSolver  # noqa: E402

DEFAULT_DB = Path(__file__).resolve().parent / "data" / "tablebase.db"
WIN_RATE_TOLERANCE = 0.005


def _last_move(row: sqlite3.Row) -> Optional[tuple[int, int]]:
    if row["pos_last_move_row"] is None or row["pos_last_move_col"] is None:
        return None
    return int(row["pos_last_move_row"]), int(row["pos_last_move_col"])


def repair(
    conn: sqlite3.Connection,
    hash_key: str,
    *,
    dry_run: bool = False,
) -> str:
    """Retourne un verdict lisible : `corrigee`, `intacte` ou `indecidable`."""
    row = conn.execute(
        """
        SELECT hash, board_blob, board_json, current_player, pos_last_move_row,
               pos_last_move_col, result, win_rate, best_move_row, best_move_col,
               depth_remaining, empty_cells
        FROM positions WHERE hash = ?
        """,
        (hash_key,),
    ).fetchone()
    if row is None:
        return "absente"
    if row["board_blob"] is None and row["board_json"] is None:
        return "plateau illisible"

    board = np.array(board_from_blob(row["board_blob"]), dtype=int)
    player = int(row["current_player"])
    last_move = _last_move(row)
    empty = int(row["empty_cells"]) if row["empty_cells"] is not None else 64

    solver = RetrogradeSolver(max_empty=max(empty, 12))
    analysis = solver.analyze_moves(board, player, last_move)
    if analysis is None:
        return "indecidable"
    solved = analysis.get("position_result")
    solved_wr = float(analysis.get("position_win_rate", 0.0))
    if solved is None:
        return "indecidable"

    stored = str(row["result"])
    stored_wr = float(row["win_rate"] or 0.0)
    best = analysis.get("best_move")
    if (
        stored == solved
        and abs(stored_wr - solved_wr) < WIN_RATE_TOLERANCE
        and best is not None
        and row["best_move_row"] == best[0]
        and row["best_move_col"] == best[1]
    ):
        return "intacte"

    print(
        f"  {hash_key} : {stored} ({stored_wr:.2f}) coup "
        f"{(row['best_move_row'], row['best_move_col'])} "
        f"-> {solved} ({solved_wr:.2f}) coup {best}"
    )
    if dry_run or best is None:
        return "corrigee (simulation)" if best is not None else "intacte"

    conn.execute(
        """
        UPDATE positions
           SET result = ?, win_rate = ?, best_move_row = ?, best_move_col = ?
         WHERE hash = ?
        """,
        (solved, solved_wr, int(best[0]), int(best[1]), hash_key),
    )
    return "corrigee"


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("hashes", nargs="+", help="hashes à corriger")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="chemin de tablebase.db")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="affiche les corrections sans écrire (à faire en premier)",
    )
    args = parser.parse_args(argv)

    if args.dry_run:
        print("Mode simulation : aucune écriture.")
    if not os.path.exists(args.db):
        print(f"Base absente : {args.db}", file=sys.stderr)
        return 2

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    verdicts: dict[str, int] = {}
    try:
        for hash_key in args.hashes:
            verdict = repair(conn, hash_key, dry_run=args.dry_run)
            verdicts[verdict] = verdicts.get(verdict, 0) + 1
            print(f"  → {verdict}")
        if not args.dry_run:
            conn.commit()
    finally:
        conn.close()

    print("Bilan : " + ", ".join(f"{n} {verdict}" for verdict, n in sorted(verdicts.items())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
