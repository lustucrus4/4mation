"""Balayage des ouvertures : le bot testé encaisse-t-il les dix premiers coups ?

Le bot de niveau 6 gagne presque toujours avec le trait mais perd des parties quand il
subit l'ouverture. Ce script mesure ce déficit au lieu de le supposer : il force le
premier coup de l'attaquant, laisse les deux bots jouer normalement ensuite, et rend le
score du défenseur ouverture par ouverture.

Le premier coup est choisi dans les **orbites de symétrie** du plateau vide (rotation et
miroir) : jouer les 49 cases ne dirait rien de plus, et forcer plusieurs cases d'une même
orbite vérifie au passage que le bot répond aussi bien à une ouverture tournée qu'à sa
forme canonique — un moteur qui gère mal les symétries se trahit là.

    python scripts/opening_sweep.py --bot level_6 --opponent level_6
    python scripts/opening_sweep.py --bot level_6 --opponent level_5 --per-orbit 3
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
for path in (str(ROOT), str(ROOT / "script")):
    if path not in sys.path:
        sys.path.insert(0, path)

from api.services.bot_registry import BotRegistry, DifficultyBot  # noqa: E402
from game.game_engine import GameEngine  # noqa: E402
from solver.extract_opening_theory import first_move_orbits  # noqa: E402

MAX_MOVES = 90


def play_game(
    attacker: str,
    defender: str,
    opening: Tuple[int, int],
    registry: BotRegistry,
    defender_bot: Optional[Any] = None,
    attacker_bot: Optional[Any] = None,
) -> Dict[str, Any]:
    """Partie avec le premier coup de l'attaquant imposé à ``opening``.

    `defender_bot` et `attacker_bot` permettent de tester une variante de budget pour un
    camp sans toucher au registre des niveaux : c'est ainsi qu'on mesure si la défaite du
    second joueur tient à sa force ou à l'ouverture — et, en handicapant l'attaquant, si le
    moteur est biaisé en faveur du premier joueur plutôt que l'ouverture gagnante.
    """
    engine = GameEngine()
    engine.reset()

    applied = engine.step(opening)[1]
    if not applied:
        raise RuntimeError(f"premier coup imposé refusé : {opening}")

    first_move = (int(opening[0]), int(opening[1]))
    moves: List[Dict[str, Any]] = [
        {"ply": 0, "player": 1, "bot": attacker, "move": list(first_move), "secs": 0.0}
    ]
    winner: Optional[int] = None

    while not engine.is_terminal() and len(moves) < MAX_MOVES:
        player = int(engine.get_current_player())
        bot_id = attacker if player == 1 else defender
        start = time.perf_counter()
        if player == 2 and defender_bot is not None:
            move = defender_bot.choose_move(engine)
        elif player == 1 and attacker_bot is not None:
            move = attacker_bot.choose_move(engine)
        else:
            move = registry.choose_move(bot_id, engine)
        secs = time.perf_counter() - start
        if move is None:
            break
        _, ok, step_winner = engine.step(move)
        if not ok:
            break
        moves.append(
            {
                "ply": len(moves),
                "player": player,
                "bot": bot_id,
                "move": [int(move[0]), int(move[1])],
                "secs": round(secs, 3),
            }
        )
        if engine.is_terminal():
            winner = step_winner
            break

    if winner is None and engine.is_terminal():
        winner = engine.get_winner()
    winner = None if winner is None else int(winner)

    defender_plies = [m for m in moves if m["bot"] == defender]
    return {
        "opening": list(first_move),
        "attacker": attacker,
        "defender": defender,
        "winner": winner,
        "plies": len(moves),
        "truncated": len(moves) >= MAX_MOVES and winner is None,
        "defender_avg_secs": round(
            sum(m["secs"] for m in defender_plies) / len(defender_plies), 3
        )
        if defender_plies
        else 0.0,
        "moves": moves,
    }


def score_for(defender: str, game: Dict[str, Any]) -> float:
    """Score du défenseur (pierres O) : 1 victoire, 0,5 nulle, 0 défaite."""
    if game["winner"] == 2:
        return 1.0
    if game["winner"] == 1:
        return 0.0
    return 0.5


def main() -> int:
    parser = argparse.ArgumentParser(description="Balayage des ouvertures subies")
    parser.add_argument("--bot", default="level_6", help="Bot testé (pierres O)")
    parser.add_argument("--opponent", default="level_6", help="Attaquant (pierres X)")
    parser.add_argument("--per-orbit", type=int, default=1, help="Cases jouées par orbite")
    parser.add_argument("--max-orbits", type=int, default=0, help="Limiter le nombre d'orbites (0 = toutes)")
    parser.add_argument(
        "--only-opening",
        default=None,
        help="Ouvertures à jouer seules, en liste « 3,3 2,2 »",
    )
    parser.add_argument(
        "--defender-depth",
        type=int,
        default=None,
        help="Profondeur de la défense (défaut : celle du niveau)",
    )
    parser.add_argument(
        "--defender-time-ms",
        type=int,
        default=None,
        help="Budget temps de la défense en ms (défaut : celui du niveau)",
    )
    parser.add_argument(
        "--attacker-depth",
        type=int,
        default=None,
        help="Profondeur de l'attaque (défaut : celle du niveau)",
    )
    parser.add_argument(
        "--attacker-time-ms",
        type=int,
        default=None,
        help="Budget temps de l'attaque en ms (défaut : celui du niveau)",
    )
    parser.add_argument("--out", default="_tmp_opening_sweep.json", help="Rapport JSON")
    args = parser.parse_args()

    registry = BotRegistry()
    for bot_id in (args.bot, args.opponent):
        if not registry.is_valid_bot(bot_id):
            print(f"Bot inconnu : {bot_id}")
            return 2

    defender_bot = None
    if args.defender_depth is not None or args.defender_time_ms is not None:
        base = BotRegistry._LEVELS[args.bot]
        defender_bot = DifficultyBot(
            depth=args.defender_depth if args.defender_depth is not None else base["depth"],
            time_budget_ms=(
                args.defender_time_ms
                if args.defender_time_ms is not None
                else base["time_budget_ms"]
            ),
            use_tablebase=base["use_tablebase"],
            blunder_rate=0.0,
            use_engine=base.get("use_engine", False),
        )
        print(
            f"Défense renforcée : profondeur {defender_bot.depth}, "
            f"budget {defender_bot.time_budget_ms} ms",
            flush=True,
        )

    attacker_bot = None
    if args.attacker_depth is not None or args.attacker_time_ms is not None:
        base = BotRegistry._LEVELS[args.opponent]
        attacker_bot = DifficultyBot(
            depth=args.attacker_depth if args.attacker_depth is not None else base["depth"],
            time_budget_ms=(
                args.attacker_time_ms
                if args.attacker_time_ms is not None
                else base["time_budget_ms"]
            ),
            use_tablebase=base["use_tablebase"],
            blunder_rate=0.0,
            use_engine=base.get("use_engine", False),
        )
        print(
            f"Attaque handicapée : profondeur {attacker_bot.depth}, "
            f"budget {attacker_bot.time_budget_ms} ms",
            flush=True,
        )

    matches: List[Dict[str, Any]] = []
    orbits = first_move_orbits()
    if args.only_opening:
        # « 3,3 2,2 » et « 3 3 2 2 » sont acceptés : on normalise en une liste de paires.
        tokens = args.only_opening.replace(",", " ").split()
        if not tokens or len(tokens) % 2:
            print(f"Ouvertures illisibles : {args.only_opening}")
            return 2
        wanted_cells = [
            (int(tokens[i]), int(tokens[i + 1])) for i in range(0, len(tokens), 2)
        ]
        orbits = [
            (h, [cell for cell in cells if cell in wanted_cells]) for h, cells in orbits
        ]
        orbits = [(h, cells) for h, cells in orbits if cells]
        if not orbits:
            print(f"Ouvertures inconnues : {args.only_opening}")
            return 2
    if args.max_orbits > 0:
        orbits = orbits[: args.max_orbits]
    for _hash, cells in orbits:
        for cell in cells[: max(1, args.per_orbit)]:
            start = time.perf_counter()
            game = play_game(args.opponent, args.bot, cell, registry, defender_bot, attacker_bot)
            score = score_for(args.bot, game)
            matches.append({"score": score, **game})
            verdict = (
                f"{args.bot} gagne"
                if game["winner"] == 2
                else f"{args.opponent} gagne"
                if game["winner"] == 1
                else "nulle"
            )
            print(
                f"ouverture {cell[0]},{cell[1]} | {verdict} en {game['plies']} demi-coups "
                f"| {game['defender_avg_secs']:.2f} s/coup pour {args.bot} "
                f"| {time.perf_counter() - start:.0f} s",
                flush=True,
            )

    total = len(matches)
    points = sum(m["score"] for m in matches)
    wins = sum(1 for m in matches if m["score"] == 1.0)
    draws = sum(1 for m in matches if m["score"] == 0.5)
    losses = sum(1 for m in matches if m["score"] == 0.0)

    print()
    print(f"{total} parties : {args.opponent} (X) vs {args.bot} (O)")
    print(f"  {args.bot} : {points:g} / {total:g} = {100 * points / total:.1f} % des points")
    print(f"  {wins} victoire(s), {draws} nulle(s), {losses} défaite(s)")

    per_orbit: Dict[str, List[float]] = {}
    for m in matches:
        key = f"{m['opening'][0]},{m['opening'][1]}"
        per_orbit.setdefault(key, []).append(m["score"])
    if losses or draws:
        print()
        print("Ouvertures qui ne rapportent pas le point entier :")
        for key, scores in per_orbit.items():
            if min(scores) < 1.0:
                detail = ", ".join(f"{s:g}" for s in scores)
                print(f"  ({key}) : {detail}")

    # Table par ouverture, triée par rendement de la défense : c'est la mesure utile pour
    # la théorie — elle dit quelles ouvertures laissent une chance au second joueur.
    par_ouverture = []
    for key, scores in per_orbit.items():
        row, col = (int(x) for x in key.split(","))
        par_ouverture.append(
            {
                "ouverture": [row, col],
                "parties": len(scores),
                "points_defense": round(sum(scores), 2),
                "score_defense": round(sum(scores) / len(scores), 3),
                "defaites": sum(1 for s in scores if s == 0.0),
                "nulles": sum(1 for s in scores if s == 0.5),
                "duree_moyenne_plies": round(
                    sum(m["plies"] for m in matches if m["opening"] == [row, col])
                    / max(1, sum(1 for m in matches if m["opening"] == [row, col])),
                    1,
                ),
            }
        )
    par_ouverture.sort(key=lambda e: -e["score_defense"])

    print()
    print(f"{'ouverture':>10} {'parties':>7} {'points':>7} {'score':>7} {'plies':>7}")
    for entry in par_ouverture:
        print(
            f"  ({entry['ouverture'][0]},{entry['ouverture'][1]}) "
            f"{entry['parties']:>7} {entry['points_defense']:>7g} "
            f"{entry['score_defense']:>7.2f} {entry['duree_moyenne_plies']:>7g}"
        )

    Path(args.out).write_text(
        json.dumps(
            {
                "config": {
                    "bot": args.bot,
                    "opponent": args.opponent,
                    "per_orbit": args.per_orbit,
                    "defender_depth": args.defender_depth,
                    "defender_time_ms": args.defender_time_ms,
                    "attacker_depth": args.attacker_depth,
                    "attacker_time_ms": args.attacker_time_ms,
                },
                "par_ouverture": par_ouverture,
                "matches": matches,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nRapport : {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
