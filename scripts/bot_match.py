"""Banc d'essai bot contre bot : mesure la force relative des niveaux.

Chaque manche se joue en deux parties, une par couleur, pour neutraliser
l'avantage du premier joueur (qui joue le centre et mène la danse).

    python scripts/bot_match.py --bot1 level_6 --bot2 level_5 --games 2

Le script est volontairement bavard : une ligne par partie, puis un bilan.
Il sert aussi de test de non-régression sur le niveau 6 : si le moteur Rust
tombe en panne, le repli Minimax doit rester légal et le script continuer.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for path in (str(ROOT), str(ROOT / "script")):
    if path not in sys.path:
        sys.path.insert(0, path)

from api.services.bot_registry import BotRegistry  # noqa: E402
from game.game_engine import GameEngine  # noqa: E402

MAX_MOVES = 90


def play_game(p1: str, p2: str, registry: BotRegistry) -> dict:
    """Joue une partie : `p1` a les pierres du joueur 1, `p2` celles du joueur 2."""
    engine = GameEngine()
    engine.reset()

    moves: list[str] = []
    winner = None
    start = time.perf_counter()
    while not engine.is_terminal() and len(moves) < MAX_MOVES:
        player = int(engine.get_current_player())
        bot_id = p1 if player == 1 else p2
        move = registry.choose_move(bot_id, engine)
        if move is None:
            break
        # `step` renvoie (état, coup appliqué, gagnant) : le second champ n'est pas
        # « partie terminée », c'est un piège classique de cette API.
        _, applied, step_winner = engine.step(move)
        if not applied:
            break
        moves.append(f"{player}:{move[0]},{move[1]}")
        if engine.is_terminal():
            winner = step_winner
            break

    if winner is None and engine.is_terminal():
        winner = engine.get_winner()

    return {
        "winner": winner,
        "moves": len(moves),
        "secs": time.perf_counter() - start,
        "truncated": len(moves) >= MAX_MOVES and winner is None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Match bot contre bot")
    parser.add_argument("--bot1", default="level_6")
    parser.add_argument("--bot2", default="level_5")
    parser.add_argument("--games", type=int, default=2, help="manches (2 parties chacune)")
    parser.add_argument("--color", choices=["both", "first", "second"], default="both")
    args = parser.parse_args()

    registry = BotRegistry()
    for bot_id in (args.bot1, args.bot2):
        if not registry.is_valid_bot(bot_id):
            print(f"Bot inconnu : {bot_id}")
            return 2

    firsts = [(args.bot1, args.bot2)]
    if args.color == "both":
        firsts.append((args.bot2, args.bot1))
    elif args.color == "second":
        firsts = [(args.bot2, args.bot1)]

    scores = {args.bot1: 0.0, args.bot2: 0.0}
    played = 0
    start = time.perf_counter()

    for manche in range(1, args.games + 1):
        for p1, p2 in firsts:
            played += 1
            result = play_game(p1, p2, registry)
            if result["winner"] == 1:
                scores[p1] += 1.0
                verdict = f"{p1} gagne"
            elif result["winner"] == 2:
                scores[p2] += 1.0
                verdict = f"{p2} gagne"
            else:
                scores[p1] += 0.5
                scores[p2] += 0.5
                verdict = "nulle" + (" (limite de coups)" if result["truncated"] else "")

            print(
                f"manche {manche} partie {played} | {p1} (X) vs {p2} (O) | "
                f"{verdict} en {result['moves']} coups, {result['secs']:.0f} s"
            )

    total = scores[args.bot1] + scores[args.bot2]
    elapsed = time.perf_counter() - start
    print()
    print(f"{played} parties en {elapsed / 60:.1f} min")
    print(f"  {args.bot1} : {scores[args.bot1]:g} / {total:g}")
    print(f"  {args.bot2} : {scores[args.bot2]:g} / {total:g}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
