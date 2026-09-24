"""Vérifie que le moteur Rust et le moteur de jeu Python listent les mêmes coups.

Un désaccord sur les coups légaux (case libre, adjacence au dernier coup, couleur au
trait) ferait proposer au site des coups que le moteur de jeu refuserait. On compare
les ensembles sur une marche aléatoire de parties, et on analyse chaque position avec
le chemin complet de l'API pour voir d'où vient la réponse.
"""

import random
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
for p in (str(ROOT), str(ROOT / "script")):
    if p not in sys.path:
        sys.path.insert(0, p)

from api.services.engine_client import EngineClient  # noqa: E402
from api.services.tablebase_lookup import get_tablebase_lookup  # noqa: E402
from game.game_engine import GameEngine  # noqa: E402
from game_tree.optimized_minimax import OptimizedMinimaxAdvisor  # noqa: E402

rng = random.Random(7)
advisor = OptimizedMinimaxAdvisor(depth=1, use_iterative_deepening=False)
client = EngineClient(default_depth=10, default_time_ms=300)

if not client.is_available():
    print("moteur absent")
    raise SystemExit(1)

mismatches = 0
checked = 0
labels: dict[str, int] = {}
sources: dict[str, int] = {}
tb = get_tablebase_lookup()

for game in range(12):
    engine = GameEngine()
    engine.reset()
    for ply in range(40):
        if engine.is_terminal():
            break
        state = engine.get_state()
        board = state.board
        player = int(state.current_player)
        last = None
        if state.action_history:
            _, r, c = state.action_history[-1]
            last = (int(r), int(c))

        py_moves = set(advisor._get_frontier_moves(board, last, player))
        resp = client.request(
            {
                "board": [[int(c) for c in row] for row in board],
                "current_player": player,
                "last_move": [int(last[0]), int(last[1])] if last else None,
                "depth": 10,
                "time_ms": 300,
                "exact": True,
            }
        )
        if not resp or "moves" not in resp:
            print("réponse moteur invalide :", resp)
            raise SystemExit(1)
        rs_moves = {(int(m["row"]), int(m["col"])) for m in resp["moves"]}
        checked += 1
        if py_moves != rs_moves:
            mismatches += 1
            if mismatches <= 5:
                print(f"DÉSACCORD partie {game} ply {ply} joueur {player} dernier={last}")
                print("   python - rust :", sorted(py_moves - rs_moves))
                print("   rust - python :", sorted(rs_moves - py_moves))
                for row in board:
                    print("   " + " ".join("." if c == 0 else ("X" if c == 1 else "O") for c in row))

        if ply % 3 == 0:
            analysis = tb.analyze_position(board, player, last)
            if analysis:
                labels[str(analysis.get("label"))] = labels.get(str(analysis.get("label")), 0) + 1
                sources[str(analysis.get("source"))] = sources.get(str(analysis.get("source")), 0) + 1

        move = rng.choice(sorted(py_moves)) if py_moves else None
        if move is None:
            break
        applied, _, _ = engine.step(move)
        if not applied:
            break

print()
print(f"{checked} positions comparées | {mismatches} désaccords sur les coups légaux")
print("sources d'analyse :", sources)
print("libellés          :", labels)
client.close()
