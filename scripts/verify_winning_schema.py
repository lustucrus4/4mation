#!/usr/bin/env python3
"""Vérifie qu'un schéma gagnant tient contre plusieurs défenses, pas seulement la meilleure.

Un schéma tiré d'une seule partie ne prouve rien : la défense jouée peut avoir été la
meilleure sans que les autres soient pires. Ce script rejoue la même ouverture plusieurs
fois, l'attaque jouant toujours son meilleur coup, la défense choisissant à chaque tour un
coup parmi les **meilleurs coups du moteur** (tirage contrôlé par une graine, donc
reproductible). Chaque partie est donc une défense différente mais toujours forte.

Trois verdicts possibles :

- **schéma robuste** : toutes les lignes tournent de la même façon, quel que soit le choix
  de la défense ;
- **défense sauvée** : au moins une ligne échappe au gain — la ligne de référence n'était
  pas forcée, elle sanctionnait une imprécision ;
- **nulle** : les lignes se terminent sans vainqueur (grille pleine).

Usage :
    python scripts/verify_winning_schema.py --opening 3,3 --games 6 --defense-top 3
    python scripts/verify_winning_schema.py --opening 0,0 --games 6   # contrôle
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
for _path in (str(ROOT), str(ROOT / "script")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from api.services.engine_analysis import result_for  # noqa: E402
from api.services.engine_client import EngineClient  # noqa: E402
from game.game_engine import GameEngine  # noqa: E402

MAX_MOVES = 90
SYMBOLS = {0: ".", 1: "X", 2: "O"}


def best_moves(
    client: EngineClient,
    board: np.ndarray,
    player: int,
    last: Optional[Tuple[int, int]],
    depth: int,
    time_ms: int,
) -> List[Dict[str, Any]]:
    """Coups du moteur, du meilleur au pire, avec leur taux de victoire.

    Le moteur renvoie un score heuristique et un verdict (`gain` / `perte` / `nulle` quand
    il a la preuve). La conversion en taux de victoire passe par `result_for`, la même
    fonction que celle qui alimente l'analyse du site : les deux ne peuvent pas diverger.
    """
    analysis = client.analyze(board, player, last, depth=depth, time_ms=time_ms, exact=True)
    if not analysis or not analysis.get("moves"):
        return []
    rows: List[Dict[str, Any]] = []
    for entry in analysis["moves"]:
        move = entry.get("move")
        if move is None:
            if entry.get("row") is None or entry.get("col") is None:
                continue
            move = (entry["row"], entry["col"])
        proven = entry.get("proven")
        _, win_rate, exact = result_for(float(entry.get("score") or 0.0), proven)
        rows.append(
            {
                "coup": (int(move[0]), int(move[1])),
                "win_rate": float(win_rate),
                "score": float(entry.get("score") or 0.0),
                "verdict": str(proven or ""),
                "exact": bool(exact),
            }
        )
    rows.sort(key=lambda item: -item["win_rate"])
    return rows


def play(
    client: EngineClient,
    opening: Tuple[int, int],
    depth: int,
    time_ms: int,
    defense_top: int,
    rng: random.Random,
) -> Dict[str, Any]:
    """Une partie : l'attaque joue le meilleur coup, la défense tire dans son top N."""
    engine = GameEngine()
    engine.reset()
    if not engine.step(opening)[1]:
        raise RuntimeError(f"ouverture refusée : {opening}")

    moves: List[Dict[str, Any]] = [
        {"ply": 0, "player": 1, "move": list(opening), "win_rate": None, "rang": 0, "choix": 1}
    ]
    analyses = 0
    while not engine.is_terminal() and len(moves) < MAX_MOVES:
        state = engine.get_state()
        board = np.array(state.board, dtype=np.int8).reshape(7, 7)
        player = int(state.current_player)
        last_raw = state.last_move_position
        last = tuple(last_raw) if last_raw is not None else None

        candidates = best_moves(client, board, player, last, depth, time_ms)
        analyses += 1
        if not candidates:
            break

        if player == 2 and defense_top > 1:
            pool = candidates[:defense_top]
            rank = rng.randrange(len(pool))
            chosen = pool[rank]
        else:
            rank = 0
            chosen = candidates[0]

        applied = engine.step(chosen["coup"])[1]
        if not applied:
            break
        moves.append(
            {
                "ply": len(moves),
                "player": player,
                "move": list(chosen["coup"]),
                "win_rate": round(chosen["win_rate"], 4),
                "rang": rank,
                "choix": len(candidates),
                "verdict": chosen["verdict"],
                "exact": chosen["exact"],
            }
        )

    winner = engine.get_winner()
    return {
        "opening": list(opening),
        "winner": None if winner is None else int(winner),
        "plies": len(moves),
        "analyses": analyses,
        "moves": moves,
        "defense_rangs": [m["rang"] for m in moves if m["player"] == 2],
    }


def render_board(board: np.ndarray, last: Optional[Tuple[int, int]] = None) -> List[str]:
    lines = ["      c0   c1   c2   c3   c4   c5   c6"]
    for row in range(7):
        cells = []
        for col in range(7):
            label = SYMBOLS[int(board[row, col])]
            if last == (row, col):
                label += "#"
            cells.append(f"{label:<4}")
        lines.append(f"  r{row}  " + "".join(cells))
    return lines


def line_text(game: Dict[str, Any]) -> str:
    """La partie en une ligne : `X3,3 O2,2 ...` du premier au dernier demi-coup."""
    return " ".join(
        f"{'X' if m['player'] == 1 else 'O'}{m['move'][0]},{m['move'][1]}"
        for m in game["moves"]
    )


def replay(moves: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Rejoue la partie et renvoie un instantané après chaque demi-coup."""
    engine = GameEngine()
    engine.reset()
    frames: List[Dict[str, Any]] = []
    for entry in moves:
        move = (int(entry["move"][0]), int(entry["move"][1]))
        engine.step(move)
        state = engine.get_state()
        frames.append(
            {
                "board": np.array(state.board, dtype=np.int8).reshape(7, 7).copy(),
                "last": move,
                "move": move,
                "player": int(entry["player"]),
                "win_rate": entry.get("win_rate"),
                "rang": int(entry.get("rang") or 0),
            }
        )
    return frames


def render(payload: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append("# Vérification d'un schéma gagnant contre plusieurs défenses")
    lines.append("")
    lines.append(
        f"Ouverture ({payload['opening'][0]},{payload['opening'][1]}), "
        f"{payload['parties']} partie(s), analyse à la profondeur {payload['profondeur']} "
        f"pendant {payload['budget_ms']} ms. L'attaque joue toujours son meilleur coup ; "
        f"la défense tire à chaque tour dans ses {payload['defense_top']} meilleurs coups."
    )
    lines.append("")
    lines.append("## Résultat par partie")
    lines.append("")
    lines.append("| Partie | Vainqueur | Demi-coups | Rangs défensifs tirés | Taux final du trait |")
    lines.append("|--------|-----------|------------|----------------------|---------------------|")
    for game in payload["jeux"]:
        winner = game["winner"]
        verdict = "X" if winner == 1 else "O" if winner == 2 else "nulle"
        last_wr = game["moves"][-1]["win_rate"] if game["moves"] else None
        rangs = " ".join(str(r) for r in game["defense_rangs"]) or "—"
        lines.append(
            f"| {game['index']} | {verdict} | {game['plies']} | {rangs} | "
            f"{'—' if last_wr is None else f'{last_wr * 100:.0f} %'} |"
        )
    lines.append("")
    lines.append("## Lignes jouées")
    lines.append("")
    lines.append(
        "Chaque ligne part de l'ouverture imposée. `Xn,m` = coup du premier joueur, "
        "`On,m` = coup du second joueur, au format `ligne,colonne` (0 à 6)."
    )
    lines.append("")
    for game in payload["jeux"]:
        winner = game["winner"]
        verdict = "X" if winner == 1 else "O" if winner == 2 else "nulle"
        lines.append(f"- **{game['index']}** ({verdict}, {game['plies']} demi-coups) : {line_text(game)}")
    lines.append("")

    decisive = [g for g in payload["jeux"] if g["winner"] is not None]
    if decisive:
        shortest = min(decisive, key=lambda g: g["plies"])
        lines.append("## Ligne la plus courte")
        lines.append("")
        lines.append(
            f"Partie {shortest['index']}, gagnée par "
            f"{'X' if shortest['winner'] == 1 else 'O'} en {shortest['plies']} demi-coups — "
            "la ligne la plus directe, celle qu'un cours peut montrer telle quelle."
        )
        lines.append("")
        for index, frame in enumerate(replay(shortest["moves"])):
            side = "X" if frame["player"] == 1 else "O"
            wr = frame["win_rate"]
            if wr is None:
                head = f"**{index}. {side} joue `{frame['move'][0]},{frame['move'][1]}`**"
            else:
                head = (
                    f"**{index}. {side} joue `{frame['move'][0]},{frame['move'][1]}`** — "
                    f"rang {frame['rang']}, évaluation avant le coup "
                    f"{wr * 100:.0f} %"
                )
            lines.append(head)
            lines.append("")
            lines.append("```")
            lines.extend(render_board(frame["board"], frame["last"]))
            lines.append("```")
            lines.append("")

    counts = Counter(
        "X" if g["winner"] == 1 else "O" if g["winner"] == 2 else "nulle"
        for g in payload["jeux"]
    )
    distinct_defenses = len({" ".join(str(r) for r in g["defense_rangs"]) for g in payload["jeux"]})
    lines.append("## Verdict")
    lines.append("")
    lines.append(
        f"Répartition : {counts.get('X', 0)} victoire(s) du premier joueur, "
        f"{counts.get('O', 0)} du second, {counts.get('nulle', 0)} nulle(s), "
        f"sur {len(payload['jeux'])} partie(s) dont {distinct_defenses} défense(s) distincte(s)."
    )
    lines.append("")
    if counts.get("X", 0) == len(payload["jeux"]) and len(payload["jeux"]) > 1:
        lines.append(
            "**Schéma robuste** : aucune des défenses essayées n'a tenu, et plusieurs "
            "d'entre elles sont distinctes. Le gain ne dépend pas d'une imprécision "
            "particulière de la défense."
        )
    elif counts.get("X", 0) == len(payload["jeux"]):
        lines.append(
            "Gain unique : une seule ligne a été jouée, il en faut d'autres pour parler de "
            "schéma (relancer avec `--games` plus grand)."
        )
    else:
        lines.append(
            "**Défense sauvée** : au moins une ligne échappe au gain. La ligne de référence "
            "n'était donc pas forcée — à revoir avant d'en faire une leçon."
        )
    lines.append("")
    lines.append("## Limites")
    lines.append("")
    lines.append(
        "- Le tirage porte sur les meilleurs coups du moteur, pas sur tous les coups légaux : "
        "une défense *exotique* qui tiendrait n'est pas testée. Le verdict porte donc sur les "
        "défenses fortes, ce qui est l'usage d'un cours."
    )
    lines.append(
        "- Les taux de victoire sont des estimations du moteur (sigmoïde calibrée) : ils "
        "servent à classer les coups, pas à mesurer une fréquence."
    )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Vérification d'un schéma gagnant")
    parser.add_argument("--opening", required=True, help="Ouverture, « 3,3 »")
    parser.add_argument("--games", type=int, default=6, help="Nombre de parties")
    parser.add_argument("--defense-top", type=int, default=3, help="Coups tirés par la défense")
    parser.add_argument("--depth", type=int, default=18)
    parser.add_argument("--time-ms", type=int, default=1500)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--out-json", default=None)
    parser.add_argument("--out-md", default=None)
    args = parser.parse_args()

    row, col = (int(v) for v in args.opening.split(","))
    client = EngineClient(default_depth=args.depth, default_time_ms=args.time_ms)
    if not client.is_available():
        raise SystemExit("Moteur indisponible")

    rng = random.Random(args.seed)
    games: List[Dict[str, Any]] = []
    started = time.perf_counter()
    for index in range(1, args.games + 1):
        game = play(client, (row, col), args.depth, args.time_ms, args.defense_top, rng)
        game["index"] = index
        games.append(game)
        verdict = (
            "X gagne" if game["winner"] == 1 else "O gagne" if game["winner"] == 2 else "nulle"
        )
        print(
            f"partie {index}/{args.games} : {verdict} en {game['plies']} demi-coups "
            f"(rangs défensifs {' '.join(str(r) for r in game['defense_rangs'])})",
            flush=True,
        )
    client.close()

    payload = {
        "genere_le": datetime.now().isoformat(timespec="seconds"),
        "opening": [row, col],
        "parties": args.games,
        "defense_top": args.defense_top,
        "profondeur": args.depth,
        "budget_ms": args.time_ms,
        "graine": args.seed,
        "duree_s": round(time.perf_counter() - started, 1),
        "jeux": games,
    }

    if args.out_md:
        Path(args.out_md).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out_md).write_text(render(payload), encoding="utf-8")
        print(f"Rapport : {args.out_md}")
    if args.out_json:
        Path(args.out_json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out_json).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"JSON : {args.out_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
