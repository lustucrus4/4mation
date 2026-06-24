"""
Schéma SQLite partagé pour tablebase fin de partie et livre d'ouverture.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS positions (
    hash TEXT PRIMARY KEY,
    result TEXT NOT NULL,
    win_rate REAL NOT NULL,
    best_move_row INTEGER,
    best_move_col INTEGER,
    depth_remaining INTEGER,
    solved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS opening_book (
    hash TEXT PRIMARY KEY,
    result TEXT NOT NULL,
    win_rate REAL NOT NULL,
    best_move_row INTEGER,
    best_move_col INTEGER,
    ply INTEGER NOT NULL,
    solved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS solver_progress (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    total_queued INTEGER DEFAULT 0,
    total_solved INTEGER DEFAULT 0,
    last_hash TEXT,
    started_at TIMESTAMP,
    current_phase TEXT DEFAULT 'full',
    solver_running INTEGER DEFAULT 0,
    total_target INTEGER,
    progress_percent REAL DEFAULT 0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS work_queue (
    hash TEXT PRIMARY KEY,
    board_json TEXT NOT NULL,
    player INTEGER NOT NULL,
    last_move_row INTEGER,
    last_move_col INTEGER,
    status TEXT NOT NULL DEFAULT 'pending',
    worker_id TEXT,
    claimed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_positions_depth ON positions(depth_remaining);
CREATE INDEX IF NOT EXISTS idx_opening_ply ON opening_book(ply);
CREATE INDEX IF NOT EXISTS idx_work_queue_status ON work_queue(status);
CREATE INDEX IF NOT EXISTS idx_work_queue_claimed ON work_queue(claimed_at);
"""


def connect(db_path: str | Path) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=10000")
    return conn


_MIGRATIONS = [
    "ALTER TABLE positions ADD COLUMN board_json TEXT",
    "ALTER TABLE positions ADD COLUMN current_player INTEGER",
    "ALTER TABLE positions ADD COLUMN pos_last_move_row INTEGER",
    "ALTER TABLE positions ADD COLUMN pos_last_move_col INTEGER",
    "ALTER TABLE solver_progress ADD COLUMN started_at TIMESTAMP",
    "ALTER TABLE solver_progress ADD COLUMN current_phase TEXT DEFAULT 'full'",
    "ALTER TABLE solver_progress ADD COLUMN solver_running INTEGER DEFAULT 0",
    "ALTER TABLE solver_progress ADD COLUMN total_target INTEGER",
    "ALTER TABLE solver_progress ADD COLUMN progress_percent REAL DEFAULT 0",
]


def _migrate(conn: sqlite3.Connection) -> None:
    for sql in _MIGRATIONS:
        try:
            conn.execute(sql)
        except sqlite3.OperationalError:
            pass


def init_db(db_path: str | Path) -> sqlite3.Connection:
    conn = connect(db_path)
    conn.executescript(SCHEMA_SQL)
    _migrate(conn)
    conn.commit()
    return conn
