"""Vérifie la conversion moteur → format API sur trois familles de positions."""

import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for p in (str(ROOT), str(ROOT / "script")):
    if p not in sys.path:
        sys.path.insert(0, p)

from api.services.engine_analysis import engine_analysis, get_scale_cache  # noqa: E402
from solver.db_schema import board_from_blob  # noqa: E402

print("échelle de score :", get_scale_cache().scale)
print()


def render(board):
    for row in board:
        print("   " + " ".join("." if c == 0 else ("X" if c == 1 else "O") for c in row))


def show(name, board, player, last, **kw):
    print(f"=== {name} ===")
    if board is not None:
        render(board)
    a = engine_analysis(board, player, last, **kw)
    if a is None:
        print("   moteur indisponible")
        return
    print(f"   {a['label']} | source={a['source']} exact={a['exact']} "
          f"taux={a['position_win_rate']:.3f} ({a['position_result']}) "
          f"| profondeur {a['engine_depth']} | {a['elapsed_ms']} ms")
    print(f"   meilleur coup : {a['best_move']} | couverture {a['coverage_percent']:.0f}%"
          f" | interrompu={a['truncated']}")
    for m in a["moves"][:6]:
        mate = f" mat en {m['mate_in']}" if m["mate_in"] else ""
        print(f"     ({m['row']},{m['col']}) taux={m['win_rate']:.3f} {m['result']} "
              f"score={m['score']:>7} prouvé={m['proven']}{mate}")
    print()


# 1) Plateau vide : le moteur doit proposer le centre, en estimation.
empty = [[0] * 7 for _ in range(7)]
show("plateau vide (ply 0)", empty, 1, None)

# 2) Défense : X aligne 3 en colonne, O doit bloquer.
board = [[0] * 7 for _ in range(7)]
board[3][3] = 1
board[3][4] = 2
board[2][3] = 1
board[4][4] = 2
board[1][3] = 1
show("O doit tenir la colonne 3", board, 2, (1, 3))

# 3) Finale exacte lue dans la tablebase (le moteur y accède).
db = ROOT / "script" / "solver" / "data" / "tablebase.db"
con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
con.row_factory = sqlite3.Row
row = con.execute(
    """
    SELECT board_blob, current_player, pos_last_move_row, pos_last_move_col, result, empty_cells
    FROM positions
    WHERE empty_cells = 6 AND board_blob IS NOT NULL
      AND pos_last_move_row >= 0
    ORDER BY rowid LIMIT 1
    """
).fetchone()
if row:
    b = board_from_blob(bytes(row["board_blob"]))
    show(
        f"finale {row['empty_cells']} cases vides (tablebase : {row['result']})",
        b,
        int(row["current_player"]),
        (int(row["pos_last_move_row"]), int(row["pos_last_move_col"])),
    )
