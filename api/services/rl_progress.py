"""Lecture de l'avancement entraînement RL Rust (status.json + metrics)."""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

DEFAULT_DATA_DIR = (
    Path(__file__).resolve().parent.parent.parent / "script" / "rl_rust" / "data"
)


class RlProgressService:
    def __init__(self, data_dir: Optional[str | Path] = None) -> None:
        env = os.environ.get("RL_DATA_DIR")
        self.data_dir = Path(data_dir or env or DEFAULT_DATA_DIR)
        self.status_path = self.data_dir / "status.json"
        self.metrics_path = self.data_dir / "metrics.jsonl"
        self.db_path = self.data_dir / "metrics.db"

    def get_status(self) -> Dict[str, Any]:
        if not self.status_path.exists():
            return {
                "running": False,
                "step": 0,
                "total_games": 0,
                "message": "Aucun entraînement RL détecté",
                "data_dir": str(self.data_dir),
            }
        try:
            data = json.loads(self.status_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {"running": False, "message": "status.json illisible"}
        data["data_dir"] = str(self.data_dir)
        return data

    def get_metrics(self, limit: int = 500) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        if self.db_path.exists():
            try:
                conn = sqlite3.connect(self.db_path)
                conn.row_factory = sqlite3.Row
                cur = conn.execute(
                    """
                    SELECT ts, step, event, games, self_play_win_rate,
                           eval_vs_level5, policy_version, games_per_sec, payload
                    FROM metrics
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (limit,),
                )
                for r in cur.fetchall():
                    rows.append(dict(r))
                conn.close()
                rows.reverse()
                if rows:
                    return rows
            except sqlite3.Error:
                pass

        if not self.metrics_path.exists():
            return []
        try:
            lines = self.metrics_path.read_text(encoding="utf-8").strip().splitlines()
        except OSError:
            return []
        for line in lines[-limit:]:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return rows


_service: Optional[RlProgressService] = None


def get_rl_progress_service() -> RlProgressService:
    global _service
    if _service is None:
        _service = RlProgressService()
    return _service
