"""
Lookup tablebase / livre d'ouverture pour l'API 4mation.

Priorité : opening_book → positions (endgame) → None (fallback Minimax/MCTS).
"""

from __future__ import annotations

import logging
import os
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from game_tree.optimized_minimax import OptimizedMinimaxAdvisor
from solver.db_schema import connect, init_db
from solver.position_hasher import HASHER
from solver.retrograde_solver import RetrogradeSolver, RESULT_DRAW, RESULT_LOSS, RESULT_WIN

logger = logging.getLogger(__name__)

DEFAULT_DB = Path(__file__).resolve().parent.parent.parent / "script" / "solver" / "data" / "tablebase.db"


@dataclass
class TablebaseHit:
    hash_key: str
    result: str
    win_rate: float
    best_move: Optional[Tuple[int, int]]
    source: str  # "opening_book" | "tablebase"
    depth_remaining: int = 0
    ply: int = 0
    exact: bool = True


class TablebaseLookup:
    """Service de consultation SQLite (lecture seule, rechargement à chaud)."""

    def __init__(
        self,
        db_path: Optional[str | Path] = None,
        max_endgame_empty: int = 12,
        max_opening_ply: int = 12,
    ) -> None:
        env_path = os.environ.get("TABLEBASE_DB_PATH")
        self.db_path = Path(db_path or env_path or DEFAULT_DB)
        self.max_endgame_empty = int(os.environ.get("TABLEBASE_MAX_EMPTY", max_endgame_empty))
        self.max_opening_ply = int(os.environ.get("TABLEBASE_MAX_OPENING_PLY", max_opening_ply))
        self._lock = threading.Lock()
        self._advisor = OptimizedMinimaxAdvisor(depth=4, use_iterative_deepening=False)
        self._retrograde = RetrogradeSolver(max_empty=self.max_endgame_empty)
        self._mcts = None
        self._mcts_budget_ms = int(os.environ.get("TABLEBASE_MCTS_MS", "600"))
        self._last_mtime: float = 0.0
        self._conn: Optional[sqlite3.Connection] = None
        self._ensure_db()

    def _get_mcts(self):
        if self._mcts is None:
            from game_tree.mcts_advisor import MCTSAdvisor

            self._mcts = MCTSAdvisor(time_budget_ms=self._mcts_budget_ms)
        return self._mcts

    def _enrich_analysis_meta(self, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Ajoute position_status et flags proven_* sur chaque coup."""
        moves = analysis.get("moves") or []
        exact = bool(analysis.get("exact"))
        if not moves:
            analysis["position_status"] = "estimated"
            return analysis

        best_wr = max(float(m["win_rate"]) for m in moves)
        worst_wr = min(float(m["win_rate"]) for m in moves)
        for m in moves:
            wr = float(m["win_rate"])
            m["proven_loss"] = exact and wr <= 0.005
            m["proven_win"] = exact and wr >= 0.995

        if exact and best_wr <= 0.005:
            analysis["position_status"] = "proven_losing"
        elif exact and worst_wr >= 0.995:
            analysis["position_status"] = "proven_winning"
        elif exact and all(abs(float(m["win_rate"]) - 0.5) < 0.01 for m in moves):
            analysis["position_status"] = "proven_draw"
        else:
            analysis["position_status"] = "estimated"
        return analysis

    def _build_mcts_analysis(
        self,
        board: np.ndarray,
        current_player: int,
        last_move: Optional[Tuple[int, int]],
        start: float,
        *,
        label: str = "Estimé (MCTS)",
    ) -> Dict[str, Any]:
        """Analyse MCTS complète (toutes les cases jouables)."""
        raw = self._get_mcts().analyze_position(board, current_player, last_move)
        moves = raw.get("moves") or []
        best = raw.get("best_move")
        best_wr = float(moves[0]["win_rate"]) if moves else 0.5
        analysis: Dict[str, Any] = {
            "moves": moves,
            "best_move": best,
            "current_player": current_player,
            "valid_moves_count": int(raw.get("valid_moves_count") or len(moves)),
            "elapsed_ms": int((time.perf_counter() - start) * 1000),
            "source": "mcts",
            "exact": False,
            "label": label,
            "position_win_rate": best_wr,
            "coverage_percent": 100.0 if moves else 0.0,
        }
        return self._enrich_analysis_meta(analysis)

    def _ensure_db(self) -> None:
        if not self.db_path.exists():
            logger.warning("Tablebase absente : %s — fallback Minimax/MCTS", self.db_path)
            return
        init_db(self.db_path)

    def _get_conn(self) -> Optional[sqlite3.Connection]:
        if not self.db_path.exists():
            return None
        mtime = self.db_path.stat().st_mtime
        with self._lock:
            if self._conn is None or mtime > self._last_mtime:
                if self._conn is not None:
                    try:
                        self._conn.close()
                    except sqlite3.Error:
                        pass
                self._conn = connect(self.db_path)
                self._last_mtime = mtime
                logger.info("Tablebase rechargée : %s", self.db_path)
            return self._conn

    def reload(self) -> None:
        with self._lock:
            if self._conn is not None:
                try:
                    self._conn.close()
                except sqlite3.Error:
                    pass
                self._conn = None
            self._last_mtime = 0.0
        self._get_conn()

    def _row_to_hit(self, row: sqlite3.Row, source: str) -> TablebaseHit:
        best = None
        if row["best_move_row"] is not None and row["best_move_row"] >= 0:
            best = (int(row["best_move_row"]), int(row["best_move_col"]))
        # Les positions (endgame) sont toujours exactes ; le livre d'ouverture porte un
        # flag exact (1 = prouvé via tablebase, 0 = estimation Minimax).
        keys = row.keys()
        is_exact = bool(row["exact"]) if "exact" in keys else True
        return TablebaseHit(
            hash_key=row["hash"],
            result=str(row["result"]),
            win_rate=float(row["win_rate"]),
            best_move=best,
            source=source,
            depth_remaining=int(row["depth_remaining"]) if "depth_remaining" in keys else 0,
            ply=int(row["ply"]) if "ply" in keys else 0,
            exact=is_exact,
        )

    def lookup(
        self,
        board: np.ndarray,
        current_player: int,
        last_move: Optional[Tuple[int, int]] = None,
    ) -> Optional[TablebaseHit]:
        conn = self._get_conn()
        if conn is None:
            return None

        h = HASHER.hash_key(board, current_player, last_move)
        ply = HASHER.move_count(board)

        if ply <= self.max_opening_ply:
            row = conn.execute(
                "SELECT hash, result, win_rate, best_move_row, best_move_col, ply, exact FROM opening_book WHERE hash=?",
                (h,),
            ).fetchone()
            if row is not None:
                return self._row_to_hit(row, "opening_book")

        row = conn.execute(
            "SELECT hash, result, win_rate, best_move_row, best_move_col, depth_remaining FROM positions WHERE hash=?",
            (h,),
        ).fetchone()
        if row is not None:
            return self._row_to_hit(row, "tablebase")

        return None

    def _child_win_rate(self, child_result: str, child_wr: float) -> Tuple[str, float]:
        """Valeur du coup parent : inverse le taux enfant (perspective adverse).

        On utilise 1 - child_wr pour conserver la calibration des estimations
        (exact=0). Se baser uniquement sur W/L/D donnerait 0 % ou 50 % partout."""
        wr = max(0.0, min(1.0, 1.0 - child_wr))
        if wr > 0.55:
            return RESULT_WIN, wr
        if wr < 0.45:
            return RESULT_LOSS, wr
        return RESULT_DRAW, wr

    def _lookup_child(
        self,
        conn: sqlite3.Connection,
        board: np.ndarray,
        move: Tuple[int, int],
        current_player: int,
    ) -> Optional[Tuple[str, float]]:
        nb = board.copy()
        nb[move[0], move[1]] = current_player
        opponent = 3 - current_player
        h = HASHER.hash_key(nb, opponent, move)

        row = conn.execute(
            "SELECT result, win_rate FROM opening_book WHERE hash=?", (h,)
        ).fetchone()
        if row is None:
            row = conn.execute(
                "SELECT result, win_rate FROM positions WHERE hash=?", (h,)
            ).fetchone()
        if row is None:
            return None
        return self._child_win_rate(str(row["result"]), float(row["win_rate"]))

    def opening_book_coach_analysis(
        self,
        board: np.ndarray,
        current_player: int,
        last_move: Optional[Tuple[int, int]],
        hit: TablebaseHit,
    ) -> Dict[str, Any]:
        """Analyse livre d'ouverture pour le coach (coups frontier légaux uniquement)."""
        return self._opening_book_analysis(
            board, current_player, last_move, hit, time.perf_counter()
        )

    def _opening_book_analysis(
        self,
        board: np.ndarray,
        current_player: int,
        last_move: Optional[Tuple[int, int]],
        hit: TablebaseHit,
        start: float,
    ) -> Dict[str, Any]:
        """Analyse à partir d'une entrée du livre d'ouverture, en respectant son flag
        exact (prouvé via tablebase) ou estimé (Minimax)."""
        conn = self._get_conn()
        moves_out: List[Dict[str, Any]] = []
        if conn is not None:
            for move in self._advisor._get_frontier_moves(board, last_move, current_player):
                if self._advisor._is_winning_move(board, move, current_player):
                    moves_out.append({
                        "move": move, "row": move[0], "col": move[1],
                        "win_rate": 1.0, "result": RESULT_WIN,
                    })
                    continue
                child = self._lookup_child(conn, board, move, current_player)
                if child is not None:
                    res, wr = child
                    moves_out.append({
                        "move": move, "row": move[0], "col": move[1],
                        "win_rate": wr, "result": res,
                    })
            moves_out.sort(key=lambda m: m["win_rate"], reverse=True)

        valid_moves = self._advisor._get_frontier_moves(board, last_move, current_player)
        label = "Exact (livre d'ouverture)" if hit.exact else "Estimé (livre d'ouverture)"
        position_wr = moves_out[0]["win_rate"] if moves_out else hit.win_rate
        best_move = moves_out[0]["move"] if moves_out else hit.best_move
        coverage = (
            100.0 * len(moves_out) / len(valid_moves) if valid_moves else 100.0
        )
        return {
            "moves": moves_out,
            "best_move": best_move,
            "current_player": current_player,
            "valid_moves_count": len(valid_moves),
            "elapsed_ms": int((time.perf_counter() - start) * 1000),
            "source": "opening_book",
            "exact": bool(hit.exact),
            "label": label,
            "position_win_rate": position_wr,
            "coverage_percent": coverage,
            "partial": coverage < 99.9,
        }

    def analyze_position(
        self,
        board: np.ndarray,
        current_player: int = 1,
        last_move: Optional[Tuple[int, int]] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Analyse exacte si toutes les sous-positions sont en base,
        ou via solveur rétrograde pour endgame.
        """
        start = time.perf_counter()
        hit = self.lookup(board, current_player, last_move)

        # Livre d'ouverture estimé (exact=0) : MCTS sur toutes les cases pour éviter
        # des 0 % trompeurs et des sauts livre → MCTS au coup suivant.
        if hit is not None and hit.source == "opening_book":
            if not hit.exact:
                return self._build_mcts_analysis(
                    board,
                    current_player,
                    last_move,
                    start,
                    label="Estimé (MCTS)",
                )
            book = self._opening_book_analysis(
                board, current_player, last_move, hit, start
            )
            if book.get("partial") or not book.get("moves"):
                return self._build_mcts_analysis(
                    board,
                    current_player,
                    last_move,
                    start,
                    label="Estimé (MCTS — couverture partielle)",
                )
            return self._enrich_analysis_meta(book)

        if hit is not None:
            retro = self._retrograde.analyze_moves(board, current_player, last_move)
            if retro is not None:
                retro["source"] = hit.source
                retro["exact"] = True
                retro["label"] = "Exact (tablebase)"
                retro["elapsed_ms"] = int((time.perf_counter() - start) * 1000)
                retro["coverage_percent"] = 100.0
                return self._enrich_analysis_meta(retro)

        if HASHER.empty_cells(board) <= self.max_endgame_empty:
            retro = self._retrograde.analyze_moves(board, current_player, last_move)
            if retro is not None:
                retro["source"] = hit.source if hit else "tablebase"
                retro["exact"] = True
                retro["label"] = "Exact (tablebase)"
                retro["elapsed_ms"] = int((time.perf_counter() - start) * 1000)
                return self._enrich_analysis_meta(retro)

        conn = self._get_conn()
        if conn is None:
            return None

        valid_moves = self._advisor._get_frontier_moves(board, last_move, current_player)
        if not valid_moves:
            return None

        moves_out: List[Dict[str, Any]] = []
        all_found = True

        for move in valid_moves:
            if self._advisor._is_winning_move(board, move, current_player):
                moves_out.append({
                    "move": move,
                    "row": move[0],
                    "col": move[1],
                    "win_rate": 1.0,
                    "result": RESULT_WIN,
                })
                continue

            child = self._lookup_child(conn, board, move, current_player)
            if child is None:
                all_found = False
                break
            res, wr = child
            moves_out.append({
                "move": move,
                "row": move[0],
                "col": move[1],
                "win_rate": wr,
                "result": res,
            })

        if not all_found:
            if moves_out:
                elapsed_ms = int((time.perf_counter() - start) * 1000)
                found_count = len(moves_out)
                coverage = 100.0 * found_count / len(valid_moves) if valid_moves else 0.0
                moves_out.sort(key=lambda m: m["win_rate"], reverse=True)
                return self._enrich_analysis_meta({
                    "moves": moves_out,
                    "best_move": moves_out[0]["move"],
                    "current_player": current_player,
                    "valid_moves_count": len(valid_moves),
                    "elapsed_ms": elapsed_ms,
                    "source": hit.source if hit else "tablebase",
                    "exact": True,
                    "label": f"Exact ({hit.source if hit else 'tablebase'})",
                    "position_win_rate": moves_out[0]["win_rate"],
                    "partial": True,
                    "coverage_percent": coverage,
                })
            return None

        moves_out.sort(key=lambda m: m["win_rate"], reverse=True)
        best_move = moves_out[0]["move"] if moves_out else None
        source = hit.source if hit else "tablebase"
        elapsed_ms = int((time.perf_counter() - start) * 1000)

        return self._enrich_analysis_meta({
            "moves": moves_out,
            "best_move": best_move,
            "current_player": current_player,
            "valid_moves_count": len(valid_moves),
            "elapsed_ms": elapsed_ms,
            "source": source,
            "exact": True,
            "label": f"Exact ({source})",
            "position_win_rate": hit.win_rate if hit else moves_out[0]["win_rate"],
            "coverage_percent": 100.0,
        })

    def choose_move(
        self,
        board: np.ndarray,
        current_player: int,
        last_move: Optional[Tuple[int, int]] = None,
        valid_moves: Optional[List[Tuple[int, int]]] = None,
    ) -> Optional[Tuple[int, int]]:
        hit = self.lookup(board, current_player, last_move)
        if hit is None or hit.best_move is None:
            return None
        if valid_moves and hit.best_move not in valid_moves:
            return None
        return hit.best_move

    def stats(self) -> Dict[str, Any]:
        conn = self._get_conn()
        if conn is None:
            return {"available": False, "path": str(self.db_path)}
        pos = conn.execute("SELECT COUNT(*) FROM positions").fetchone()[0]
        opening = conn.execute("SELECT COUNT(*) FROM opening_book").fetchone()[0]
        progress_row = conn.execute(
            "SELECT total_solved, current_phase, progress_percent FROM solver_progress WHERE id=1"
        ).fetchone()
        return {
            "available": True,
            "path": str(self.db_path),
            "positions": pos,
            "opening_book": opening,
            "solver_phase": progress_row["current_phase"] if progress_row else None,
            "solver_progress_percent": progress_row["progress_percent"] if progress_row else None,
        }


# Singleton API
_lookup: Optional[TablebaseLookup] = None


def get_tablebase_lookup() -> TablebaseLookup:
    global _lookup
    if _lookup is None:
        _lookup = TablebaseLookup()
    return _lookup
