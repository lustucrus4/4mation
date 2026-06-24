"""
Lecture de l'avancement du solveur Phase C (JSON live + SQLite).
"""

from __future__ import annotations

import logging
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from solver.db_schema import connect, init_db
from solver.solver_status import (
    STALE_SECONDS,
    default_status,
    is_solver_active,
    read_status,
)

logger = logging.getLogger(__name__)

DEFAULT_DB = (
    Path(__file__).resolve().parent.parent.parent / "script" / "solver" / "data" / "tablebase.db"
)


class SolverProgressService:
    def __init__(
        self,
        db_path: Optional[str | Path] = None,
        status_path: Optional[str | Path] = None,
    ) -> None:
        env_db = os.environ.get("TABLEBASE_DB_PATH")
        self.db_path = Path(db_path or env_db or DEFAULT_DB)
        env_status = os.environ.get("SOLVER_STATUS_PATH")
        self.status_path = Path(status_path or env_status) if (status_path or env_status) else None

    def _get_conn(self) -> Optional[sqlite3.Connection]:
        if not self.db_path.exists():
            return None
        return connect(self.db_path)

    def get_status(self) -> Dict[str, Any]:
        live = read_status(self.status_path)
        conn = self._get_conn()

        db_solved = 0
        db_queued = 0
        db_phase = "full"
        db_started: Optional[str] = None
        db_updated: Optional[str] = None
        db_running = False

        if conn is not None:
            init_db(self.db_path)
            row = conn.execute(
                """
                SELECT total_solved, total_queued, current_phase, started_at,
                       solver_running, updated_at, total_target, progress_percent
                FROM solver_progress WHERE id = 1
                """
            ).fetchone()
            if row is not None:
                db_solved = int(row["total_solved"] or 0)
                db_queued = int(row["total_queued"] or 0)
                db_phase = str(row["current_phase"] or "full")
                db_started = row["started_at"]
                db_updated = row["updated_at"]
                db_running = bool(row["solver_running"])
            else:
                db_solved = conn.execute("SELECT COUNT(*) FROM positions").fetchone()[0]
            conn.close()

        total_solved = max(int(live.get("total_positions_solved") or 0), db_solved)
        total_target = live.get("total_positions_target")

        total_queued = int(live.get("total_queued") or db_queued)

        progress_unknown = bool(live.get("progress_unknown", total_target is None))
        if live.get("progress_percent") is None or progress_unknown:
            progress = None
        elif total_target and int(total_target) > 0:
            progress = min(100.0, 100.0 * total_solved / int(total_target))
        else:
            progress = None
            progress_unknown = True

        running = is_solver_active(live, STALE_SECONDS) or db_running
        if live.get("last_update") is None and db_updated:
            running = db_running

        started_at = live.get("started_at") or db_started
        last_update = live.get("last_update") or db_updated

        stale_age: Optional[float] = None
        if last_update:
            try:
                ts = datetime.fromisoformat(str(last_update).replace("Z", "+00:00"))
                stale_age = (datetime.now(timezone.utc) - ts).total_seconds()
            except (ValueError, TypeError):
                stale_age = None

        eta = live.get("eta_seconds")
        rate = float(live.get("positions_per_second") or 0.0)
        if (
            eta is None
            and not progress_unknown
            and rate > 0
            and total_target
            and total_solved < int(total_target)
        ):
            eta = int((int(total_target) - total_solved) / rate)

        recent: List[Dict[str, Any]] = list(live.get("recent_positions") or [])
        if not recent:
            recent = self._recent_from_db()

        status_label = "termine"
        if running:
            if stale_age is not None and stale_age > 60:
                status_label = "calcul_long"
            else:
                status_label = "en_cours"
        elif not progress_unknown and total_target and total_solved >= int(total_target):
            status_label = "termine"
        elif total_solved > 0 and not running:
            if stale_age is not None and stale_age <= 90:
                status_label = "rechargement"
            else:
                status_label = "pause"

        progress_value = round(float(progress), 4) if progress is not None else None

        phase_labels = {
            "endgame": "Fin de partie",
            "midgame": "Milieu de partie",
            "opening": "Ouverture",
            "complet": "Complet",
            "full": "Exploration",
        }
        raw_phase = live.get("current_phase") or db_phase
        phase_display = phase_labels.get(str(raw_phase), str(raw_phase))

        return {
            "total_positions_solved": total_solved,
            "total_positions_target": total_target,
            "total_queued": total_queued,
            "progress_percent": progress_value,
            "progress_unknown": progress is None,
            "max_empty": live.get("max_empty"),
            "phase_label": phase_display,
            "positions_per_second": round(rate, 2),
            "eta_seconds": eta,
            "solver_running": running,
            "status": status_label,
            "started_at": started_at,
            "last_update": last_update,
            "current_phase": raw_phase,
            "recent_positions": recent[:20],
            "db_path": str(self.db_path),
            "db_available": self.db_path.exists(),
        }

    def _recent_from_db(self) -> List[Dict[str, Any]]:
        conn = self._get_conn()
        if conn is None:
            return []
        try:
            rows = conn.execute(
                """
                SELECT hash, result, win_rate, best_move_row, best_move_col,
                       board_json, current_player, pos_last_move_row, pos_last_move_col, solved_at
                FROM positions
                WHERE board_json IS NOT NULL
                ORDER BY solved_at DESC
                LIMIT 20
                """
            ).fetchall()
        except sqlite3.Error:
            return []
        finally:
            conn.close()

        out: List[Dict[str, Any]] = []
        import json

        for row in rows:
            try:
                board = json.loads(row["board_json"])
            except (json.JSONDecodeError, TypeError):
                continue
            bm = None
            if row["best_move_row"] is not None and row["best_move_row"] >= 0:
                bm = {"row": row["best_move_row"], "col": row["best_move_col"]}
            lm = None
            if row["pos_last_move_row"] is not None and row["pos_last_move_row"] >= 0:
                lm = {"row": row["pos_last_move_row"], "col": row["pos_last_move_col"]}
            out.append({
                "hash": row["hash"],
                "board": board,
                "current_player": row["current_player"],
                "last_move": lm,
                "best_move": bm,
                "result": row["result"],
                "win_rate": row["win_rate"],
                "solved_at": row["solved_at"],
            })
        return out

    def get_position(self, hash_key: str) -> Optional[Dict[str, Any]]:
        conn = self._get_conn()
        if conn is None:
            return None
        row = conn.execute(
            """
            SELECT hash, result, win_rate, best_move_row, best_move_col,
                   board_json, current_player, pos_last_move_row, pos_last_move_col,
                   depth_remaining, solved_at
            FROM positions WHERE hash = ?
            """,
            (hash_key.lower(),),
        ).fetchone()
        conn.close()
        if row is None:
            live = read_status(self.status_path)
            for rp in live.get("recent_positions") or []:
                if str(rp.get("hash", "")).lower() == hash_key.lower():
                    return {
                        "hash": rp["hash"],
                        "board": rp.get("board"),
                        "current_player": rp.get("current_player"),
                        "last_move": rp.get("last_move"),
                        "best_move": rp.get("best_move"),
                        "result": rp.get("result"),
                        "win_rate": rp.get("win_rate"),
                        "depth_remaining": None,
                        "solved_at": rp.get("solved_at"),
                    }
            return None

        import json

        board = None
        if row["board_json"]:
            try:
                board = json.loads(row["board_json"])
            except (json.JSONDecodeError, TypeError):
                pass
        bm = None
        if row["best_move_row"] is not None and row["best_move_row"] >= 0:
            bm = {"row": row["best_move_row"], "col": row["best_move_col"]}
        lm = None
        if row["pos_last_move_row"] is not None and row["pos_last_move_row"] >= 0:
            lm = {"row": row["pos_last_move_row"], "col": row["pos_last_move_col"]}

        return {
            "hash": row["hash"],
            "board": board,
            "current_player": row["current_player"],
            "last_move": lm,
            "best_move": bm,
            "result": row["result"],
            "win_rate": float(row["win_rate"]),
            "depth_remaining": row["depth_remaining"],
            "solved_at": row["solved_at"],
        }


_service: Optional[SolverProgressService] = None


def get_solver_progress_service() -> SolverProgressService:
    global _service
    if _service is None:
        _service = SolverProgressService()
    return _service
