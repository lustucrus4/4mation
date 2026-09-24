#!/usr/bin/env python3
"""Contrôle d'intégrité du livre d'ouverture.

Le livre d'ouverture est la matière première des cours d'ouverture : chaque ligne doit
être utilisable telle quelle. Ce script vérifie, ligne par ligne, les propriétés dont
dépendent l'API et le constructeur de cours.

Contrôles structurels (erreurs) :

- ``plateau`` : un plateau non vide doit avoir un dernier coup enregistré. Sans lui, la
  ligne est un vestige des anciens bugs de génération : elle n'est atteignable par
  aucune partie réelle.
- ``dernier_coup`` : la case du dernier coup doit porter un pion de l'adversaire du
  joueur au trait (c'est lui qui vient de jouer).
- ``pions`` : le nombre de pions doit être égal au demi-coup enregistré.
- ``coup_legal`` : le meilleur coup enregistré doit faire partie des coups légaux du
  plateau enregistré. Un coup illégal vient d'un décalage d'orientation : la clé est
  canonique (symétries), la position stockée ne l'est pas.

Contrôle de cohérence (avertissement) :

- ``coherence`` : la valeur du parent doit être l'opposée de celle de l'enfant atteint
  par son meilleur coup. Pour les valeurs **prouvées** (``exact=1``) la relation est
  stricte : toute différence est un bug. Pour les estimations, elle n'est qu'indicative
  (les budgets de recherche diffèrent d'un demi-coup à l'autre).

Usage :
    python script/solver/check_opening_book.py --sample 2000
    python script/solver/check_opening_book.py --ply 0 1 2 3 --all
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

ROOT = Path(__file__).resolve().parent.parent.parent
for _p in (str(ROOT), str(ROOT / "script")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from game_tree.optimized_minimax import OptimizedMinimaxAdvisor  # noqa: E402
from solver.position_hasher import HASHER  # noqa: E402

DEFAULT_DB = ROOT / "script" / "solver" / "data" / "tablebase.db"


def open_readonly(db_path: Path) -> sqlite3.Connection:
    """Ouverture en lecture seule : le contrôle peut tourner pendant une écriture."""
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=15.0)
    conn.row_factory = sqlite3.Row
    return conn


def _board_of(row: sqlite3.Row) -> Optional[np.ndarray]:
    raw = row["board_json"]
    if not raw:
        return None
    return np.array(json.loads(raw), dtype=int)


def _win_rate(row: sqlite3.Row) -> float:
    """Taux de victoire stocké, en gardant 0,0 comme valeur légitime.

    ``row["win_rate"] or 0.5`` serait faux : 0,0 (défaite prouvée) est évalué comme
    « faux » en Python et serait relu 0,5, ce qui fabriquerait de faux conflits.
    """
    value = row["win_rate"]
    return 0.5 if value is None else float(value)


def _child_hash(nb: np.ndarray, opponent: int, move: Tuple[int, int]) -> str:
    return HASHER.hash_key(nb, opponent, move)


def _abs_stats(values: List[float]) -> Optional[Tuple[int, float, float, float, int]]:
    """(paires, écart moyen, médian, 95ᵉ centile, nombre d'écarts > 0,10) en valeur absolue."""
    if not values:
        return None
    arr = np.abs(np.array(values))
    return (
        len(values),
        float(arr.mean()),
        float(np.median(arr)),
        float(np.percentile(arr, 95)),
        int((arr > 0.10).sum()),
    )


def check(
    db_path: Path,
    *,
    plies: Optional[List[int]] = None,
    sample_per_ply: int = 2000,
    include_estimates: bool = True,
    verbose: bool = True,
    by_ply: bool = False,
) -> Dict[str, int]:
    conn = open_readonly(db_path)
    advisor = OptimizedMinimaxAdvisor(depth=1, use_iterative_deepening=False)

    all_counts: Counter = Counter()
    for row in conn.execute(
        "SELECT ply, COUNT(*) AS n FROM opening_book GROUP BY ply ORDER BY ply"
    ):
        all_counts[int(row["ply"])] = int(row["n"])
    ply_counts = Counter(
        {p: n for p, n in all_counts.items() if not plies or p in plies}
    )

    if verbose:
        total = sum(all_counts.values())
        print(f"Livre : {total} lignes au total — {len(all_counts)} demi-coups distincts.")
        print("  " + " | ".join(f"ply {p}: {n}" for p, n in sorted(all_counts.items())))
        if plies:
            print(f"  contrôlés : {sorted(ply_counts)} ({sum(ply_counts.values())} lignes)")

    errors: Counter = Counter()
    examples: Dict[str, List[str]] = defaultdict(list)

    def fail(kind: str, h: str, detail: str) -> None:
        errors[kind] += 1
        if len(examples[kind]) < 5:
            examples[kind].append(f"{h[:16]}… {detail}")

    checked = 0
    exact_deltas: List[float] = []
    est_deltas: List[float] = []
    exact_by_ply: Dict[int, List[float]] = defaultdict(list)
    est_by_ply: Dict[int, List[float]] = defaultdict(list)
    exclusive = 0
    exclusive_by_ply: Counter = Counter()

    for ply, _count in sorted(ply_counts.items()):
        query = "SELECT * FROM opening_book WHERE ply=? ORDER BY hash"
        if sample_per_ply > 0:
            query += f" LIMIT {int(sample_per_ply)}"
        for row in conn.execute(query, (ply,)):
            checked += 1
            h = str(row["hash"])
            board = _board_of(row)
            player = int(row["current_player"] or 1)
            last = (
                int(row["pos_last_move_row"]),
                int(row["pos_last_move_col"]),
            )
            has_last = last[0] >= 0 and last[1] >= 0
            stones = int(np.count_nonzero(board)) if board is not None else 0

            if board is None:
                continue
            if stones > 0 and not has_last:
                fail("plateau", h, "plateau non vide sans dernier coup enregistré")
                continue
            if stones != int(ply):
                fail("pions", h, f"{stones} pions pour un ply de {ply}")
                continue
            if has_last:
                lr, lc = last
                if not (0 <= lr < 7 and 0 <= lc < 7):
                    fail("dernier_coup", h, f"dernier coup hors plateau {last}")
                    continue
                if board[lr, lc] != 3 - player:
                    fail(
                        "dernier_coup",
                        h,
                        f"case {last} = {board[lr, lc]}, attendu {3 - player} (adversaire)",
                    )
                    continue

            legal = advisor._get_frontier_moves(board, last if has_last else None, player)
            br, bc = int(row["best_move_row"]), int(row["best_move_col"])
            has_best = br >= 0 and bc >= 0
            if has_best and (br, bc) not in legal:
                fail(
                    "coup_legal",
                    h,
                    f"meilleur coup ({br},{bc}) hors des {len(legal)} coups légaux",
                )
                continue

            if not has_best or not legal:
                continue

            nb = board.copy()
            nb[br, bc] = player
            opponent = 3 - player
            child_h = _child_hash(nb, opponent, (br, bc))
            child = conn.execute(
                "SELECT result, win_rate, exact FROM opening_book WHERE hash=?",
                (child_h,),
            ).fetchone()
            if child is None:
                exclusive += 1
                exclusive_by_ply[ply] += 1
                continue

            parent_wr = _win_rate(row)
            child_wr = _win_rate(child)
            expected = 1.0 - child_wr
            delta = expected - parent_wr
            if int(row["exact"] or 0) == 1 and int(child["exact"] or 0) == 1:
                exact_deltas.append(delta)
                exact_by_ply[ply].append(delta)
            elif include_estimates:
                est_deltas.append(delta)
                est_by_ply[ply].append(delta)

    conn.close()

    def stats(values: List[float]) -> str:
        s = _abs_stats(values)
        if s is None:
            return "aucune donnée"
        n, mean, median, p95, over = s
        return (
            f"{n} paires | écart moyen {mean:.3f} | "
            f"médian {median:.3f} | 95ᵉ centile {p95:.3f} | "
            f"écarts > 0,10 : {over}"
        )

    if verbose:
        print()
        print(f"Lignes contrôlées : {checked}")
        print()
        print("Contrôles structurels")
        for kind in ("plateau", "pions", "dernier_coup", "coup_legal"):
            n = errors[kind]
            verdict = "OK" if n == 0 else f"{n} ERREURS"
            print(f"  {kind:<12} {verdict}")
            for line in examples[kind]:
                print(f"      {line}")
        if errors["coup_legal"] == 0:
            print("  → tous les meilleurs coups enregistrés sont légaux sur leur plateau")

        print()
        print("Cohérence parent / enfant (valeur du parent = opposé de l'enfant)")
        print(f"  valeurs prouvées (exact=1)  : {stats(exact_deltas)}")
        print(f"  estimations (exact=0)       : {stats(est_deltas)}")
        print(f"  sans enfant dans le livre    : {exclusive} lignes (bout de livre, normal)")

        if by_ply:
            print()
            print("Détail par demi-coup du parent (repère : à partir du ply 5-6, les")
            print("couches basses et hautes du livre viennent de calculateurs différents)")
            header = (
                f"  {'ply':>4} {'paires':>7} {'moyen':>7} {'médian':>7} "
                f"{'p95':>7} {'>0,10':>6} {'sans enfant':>12}   natures"
            )
            print(header)
            for p in sorted(set(est_by_ply) | set(exact_by_ply) | set(exclusive_by_ply)):
                row_est = est_by_ply.get(p, [])
                row_ex = exact_by_ply.get(p, [])
                s = _abs_stats(row_est + row_ex)
                if s is None:
                    print(
                        f"  {p:>4} {'—':>7} {'—':>7} {'—':>7} {'—':>7} {'—':>6} "
                        f"{exclusive_by_ply[p]:>12}   aucune paire"
                    )
                    continue
                n, mean, median, p95, over = s
                natures = []
                if row_ex:
                    natures.append(f"{len(row_ex)} prouvées")
                if row_est:
                    natures.append(f"{len(row_est)} estimées")
                print(
                    f"  {p:>4} {n:>7} {mean:>7.3f} {median:>7.3f} {p95:>7.3f} {over:>6} "
                    f"{exclusive_by_ply[p]:>12}   {', '.join(natures)}"
                )

    return {
        "checked": checked,
        "errors": sum(errors.values()),
        "exclusives": exclusive,
        "exact_pairs": len(exact_deltas),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Contrôle d'intégrité du livre d'ouverture")
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument(
        "--ply",
        type=int,
        nargs="*",
        default=None,
        help="Demi-coups à contrôler (défaut : tous)",
    )
    parser.add_argument(
        "--sample",
        type=int,
        default=2000,
        help="Lignes contrôlées par demi-coup (0 = aucune limite)",
    )
    parser.add_argument("--all", action="store_true", help="Contrôler toutes les lignes")
    parser.add_argument(
        "--by-ply",
        action="store_true",
        help="Détail des écarts de cohérence demi-coup par demi-coup",
    )
    args = parser.parse_args()

    result = check(
        Path(args.db),
        plies=args.ply,
        sample_per_ply=0 if args.all else args.sample,
        by_ply=args.by_ply,
    )
    sys.exit(1 if result["errors"] else 0)


if __name__ == "__main__":
    main()
