"""Vérifie que le mode exact est bien réglable par requête sur un même processus."""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BIN = ROOT / "script" / "solver_rust" / "target" / "release" / "4mation-engine.exe"

board = [[0] * 7 for _ in range(7)]
board[3][3] = 1
board[3][4] = 2
board[2][3] = 1
board[4][4] = 2
board[1][3] = 1

proc = subprocess.Popen(
    [str(BIN), "--tt-mb", "64", "--depth", "12", "--time-ms", "1200"],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    text=True,
    encoding="utf-8",
    bufsize=1,
)


def ask(exact):
    req = {
        "board": board,
        "current_player": 2,
        "last_move": [1, 3],
        "depth": 12,
        "time_ms": 1200,
        "exact": exact,
    }
    proc.stdin.write(json.dumps(req) + "\n")
    proc.stdin.flush()
    return json.loads(proc.stdout.readline())


for flag in (False, True, False):
    resp = ask(flag)
    moves = resp.get("moves") or []
    n_exact = sum(1 for m in moves if m.get("exact"))
    print(
        f"exact={flag!s:>5} -> exact_root={resp.get('exact_root')} | "
        f"best={resp.get('best_move')} score={resp.get('score')} proven={resp.get('proven')} | "
        f"{n_exact}/{len(moves)} scores exacts | {resp.get('nodes')} nœuds"
    )
    for m in moves[:5]:
        print(f"    ({m['row']},{m['col']}) score={m['score']:>7} exact={m['exact']} {m['proven']}")

proc.stdin.write('{"type":"quit"}\n')
proc.stdin.flush()
proc.wait(timeout=5)
sys.exit(0)
