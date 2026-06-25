#!/usr/bin/env python3
"""
Finalisation du livre d'ouverture (usage unique) :
1. Construit le livre une fois jusqu'au bout (garde les estimations déjà présentes).
2. Consolide la base : checkpoint WAL (TRUNCATE) pour replier le -wal dans le fichier
   principal → fichier propre, prêt à servir / déployer.
3. S'arrête (pas de boucle, pas de surveillance permanente).

Usage:
    python script/solver/finalize_opening_book.py [--db PATH] [--max-ply 12]
        [--max-positions 2000]
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

DEFAULT_DB = SCRIPT / "solver" / "data" / "tablebase.db"


def _ts() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def consolidate(db_path: Path) -> None:
    """Replie le WAL dans le fichier principal et compacte légèrement."""
    conn = sqlite3.connect(str(db_path))
    try:
        res = conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
        print(f"[{_ts()}] Checkpoint WAL: {res}")
        conn.execute("PRAGMA optimize")
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Finalise le livre d'ouverture + consolide la DB")
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--max-ply", type=int, default=12)
    parser.add_argument("--max-positions", type=int, default=2000)
    args = parser.parse_args()
    db_path = Path(args.db)

    print(f"[{_ts()}] Construction finale du livre d'ouverture…")
    n_exact, n_est = build_opening_book(
        db_path,
        max_ply=args.max_ply,
        max_positions=args.max_positions,
        refresh_estimates=False,
        verbose=True,
    )
    print(f"[{_ts()}] Livre terminé : exact={n_exact}, estimé={n_est}.")

    print(f"[{_ts()}] Consolidation de la base…")
    consolidate(db_path)
    print(f"[{_ts()}] FINALISATION TERMINEE.")


if __name__ == "__main__":
    main()
