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
        self._last_mtime: float = 0.0
        self._conn: Optional[sqlite3.Connection] = None
        self._ensure_db()

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
        return TablebaseHit(
            hash_key=row["hash"],
            result=str(row["result"]),
            win_rate=float(row["win_rate"]),
            best_move=best,
            source=source,
            depth_remaining=int(row["depth_remaining"]) if "depth_remaining" in row.keys() else 0,
            ply=int(row["ply"]) if "ply" in row.keys() else 0,
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
                "SELECT hash, result, win_rate, best_move_row, best_move_col, ply FROM opening_book WHERE hash=?",
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
        if child_result == RESULT_WIN:
            return RESULT_LOSS, 0.0
        if child_result == RESULT_LOSS:
            return RESULT_WIN, 1.0
        return RESULT_DRAW, 0.5

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

        if hit is not None:
            retro = self._retrograde.analyze_moves(board, current_player, last_move)
            if retro is not None:
                retro["source"] = hit.source
                retro["exact"] = True
                retro["label"] = "Exact (tablebase)"
                retro["elapsed_ms"] = int((time.perf_counter() - start) * 1000)
                retro["coverage_percent"] = 100.0
                return retro

        if HASHER.empty_cells(board) <= self.max_endgame_empty:
            retro = self._retrograde.analyze_moves(board, current_player, last_move)
            if retro is not None:
                retro["source"] = hit.source if hit else "tablebase"
                retro["exact"] = True
                retro["label"] = "Exact (tablebase)"
                retro["elapsed_ms"] = int((time.perf_counter() - start) * 1000)
                return retro

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
            if hit is not None and hit.best_move is not None:
                elapsed_ms = int((time.perf_counter() - start) * 1000)
                found_count = len(moves_out)
                coverage = 100.0 * found_count / len(valid_moves) if valid_moves else 0.0
                return {
                    "moves": moves_out,
                    "best_move": hit.best_move,
                    "current_player": current_player,
                    "valid_moves_count": len(valid_moves),
                    "elapsed_ms": elapsed_ms,
                    "source": hit.source,
                    "exact": True,
                    "label": f"Exact ({hit.source})",
                    "position_win_rate": hit.win_rate,
                    "partial": True,
                    "coverage_percent": coverage,
                }
            return None

        moves_out.sort(key=lambda m: m["win_rate"], reverse=True)
        best_move = moves_out[0]["move"] if moves_out else None
        source = hit.source if hit else "tablebase"
        elapsed_ms = int((time.perf_counter() - start) * 1000)

        return {
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
        }

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
