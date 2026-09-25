"""Rejoue une partie de bots et pointe les coups fautifs à l'aide du moteur.

Le bot de niveau 6 perd environ une partie sur trois quand il **subit** l'ouverture
(il gagne presque toujours avec le trait). Ce script répond à la seule question qui
compte pour corriger : *où* perd-il la partie — quel demi-coup, quelle case jouée,
quelle case il fallait jouer, et combien de points de taux de victoire la faute coûte.

La partie est jouée par les bots réels puis auditée coup par coup par l'analyse du
site (`TablebaseLookup.analyze_position`), celle-là même que voient le coach et la
revue de partie. Une faute se mesure donc dans la même unité que ce que le site
affiche au joueur.

    python scripts/diagnose_bot_game.py --first level_5 --second level_6
    python scripts/diagnose_bot_game.py --first level_5 --second level_6 --json _tmp_partie.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
for path in (str(ROOT), str(ROOT / "script")):
    if path not in sys.path:
        sys.path.insert(0, path)

from api.services.bot_registry import BotRegistry  # noqa: E402
from api.services.tablebase_lookup import TablebaseLookup  # noqa: E402
from game.game_engine import GameEngine  # noqa: E402

MAX_MOVES = 90
SEUILS = (("gaffe", 0.20), ("faute", 0.10), ("imprécision", 0.05))


def render(board: np.ndarray, played=None, best=None, last=None) -> List[str]:
    """Rend le plateau en texte.

    Marques : ``*`` coup joué, ``^`` meilleur coup, ``#`` case du dernier coup.
    """
    symbols = {0: ".", 1: "X", 2: "O"}
    lines = []
    for r in range(7):
        cells = []
        for c in range(7):
            mark = symbols[int(board[r, c])]
            if played == (r, c):
                mark += "*"
            elif best == (r, c):
                mark += "^"
            if last == (r, c):
                mark += "#"
            cells.append(f"{mark:>4}")
        lines.append("".join(cells))
    return lines


def play_game(p1: str, p2: str, registry: BotRegistry) -> Dict[str, Any]:
    """Joue la partie et renvoie les états rencontrés, coup par coup."""
    engine = GameEngine()
    engine.reset()
    timeline: List[Dict[str, Any]] = []

    while not engine.is_terminal() and len(timeline) < MAX_MOVES:
        state = engine.get_state()
        board = np.array(state.board, dtype=np.int8).reshape(7, 7)
        player = int(state.current_player)
        last_raw = state.last_move_position
        last = tuple(last_raw) if last_raw is not None else None
        bot_id = p1 if player == 1 else p2

        move = registry.choose_move(bot_id, engine)
        if move is None:
            break
        applied = engine.step(move)[1]
        if not applied:
            break

        timeline.append(
            {
                "ply": len(timeline),
                "player": player,
                "bot": bot_id,
                "move": (int(move[0]), int(move[1])),
                "board": board.tolist(),
                "last_move": list(last) if last else None,
            }
        )

    return {
        "first_bot": p1,
        "second_bot": p2,
        "winner": engine.get_winner(),
        "moves": timeline,
    }


def audit(
    game: Dict[str, Any],
    seat: int,
    lookup: TablebaseLookup,
    depth: int,
    time_ms: int,
) -> List[Dict[str, Any]]:
    """Analyse chaque coup du siège auditê et mesure l'écart au meilleur coup.

    L'audit porte sur un **siège** (X ou O), pas sur un nom de bot : deux niveaux
    identiques peuvent s'affronter, et confondre les deux camps rendrait le bilan
    inutilisable.
    """
    findings: List[Dict[str, Any]] = []
    for entry in game["moves"]:
        if entry["player"] != seat:
            continue
        board = np.array(entry["board"], dtype=np.int8)
        last = tuple(entry["last_move"]) if entry["last_move"] else None
        analysis = lookup.analyze_position(
            board,
            int(entry["player"]),
            last,
            engine_depth=depth,
            engine_time_ms=time_ms,
        )
        if not analysis or not analysis.get("moves"):
            continue
        played = tuple(entry["move"])
        scores = {tuple(m["move"]): float(m["win_rate"]) for m in analysis["moves"]}
        if played not in scores:
            continue
        best_move = tuple(analysis["best_move"])
        best_wr = float(analysis.get("position_win_rate") or scores[best_move])
        played_wr = scores[played]
        delta = best_wr - played_wr

        kind = "correct"
        for label, threshold in SEUILS:
            if delta >= threshold:
                kind = label
                break

        findings.append(
            {
                "ply": entry["ply"],
                "move_number": entry["ply"] // 2 + 1,
                "player": entry["player"],
                "played": list(played),
                "best": list(best_move),
                "played_win_rate": round(played_wr, 4),
                "best_win_rate": round(best_wr, 4),
                "delta": round(delta, 4),
                "kind": kind,
                "source": analysis.get("source"),
                "exact": bool(analysis.get("exact")),
                "board": entry["board"],
                "last_move": entry["last_move"],
            }
        )
    return findings


def report(game: Dict[str, Any], findings: List[Dict[str, Any]], seat: int, label: str) -> None:
    print(
        f"{game['first_bot']} (X) vs {game['second_bot']} (O) — "
        f"{len(game['moves'])} demi-coups, gagnant : {game['winner']}"
    )
    print()

    print(f"Audit du siège {'X' if seat == 1 else 'O'} ({label})")
    counts: Dict[str, int] = {}
    for f in findings:
        counts[f["kind"]] = counts.get(f["kind"], 0) + 1
    total = sum(counts.values()) or 1
    for label_kind, _ in SEUILS:
        n = counts.get(label_kind, 0)
        print(f"  {label_kind:<13} {n:>3} / {total}")
    print(f"  {'correct':<13} {counts.get('correct', 0):>3} / {total}")

    fautes = [f for f in findings if f["kind"] != "correct"]
    if not fautes:
        print("\nAucune faute : la partie s'est jouée sans écart notable.")
        return

    print()
    print("Coups fautifs, du plus coûteux au moins coûteux")
    for f in sorted(fautes, key=lambda x: x["delta"], reverse=True)[:8]:
        print()
        print(
            f"  coup {f['move_number']} (ply {f['ply']}, joueur {f['player']}) — "
            f"{f['kind']} : {f['delta'] * 100:.1f} points de taux de victoire"
        )
        print(
            f"    joué ({f['played'][0]},{f['played'][1]}) à {f['played_win_rate'] * 100:.1f} % "
            f"| meilleur ({f['best'][0]},{f['best'][1]}) à {f['best_win_rate'] * 100:.1f} % "
            f"| source {f['source']}{' (prouvé)' if f['exact'] else ''}"
        )
        board = np.array(f["board"], dtype=np.int8)
        for line in render(
            board,
            played=tuple(f["played"]),
            best=tuple(f["best"]) if tuple(f["best"]) != tuple(f["played"]) else None,
            last=tuple(f["last_move"]) if f["last_move"] else None,
        ):
            print(f"    {line}")


def replay(path: Path, opening: Optional[Tuple[int, int]] = None) -> Dict[str, Any]:
    """Reconstruit une partie enregistrée par `opening_sweep.py`.

    Le balayage ne stocke que les coups joués et leurs durées, pas le plateau : il est
    reconstruit ici en appliquant les coups depuis le plateau vide, ce qui garantit que
    l'audit voit exactement les positions vues par les bots.
    """
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    matches = data["matches"]
    if opening is not None:
        matches = [m for m in matches if tuple(m["opening"]) == opening]
        if not matches:
            raise SystemExit(f"Aucune partie pour l'ouverture {opening} dans {path}")
    match = matches[0]

    board = np.zeros((7, 7), dtype=np.int8)
    timeline: List[Dict[str, Any]] = []
    last: Optional[Tuple[int, int]] = None
    for entry in match["moves"]:
        move = tuple(int(v) for v in entry["move"])
        timeline.append(
            {
                "ply": entry["ply"],
                "player": int(entry["player"]),
                "bot": entry["bot"],
                "move": move,
                "board": board.tolist(),
                "last_move": list(last) if last else None,
            }
        )
        board[move[0], move[1]] = int(entry["player"])
        last = move

    return {
        "first_bot": match["attacker"],
        "second_bot": match["defender"],
        "winner": match["winner"],
        "moves": timeline,
        "opening": match["opening"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Diagnostic d'une défaite de bot")
    parser.add_argument("--first", default="level_5", help="Bot qui a les pierres X")
    parser.add_argument("--second", default="level_6", help="Bot qui a les pierres O")
    parser.add_argument(
        "--seat",
        choices=["X", "O"],
        default="O",
        help="Siège audité : X (premier joueur) ou O (second). Défaut : O, la défense.",
    )
    parser.add_argument("--depth", type=int, default=18, help="Profondeur d'analyse")
    parser.add_argument("--time-ms", type=int, default=2000, help="Budget par position")
    parser.add_argument("--json", default=None, help="Enregistrer la partie auditée")
    parser.add_argument(
        "--replay",
        default=None,
        help="Auditer une partie enregistrée par opening_sweep.py au lieu d'en jouer une",
    )
    parser.add_argument(
        "--opening",
        default=None,
        help="Ouverture de la partie à rejouer, au format « 3,3 »",
    )
    args = parser.parse_args()

    registry = BotRegistry()

    if args.replay:
        opening = None
        if args.opening:
            r, c = args.opening.split(",")
            opening = (int(r), int(c))
        game = replay(Path(args.replay), opening)
        print(
            f"Partie rejouée : {game['first_bot']} (X) vs {game['second_bot']} (O), "
            f"ouverture {game['opening']}"
        )
    else:
        for bot_id in (args.first, args.second):
            if not registry.is_valid_bot(bot_id):
                print(f"Bot inconnu : {bot_id}")
                return 2
        print(f"Partie {args.first} (X) vs {args.second} (O)...")
        game = play_game(args.first, args.second, registry)

    print(
        f"  terminée en {len(game['moves'])} demi-coups, gagnant : {game['winner']} "
        f"({'X' if game['winner'] == 1 else 'O' if game['winner'] == 2 else 'aucun'})"
    )
    print()

    lookup = TablebaseLookup()
    seat = 1 if args.seat == "X" else 2
    label = game["first_bot"] if seat == 1 else game["second_bot"]
    findings = audit(game, seat, lookup, args.depth, args.time_ms)
    report(game, findings, seat, label)

    if args.json:
        payload = {"game": game, "findings": findings, "seat": seat}
        Path(args.json).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"\nDétail enregistré dans {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
