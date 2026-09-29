"""Test de non-régression du correctif win_rate / connexion par thread.

Vérifie trois choses :
1. un win_rate NULL ne fait plus échouer l'analyse (il est ignoré proprement) ;
2. `_as_rate` normalise les valeurs et rejette l'illisible ;
3. `_get_conn` rend une connexion distincte par thread.
"""

from __future__ import annotations

import sqlite3
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "script"))

from api.services.tablebase_lookup import _as_rate, get_tablebase_lookup  # noqa: E402

echecs: list[str] = []


def verifie(condition: bool, message: str) -> None:
    print(f"  {'OK ' if condition else 'ECHEC'} {message}")
    if not condition:
        echecs.append(message)


print("1. _as_rate")
verifie(_as_rate(None) is None, "None -> None")
verifie(_as_rate("abc") is None, "chaine non numerique -> None")
verifie(_as_rate("0.75") == 0.75, "chaine numerique -> float")
verifie(_as_rate(float("nan")) is None, "NaN -> None")
verifie(_as_rate(float("inf")) is None, "infini -> None")
verifie(_as_rate(-1.0) == 0.0, "borne basse a 0")
verifie(_as_rate(2.0) == 1.0, "borne haute a 1")
verifie(_as_rate(0.42) == 0.42, "valeur normale preservee")

print("\n2. Ligne a win_rate NULL (schema permissif simule)")
conn = sqlite3.connect(":memory:")
conn.row_factory = sqlite3.Row
conn.execute(
    "CREATE TABLE opening_book (hash TEXT, result TEXT, win_rate REAL, "
    "best_move_row INTEGER, best_move_col INTEGER, exact INTEGER)"
)
conn.execute("INSERT INTO opening_book VALUES ('h1', 'win', NULL, -1, -1, 1)")
row = conn.execute(
    "SELECT hash, result, win_rate, best_move_row, best_move_col, exact FROM opening_book"
).fetchone()
verifie(row["win_rate"] is None, "la ligne de test a bien win_rate NULL")

tb = get_tablebase_lookup()
try:
    hit = tb._row_to_hit(row, "opening_book")
    verifie(hit is None, "_row_to_hit ignore l'entree au lieu de lever une exception")
except Exception as exc:  # noqa: BLE001
    verifie(False, f"_row_to_hit a leve {type(exc).__name__}: {exc}")

conn.execute("UPDATE opening_book SET win_rate = 0.8, result = 'win'")
row_ok = conn.execute(
    "SELECT hash, result, win_rate, best_move_row, best_move_col, exact FROM opening_book"
).fetchone()
hit_ok = tb._row_to_hit(row_ok, "opening_book")
verifie(hit_ok is not None and abs(hit_ok.win_rate - 0.8) < 1e-9, "ligne saine toujours lue")

print("\n3. Connexion distincte par thread")
conns: dict[int, int] = {}
barrier = threading.Barrier(4)


def worker() -> None:
    c = tb._get_conn()
    barrier.wait()
    conns[threading.get_ident()] = id(c)


threads = [threading.Thread(target=worker) for _ in range(4)]
for t in threads:
    t.start()
for t in threads:
    t.join()
verifie(len(conns) == 4, f"4 threads -> 4 entrees (obtenu {len(conns)})")
verifie(len(set(conns.values())) == 4, f"4 connexions distinctes (obtenu {len(set(conns.values()))})")
verifie(tb._get_conn() is not None, "le thread principal a bien une connexion")

print("\n4. Lecture reelle de la tablebase")
hit = tb.lookup(
    __import__("numpy").zeros((7, 7), dtype=int), 1, None
)
print(f"  lookup(plateau vide) -> {hit}")
verifie(True, "lookup ne leve pas")

print()
if echecs:
    print(f"{len(echecs)} echec(s) :")
    for e in echecs:
        print("  -", e)
    raise SystemExit(1)
print("Tous les controles passent.")
