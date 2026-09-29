"""Diagnostic du plantage win_rate NULL dans le livre d'ouverture.

Affiche le chemin de base réellement utilisé par l'API, le schéma des tables et les
lignes incohérentes (win_rate ou result NULL) sur l'ensemble des tables lues.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "script"))

from api.services.tablebase_lookup import DEFAULT_DB  # noqa: E402

print(f"Chemin utilise par l'API : {DEFAULT_DB}")
print(f"Existe : {DEFAULT_DB.exists()}")
print()

conn = sqlite3.connect(f"file:{DEFAULT_DB}?mode=ro", uri=True)
conn.row_factory = sqlite3.Row

tables = [
    r[0]
    for r in conn.execute("select name from sqlite_master where type='table' order by name")
]
print("Tables :", ", ".join(tables))
print()

for table in tables:
    cols = {d[1]: d for d in conn.execute(f"pragma table_info({table})")}
    print(f"--- {table} ({conn.execute(f'select count(*) from {table}').fetchone()[0]} lignes) ---")
    for name, d in cols.items():
        notnull = "NOT NULL" if d[3] else "nullable"
        print(f"    {name:<16} {d[2]:<8} {notnull}")

    if "win_rate" in cols:
        n = conn.execute(f"select count(*) from {table} where win_rate is null").fetchone()[0]
        print(f"    >> win_rate NULL : {n}")
    if "result" in cols:
        n = conn.execute(f"select count(*) from {table} where result is null").fetchone()[0]
        print(f"    >> result   NULL : {n}")
    print()

conn.close()
