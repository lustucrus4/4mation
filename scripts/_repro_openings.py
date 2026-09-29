"""Reproduction du 500 sur /api/learn/openings/explore.

Balaye des lignes d'ouverture en rejouant `explore_opening` et rapporte la première
séquence qui lève une exception, avec la trace complète. Utilitaire de diagnostic.
"""

from __future__ import annotations

import itertools
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "script"))

from api.services.opening_explorer import explore_opening  # noqa: E402
from api.services.tablebase_lookup import get_tablebase_lookup  # noqa: E402
from game.game_engine import GameEngine  # noqa: E402


def scan(depth: int) -> list[tuple[list[tuple[int, int]], BaseException]]:
    failures: list[tuple[list[tuple[int, int]], BaseException]] = []
    engine = GameEngine()
    engine.reset()
    checked = 0

    def walk(prefix: list[tuple[int, int]], valid: list[tuple[int, int]]) -> None:
        nonlocal checked
        for move in valid:
            line = prefix + [move]
            checked += 1
            try:
                explore_opening(line)
            except Exception as exc:  # noqa: BLE001 - on veut tout attraper
                failures.append((line, exc))
                print(f"ECHEC {line}: {type(exc).__name__}: {exc}")
                if len(failures) >= 5:
                    return
            if len(line) < depth:
                nxt = GameEngine()
                nxt.reset()
                for m in line:
                    nxt.step(m)
                walk(line, list(nxt.get_valid_actions()))

    walk([], list(engine.get_valid_actions()))
    print(f"\n{depth} demi-coup(s) : {checked} lignes testees, {len(failures)} echec(s)")
    return failures


def inspect_line(line: list[tuple[int, int]]) -> None:
    """Détaille le coup qui casse : interroge directement la base."""
    engine = GameEngine()
    engine.reset()
    for row, col in line:
        engine.step((row, col))
    state = engine.get_state()
    last = None
    if state.action_history:
        _, r, c = state.action_history[-1]
        last = (int(r), int(c))

    tb = get_tablebase_lookup()
    hit = tb.lookup(state.board, int(state.current_player), last)
    print(f"\n--- ligne {line} ---")
    print(f"hit: {hit}")
    moves = tb._advisor._get_frontier_moves(state.board, last, int(state.current_player))
    import numpy as np

    from game.hasher import HASHER

    for move in moves:
        nb = state.board.copy()
        nb[move[0], move[1]] = int(state.current_player)
        opp = 3 - int(state.current_player)
        h = HASHER.hash_key(nb, opp, move)
        conn = tb._get_conn()
        b = conn.execute(
            "SELECT result, win_rate, exact FROM opening_book WHERE hash=?", (h,)
        ).fetchone()
        p = conn.execute(
            "SELECT result, win_rate FROM positions WHERE hash=?", (h,)
        ).fetchone()
        print(f"  coup {move} hash={h}")
        print(f"    opening_book={dict(b) if b else None}")
        print(f"    positions   ={dict(p) if p else None}")


if __name__ == "__main__":
    depth = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    fails = scan(depth)
    if fails:
        inspect_line(fails[0][0])
        print("\nTrace complete :")
        traceback.print_exception(fails[0][1])
