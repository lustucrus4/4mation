#!/usr/bin/env python3
"""Théorie d'ouverture : ce que le livre dit des premiers coups, prêt pour les cours.

Le livre d'ouverture contient une évaluation par position, écrite par le moteur (voir
`build_opening_book_engine.py`). Ce script en tire la lecture humaine :

- l'évaluation de la position de départ et le coup recommandé ;
- les **10 ouvertures uniques** (le plateau est symétrique par rotation et miroir) avec
  le score du premier joueur et l'écart au meilleur coup ;
- la **ligne principale** (meilleur jeu des deux camps) avec le score à chaque demi-coup ;
- les **seuils** qui séparent « favorable » de « jouable » et de « perdant », adossés à
  la table de fiabilité du calibrage.

Attention aux mots : la valeur chiffrée est un **score espéré** (victoire = 1, nulle =
0,5, défaite = 0), c'est la grandeur sur laquelle la sigmoïde a été calibrée — pas une
probabilité de victoire. Dans un jeu où la nulle est fréquente, 58 % de score espéré ne
veut pas dire 58 % de victoires. Le vocabulaire est explicite dans tout le rapport.

Deux natures de valeurs, jamais mélangées dans le rapport :

- **prouvé** (`exact=1`) : mat forcé ou verdict lu dans la tablebase ;
- **estimé** : évaluation heuristique du moteur, convertie en score espéré par une sigmoïde
  calibrée. C'est une estimation assumée, pas une mesure.

Usage :
    python script/solver/extract_opening_theory.py --max-ply 6
    python script/solver/extract_opening_theory.py --max-ply 8 --out-md script/solver/THEORIE_OUVERTURE.md
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

ROOT = Path(__file__).resolve().parent.parent.parent
for _p in (str(ROOT), str(ROOT / "script")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from game_tree.optimized_minimax import OptimizedMinimaxAdvisor  # noqa: E402
from solver.position_hasher import HASHER  # noqa: E402
from solver.symmetry import ALL_SYMMETRIES, apply_symmetry, transform_cell  # noqa: E402

DEFAULT_DB = ROOT / "script" / "solver" / "data" / "tablebase.db"
DEFAULT_JSON = ROOT / "script" / "solver" / "opening_theory.json"
DEFAULT_MD = ROOT / "script" / "solver" / "THEORIE_OUVERTURE.md"
SCALE_FILE = ROOT / "script" / "solver" / "data" / "engine_scale.json"

# Seuils lus dans la table de fiabilité du calibrage : au-delà de ±40 points
# d'évaluation, la prédiction s'écarte franchement de 50 % (0,54 / 0,46).
BAND_SCORE = 40.0
BAND_PROVEN = {"win": "gagnant (prouvé)", "draw": "nulle (prouvée)", "loss": "perdant (prouvé)"}


@dataclass
class Entry:
    hash: str
    result: str
    win_rate: float
    best_move: Optional[Tuple[int, int]]
    ply: int
    exact: bool
    board: Optional[np.ndarray] = None
    player: int = 1
    last_move: Optional[Tuple[int, int]] = None


@dataclass
class Step:
    ply: int
    player: int
    move: Optional[Tuple[int, int]]
    entry: Optional[Entry]
    board: np.ndarray
    note: str = ""


@dataclass
class Report:
    root: Optional[Entry] = None
    first_moves: List[dict] = field(default_factory=list)
    main_line: List[dict] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    coverage: dict = field(default_factory=dict)
    scale: float = 0.0


def load_book(db_path: Path, max_ply: int) -> Dict[str, Entry]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT hash, result, win_rate, best_move_row, best_move_col, ply, exact,
               board_json, current_player, pos_last_move_row, pos_last_move_col
        FROM opening_book
        WHERE ply <= ?
        """,
        (max_ply,),
    ).fetchall()
    conn.close()

    book: Dict[str, Entry] = {}
    for r in rows:
        board = None
        if r["board_json"]:
            try:
                board = np.array(json.loads(r["board_json"]), dtype=np.int8)
            except Exception:
                board = None
        lmr, lmc = r["pos_last_move_row"], r["pos_last_move_col"]
        last = None if lmr is None or lmr < 0 else (int(lmr), int(lmc))
        br, bc = r["best_move_row"], r["best_move_col"]
        best = None if br is None or br < 0 else (int(br), int(bc))
        book[r["hash"]] = Entry(
            hash=r["hash"],
            result=r["result"],
            win_rate=float(r["win_rate"]),
            best_move=best,
            ply=int(r["ply"]),
            exact=bool(r["exact"]),
            board=board,
            player=int(r["current_player"] or 1),
            last_move=last,
        )
    return book


def load_scale() -> Tuple[float, List[dict]]:
    if not SCALE_FILE.exists():
        return 0.0, []
    try:
        data = json.loads(SCALE_FILE.read_text(encoding="utf-8"))
        return float(data.get("scale") or 0.0), list(data.get("reliability") or [])
    except Exception:
        return 0.0, []


def child_hash(board: np.ndarray, player: int, move: Tuple[int, int]) -> str:
    nb = board.copy()
    nb[move[0], move[1]] = player
    return HASHER.hash_key(nb, 3 - player, move)


def expected_score_p1(entry: Entry) -> float:
    """Score espéré ramené au premier joueur, quel que soit le camp au trait.

    ``Entry.win_rate`` est le nom de la colonne du livre ; la grandeur qu'elle porte est
    un score espéré (victoire = 1, nulle = 0,5, défaite = 0), cible du calibrage.
    """
    return entry.win_rate if entry.player == 1 else 1.0 - entry.win_rate


def band(entry: Entry, scale: float) -> str:
    if entry.exact:
        return BAND_PROVEN.get(entry.result, "prouvé")
    if entry.result == "win" and entry.win_rate >= 0.54:
        return "favorable"
    if entry.result == "loss" and entry.win_rate <= 0.46:
        return "défavorable"
    return "équilibré"


def first_move_orbits() -> List[Tuple[str, List[Tuple[int, int]]]]:
    """Les 10 orbites de premier coup (symétries D₄), représentant = la plus petite case."""
    groups: Dict[str, List[Tuple[int, int]]] = {}
    for r in range(7):
        for c in range(7):
            board = np.zeros((7, 7), dtype=np.int8)
            board[r, c] = 1
            h = HASHER.hash_key(board, 2, (r, c))
            groups.setdefault(h, []).append((r, c))
    out = []
    for h, cells in groups.items():
        out.append((h, sorted(cells)))
    out.sort(key=lambda item: (item[1][0], len(item[1])))
    return out


def legal_moves(advisor: OptimizedMinimaxAdvisor, board, player, last):
    return set(advisor._get_frontier_moves(board, last, player))


def reorient(
    entry: Entry,
    board: np.ndarray,
    last: Optional[Tuple[int, int]],
) -> Optional[Tuple[Tuple[int, int], int]]:
    """Exprime le meilleur coup de ``entry`` dans l'orientation de ``board``.

    Le livre enregistre chaque position dans la première orientation rencontrée par son
    parcours ; le coup enregistré est légal *sur ce plateau-là*. Pour suivre une ligne,
    il faut donc retrouver, parmi les 8 images symétriques du plateau stocké, celle qui
    correspond à la position courante, puis transporter le coup par la même symétrie.

    Renvoie ``(coup, rang de la symétrie)`` ou ``None`` si rien ne correspond.
    """
    if entry.board is None or entry.best_move is None:
        return None
    for rank, sym in enumerate(ALL_SYMMETRIES):
        image, image_last = apply_symmetry(entry.board, entry.last_move, sym)
        if image_last == last and np.array_equal(image, board):
            mv = transform_cell(entry.best_move[0], entry.best_move[1], sym)
            return mv, rank
    return None


def build_main_line(
    book: Dict[str, Entry],
    root: Entry,
    advisor: OptimizedMinimaxAdvisor,
    max_ply: int,
    report: Report,
) -> List[Step]:
    steps: List[Step] = []
    board = root.board
    player = root.player
    last = root.last_move
    entry = root
    rotated = 0

    for ply in range(max_ply + 1):
        if entry is None or board is None:
            break
        move = None
        note = ""
        oriented = reorient(entry, board, last)
        if oriented is None:
            note = "meilleur coup introuvable dans cette orientation"
            report.warnings.append(f"ply {ply} : {note}")
        else:
            move, rank = oriented
            if rank != 0:
                rotated += 1
            legal = legal_moves(advisor, board, player, last)
            if move not in legal:
                note = f"coup {move} illégal sur ce plateau ({len(legal)} coups légaux)"
                report.warnings.append(f"ply {ply} : {note}")
                move = None

        steps.append(Step(ply=ply, player=player, move=move, entry=entry, board=board, note=note))
        if move is None:
            break
        nb = board.copy()
        nb[move[0], move[1]] = player
        if advisor._check_winner(nb) is not None:
            steps.append(
                Step(
                    ply=ply + 1,
                    player=3 - player,
                    move=None,
                    entry=None,
                    board=nb,
                    note="partie terminée (alignement)",
                )
            )
            break
        last = move
        player = 3 - player
        board = nb
        entry = book.get(HASHER.hash_key(board, player, last))

    if rotated:
        report.warnings.append(
            f"ligne principale : {rotated} demi-coup(s) lu(s) après transport par symétrie"
        )
    return steps


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", type=Path, default=DEFAULT_DB)
    ap.add_argument("--max-ply", type=int, default=6)
    ap.add_argument("--out-json", type=Path, default=DEFAULT_JSON)
    ap.add_argument("--out-md", type=Path, default=DEFAULT_MD)
    ap.add_argument("--top-lines", type=int, default=3, help="Lignes alternatives à détailler")
    args = ap.parse_args()

    if not args.db.exists():
        raise SystemExit(f"Base introuvable : {args.db}")

    book = load_book(args.db, args.max_ply)
    scale, reliability = load_scale()
    report = Report(scale=scale)

    if not book:
        raise SystemExit("Livre d'ouverture vide : lancer build_opening_book_engine.py")

    by_ply: Dict[int, int] = {}
    exact_by_ply: Dict[int, int] = {}
    for e in book.values():
        by_ply[e.ply] = by_ply.get(e.ply, 0) + 1
        if e.exact:
            exact_by_ply[e.ply] = exact_by_ply.get(e.ply, 0) + 1
    report.coverage = {
        "ply": {str(k): {"entrees": by_ply[k], "exactes": exact_by_ply.get(k, 0)}
                for k in sorted(by_ply)}
    }

    root_hash = HASHER.hash_key(np.zeros((7, 7), dtype=np.int8), 1, None)
    root = book.get(root_hash)
    if root is None or root.board is None:
        raise SystemExit(
            f"Position de départ absente ou sans plateau dans le livre ({root_hash})."
        )
    report.root = root

    advisor = OptimizedMinimaxAdvisor(depth=1, use_iterative_deepening=False)

    # Ouvertures uniques : une entrée de livre par orbite (même hash canonique).
    best_score = None
    for h, cells in first_move_orbits():
        entry = book.get(h)
        if entry is None or entry.board is None:
            report.warnings.append(f"orbite {cells[0]} absente du livre")
            continue
        wr = expected_score_p1(entry)
        best_score = wr if best_score is None else max(best_score, wr)

        # Meilleure réponse, exprimée dans l'orientation où le premier coup est joué
        # sur la case représentative de l'orbite (celle qu'un cours montrerait).
        rep = cells[0]
        after = np.zeros((7, 7), dtype=np.int8)
        after[rep[0], rep[1]] = 1
        reply_entry = book.get(HASHER.hash_key(after, 2, rep))
        reply = None
        if reply_entry is not None:
            oriented = reorient(reply_entry, after, rep)
            if oriented is not None:
                reply = list(oriented[0])

        report.first_moves.append(
            {
                "hash": h,
                "cells": [list(c) for c in cells],
                "representative": list(rep),
                "taille_orbite": len(cells),
                "score_espere_p1": round(wr, 4),
                "resultat_camp_au_trait": entry.result,
                "exact": entry.exact,
                "lecture": band(entry, scale),
                "meilleure_reponse": reply,
            }
        )

    for item in report.first_moves:
        item["ecart_au_meilleur"] = (
            round(best_score - item["score_espere_p1"], 4) if best_score is not None else None
        )
    report.first_moves.sort(key=lambda i: -i["score_espere_p1"])

    steps = build_main_line(book, root, advisor, args.max_ply, report)
    for s in steps:
        row = {
            "ply": s.ply,
            "joueur": s.player,
            "coup": list(s.move) if s.move else None,
            "note": s.note,
        }
        if s.entry is not None:
            row.update(
                {
                    "score_espere_p1": round(expected_score_p1(s.entry), 4),
                    "resultat_camp_au_trait": s.entry.result,
                    "exact": s.entry.exact,
                    "lecture": band(s.entry, scale),
                    "hash": s.entry.hash,
                }
            )
        report.main_line.append(row)

    # Lignes alternatives : les autres orbites de premier coup, jouées aussi loin
    # que le livre le permet (meilleur jeu des deux camps ensuite).
    alternatives = []
    best_first = list(steps[0].move) if steps and steps[0].move else None
    for item in report.first_moves:
        if len(alternatives) >= args.top_lines:
            break
        if best_first is not None and item["representative"] == best_first:
            continue
        entry = book.get(item["hash"])
        if entry is None or entry.board is None:
            continue
        sub_warnings: List[str] = []
        sub_report = Report(scale=scale, warnings=sub_warnings)
        sub_steps = build_main_line(book, entry, advisor, args.max_ply, sub_report)
        report.warnings.extend(f"alt {item['representative']} : {w}" for w in sub_warnings)
        if len(sub_steps) < 2:
            continue
        alternatives.append(
            {
                "premier_coup": item["representative"],
                "score_espere_p1": item["score_espere_p1"],
                "ligne": [
                    {
                        "ply": s.ply,
                        "coup": list(s.move) if s.move else None,
                        "score_espere_p1": round(expected_score_p1(s.entry), 4) if s.entry else None,
                        "exact": s.entry.exact if s.entry else None,
                    }
                    for s in sub_steps
                ],
            }
        )

    payload = {
        "genere_le": datetime.now().isoformat(timespec="seconds"),
        "base": str(args.db),
        "max_ply": args.max_ply,
        "echelle_score": scale,
        "bandes": {
            "seuil_score": BAND_SCORE,
            "favorable": "score >= +40 (taux >= 0,54)",
            "equilibre": "-40 < score < +40 (0,46 - 0,54)",
            "defavorable": "score <= -40 (taux <= 0,46)",
        },
        "fiabilite": reliability,
        "couverture": report.coverage,
        "racine": {
            "hash": root.hash,
            "score_espere_p1": round(expected_score_p1(root), 4),
            "exact": root.exact,
            "lecture": band(root, scale),
            "meilleur_coup": list(root.best_move) if root.best_move else None,
        },
        "ouvertures": report.first_moves,
        "ligne_principale": report.main_line,
        "lignes_alternatives": alternatives,
        "avertissements": report.warnings,
    }

    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    md = render_markdown(payload, report)
    args.out_md.parent.mkdir(parents=True, exist_ok=True)
    args.out_md.write_text(md, encoding="utf-8")

    print(md)
    print(f"\nJSON : {args.out_json}")
    print(f"Rapport : {args.out_md}")
    return 0


def _wr(value: Optional[float]) -> str:
    return "—" if value is None else f"{value * 100:.1f} %"


def _cell(move) -> str:
    return "—" if not move else f"({move[0]}, {move[1]})"


def render_tips(payload: dict) -> List[str]:
    """Conseils tirés des chiffres du livre, prêts à être enseignés."""
    lines: List[str] = []
    openings = payload["ouvertures"]
    if not openings:
        return lines

    best = openings[0]
    worst = openings[-1]
    spread = best["score_espere_p1"] - worst["score_espere_p1"]
    proven = sum(1 for o in openings if o["exact"])

    lines.append("## Conseils prêts pour un cours")
    lines.append("")
    lines.append(
        f"- **Commencer au centre** : {_cell(best['representative'])} donne le meilleur "
        f"score espéré du premier joueur ({_wr(best['score_espere_p1'])})."
    )
    lines.append(
        f"- **Le premier coup ne décide pas la partie** : les dix ouvertures uniques "
        f"tiennent dans {spread * 100:.1f} points de score espéré, et aucune n'est "
        "classée perdante par le moteur."
    )
    lines.append(
        f"- **Le coup le plus faible** est {_cell(worst['representative'])} "
        f"({_wr(worst['score_espere_p1'])}), soit {_wr(worst['ecart_au_meilleur'])} de moins "
        "que le meilleur : de quoi l'écarter, pas de quoi perdre sur-le-champ."
    )
    replies = [
        (o["representative"], o["meilleure_reponse"])
        for o in openings
        if o.get("meilleure_reponse")
    ]
    if replies:
        lines.append("- **Réponses au premier coup** : " + " ; ".join(
            f"{_cell(mv)} → {_cell(rep)}" for mv, rep in replies[:5]
        ) + ".")
    if proven:
        lines.append(
            f"- **Valeurs prouvées** : {proven} ouverture(s) de cette table sont des "
            "verdicts, le reste est estimé par le moteur."
        )
    else:
        lines.append(
            "- **Aucune ouverture n'est prouvée à ce jour** : tout ce tableau est une "
            "estimation du moteur, à présenter comme telle."
        )
    lines.append(
        "- **Notion à enseigner** : la différence entre une valeur *prouvée* (mat forcé "
        "ou verdict de la tablebase) et une *estimation* — le premier coup de la ligne "
        "principale illustre les deux cas."
    )
    lines.append("")
    return lines


def render_markdown(payload: dict, report: Report) -> str:
    root = payload["racine"]
    lines: List[str] = []
    lines.append("# Théorie d'ouverture")
    lines.append("")
    lines.append(
        f"Extraite du livre d'ouverture évalué par `4mation-engine` "
        f"({payload['genere_le']}, demi-coups 0 à {payload['max_ply']})."
    )
    lines.append("")
    lines.append(
        "Deux natures de valeurs, jamais confondues : **prouvé** (`exact=1`, mat forcé ou "
        "verdict de la tablebase) et **estimé** (évaluation du moteur convertie en taux de "
        "victoire par une sigmoïde calibrée, échelle "
        f"{payload['echelle_score']:.0f})."
    )
    lines.append("")
    lines.append("## Position de départ")
    lines.append("")
    lines.append("| Mesure | Valeur |")
    lines.append("|--------|--------|")
    lines.append(f"| Meilleur coup | {_cell(root['meilleur_coup'])} |")
    lines.append(f"| Score espéré du 1ᵉʳ joueur (V=1, N=0,5) | {_wr(root['score_espere_p1'])} |")
    lines.append(f"| Lecture | {root['lecture']} |")
    lines.append(f"| Nature | {'prouvé' if root['exact'] else 'estimé'} |")
    lines.append("")

    lines.append("## Les 10 ouvertures uniques")
    lines.append("")
    lines.append(
        "Le plateau est symétrique (rotations et miroir) : ces dix coups couvrent les "
        "49 cases de départ."
    )
    lines.append("")
    lines.append(
        "| Case | Taille d'orbite | Score espéré (1ᵉʳ joueur) | Écart au meilleur | "
        "Meilleure réponse | Lecture | Nature |"
    )
    lines.append(
        "|------|-----------------|----------------------------|-------------------|"
        "-------------------|---------|--------|"
    )
    for item in payload["ouvertures"]:
        lines.append(
            f"| {_cell(item['representative'])} | {item['taille_orbite']} | "
            f"{_wr(item['score_espere_p1'])} | {_wr(item['ecart_au_meilleur'])} | "
            f"{_cell(item.get('meilleure_reponse'))} | "
            f"{item['lecture']} | {'prouvé' if item['exact'] else 'estimé'} |"
        )
    lines.append("")

    lines.append("## Ligne principale")
    lines.append("")
    lines.append("Meilleur jeu supposé des deux camps, demi-coup par demi-coup.")
    lines.append("")
    lines.append("| Demi-coup | Camp | Coup | Score espéré (1ᵉʳ joueur) | Lecture |")
    lines.append("|-----------|------|------|----------------------------|---------|")
    for row in payload["ligne_principale"]:
        note = f" — {row['note']}" if row.get("note") else ""
        lines.append(
            f"| {row['ply']} | {row['joueur']} | {_cell(row['coup'])}{note} | "
            f"{_wr(row.get('score_espere_p1'))} | {row.get('lecture', '—')} |"
        )
    lines.append("")

    if payload["lignes_alternatives"]:
        lines.append("## Alternatives après le premier coup")
        lines.append("")
        for alt in payload["lignes_alternatives"]:
            moves = " ".join(
                _cell(step["coup"]) for step in alt["ligne"][:9] if step["coup"]
            )
            lines.append(
                f"- **{_cell(alt['premier_coup'])}** ({_wr(alt['score_espere_p1'])}) : {moves}"
            )
        lines.append("")

    lines.append("## Seuils de lecture")
    lines.append("")
    lines.append("| Bande | Score moteur | Score espéré | Ce que ça veut dire |")
    lines.append("|-------|--------------|--------------|---------------------|")
    lines.append("| Favorable | ≥ +40 | ≥ 0,54 | le camp au trait a mieux que la moyenne |")
    lines.append("| Équilibré | entre −40 et +40 | 0,46 – 0,54 | position sans avantage net |")
    lines.append("| Défavorable | ≤ −40 | ≤ 0,46 | le camp au trait subit |")
    lines.append("")
    lines.append(
        "Le seuil de ±40 points vient de la table de fiabilité du calibrage : c'est "
        "l'écart à partir duquel la prédiction s'écarte vraiment de 0,50."
    )
    lines.append("")
    if payload["fiabilite"]:
        lines.append("| Score | n | Prédit | Observé sur les finales exactes |")
        lines.append("|-------|---|--------|--------------------------------|")
        for band_row in payload["fiabilite"]:
            lines.append(
                f"| {band_row['score_min']} → {band_row['score_max']} | {band_row['n']} | "
                f"{band_row['predicted']:.3f} | {band_row['observed']:.3f} |"
            )
        lines.append("")

    lines.append("## Couverture du livre")
    lines.append("")
    lines.append("| Demi-coup | Entrées | dont prouvées |")
    lines.append("|-----------|---------|---------------|")
    for ply, info in payload["couverture"]["ply"].items():
        lines.append(f"| {ply} | {info['entrees']} | {info['exactes']} |")
    lines.append("")

    if payload["avertissements"]:
        lines.append("## Avertissements")
        lines.append("")
        for w in payload["avertissements"]:
            lines.append(f"- {w}")
        lines.append("")

    lines.extend(render_tips(payload))

    lines.append("## Limites")
    lines.append("")
    lines.append(
        "- La valeur chiffrée est un **score espéré** (victoire = 1, nulle = 0,5, défaite "
        "= 0) : c'est la cible sur laquelle la sigmoïde a été calibrée. Ce n'est pas une "
        "probabilité de victoire ; dans un jeu où la nulle est fréquente, les deux "
        "chiffres diffèrent nettement."
    )
    lines.append(
        "- Au-delà des positions prouvées, les scores sont des estimations du moteur, "
        "pas des résultats exacts : ils servent à classer les coups, pas à trancher une "
        "partie."
    )
    lines.append(
        "- La tablebase exacte couvre les finales (≤ 12 cases vides) ; l'ouverture reste "
        "hors de sa portée, c'est le livre qui l'évalue."
    )
    lines.append(
        "- Les coups sont donnés dans l'orientation du plateau de départ du livre ; pour "
        "lire une ligne, le script transporte chaque coup par la symétrie qui fait "
        "correspondre la position (voir `reorient`)."
    )
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
