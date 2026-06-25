#!/usr/bin/env python3
"""
Relance automatique du livre d'ouverture (option A « évolutive »).

Surveille la croissance de la tablebase (`positions`) et reconstruit le livre
d'ouverture dès qu'elle a suffisamment grimpé. À chaque reconstruction, comme
l'écart entre l'ouverture et les feuilles exactes a diminué, davantage d'entrées
passent d'« estimé » à « exact » → l'ouverture converge vers le parfait, sans y penser.

Usage:
    python script/solver/auto_opening_book.py
        [--db PATH] [--interval 600] [--growth 500000]
        [--max-ply 12] [--depth 14] [--time-ms 3000]
        [--max-positions 5000] [--branch 7]

Lancer en arrière-plan, à côté du solveur Rust. S'arrête proprement au Ctrl+C.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = ROOT / "script"
if str(SCRIPT) not in sys.path:
    sys.path.insert(0, str(SCRIPT))

from solver.build_opening_book import build_opening_book
from solver.db_schema import connect

DEFAULT_DB = SCRIPT / "solver" / "data" / "tablebase.db"


def _positions_count(db_path: Path) -> int:
    if not db_path.exists():
        return 0
    try:
        conn = connect(db_path)
        try:
            return int(conn.execute("SELECT COUNT(*) FROM positions").fetchone()[0])
        finally:
            conn.close()
    except sqlite3.Error:
        return 0


def _ts() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def run_watcher(
    db_path: Path,
    interval: int,
    growth: int,
    build_kwargs: dict,
) -> None:
    print(f"[{_ts()}] Watcher livre d'ouverture démarré (db={db_path})")
    print(f"[{_ts()}] Reconstruction tous les +{growth:,} positions, sondage {interval}s.")

    last_built_count = -1  # force une première construction au démarrage
    while True:
        count = _positions_count(db_path)
        if last_built_count < 0 or (count - last_built_count) >= growth:
            reason = "démarrage" if last_built_count < 0 else f"+{count - last_built_count:,} positions"
            print(f"[{_ts()}] Reconstruction du livre ({reason}, tablebase={count:,})…")
            try:
                n_exact, n_est = build_opening_book(db_path, verbose=True, **build_kwargs)
                print(f"[{_ts()}] Terminé : exact={n_exact}, estimé={n_est}.")
            except Exception as exc:  # noqa: BLE001 — on ne veut jamais tuer le watcher
                print(f"[{_ts()}] ERREUR build_opening_book : {exc}")
            last_built_count = count
        time.sleep(interval)


def main() -> None:
    parser = argparse.ArgumentParser(description="Relance auto du livre d'ouverture 4mation")
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--interval", type=int, default=900, help="Secondes entre deux sondages")
    parser.add_argument("--growth", type=int, default=1000000, help="Delta positions déclenchant un rebuild")
    parser.add_argument("--max-ply", type=int, default=12)
    parser.add_argument("--max-positions", type=int, default=2000)
    args = parser.parse_args()

    build_kwargs = dict(
        max_ply=args.max_ply,
        max_positions=args.max_positions,
    )
    try:
        run_watcher(Path(args.db), args.interval, args.growth, build_kwargs)
    except KeyboardInterrupt:
        print(f"\n[{_ts()}] Watcher arrêté.")


if __name__ == "__main__":
    main()
