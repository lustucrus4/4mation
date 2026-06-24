"""
File de travail partagée pour workers solveur distribués (SQLite).
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional, Tuple

from solver.db_schema import connect, init_db

logger = logging.getLogger(__name__)

DEFAULT_DB = (
    Path(__file__).resolve().parent.parent.parent / "script" / "solver" / "data" / "tablebase.db"
)

CLAIM_TIMEOUT_SEC = int(os.environ.get("SOLVER_CLAIM_TIMEOUT_SEC", "300"))
MAX_CLAIM_BATCH = int(os.environ.get("SOLVER_MAX_CLAIM_BATCH", "50"))
RATE_LIMIT_CLAIMS = int(os.environ.get("SOLVER_RATE_LIMIT_CLAIMS", "120"))
RATE_LIMIT_WINDOW_SEC = int(os.environ.get("SOLVER_RATE_LIMIT_WINDOW_SEC", "60"))


class WorkQueueService:
    def __init__(self, db_path: Optional[str | Path] = None) -> None:
        env_db = os.environ.get("TABLEBASE_DB_PATH")
        self.db_path = Path(db_path or env_db or DEFAULT_DB)
        self._lock = threading.Lock()
        self._claim_log: Dict[str, Deque[float]] = defaultdict(deque)

    def _get_conn(self) -> sqlite3.Connection:
        init_db(self.db_path)
        return connect(self.db_path)

    def _check_rate_limit(self, worker_id: str) -> bool:
        now = time.monotonic()
        window = self._claim_log[worker_id]
        while window and now - window[0] > RATE_LIMIT_WINDOW_SEC:
            window.popleft()
        if len(window) >= RATE_LIMIT_CLAIMS:
            return False
        window.append(now)
        return True

    def _reclaim_stale(self, conn: sqlite3.Connection) -> int:
        cutoff = (datetime.now(timezone.utc) - timedelta(seconds=CLAIM_TIMEOUT_SEC)).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        cur = conn.execute(
            """
            UPDATE work_queue
            SET status = 'pending', worker_id = NULL, claimed_at = NULL
            WHERE status = 'in_progress'
              AND claimed_at IS NOT NULL
              AND claimed_at < ?
            """,
            (cutoff,),
        )
        return cur.rowcount

    def claim(self, worker_id: str, count: int) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        worker_id = (worker_id or "").strip()
        if not worker_id:
            return [], "worker_id requis"
        count = max(1, min(int(count or 1), MAX_CLAIM_BATCH))

        with self._lock:
            if not self._check_rate_limit(worker_id):
                return [], "rate limit claim dépassé"

            conn = self._get_conn()
            try:
                conn.execute("BEGIN IMMEDIATE")
                reclaimed = self._reclaim_stale(conn)

                rows = conn.execute(
                    """
                    SELECT hash, board_json, player, last_move_row, last_move_col
                    FROM work_queue
                    WHERE status = 'pending'
                    ORDER BY created_at ASC
                    LIMIT ?
                    """,
                    (count,),
                ).fetchall()

                claimed: List[Dict[str, Any]] = []
                for row in rows:
                    conn.execute(
                        """
                        UPDATE work_queue
                        SET status = 'in_progress', worker_id = ?, claimed_at = CURRENT_TIMESTAMP
                        WHERE hash = ? AND status = 'pending'
                        """,
                        (worker_id, row["hash"]),
                    )
                    last_move = None
                    if row["last_move_row"] is not None and int(row["last_move_row"]) >= 0:
                        last_move = {
                            "row": int(row["last_move_row"]),
                            "col": int(row["last_move_col"]),
                        }
                    try:
                        board = json.loads(row["board_json"])
                    except (json.JSONDecodeError, TypeError):
                        board = row["board_json"]
                    claimed.append(
                        {
                            "hash": row["hash"],
                            "board_json": board,
                            "player": int(row["player"]),
                            "last_move": last_move,
                        }
                    )

                self._sync_queued_count(conn)
                conn.commit()
                if reclaimed:
                    logger.info("Reclaim %d positions expirées", reclaimed)
                return claimed, None
            except sqlite3.Error as exc:
                conn.rollback()
                logger.exception("Erreur claim work_queue")
                return [], str(exc)
            finally:
                conn.close()

    def submit(self, payload: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        hash_key = str(payload.get("hash") or "").strip().lower()
        result = str(payload.get("result") or "").strip().upper()
        if not hash_key:
            return False, "hash requis"
        if result not in ("W", "L", "D"):
            return False, "result invalide (W/L/D)"

        try:
            win_rate = float(payload.get("win_rate", 0.5))
        except (TypeError, ValueError):
            return False, "win_rate invalide"

        best_move = payload.get("best_move")
        br, bc = -1, -1
        if isinstance(best_move, dict):
            if best_move.get("row") is not None and int(best_move["row"]) >= 0:
                br = int(best_move["row"])
                bc = int(best_move.get("col", -1))

        board_json = payload.get("board_json")
        player = payload.get("player")
        last_move = payload.get("last_move")
        depth_remaining = int(payload.get("depth_remaining") or 0)

        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute("BEGIN IMMEDIATE")

                row = conn.execute(
                    "SELECT board_json, player, last_move_row, last_move_col FROM work_queue WHERE hash = ?",
                    (hash_key,),
                ).fetchone()

                if board_json is None and row is not None:
                    board_json = row["board_json"]
                if player is None and row is not None:
                    player = row["player"]
                if last_move is None and row is not None:
                    if row["last_move_row"] is not None and int(row["last_move_row"]) >= 0:
                        last_move = {"row": int(row["last_move_row"]), "col": int(row["last_move_col"])}

                if board_json is None:
                    conn.rollback()
                    return False, "board_json manquant"

                if isinstance(board_json, list):
                    board_json_str = json.dumps(board_json)
                else:
                    board_json_str = str(board_json)

                lmr, lmc = -1, -1
                if isinstance(last_move, dict) and last_move.get("row") is not None:
                    if int(last_move["row"]) >= 0:
                        lmr = int(last_move["row"])
                        lmc = int(last_move.get("col", -1))

                conn.execute(
                    """
                    INSERT OR REPLACE INTO positions
                    (hash, result, win_rate, best_move_row, best_move_col, depth_remaining,
                     board_json, current_player, pos_last_move_row, pos_last_move_col, solved_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    """,
                    (
                        hash_key,
                        result,
                        win_rate,
                        br,
                        bc,
                        depth_remaining,
                        board_json_str,
                        int(player or 1),
                        lmr,
                        lmc,
                    ),
                )

                conn.execute(
                    """
                    UPDATE work_queue
                    SET status = 'done', worker_id = COALESCE(worker_id, ?), claimed_at = COALESCE(claimed_at, CURRENT_TIMESTAMP)
                    WHERE hash = ?
                    """,
                    (payload.get("worker_id"), hash_key),
                )

                total_solved = conn.execute("SELECT COUNT(*) FROM positions").fetchone()[0]
                conn.execute(
                    """
                    INSERT INTO solver_progress (id, total_solved, total_queued, updated_at)
                    VALUES (1, ?, COALESCE((SELECT total_queued FROM solver_progress WHERE id = 1), 0), CURRENT_TIMESTAMP)
                    ON CONFLICT(id) DO UPDATE SET
                        total_solved = excluded.total_solved,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (total_solved,),
                )
                self._sync_queued_count(conn)
                conn.commit()
                return True, None
            except sqlite3.Error as exc:
                conn.rollback()
                logger.exception("Erreur submit work_queue")
                return False, str(exc)
            finally:
                conn.close()

    def _sync_queued_count(self, conn: sqlite3.Connection) -> None:
        pending = conn.execute(
            "SELECT COUNT(*) FROM work_queue WHERE status = 'pending'"
        ).fetchone()[0]
        conn.execute(
            """
            INSERT INTO solver_progress (id, total_queued, updated_at)
            VALUES (1, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(id) DO UPDATE SET total_queued = excluded.total_queued, updated_at = CURRENT_TIMESTAMP
            """,
            (pending,),
        )

    def submit_batch(
        self, worker_id: str, results: List[Dict[str, Any]]
    ) -> Tuple[int, int, List[str]]:
        """Soumet plusieurs positions en une transaction. Retourne (ok, fail, erreurs)."""
        if not results:
            return 0, 0, []

        ok_count = 0
        fail_count = 0
        errors: List[str] = []

        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute("BEGIN IMMEDIATE")
                for payload in results:
                    if worker_id and not payload.get("worker_id"):
                        payload = {**payload, "worker_id": worker_id}
                    hash_key = str(payload.get("hash") or "").strip().lower()
                    result = str(payload.get("result") or "").strip().upper()
                    if not hash_key or result not in ("W", "L", "D"):
                        fail_count += 1
                        errors.append(f"{hash_key or '?'}: payload invalide")
                        continue
                    try:
                        win_rate = float(payload.get("win_rate", 0.5))
                    except (TypeError, ValueError):
                        fail_count += 1
                        errors.append(f"{hash_key}: win_rate invalide")
                        continue

                    best_move = payload.get("best_move")
                    br, bc = -1, -1
                    if isinstance(best_move, dict):
                        if best_move.get("row") is not None and int(best_move["row"]) >= 0:
                            br = int(best_move["row"])
                            bc = int(best_move.get("col", -1))

                    board_json = payload.get("board_json")
                    player = payload.get("player")
                    last_move = payload.get("last_move")
                    depth_remaining = int(payload.get("depth_remaining") or 0)

                    row = conn.execute(
                        "SELECT board_json, player, last_move_row, last_move_col FROM work_queue WHERE hash = ?",
                        (hash_key,),
                    ).fetchone()

                    if board_json is None and row is not None:
                        board_json = row["board_json"]
                    if player is None and row is not None:
                        player = row["player"]
                    if last_move is None and row is not None:
                        if row["last_move_row"] is not None and int(row["last_move_row"]) >= 0:
                            last_move = {
                                "row": int(row["last_move_row"]),
                                "col": int(row["last_move_col"]),
                            }

                    if board_json is None:
                        fail_count += 1
                        errors.append(f"{hash_key}: board_json manquant")
                        continue

                    board_json_str = (
                        json.dumps(board_json)
                        if isinstance(board_json, list)
                        else str(board_json)
                    )

                    lmr, lmc = -1, -1
                    if isinstance(last_move, dict) and last_move.get("row") is not None:
                        if int(last_move["row"]) >= 0:
                            lmr = int(last_move["row"])
                            lmc = int(last_move.get("col", -1))

                    conn.execute(
                        """
                        INSERT OR REPLACE INTO positions
                        (hash, result, win_rate, best_move_row, best_move_col, depth_remaining,
                         board_json, current_player, pos_last_move_row, pos_last_move_col, solved_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                        """,
                        (
                            hash_key,
                            result,
                            win_rate,
                            br,
                            bc,
                            depth_remaining,
                            board_json_str,
                            int(player or 1),
                            lmr,
                            lmc,
                        ),
                    )
                    conn.execute(
                        """
                        UPDATE work_queue
                        SET status = 'done', worker_id = COALESCE(worker_id, ?), claimed_at = COALESCE(claimed_at, CURRENT_TIMESTAMP)
                        WHERE hash = ?
                        """,
                        (payload.get("worker_id"), hash_key),
                    )
                    ok_count += 1

                total_solved = conn.execute("SELECT COUNT(*) FROM positions").fetchone()[0]
                conn.execute(
                    """
                    INSERT INTO solver_progress (id, total_solved, total_queued, updated_at)
                    VALUES (1, ?, COALESCE((SELECT total_queued FROM solver_progress WHERE id = 1), 0), CURRENT_TIMESTAMP)
                    ON CONFLICT(id) DO UPDATE SET
                        total_solved = excluded.total_solved,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (total_solved,),
                )
                self._sync_queued_count(conn)
                conn.commit()
                return ok_count, fail_count, errors
            except sqlite3.Error as exc:
                conn.rollback()
                logger.exception("Erreur submit_batch work_queue")
                return ok_count, fail_count, errors + [str(exc)]
            finally:
                conn.close()

    def release(self, worker_id: str, hash_key: str) -> Tuple[bool, Optional[str]]:
        hash_key = str(hash_key or "").strip().lower()
        worker_id = (worker_id or "").strip()
        if not hash_key or not worker_id:
            return False, "hash et worker_id requis"

        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute(
                    """
                    UPDATE work_queue
                    SET status = 'pending', worker_id = NULL, claimed_at = NULL
                    WHERE hash = ? AND status = 'in_progress' AND worker_id = ?
                    """,
                    (hash_key, worker_id),
                )
                self._sync_queued_count(conn)
                conn.commit()
                return True, None
            except sqlite3.Error as exc:
                conn.rollback()
                return False, str(exc)
            finally:
                conn.close()

    def get_stats(self) -> Dict[str, Any]:
        conn = self._get_conn()
        try:
            self._reclaim_stale(conn)
            conn.commit()

            pending = conn.execute(
                "SELECT COUNT(*) FROM work_queue WHERE status = 'pending'"
            ).fetchone()[0]
            in_progress = conn.execute(
                "SELECT COUNT(*) FROM work_queue WHERE status = 'in_progress'"
            ).fetchone()[0]
            done_queue = conn.execute(
                "SELECT COUNT(*) FROM work_queue WHERE status = 'done'"
            ).fetchone()[0]
            solved = conn.execute("SELECT COUNT(*) FROM positions").fetchone()[0]

            cutoff = (datetime.now(timezone.utc) - timedelta(seconds=CLAIM_TIMEOUT_SEC)).strftime(
                "%Y-%m-%d %H:%M:%S"
            )
            workers_rows = conn.execute(
                """
                SELECT worker_id, COUNT(*) AS cnt, MAX(claimed_at) AS last_claim
                FROM work_queue
                WHERE status = 'in_progress'
                  AND worker_id IS NOT NULL
                  AND claimed_at >= ?
                GROUP BY worker_id
                ORDER BY last_claim DESC
                """,
                (cutoff,),
            ).fetchall()

            active_workers = [
                {
                    "worker_id": r["worker_id"],
                    "positions_in_progress": int(r["cnt"]),
                    "last_claim": r["last_claim"],
                }
                for r in workers_rows
            ]

            return {
                "pending": int(pending),
                "in_progress": int(in_progress),
                "done_in_queue": int(done_queue),
                "solved": int(solved),
                "active_workers": active_workers,
                "active_worker_count": len(active_workers),
                "claim_timeout_sec": CLAIM_TIMEOUT_SEC,
            }
        finally:
            conn.close()

    def enqueue_position(
        self,
        conn: sqlite3.Connection,
        *,
        hash_key: str,
        board_json: str,
        player: int,
        last_move: Optional[Tuple[int, int]],
    ) -> bool:
        lmr, lmc = (-1, -1)
        if last_move is not None:
            lmr, lmc = last_move
        try:
            conn.execute(
                """
                INSERT OR IGNORE INTO work_queue
                (hash, board_json, player, last_move_row, last_move_col, status)
                VALUES (?, ?, ?, ?, ?, 'pending')
                """,
                (hash_key, board_json, player, lmr, lmc),
            )
            return conn.total_changes > 0
        except sqlite3.Error:
            return False


_service: Optional[WorkQueueService] = None


def get_work_queue_service() -> WorkQueueService:
    global _service
    if _service is None:
        _service = WorkQueueService()
    return _service
