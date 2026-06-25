#!/usr/bin/env python3
"""
Rapport de couverture de la tablebase 4mation.

Deux mesures complementaires :

1. Distribution statique : nombre de positions stockees par nombre de cases vides
   (lecture directe de la colonne empty_cells).

2. Couverture "partie reelle" : on simule N parties (coups aleatoires guides) et,
   pour chaque position rencontree, on verifie si elle est presente en base
   (opening_book si ply <= max_opening_ply, sinon positions). On en deduit le taux
   de hit par nombre de cases vides et par ply. C'est la metrique produit : elle
   indique si la barre W/L sera "exacte" (tablebase) ou "estimee" (MCTS) en jeu.

Usage:
    python script/solver/coverage_report.py [--db PATH] [--games 300] [--max-opening-ply 12]
"""

from __future__ import annotations

import argparse
import random
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = ROOT / "script"
if str(SCRIPT) not in sys.path:
    sys.path.insert(0, str(SCRIPT))

from game_tree.optimized_minimax import OptimizedMinimaxAdvisor  # noqa: E402
from solver.position_hasher import HASHER  # noqa: E402

DEFAULT_DB = SCRIPT / "solver" / "data" / "tablebase.db"


def _connect_ro(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _has_position(conn: sqlite3.Connection, h: str, ply: int, max_opening_ply: int) -> bool:
    if ply <= max_opening_ply:
        if conn.execute("SELECT 1 FROM opening_book WHERE hash=?", (h,)).fetchone():
            return True
    return conn.execute("SELECT 1 FROM positions WHERE hash=?", (h,)).fetchone() is not None


def static_distribution(conn: sqlite3.Connection) -> None:
    print("\n=== Distribution statique (positions stockees par cases vides) ===")
    total = conn.execute("SELECT COUNT(*) FROM positions").fetchone()[0]
    rows = conn.execute(
        "SELECT empty_cells, COUNT(*) FROM positions "
        "WHERE empty_cells IS NOT NULL GROUP BY empty_cells ORDER BY empty_cells"
    ).fetchall()
    print(f"  total positions : {total:,}")
    print("  vides | positions")
    for ec, n in rows:
        print(f"    {ec:3} | {n:,}")
    null_ec = conn.execute(
        "SELECT COUNT(*) FROM positions WHERE empty_cells IS NULL"
    ).fetchone()[0]
    if null_ec:
        print(f"  (sans empty_cells : {null_ec:,})")


def game_coverage(
    conn: sqlite3.Connection,
    num_games: int,
    max_opening_ply: int,
) -> None:
    advisor = OptimizedMinimaxAdvisor(depth=2, use_iterative_deepening=False)
    by_empty_hit: dict[int, int] = defaultdict(int)
    by_empty_tot: dict[int, int] = defaultdict(int)
    by_ply_hit: dict[int, int] = defaultdict(int)
    by_ply_tot: dict[int, int] = defaultdict(int)

    for _ in range(num_games):
        board = np.zeros((7, 7), dtype=np.int8)
        current_player = 1
        last_move = None
        for ply in range(49):
            empty = int(np.count_nonzero(board == 0))
            h = HASHER.hash_key(board, current_player, last_move)
            hit = _has_position(conn, h, ply, max_opening_ply)
            by_empty_tot[empty] += 1
            by_ply_tot[ply] += 1
            if hit:
                by_empty_hit[empty] += 1
                by_ply_hit[ply] += 1

            if advisor._check_winner(board) is not None:
                break
            moves = advisor._get_frontier_moves(board, last_move, current_player)
            if not moves:
                break
            move = random.choice(moves)
            board = board.copy()
            board[move[0], move[1]] = current_player
            last_move = move
            if np.all(board != 0):
                break
            current_player = 3 - current_player

    print(f"\n=== Couverture partie reelle ({num_games} parties simulees) ===")
    print("  vides | couvert / total | taux")
    for ec in sorted(by_empty_tot, reverse=True):
        tot = by_empty_tot[ec]
        hit = by_empty_hit[ec]
        bar = "#" * int(20 * hit / tot) if tot else ""
        print(f"    {ec:3} | {hit:6} / {tot:6} | {100*hit/tot:5.1f}% {bar}")

    glob_hit = sum(by_empty_hit.values())
    glob_tot = sum(by_empty_tot.values())
    print(f"\n  couverture globale (positions rencontrees) : "
          f"{glob_hit}/{glob_tot} = {100*glob_hit/glob_tot:.1f}%")
    print("  -> en jeu : 'Exact (tablebase)' sur ces positions, sinon repli MCTS/Minimax.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Rapport de couverture tablebase 4mation")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="Chemin SQLite")
    parser.add_argument("--games", type=int, default=300, help="Parties simulees")
    parser.add_argument("--max-opening-ply", type=int, default=12)
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"Base introuvable : {db_path}")
        sys.exit(1)

    conn = _connect_ro(db_path)
    static_distribution(conn)
    game_coverage(conn, args.games, args.max_opening_ply)
    conn.close()


if __name__ == "__main__":
    main()
