"""Extraction d'une ligne de gain forcée et prouvée, à partir d'une ouverture.

La sonde de preuve (`probe_opening_proof.py`) a montré qu'après le premier coup central
`3,3`, le moteur prouve une **perte forcée** pour le second joueur (mat en 28 demi-coups).
Ce script descend la ligne en jouant, à chaque demi-coup, le meilleur coup du moteur :
l'attaquant choisit le mat le plus court, la défense la résistance la plus longue. On
obtient ainsi la ligne principale du gain, utilisable telle quelle dans les cours.

Comme la table de transposition est partagée entre les requêtes d'un même processus, la
preuve du premier demi-coup est coûteuse puis les positions suivantes sont déjà connues.

    python scripts/extract_forced_win.py --opening 3,3 --time-ms 120000 --depth 40

Le rapport indique, à chaque demi-coup, la distance de mat (qui doit diminuer de 2) et le
nombre de coups de défense qui « résistent » le plus longtemps : si tous les coups de
défense perdent, la preuve ne dépend d'aucune faute.
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
for path in (str(ROOT), str(ROOT / "script")):
    if path not in sys.path:
        sys.path.insert(0, path)

from api.services.engine_client import EngineClient  # noqa: E402

SYMBOLS = {0: ".", 1: "X", 2: "O"}


def has_four(board: np.ndarray, row: int, col: int, player: int) -> bool:
    """Alignement de 4 passant par (row, col), dans les 4 directions."""
    for dr, dc in ((0, 1), (1, 0), (1, 1), (1, -1)):
        count = 1
        for sign in (1, -1):
            step = 1
            while True:
                r, c = row + sign * dr * step, col + sign * dc * step
                if not (0 <= r < 7 and 0 <= c < 7) or board[r][c] != player:
                    break
                count += 1
                step += 1
        if count >= 4:
            return True
    return False


def board_lines(board: np.ndarray, last: Optional[Tuple[int, int]]) -> List[str]:
    head = "    " + " ".join(str(c) for c in range(7))
    lines = [head]
    for row in range(7):
        cells = []
        for col in range(7):
            symbol = SYMBOLS[int(board[row][col])]
            if last is not None and (row, col) == last:
                cells.append(f"({symbol})")
            else:
                cells.append(f" {symbol} ")
        lines.append(f"{row}  " + "".join(cells))
    return lines


def fmt_int(value: int) -> str:
    return f"{value:,}".replace(",", " ")


def step(client: EngineClient, board: np.ndarray, player: int, last: Optional[Tuple[int, int]],
         depth: int, time_ms: int) -> Dict[str, Any]:
    """Analyse complète d'une position : meilleur coup, preuve et solidité de la défense."""
    analysis = client.analyze(board, player, last, depth=depth, time_ms=time_ms, exact=True)
    if not analysis:
        raise RuntimeError("moteur muet")
    best = analysis.get("best_move")
    best_move = None if best is None else (int(best[0]), int(best[1]))
    moves = [
        {
            "move": (int(m.get("row")), int(m.get("col"))),
            "score": int(m.get("score") or 0),
            "proven": m.get("proven"),
        }
        for m in (analysis.get("moves") or [])
    ]
    return {
        "player": player,
        "move": best_move,
        "score": int(analysis.get("score") or 0),
        "proven": analysis.get("proven"),
        "mate_in": analysis.get("mate_in"),
        "depth": int(analysis.get("depth") or 0),
        "nodes": int(analysis.get("nodes") or 0),
        "elapsed_ms": int(analysis.get("elapsed_ms") or 0),
        "truncated": bool(analysis.get("truncated")),
        "legal": len(moves),
        "tb_exact": bool(analysis.get("tb_exact")),
        "moves": moves,
    }


def resistance(moves: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Combien de coups perdent le moins vite (coups « qui résistent »)."""
    if not moves:
        return {"best": 0, "same": 0, "worst_score": 0, "all_lose": False}
    best = max(m["score"] for m in moves)
    same = sum(1 for m in moves if m["score"] == best)
    return {
        "best": best,
        "same": same,
        "worst_score": min(m["score"] for m in moves),
        "all_lose": all(m["proven"] == "perte" for m in moves),
    }


def extract(client: EngineClient, opening: Tuple[int, int], depth: int, time_ms: int,
            max_plies: int) -> Dict[str, Any]:
    board = np.zeros((7, 7), dtype=np.int8)
    board[opening] = 1
    last: Optional[Tuple[int, int]] = opening
    player = 2
    plies: List[Dict[str, Any]] = [
        {
            "ply": 1,
            "player": 1,
            "move": list(opening),
            "score": None,
            "proven": "ouverture",
            "mate_in": None,
            "depth": 0,
            "nodes": 0,
            "elapsed_ms": 0,
            "truncated": False,
            "legal": 1,
            "tb_exact": False,
            "resistance": None,
            "board": board.copy(),
        }
    ]

    winner: Optional[int] = None
    while len(plies) <= max_plies:
        info = step(client, board, player, last, depth, time_ms)
        moves = info.pop("moves")
        res = resistance(moves)
        move = info["move"]
        if move is None:
            break
        board[move[0], move[1]] = player
        last = move
        info["ply"] = len(plies) + 1
        info["move"] = list(move)
        info["resistance"] = res
        info["board"] = board.copy()
        plies.append(info)
        tag = "X" if player == 1 else "O"
        print(
            f"  {info['ply']:>2} {tag} {move} | score {info['score']:>7} | {info['proven']} "
            f"| mat {info.get('mate_in')} | legal {info['legal']} | resistent {res.get('same')} "
            f"| {info['elapsed_ms'] / 1000:.1f} s",
            flush=True,
        )
        if has_four(board, move[0], move[1], player):
            winner = player
            break
        player = 3 - player

    return {
        "opening": list(opening),
        "winner": winner,
        "plies": plies,
        "depth": depth,
        "time_ms": time_ms,
    }


def render(payload: Dict[str, Any]) -> str:
    opening = payload["opening"]
    plies = payload["plies"]
    winner = payload["winner"]
    head = plies[0]
    root = plies[1] if len(plies) > 1 else None
    lines = [
        "# Gain forcé après le premier coup central",
        "",
        f"Premier coup : **X en {opening[0]},{opening[1]}** (centre).",
        (
            "Verdict du moteur : **perte forcée du second joueur** "
            f"({root['proven']}, mat en {root['mate_in']} demi-coups), prouvé en "
            f"{root['elapsed_ms'] / 1000:.1f} s à la profondeur {root['depth']}."
            if root
            else "Verdict indisponible."
        ),
        "",
        "## La ligne principale",
        "",
    ]

    line_parts = []
    for entry in plies:
        move = entry["move"]
        tag = "X" if entry["player"] == 1 else "O"
        line_parts.append(f"{tag}{move[0]},{move[1]}")
    lines += ["```", " ".join(line_parts), "```", ""]

    lines += [
        "`Xn,m` = coup du premier joueur, `On,m` = coup du second, format `ligne,colonne`.",
        "",
        "## Déroulé, demi-coup par demi-coup",
        "",
        "| # | Camp | Coup | Score | Verdict | Mat | Prof. | Coups légaux | Résistent | s |",
        "| ---: | --- | --- | ---: | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for entry in plies[1:]:
        move = entry["move"]
        tag = "X" if entry["player"] == 1 else "O"
        res = entry.get("resistance") or {}
        resistant = (
            f"{res.get('same', '?')}/{entry['legal']}" if res else "—"
        )
        mate = "—" if entry.get("mate_in") is None else str(entry["mate_in"])
        lines.append(
            f"| {entry['ply']} | {tag} | {move[0]},{move[1]} | {entry['score']} "
            f"| {entry['proven']} | {mate} | {entry['depth']} | {entry['legal']} "
            f"| {resistant} | {entry['elapsed_ms'] / 1000:.1f} |"
        )

    total_nodes = sum(int(entry.get("nodes") or 0) for entry in plies[1:])
    lines += [
        "",
        f"Total : {fmt_int(total_nodes)} nœuds sur {len(plies) - 1} demi-coups analysés.",
        "",
        "## Lecture",
        "",
        "La colonne « Résistent » donne le nombre de coups de défense qui retardent le mat "
        "autant que le meilleur coup (sur le nombre de coups légaux). Plus ce nombre est "
        "petit, plus la défense est contrainte ; le verdict final ne dépend d'aucune faute "
        "de l'adversaire puisque **tous** ses coups perdent.",
        "",
        "## Positions clés",
        "",
    ]
    step_index = max(1, len(plies) // 3)
    for entry in plies[::step_index]:
        move = entry["move"]
        tag = "X" if entry["player"] == 1 else "O"
        lines.append(f"Après {tag} {move[0]},{move[1]} (demi-coup {entry['ply']}) :")
        lines.append("")
        lines += board_lines(entry["board"], (move[0], move[1]))
        lines.append("")
    if winner:
        lines.append(f"Alignement final pour le joueur {winner}. Le premier joueur gagne.")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Ligne de gain forcée prouvée")
    parser.add_argument("--opening", default="3,3", help="Premier coup, format « ligne,colonne »")
    parser.add_argument("--depth", type=int, default=40)
    parser.add_argument("--time-ms", type=int, default=120_000)
    parser.add_argument("--timeout-s", type=float, default=3_600)
    parser.add_argument("--tt-mb", type=int, default=2_048)
    parser.add_argument("--max-plies", type=int, default=40)
    parser.add_argument("--out-json", default="script/solver/forced_win_33.json")
    parser.add_argument("--out-md", default="script/solver/GAIN_FORCE_33.md")
    args = parser.parse_args()

    row_txt, col_txt = args.opening.split(",")
    opening = (int(row_txt), int(col_txt))

    client = EngineClient(
        default_depth=args.depth,
        default_time_ms=args.time_ms,
        timeout_s=args.timeout_s,
        tt_mb=args.tt_mb,
    )
    try:
        if not client.is_available():
            print("moteur indisponible : rien à faire")
            return 1
        payload = extract(client, opening, args.depth, args.time_ms, args.max_plies)
    finally:
        client.close()

    print(f"Ouverture {opening} | vainqueur {payload['winner']} | {len(payload['plies'])} demi-coups")
    for entry in payload["plies"][1:]:
        tag = "X" if entry["player"] == 1 else "O"
        res = entry.get("resistance") or {}
        print(
            f"  {entry['ply']:>2} {tag} {entry['move']} | score {entry['score']:>7} "
            f"| {entry['proven']:<10} | mat {entry.get('mate_in')} | legal {entry['legal']:>2} "
            f"| resistent {res.get('same')} | {entry['elapsed_ms'] / 1000:.1f} s"
        )

    serial = json.loads(
        json.dumps(
            {
                **payload,
                "plies": [
                    {**entry, "board": entry["board"].tolist()} for entry in payload["plies"]
                ],
            }
        )
    )
    serial["genere_le"] = datetime.now().isoformat(timespec="seconds")
    Path(args.out_json).write_text(json.dumps(serial, indent=2), encoding="utf-8")
    Path(args.out_md).write_text(render(payload), encoding="utf-8")
    print(f"Rapport : {args.out_md}")
    print(f"JSON : {args.out_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
