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


def _discover_data_dir(explicit: Optional[str | Path] = None) -> Path:
    """Trouve le dossier `data/` actif (évite le doublon script/rl_rust/script/rl_rust/data)."""
    if explicit:
        p = Path(explicit)
        if (p / "status.json").exists() or (p / "metrics.jsonl").exists():
            return p

    rl_root = DEFAULT_DATA_DIR.parent
    candidates: list[Path] = [
        DEFAULT_DATA_DIR,
        rl_root / "script" / "rl_rust" / "data",
    ]
    env = os.environ.get("RL_DATA_DIR")
    if env:
        candidates.insert(0, Path(env))

    best: Optional[Path] = None
    best_mtime = -1.0
    for d in candidates:
        status = d / "status.json"
        if not status.exists():
            continue
        try:
            mtime = status.stat().st_mtime
        except OSError:
            continue
        if mtime > best_mtime:
            best_mtime = mtime
            best = d

    if best is not None:
        return best
    return Path(explicit) if explicit else DEFAULT_DATA_DIR


class RlProgressService:
    def __init__(self, data_dir: Optional[str | Path] = None) -> None:
        self.data_dir = _discover_data_dir(data_dir or os.environ.get("RL_DATA_DIR"))
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
            return {"running": False, "message": "status.json illisible", "data_dir": str(self.data_dir)}
        data["data_dir"] = str(self.data_dir)
        return data

    def get_metrics(self, limit: int = 500) -> List[Dict[str, Any]]:
        """Lit metrics.jsonl en priorité (schéma complet, live). SQLite = fallback."""
        rows = self._read_metrics_jsonl(limit)
        if rows:
            return rows
        return self._read_metrics_sqlite(limit)

    def _normalize_metric_row(self, row: Dict[str, Any]) -> Dict[str, Any]:
        """Unifie les noms de champs SQLite / JSONL pour le dashboard."""
        if "self_play_win_rate_p1" not in row and "self_play_win_rate" in row:
            row["self_play_win_rate_p1"] = row["self_play_win_rate"]
        payload = row.get("payload")
        if isinstance(payload, str) and payload.strip():
            try:
                extra = json.loads(payload)
                for key in (
                    "self_play_win_rate_p1",
                    "eval_vs_level3",
                    "eval_vs_level5",
                    "eval_games",
                    "avg_moves",
                    "message",
                ):
                    if key not in row and key in extra:
                        row[key] = extra[key]
            except json.JSONDecodeError:
                pass
        return row

    def _read_metrics_jsonl(self, limit: int) -> List[Dict[str, Any]]:
        if not self.metrics_path.exists():
            return []
        try:
            lines = self.metrics_path.read_text(encoding="utf-8").strip().splitlines()
        except OSError:
            return []
        rows: List[Dict[str, Any]] = []
        for line in lines[-limit:]:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return rows

    def _read_metrics_sqlite(self, limit: int) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        if not self.db_path.exists():
            return rows
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
                rows.append(self._normalize_metric_row(dict(r)))
            conn.close()
            rows.reverse()
        except sqlite3.Error:
            pass
        return rows


_service: Optional[RlProgressService] = None


def get_rl_progress_service() -> RlProgressService:
    global _service
    if _service is None:
        _service = RlProgressService()
    else:
        _service.data_dir = _discover_data_dir(os.environ.get("RL_DATA_DIR"))
        _service.status_path = _service.data_dir / "status.json"
        _service.metrics_path = _service.data_dir / "metrics.jsonl"
        _service.db_path = _service.data_dir / "metrics.db"
    return _service
