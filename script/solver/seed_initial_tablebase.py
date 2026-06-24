#!/usr/bin/env python3
"""
Génère la tablebase initiale (ouverture + endgame) pour déploiement.

Usage:
    python script/solver/seed_initial_tablebase.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = ROOT / "script"
if str(SCRIPT) not in sys.path:
    sys.path.insert(0, str(SCRIPT))

from solver.build_endgame_tablebase import DEFAULT_DB, generate_endgame_tablebase
from solver.build_opening_book import build_opening_book
from solver.db_schema import init_db


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Génère la tablebase initiale 4mation")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="Chemin SQLite cible")
    args = parser.parse_args()
    db = Path(args.db)
    print(f"Initialisation tablebase -> {db}")
    init_db(db)
    build_opening_book(db, max_ply=8, depth=4, time_budget_ms=1200)
    generate_endgame_tablebase(db, max_empty=12, num_games=80)
    print("Tablebase initiale prête.")


if __name__ == "__main__":
    main()
