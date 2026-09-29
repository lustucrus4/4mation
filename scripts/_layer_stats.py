"""Statistiques de remplissage de la tablebase par couche (cases vides).

Utilitaire de diagnostic : compte les positions par nombre de cases vides et
affiche le taux de remplissage par rapport au décompte attendu, afin de mesurer
honnêtement la couverture avant un balayage de couche.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

DB = Path(__file__).resolve().parents[1] / "script" / "solver" / "data" / "tablebase.db"


def main() -> int:
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    try:
        tables = [r[0] for r in conn.execute("select name from sqlite_master where type='table'")]
        print("Tables :", ", ".join(tables))
        cols = [d[1] for d in conn.execute("pragma table_info(positions)")]
        print("Colonnes positions :", ", ".join(cols))

        total = conn.execute("select count(*) from positions").fetchone()[0]
        print(f"Total : {total} positions\n")

        print(f"{'vides':>5} | {'lignes':>12} | {'résultats':>28}")
        for empty, count in conn.execute(
            "select empty_cells, count(*) from positions group by empty_cells order by empty_cells"
        ):
            dist = conn.execute(
                "select result, count(*) from positions where empty_cells=? group by result order by result",
                (empty,),
            ).fetchall()
            dist_txt = " ".join(f"{r}:{c}" for r, c in dist)
            print(f"{empty:>5} | {count:>12} | {dist_txt:>28}")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
