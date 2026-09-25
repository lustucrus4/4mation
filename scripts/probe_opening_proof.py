"""Sonde de preuve profonde depuis la position initiale.

Objectif : tenter de **prouver** la valeur d'une ouverture (ou de tous les premiers
coups) depuis le plateau vide, avec un très gros budget et une table de transposition
partagée. Le moteur descend profondément et, s'il tombe sur une position de la tablebase
ou sur un mat forcé, la valeur devient exacte (`gain` / `perte` / `nulle`).

Aucune preuve au premier coup n'est attendue : la partie compte 49 cases et la tablebase
s'arrête à 12 cases vides, il reste donc ~25 demi-coups à franchir avant que les finales
exactes n'aident l'arbre. La sonde sert à mesurer **jusqu'où la preuve remonte**, et à
enregistrer le meilleur coup trouvé à chaque ouverture pour alimenter la théorie.

    python scripts/probe_opening_proof.py --depth 30 --time-ms 600000 --tt-mb 2048

Le budget est indicatif : le moteur rend la main au premier des deux (profondeur ou temps).
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

from api.services.engine_analysis import result_for  # noqa: E402
from api.services.engine_client import EngineClient  # noqa: E402

# Les 10 orbites de premier coup sous la symétrie D4 (rotations + miroir).
OPENING_ORBITS: List[Tuple[int, int]] = [
    (0, 0),
    (0, 1),
    (0, 2),
    (0, 3),
    (1, 1),
    (1, 2),
    (1, 3),
    (2, 2),
    (2, 3),
    (3, 3),
]


def probe(
    client: EngineClient,
    move: Tuple[int, int],
    depth: int,
    time_ms: int,
) -> Dict[str, Any]:
    """Analyse profonde d'un premier coup depuis le plateau vide."""
    board = np.zeros((7, 7), dtype=np.int8)
    board[move] = 1
    analysis = client.analyze(board, 2, move, depth=depth, time_ms=time_ms, exact=True)
    if not analysis:
        return {"ouverture": list(move), "erreur": "moteur muet"}

    best = analysis.get("best_move")
    best_move = None
    if best is not None:
        best_move = [int(best[0]), int(best[1])] if isinstance(best, (list, tuple)) else int(best)

    proven = analysis.get("proven")
    verdict, win_rate, exact = result_for(float(analysis.get("score") or 0.0), proven)
    return {
        "ouverture": list(move),
        "reponse": best_move,
        "score": int(analysis.get("score") or 0),
        "verdict": verdict,
        "preuve": proven,
        "exact": bool(exact),
        "win_rate": round(float(win_rate), 4),
        "mate_in": analysis.get("mate_in"),
        "profondeur": int(analysis.get("depth") or 0),
        "noeuds": int(analysis.get("nodes") or 0),
        "tb_exact": int(analysis.get("tb_exact") or 0),
        "tb_skips": int(analysis.get("tb_skips") or 0),
        "tronque": bool(analysis.get("truncated")),
        "duree_ms": int(analysis.get("elapsed_ms") or 0),
        "coups_legaux": int(analysis.get("valid_moves_count") or 0),
        "coups_top": [
            {
                "coup": [int(m.get("row")), int(m.get("col"))],
                "score": int(m.get("score") or 0),
                "preuve": m.get("proven"),
            }
            for m in (analysis.get("moves") or [])[:3]
        ],
    }


def fmt_int(value: int) -> str:
    return f"{value:,}".replace(",", " ")


def render(rows: List[Dict[str, Any]], depth: int, time_ms: int) -> str:
    proven = [r for r in rows if r.get("preuve") in ("gain", "perte", "nulle")]
    lines = [
        "# Sonde de preuve profonde",
        "",
        f"Budget demandé : profondeur {depth}, {time_ms / 1000:.0f} s par coup.",
        f"Ouvertures prouvées : **{len(proven)}/{len(rows)}**.",
        "",
    ]
    if proven:
        lines += ["## Preuves obtenues", ""]
        for row in proven:
            ouv = row["ouverture"]
            lines.append(
                f"- `{ouv[0]},{ouv[1]}` -> {row['preuve']} "
                f"(score {row['score']}, mat dans {row['mate_in']}, profondeur {row['profondeur']})"
            )
        lines.append("")

    lines += [
        "## Détail",
        "",
        "| Ouverture | Meilleure réponse | Score | Verdict | Mat | Prof. | Nœuds | tb_exact | s |",
        "| --- | --- | ---: | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in sorted(rows, key=lambda r: -r.get("score", -10**9)):
        if row.get("erreur"):
            lines.append(f"| `{row['ouverture'][0]},{row['ouverture'][1]}` | — | — | erreur | — | — | — | — | — |")
            continue
        ouv = row["ouverture"]
        rep = row["reponse"]
        rep_txt = "—" if rep is None else f"`{rep[0]},{rep[1]}`"
        mat = "—" if row["mate_in"] is None else str(row["mate_in"])
        lines.append(
            f"| `{ouv[0]},{ouv[1]}` | {rep_txt} | {row['score']} | {row['preuve']} | {mat} "
            f"| {row['profondeur']} | {fmt_int(row['noeuds'])} | {fmt_int(row['tb_exact'])} "
            f"| {row['duree_ms'] / 1000:.1f} |"
        )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Sonde de preuve profonde des ouvertures")
    parser.add_argument("--depth", type=int, default=30, help="Profondeur maximale par coup")
    parser.add_argument("--time-ms", type=int, default=600_000, help="Temps maximal par coup (ms)")
    parser.add_argument("--timeout-s", type=float, default=1_800, help="Patience du client (s)")
    parser.add_argument("--tt-mb", type=int, default=2_048, help="Taille de la table de transposition")
    parser.add_argument(
        "--openings",
        default="",
        help="Liste de coups « r,c r,c » (défaut : les 10 orbites)",
    )
    parser.add_argument("--out-json", default="_tmp_proof_probe.json")
    parser.add_argument("--out-md", default="script/solver/PREUVE_PROFONDE.md")
    args = parser.parse_args()

    if args.openings.strip():
        openings = []
        for token in args.openings.replace(";", " ").split():
            row_txt, col_txt = token.split(",")
            openings.append((int(row_txt), int(col_txt)))
    else:
        openings = list(OPENING_ORBITS)

    rows: List[Dict[str, Any]] = []
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
        for move in openings:
            row = probe(client, move, args.depth, args.time_ms)
            rows.append(row)
            if row.get("erreur"):
                print(f"`{move[0]},{move[1]}` : {row['erreur']}")
                continue
            print(
                f"`{move[0]},{move[1]}` | meilleure réponse {row['reponse']} | score {row['score']} "
                f"| preuve {row['preuve']} | profondeur {row['profondeur']} "
                f"| {fmt_int(row['noeuds'])} noeuds | {row['duree_ms'] / 1000:.1f} s"
            )
    finally:
        client.close()

    Path(args.out_json).write_text(
        json.dumps(
            {
                "genere_le": datetime.now().isoformat(timespec="seconds"),
                "depth": args.depth,
                "time_ms": args.time_ms,
                "ouvertures": rows,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    report = render(rows, args.depth, args.time_ms)
    Path(args.out_md).write_text(report, encoding="utf-8")
    print(f"Rapport : {args.out_md}")
    print(f"JSON : {args.out_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
