"""Persistance SQLite des sessions (compatible multi-workers Gunicorn)."""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Optional

from game.game_engine import GameEngine

DEFAULT_DB_PATH = os.environ.get(
    "SESSION_DB_PATH",
    str(Path(__file__).resolve().parent.parent.parent / "data" / "sessions.db"),
)


class SessionStore:
    """Stockage fichier SQLite partagé entre workers."""

    def __init__(self, db_path: str | None = None) -> None:
        self.db_path = db_path or DEFAULT_DB_PATH
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _init_db(self) -> None:
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS sessions (
                        session_id TEXT PRIMARY KEY,
                        mode TEXT NOT NULL,
                        engine_json TEXT NOT NULL,
                        updated_at REAL NOT NULL
                    )
                    """
                )
                conn.commit()

    def save(self, session_id: str, mode: str, engine: GameEngine) -> None:
        payload = json.dumps(engine.to_snapshot())
        now = time.time()
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO sessions (session_id, mode, engine_json, updated_at)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(session_id) DO UPDATE SET
                        mode = excluded.mode,
                        engine_json = excluded.engine_json,
                        updated_at = excluded.updated_at
                    """,
                    (session_id, mode, payload, now),
                )
                conn.commit()

    def load(self, session_id: str) -> Optional[tuple[str, GameEngine]]:
        with self._lock:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT mode, engine_json FROM sessions WHERE session_id = ?",
                    (session_id,),
                ).fetchone()
        if row is None:
            return None
        mode, engine_json = row
        engine = GameEngine.from_snapshot(json.loads(engine_json))
        return mode, engine

    def delete(self, session_id: str) -> bool:
        with self._lock:
            with self._connect() as conn:
                cur = conn.execute(
                    "DELETE FROM sessions WHERE session_id = ?",
                    (session_id,),
                )
                conn.commit()
                return cur.rowcount > 0
