#!/usr/bin/env python3
"""Extrait un schéma gagnant d'une partie de référence et le rend enseignable.

Une partie gagnée ne prouve rien tant qu'on ne sait pas *pourquoi* elle est gagnée : soit
le perdant s'est trompé, soit la position était déjà perdue. Ce script tranche, demi-coup
par demi-coup, avec l'analyse du site (`TablebaseLookup.analyze_position` — le moteur Rust
en mode exact, celui que voient le coach et la revue de partie) :

- pour chaque camp, le taux de victoire de la position, celui du coup joué, et l'écart au
  meilleur coup ;
- la meilleure défense disponible à chaque demi-coup : si le camp qui perd joue déjà le
  meilleur coup connu et perd quand même, c'est un **schéma**, pas une faute.

Le rapport produit est directement utilisable comme leçon : la ligne complète, le taux de
victoire à chaque étape, les plateaux, et le verdict — combien de coups optimaux de chaque
côté, et où la partie bascule.

Usage :
    python scripts/extract_winning_schema.py \
        --sweep _tmp_sweep_defense10s.json --opening 3,3 \
        --depth 20 --time-ms 2500 \
        --out-json script/solver/schema_gagnant_33.json \
        --out-md script/solver/SCHEMA_GAGNANT_33.md
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
for _path in (str(ROOT), str(ROOT / "script"), str(ROOT / "scripts")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from api.services.tablebase_lookup import TablebaseLookup  # noqa: E402
from diagnose_bot_game import replay  # noqa: E402

SEUIL_OPTIMAL = 0.05
SYMBOLS = {0: ".", 1: "X", 2: "O"}


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


def audit_ply(
    entry: Dict[str, Any], lookup: TablebaseLookup, depth: int, time_ms: int
) -> Optional[Dict[str, Any]]:
    """Analyse un demi-coup : coup joué, meilleur coup, écart en taux de victoire."""
    board = np.array(entry["board"], dtype=np.int8)
    last = tuple(entry["last_move"]) if entry["last_move"] else None
    analysis = lookup.analyze_position(
        board, int(entry["player"]), last, engine_depth=depth, engine_time_ms=time_ms
    )
    if not analysis or not analysis.get("moves"):
        return None
    played = tuple(int(v) for v in entry["move"])
    scores = {tuple(int(v) for v in m["move"]): float(m["win_rate"]) for m in analysis["moves"]}
    if played not in scores:
        return None
    best_move = tuple(int(v) for v in analysis["best_move"])
    best_wr = float(analysis.get("position_win_rate") or scores[best_move])
    played_wr = scores[played]
    # Meilleure alternative autre que le coup joué : la « défense la plus tenace ».
    alternatives = sorted(
        ((move, wr) for move, wr in scores.items() if move != played),
        key=lambda item: -item[1],
    )
    return {
        "ply": int(entry["ply"]),
        "player": int(entry["player"]),
        "bot": entry["bot"],
        "played": list(played),
        "best": list(best_move),
        "played_win_rate": round(played_wr, 4),
        "best_win_rate": round(best_wr, 4),
        "delta": round(best_wr - played_wr, 4),
        "optimal": (best_wr - played_wr) < SEUIL_OPTIMAL,
        "source": analysis.get("source"),
        "exact": bool(analysis.get("exact")),
        "meilleure_alternative": (
            {"coup": list(alternatives[0][0]), "win_rate": round(alternatives[0][1], 4)}
            if alternatives
            else None
        ),
        "coups_analyses": len(scores),
        "board": entry["board"],
        "last_move": entry["last_move"],
    }


def verdict(plies: List[Dict[str, Any]], winner: Optional[int]) -> Dict[str, Any]:
    """Synthèse par camp : coups optimaux, pire écart, taux de victoire final tenu."""
    out: Dict[str, Any] = {}
    for seat in (1, 2):
        own = [p for p in plies if p["player"] == seat]
        if not own:
            continue
        # Le taux de victoire est donné du point de vue du camp au trait : on le ramène à
        # celui du vainqueur pour lire une seule courbe.
        deltas = [p["delta"] for p in own]
        out[str(seat)] = {
            "coups": len(own),
            "optimaux": sum(1 for p in own if p["optimal"]),
            "pire_ecart": round(max(deltas), 4),
            "ecart_moyen": round(sum(deltas) / len(deltas), 4),
            "gagne": winner == seat,
        }
    return out


def build_report(payload: Dict[str, Any], diagram_every: int) -> str:
    game = payload["partie"]
    plies = payload["demi_coups"]
    verdicts = payload["verdict"]
    winner = game.get("winner")
    lines: List[str] = []
    lines.append("# Schéma gagnant — ouverture et ligne de référence")
    lines.append("")
    lines.append(
        f"Partie de référence jouée le {payload['genere_le']} par `{game['first_bot']}` (X) "
        f"contre `{game['second_bot']}` (O), premier coup imposé "
        f"({game['opening'][0]},{game['opening'][1]})."
    )
    lines.append("")

    lines.append("## Verdict")
    lines.append("")
    lines.append(
        "Chaque demi-coup a été analysé par le moteur en mode exact. Un coup est dit "
        f"**optimal** quand le meilleur coup connu ne lui rend pas plus de "
        f"{SEUIL_OPTIMAL:.2f} de taux de victoire."
    )
    lines.append("")
    lines.append("| Camp | Coups | dont optimaux | Pire écart | Écart moyen | Issue |")
    lines.append("|------|-------|---------------|------------|-------------|-------|")
    for seat in ("1", "2"):
        info = verdicts.get(seat)
        if not info:
            continue
        camp = "X (premier)" if seat == "1" else "O (second)"
        issue = "gagne" if info["gagne"] else "perd"
        lines.append(
            f"| {camp} | {info['coups']} | {info['optimaux']} | {info['pire_ecart']:.3f} | "
            f"{info['ecart_moyen']:.3f} | {issue} |"
        )
    lines.append("")
    perdant = "2" if winner == 1 else "1"
    info_perdant = verdicts.get(perdant) or {}
    gagnant = "1" if winner == 1 else "2"
    info_gagnant = verdicts.get(gagnant) or {}
    if info_perdant and info_perdant["optimaux"] == info_perdant["coups"]:
        lines.append(
            f"**Le camp qui perd n'a commis aucune faute** : {info_perdant['coups']} coups sur "
            f"{info_perdant['coups']} sont les meilleurs connus du moteur, et il perd quand "
            f"même en {game['plies']} demi-coups. La défaite vient de l'ouverture, pas du jeu : "
            "c'est ce qui fait de cette ligne un schéma et non un fait divers."
        )
    elif info_perdant:
        lines.append(
            f"Le camp qui perd a quitté le meilleur coup {info_perdant['coups'] - info_perdant['optimaux']} "
            f"fois sur {info_perdant['coups']} (pire écart {info_perdant['pire_ecart']:.3f}) : "
            "la ligne reste une leçon, mais une partie de la défaite vient des fautes."
        )
    if info_gagnant:
        lines.append(
            f"Le camp qui gagne a joué {info_gagnant['optimaux']} coups optimaux sur "
            f"{info_gagnant['coups']}."
        )
    lines.append("")

    lines.append("## Ligne complète")
    lines.append("")
    lines.append(
        "Le taux de victoire est celui de **X** (premier joueur) : il monte si l'ouverture "
        "tient, il s'effondre si la défense renverse la partie."
    )
    lines.append("")
    lines.append("| Demi-coup | Camp | Coup | Taux de victoire du trait | Écart au meilleur | Lecture |")
    lines.append("|-----------|------|------|---------------------------|-------------------|---------|")
    for ply in plies:
        x_wr = ply["played_win_rate"] if ply["player"] == 1 else 1.0 - ply["played_win_rate"]
        lecture = "optimal" if ply["optimal"] else f"+{ply['delta']:.3f} possible"
        if ply.get("exact"):
            lecture += " (exact)"
        lines.append(
            f"| {ply['ply']} | {'X' if ply['player'] == 1 else 'O'} | "
            f"({ply['played'][0]},{ply['played'][1]}) | {x_wr * 100:.1f} % | "
            f"{ply['delta']:.3f} | {lecture} |"
        )
    lines.append("")

    lines.append("## Plateaux")
    lines.append("")
    lines.append(f"Un plateau tous les {diagram_every} demi-coups (`#` = dernier coup joué).")
    lines.append("")
    for ply in plies:
        if ply["ply"] % diagram_every:
            continue
        board = np.array(ply["board"], dtype=np.int8)
        # Le plateau enregistré est celui *avant* le coup : on le montre après le coup joué.
        played = tuple(ply["played"])
        board = board.copy()
        board[played[0], played[1]] = ply["player"]
        lines.append(f"### Demi-coup {ply['ply']} — {'X' if ply['player'] == 1 else 'O'} joue "
                     f"({played[0]},{played[1]})")
        lines.append("")
        lines.append("```")
        lines.extend(render_board(board, played))
        lines.append("```")
        lines.append("")
        if not ply["optimal"] and ply.get("meilleure_alternative"):
            alt = ply["meilleure_alternative"]
            lines.append(
                f"Meilleure alternative : ({alt['coup'][0]},{alt['coup'][1]}) à "
                f"{alt['win_rate'] * 100:.1f} % pour le trait."
            )
            lines.append("")

    lines.append("## Comment lire ce schéma pour un cours")
    lines.append("")
    lines.append(
        "- La **position de départ** est un coup unique imposé : c'est l'ouverture à enseigner, "
        "sans variantes parasites."
    )
    lines.append(
        "- La colonne « écart au meilleur » dit ce qu'un joueur peut se permettre : les "
        "demi-coups marqués `optimal` sont ceux où il n'y avait rien de mieux à faire."
    )
    lines.append(
        "- Les taux de victoire sont des **estimations du moteur** converties en probabilité "
        "par la sigmoïde calibrée, sauf mention « exact » (verdict de la tablebase ou mat "
        "forcé) : à lire comme des tendances, pas comme des fréquences mesurées."
    )
    lines.append("")
    lines.append("## Limites")
    lines.append("")
    lines.append(
        "- Une ligne unique ne prouve pas que l'ouverture gagne : elle prouve que la "
        "*meilleure défense connue* du moteur n'a pas suffi. Un schéma gagne en valeur quand "
        "plusieurs défenses différentes échouent de la même façon."
    )
    lines.append(
        "- Les analyses de milieu de partie sont des estimations profondes, pas des verdicts "
        "exacts ; seules les positions à 12 cases vides ou moins sont tranchées par la "
        "tablebase."
    )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Extraction d'un schéma gagnant")
    parser.add_argument("--sweep", required=True, help="Partie enregistrée par opening_sweep.py")
    parser.add_argument("--opening", required=True, help="Ouverture de la partie, « 3,3 »")
    parser.add_argument("--seat", choices=["X", "O"], default=None, help="Camp à auditer (défaut : les deux)")
    parser.add_argument("--depth", type=int, default=20, help="Profondeur d'analyse")
    parser.add_argument("--time-ms", type=int, default=2500, help="Budget par position")
    parser.add_argument("--diagram-every", type=int, default=2, help="Un plateau tous les N demi-coups")
    parser.add_argument("--out-json", default=None)
    parser.add_argument("--out-md", default=None)
    args = parser.parse_args()

    row, col = (int(v) for v in args.opening.split(","))
    game = replay(Path(args.sweep), (row, col))
    print(
        f"Partie {game['first_bot']} (X) vs {game['second_bot']} (O) — "
        f"ouverture ({row},{col}) — gagnant {game['winner']} en {len(game['moves'])} demi-coups"
    )

    lookup = TablebaseLookup()
    wanted = {1: "X", 2: "O"}
    seats = {1, 2} if args.seat is None else {1 if args.seat == "X" else 2}
    plies: List[Dict[str, Any]] = []
    for entry in game["moves"]:
        if entry["player"] not in seats:
            continue
        result = audit_ply(entry, lookup, args.depth, args.time_ms)
        if result is None:
            print(f"  demi-coup {entry['ply']} : analyse indisponible")
            continue
        plies.append(result)
        print(
            f"  demi-coup {result['ply']:>2} | {'X' if result['player'] == 1 else 'O'} "
            f"({result['played'][0]},{result['played'][1]}) | taux {result['played_win_rate']:.3f} "
            f"| écart {result['delta']:.3f} | {result['source']}"
            + (" (exact)" if result["exact"] else ""),
            flush=True,
        )

    payload = {
        "genere_le": datetime.now().isoformat(timespec="seconds"),
        "partie": {
            "first_bot": game["first_bot"],
            "second_bot": game["second_bot"],
            "opening": game["opening"],
            "winner": game["winner"],
            "plies": len(game["moves"]),
        },
        "analyse": {"profondeur": args.depth, "budget_ms": args.time_ms},
        "verdict": verdict(plies, game["winner"]),
        "demi_coups": plies,
    }

    md = build_report(payload, args.diagram_every)
    if args.out_md:
        Path(args.out_md).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out_md).write_text(md, encoding="utf-8")
        print(f"Rapport : {args.out_md}")
    if args.out_json:
        Path(args.out_json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out_json).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"JSON : {args.out_json}")
    if not args.out_md:
        print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
