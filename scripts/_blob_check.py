"""Contrôle de cohérence entre les colonnes ``empty_cells`` et ``board_blob``.

Vérifie que le décompte de cases vides recalculé depuis le plateau stocké correspond
bien à la colonne dénormalisée, sur un échantillon par couche.
"""

from __future__ import annotations

import sqlite3
import sys
from collections import Counter
from pathlib import Path

N = 7
DB = Path(__file__).resolve().parents[1] / "script" / "solver" / "data" / "tablebase.db"


def blob_to_cells(blob: bytes) -> list[int]:
    return [(blob[i // 4] >> ((i % 4) * 2)) & 0b11 for i in range(N * N)]


def main() -> int:
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    try:
        for layer in (5, 6, 7, 8, 9):
            agreed = 0
            mismatch = Counter()
            for blob, empty in conn.execute(
                "select board_blob, empty_cells from positions where empty_cells=? limit 4000",
                (layer,),
            ):
                real = sum(1 for c in blob_to_cells(blob) if c == 0)
                if real == layer:
                    agreed += 1
                else:
                    mismatch[real] += 1
            print(f"couche {layer}: {agreed}/4000 cohérents | écarts vers {dict(mismatch)}")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
