"""Bout en bout : une partie jouée par des bots, puis sa revue par le moteur.

Vérifie que la revue de partie (route `/api/account` de l'API) fonctionne avec le
moteur Rust : classification de chaque coup, précision, graphe de taux de victoire,
et surtout le temps — la revue passe d'un MCTS de 350 ms par coup à une analyse moteur.
"""

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for p in (str(ROOT), str(ROOT / "script")):
    if p not in sys.path:
        sys.path.insert(0, p)

from api.services.bot_registry import BotRegistry  # noqa: E402
from api.services.game_review import build_game_review  # noqa: E402
from api.services.engine_client import get_engine_client  # noqa: E402
from game.game_engine import GameEngine  # noqa: E402

client = get_engine_client()
print("moteur disponible :", client.is_available(), "|", client.binary)
print()

registry = BotRegistry()
engine = GameEngine()
engine.reset()
history = []

start = time.perf_counter()
while not engine.is_terminal() and len(history) < 40:
    player = int(engine.get_current_player())
    bot = "level_5" if player == 1 else "level_4"
    move = registry.choose_move(bot, engine)
    if move is None:
        break
    applied, _, _ = engine.step(move)
    if not applied:
        break
    history.append(
        {
            "index": len(history) + 1,
            "player": player,
            "row": int(move[0]),
            "col": int(move[1]),
        }
    )
play_secs = time.perf_counter() - start

state = engine.get_state()
print(f"partie : {len(history)} coups en {play_secs:.0f} s | gagnant = {engine.get_winner()}")
print()

start = time.perf_counter()
review = build_game_review(history, human_color=1)
review_secs = time.perf_counter() - start

print(f"revue  : {review['move_count']} coups en {review_secs:.1f} s "
      f"({review_secs / max(review['move_count'], 1) * 1000:.0f} ms/coup)")
print(f"précision joueur 1 (pierres X) : {review['human_accuracy']} %")
print()

counts: dict[str, int] = {}
sources: dict[str, int] = {}
for m in review["moves"]:
    counts[m["classification"]] = counts.get(m["classification"], 0) + 1
    sources[str(m["source"])] = sources.get(str(m["source"]), 0) + 1

print("classifications :", counts)
print("sources         :", sources)
print()
print("5 premiers coups analysés :")
for m in review["moves"][:5]:
    print(
        f"  #{m['index']:>2} joueur {m['player']} ({m['row']},{m['col']}) "
        f"{m['classification']:<11} taux avant {m['win_rate_before']:.3f} "
        f"joué {m['win_rate_played']:.3f} meilleur {m['win_rate_best']:.3f} "
        f"conseil {m['best_move']} | {m['source']} exact={m['exact']}"
    )
print()
print("3 derniers coups :")
for m in review["moves"][-3:]:
    print(
        f"  #{m['index']:>2} joueur {m['player']} ({m['row']},{m['col']}) "
        f"{m['classification']:<11} taux joué {m['win_rate_played']:.3f} "
        f"meilleur {m['win_rate_best']:.3f} conseil {m['best_move']} | {m['source']}"
    )
print()
print("graphe (taux du joueur 1) :", [round(g["win_rate_p1"], 2) for g in review["graph"]][:12], "...")
