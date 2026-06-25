#!/usr/bin/env python3
"""
Construit le livre d'ouverture 4mation, **adossé à la tablebase**.

Principe (option A « évolutive ») :
- On parcourt les positions d'ouverture (BFS depuis le plateau vide jusqu'à --max-ply).
- Pour chaque position, on tente une résolution EXACTE : si TOUS les coups légaux
  mènent à une feuille prouvée (coup gagnant immédiat, position déjà dans `positions`,
  ou entrée `opening_book` déjà marquée exact), alors la valeur de la position est
  prouvée → on la stocke avec exact=1.
- Sinon, on stocke la meilleure ESTIMATION, exact=0. Cette estimation est renforcée par :
    (1) une recherche Minimax PLUS PROFONDE sur les premiers coups (ceux réellement
        joués), dégressive avec la profondeur ;
    (2) un MÉLANGE avec MCTS pour calibrer le taux de victoire (barre W/L réaliste) ;
    (3) une LARGEUR d'exploration dépendante du ply (large tôt, étroite en profondeur).

Les positions sont traitées de la plus PROFONDE (proche de la fin de partie, donc de
la tablebase) vers l'ouverture : à chaque relance, comme la tablebase a grimpé, de plus
en plus d'entrées passent d'« estimé » à « exact ». Le livre CONVERGE vers le parfait
sans jamais tout recalculer.

Usage:
    python script/solver/build_opening_book.py [--db PATH] [--max-ply 12]
        [--max-positions 5000] [--refresh-estimates]
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from collections import deque
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np

ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = ROOT / "script"
if str(SCRIPT) not in sys.path:
    sys.path.insert(0, str(SCRIPT))

from game_tree.mcts_advisor import MCTSAdvisor
from game_tree.optimized_minimax import OptimizedMinimaxAdvisor
from solver.db_schema import init_db
from solver.position_hasher import HASHER
from solver.retrograde_solver import RESULT_DRAW, RESULT_LOSS, RESULT_WIN

DEFAULT_DB = SCRIPT / "solver" / "data" / "tablebase.db"

# Score Minimax (brut, négamax) au-delà duquel on considère une victoire/défaite forcée.
DECISIVE = 50000


def _search_params(ply: int) -> Tuple[int, int, int]:
    """(profondeur Minimax, budget Minimax ms, budget MCTS ms) selon le ply.

    On investit BEAUCOUP plus sur les premiers coups (peu nombreux mais réellement
    joués) et on allège en profondeur (positions exponentiellement plus nombreuses)."""
    if ply <= 1:
        return 18, 15000, 3000
    if ply == 2:
        return 16, 6000, 1500
    if ply <= 4:
        return 12, 2500, 600
    return 10, 1500, 400


def _branch_for_ply(ply: int) -> int:
    """Largeur d'exploration : large sur les premiers coups (couvrir toutes les
    réponses raisonnables), étroite ensuite (suivre les lignes principales)."""
    if ply == 0:
        return 49
    if ply <= 2:
        return 8
    if ply <= 5:
        return 6
    return 4


def _score_to_result(score: float) -> Tuple[str, float]:
    """Convertit un score Minimax brut en (résultat, taux de victoire estimé)."""
    if score > DECISIVE:
        return RESULT_WIN, 1.0
    if score < -DECISIVE:
        return RESULT_LOSS, 0.0
    if score > 1000:
        return RESULT_WIN, min(0.95, 0.5 + score / 200000)
    if score < -1000:
        return RESULT_LOSS, max(0.05, 0.5 + score / 200000)
    return RESULT_DRAW, 0.5


def _invert_for_parent(child_result: str) -> Tuple[str, float]:
    """Valeur d'un coup, vue par le joueur au trait, à partir du résultat de l'enfant
    (qui est vu par l'adversaire, joueur au trait dans la position enfant)."""
    if child_result == RESULT_WIN:
        return RESULT_LOSS, 0.0
    if child_result == RESULT_LOSS:
        return RESULT_WIN, 1.0
    return RESULT_DRAW, 0.5


def _store_opening(
    conn: sqlite3.Connection,
    h: str,
    result: str,
    wr: float,
    best_move: Optional[Tuple[int, int]],
    ply: int,
    exact: int,
) -> None:
    br, bc = (best_move[0], best_move[1]) if best_move else (-1, -1)
    conn.execute(
        """
        INSERT OR REPLACE INTO opening_book
        (hash, result, win_rate, best_move_row, best_move_col, ply, exact, solved_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """,
        (h, result, wr, br, bc, ply, exact),
    )


def _resolve_child_exact(
    conn: sqlite3.Connection,
    advisor: OptimizedMinimaxAdvisor,
    board: np.ndarray,
    move: Tuple[int, int],
    player: int,
) -> Optional[Tuple[str, float]]:
    """Renvoie (résultat, taux) du coup `move` vu par `player`, UNIQUEMENT si la valeur
    est prouvée (feuille exacte). Sinon None."""
    if advisor._is_winning_move(board, move, player):
        return RESULT_WIN, 1.0
    nb = board.copy()
    nb[move[0], move[1]] = player
    opponent = 3 - player
    h = HASHER.hash_key(nb, opponent, move)
    row = conn.execute("SELECT result FROM positions WHERE hash=?", (h,)).fetchone()
    if row is None:
        row = conn.execute(
            "SELECT result FROM opening_book WHERE hash=? AND exact=1", (h,)
        ).fetchone()
    if row is None:
        return None
    return _invert_for_parent(str(row["result"]))


def _try_exact(
    conn: sqlite3.Connection,
    advisor: OptimizedMinimaxAdvisor,
    board: np.ndarray,
    player: int,
    last_move: Optional[Tuple[int, int]],
) -> Optional[Tuple[str, float, Tuple[int, int]]]:
    """Résolution exacte si TOUS les coups légaux mènent à une feuille prouvée."""
    moves = advisor._get_frontier_moves(board, last_move, player)
    if not moves:
        return None
    resolved: List[Tuple[Tuple[int, int], str, float]] = []
    for move in moves:
        child = _resolve_child_exact(conn, advisor, board, move, player)
        if child is None:
            return None  # au moins un enfant non prouvé → position non prouvable
        resolved.append((move, child[0], child[1]))
    best_move, best_result, best_wr = max(resolved, key=lambda x: x[2])
    return best_result, best_wr, best_move


def _minimax_search(
    advisor: OptimizedMinimaxAdvisor,
    board: np.ndarray,
    player: int,
    last_move: Optional[Tuple[int, int]],
    depth: int,
    time_ms: int,
) -> Tuple[Optional[Tuple[int, int]], float]:
    """Recherche Minimax (iterative deepening, gère son propre timeout) → (coup, score brut)."""
    advisor.max_depth = depth
    advisor.time_budget_ms = time_ms
    try:
        advisor.nodes_searched = 0
        advisor._begin_search()
        return advisor._iterative_deepening(board, last_move, player)
    except Exception:
        return None, 0.0


def _calibrated_winrate(
    mcts: MCTSAdvisor,
    board: np.ndarray,
    player: int,
    last_move: Optional[Tuple[int, int]],
    raw_score: float,
    mcts_ms: int,
) -> Tuple[str, float]:
    """Taux de victoire (perspective joueur au trait) :
    - victoire/défaite forcée détectée par la recherche → 1.0 / 0.0 (on fait confiance) ;
    - sinon → mélange heuristique Minimax (40%) + MCTS (60%) pour un % calibré et lisse."""
    if raw_score > DECISIVE:
        return RESULT_WIN, 1.0
    if raw_score < -DECISIVE:
        return RESULT_LOSS, 0.0

    heur_wr = _score_to_result(raw_score)[1]
    mcts_wr = heur_wr
    try:
        mcts.time_budget_ms = mcts_ms
        analysis = mcts.analyze_position(board, player, last_move)
        moves = analysis.get("moves") or []
        if moves:
            mcts_wr = float(moves[0]["win_rate"])
    except Exception:
        pass

    wr = max(0.0, min(1.0, 0.4 * heur_wr + 0.6 * mcts_wr))
    if wr > 0.55:
        return RESULT_WIN, wr
    if wr < 0.45:
        return RESULT_LOSS, wr
    return RESULT_DRAW, wr


def _collect_positions(
    advisor: OptimizedMinimaxAdvisor,
    max_ply: int,
    max_positions: int,
) -> List[Tuple[np.ndarray, int, Optional[Tuple[int, int]], int, str]]:
    """BFS depuis le plateau vide ; largeur dépendante du ply. Renvoie une liste
    dédupliquée de positions (board, player, last_move, ply, hash)."""
    seen: set[str] = set()
    out: List[Tuple[np.ndarray, int, Optional[Tuple[int, int]], int, str]] = []
    queue: deque = deque()
    queue.append((np.zeros((7, 7), dtype=np.int8), 1, None, 0))
    while queue and len(out) < max_positions:
        board, player, last_move, ply = queue.popleft()
        h = HASHER.hash_key(board, player, last_move)
        if h in seen:
            continue
        seen.add(h)
        out.append((board, player, last_move, ply, h))
        if ply >= max_ply or advisor._check_winner(board) is not None:
            continue
        moves = advisor._get_frontier_moves(board, last_move, player)
        ordered = advisor._order_moves(board, moves, player, last_move)
        for move in ordered[: _branch_for_ply(ply)]:
            nb = board.copy()
            nb[move[0], move[1]] = player
            if advisor._check_winner(nb) is not None:
                continue
            queue.append((nb, 3 - player, move, ply + 1))
    return out


def build_opening_book(
    db_path: Path,
    max_ply: int = 12,
    max_positions: int = 5000,
    refresh_estimates: bool = False,
    verbose: bool = True,
) -> Tuple[int, int]:
    """Construit / met à jour le livre d'ouverture.

    refresh_estimates=False (défaut, idéal pour les relances auto) : on tente toujours la
    promotion EXACTE (lookups bon marché), mais on NE recalcule PAS l'estimation des
    positions déjà présentes. Les relances sont donc rapides.
    refresh_estimates=True : on recalcule toutes les estimations (recherche + MCTS).
    """
    conn = init_db(db_path)
    advisor = OptimizedMinimaxAdvisor(
        depth=12, use_iterative_deepening=True, cache_size=200000
    )
    mcts = MCTSAdvisor(time_budget_ms=800)

    existing_estimates: set[str] = set()
    if not refresh_estimates:
        existing_estimates = {
            row[0] for row in conn.execute(
                "SELECT hash FROM opening_book WHERE exact=0"
            ).fetchall()
        }

    positions = _collect_positions(advisor, max_ply, max_positions)
    # Plus profond d'abord : les enfants (ply+1) sont traités avant leurs parents, donc
    # les entrées exact=1 nouvellement écrites peuvent prouver les parents dans la foulée.
    positions.sort(key=lambda p: p[3], reverse=True)

    if verbose:
        print(f"{len(positions)} positions d'ouverture collectées (ply<={max_ply}).")

    n_exact = 0
    n_estimate = 0
    n_kept = 0
    for i, (board, player, last_move, ply, h) in enumerate(positions):
        exact = _try_exact(conn, advisor, board, player, last_move)
        if exact is not None:
            result, wr, best = exact
            _store_opening(conn, h, result, wr, best, ply, exact=1)
            n_exact += 1
        elif not refresh_estimates and h in existing_estimates:
            n_kept += 1
            continue
        else:
            depth, mm_ms, mcts_ms = _search_params(ply)
            best, raw = _minimax_search(advisor, board, player, last_move, depth, mm_ms)
            if best is None:
                continue
            result, wr = _calibrated_winrate(mcts, board, player, last_move, raw, mcts_ms)
            _store_opening(conn, h, result, wr, best, ply, exact=0)
            n_estimate += 1

        if verbose and (i + 1) % 25 == 0:
            conn.commit()
            print(
                f"  {i + 1}/{len(positions)} traitées "
                f"(exact={n_exact}, estimé={n_estimate}, conservées={n_kept})"
            )

    conn.commit()
    conn.close()
    if verbose:
        print(
            f"Livre d'ouverture : {n_exact} exact(s) + {n_estimate} estimé(s) "
            f"+ {n_kept} conservée(s) -> {db_path}"
        )
    return n_exact, n_estimate


def main() -> None:
    parser = argparse.ArgumentParser(description="Génère le livre d'ouverture 4mation")
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--max-ply", type=int, default=12)
    parser.add_argument("--max-positions", type=int, default=5000)
    parser.add_argument(
        "--refresh-estimates", action="store_true",
        help="Recalcule les estimations existantes (sinon on ne fait que la promotion exacte)",
    )
    args = parser.parse_args()

    print(
        f"Construction livre d'ouverture (ply<={args.max_ply}, max={args.max_positions}, "
        f"recherche profonde + MCTS + largeur dépendante du ply)..."
    )
    build_opening_book(
        Path(args.db),
        max_ply=args.max_ply,
        max_positions=args.max_positions,
        refresh_estimates=args.refresh_estimates,
    )


if __name__ == "__main__":
    main()
