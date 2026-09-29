"""Contrôle d'intégrité ciblé de la tablebase.

Vérifie les index du livre d'ouverture et cherche des entrées d'index pointant vers
une ligne incohérente — piste privilégiée pour expliquer un win_rate NULL alors que
la colonne est NOT NULL.
"""

from __future__ import annotations

import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "script"))

from api.services.tablebase_lookup import DEFAULT_DB  # noqa: E402

conn = sqlite3.connect(f"file:{DEFAULT_DB}?mode=ro", uri=True)
conn.row_factory = sqlite3.Row

print("Index et tables :")
for r in conn.execute(
    "select type, name, tbl_name from sqlite_master where type in ('index','table') order by tbl_name, type"
):
    print(f"  {r['type']:<6} {r['name']:<40} sur {r['tbl_name']}")
print()

for table in ("opening_book", "positions"):
    t0 = time.perf_counter()
    try:
        res = conn.execute(f"pragma integrity_check({table})").fetchall()
        vals = [r[0] for r in res]
        ok = vals == ["ok"]
        print(f"integrity_check({table}) : {'OK' if ok else 'PROBLEME'} en {time.perf_counter()-t0:.1f}s")
        for v in vals[:20]:
            if v != "ok":
                print("   ", v)
    except sqlite3.Error as exc:
        print(f"integrity_check({table}) : erreur {exc}")

print()
# Vérifie qu'un échantillon d'entrées d'index retrouve bien sa ligne.
for table, index in (("opening_book", None), ("positions", None)):
    idx = conn.execute(
        "select name from sqlite_master where type='index' and tbl_name=?", (table,)
    ).fetchall()
    for row in idx:
        name = row["name"]
        t0 = time.perf_counter()
        bad = conn.execute(
            f"select count(*) from {table} indexed by {name} where win_rate is null"
        ).fetchone()[0]
        print(f"{table} via index {name} : win_rate NULL = {bad} ({time.perf_counter()-t0:.1f}s)")

conn.close()
