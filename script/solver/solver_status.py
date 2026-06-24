"""
État live du solveur Phase C — fichier JSON partagé API / script.

Chemin par défaut : script/solver/data/solver_status.json
Sur VPS : /app/data/solver_status.json (variable SOLVER_STATUS_PATH).
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

DEFAULT_STATUS_PATH = Path(__file__).resolve().parent / "data" / "solver_status.json"
RECENT_LIMIT = 20
STALE_SECONDS = 120


def _status_path() -> Path:
    env = os.environ.get("SOLVER_STATUS_PATH")
    return Path(env) if env else DEFAULT_STATUS_PATH


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def board_to_list(board: np.ndarray) -> List[List[int]]:
    return [[int(board[r, c]) for c in range(board.shape[1])] for r in range(board.shape[0])]


def default_status() -> Dict[str, Any]:
    return {
        "solver_running": False,
        "started_at": None,
        "last_update": None,
        "current_phase": "full",
        "total_positions_solved": 0,
        "total_positions_target": None,
        "total_queued": 0,
        "progress_percent": 0.0,
        "positions_per_second": 0.0,
        "eta_seconds": None,
        "recent_positions": [],
    }


def read_status(path: Optional[Path] = None) -> Dict[str, Any]:
    p = path or _status_path()
    if not p.exists():
        return default_status()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        base = default_status()
        base.update(data)
        return base
    except (json.JSONDecodeError, OSError):
        return default_status()


def write_status(data: Dict[str, Any], path: Optional[Path] = None) -> None:
    p = path or _status_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, ensure_ascii=False, indent=2)
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(payload)
        os.replace(tmp, p)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def append_recent(
    recent: List[Dict[str, Any]],
    entry: Dict[str, Any],
    limit: int = RECENT_LIMIT,
) -> List[Dict[str, Any]]:
    updated = [entry] + [r for r in recent if r.get("hash") != entry.get("hash")]
    return updated[:limit]


def position_entry(
    *,
    hash_key: str,
    board: np.ndarray,
    current_player: int,
    last_move: Optional[tuple[int, int]],
    best_move: Optional[tuple[int, int]],
    result: str,
    win_rate: float,
) -> Dict[str, Any]:
    lm = None
    if last_move is not None:
        lm = {"row": last_move[0], "col": last_move[1]}
    bm = None
    if best_move is not None:
        bm = {"row": best_move[0], "col": best_move[1]}
    return {
        "hash": hash_key,
        "board": board_to_list(board),
        "current_player": current_player,
        "last_move": lm,
        "best_move": bm,
        "result": result,
        "win_rate": win_rate,
        "solved_at": _now_iso(),
    }


def is_solver_active(status: Dict[str, Any], stale_seconds: int = STALE_SECONDS) -> bool:
    if not status.get("solver_running"):
        return False
    last = status.get("last_update")
    if not last:
        return False
    try:
        ts = datetime.fromisoformat(str(last).replace("Z", "+00:00"))
        age = (datetime.now(timezone.utc) - ts).total_seconds()
        return age <= stale_seconds
    except (ValueError, TypeError):
        return False
