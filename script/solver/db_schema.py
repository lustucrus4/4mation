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
    exact INTEGER DEFAULT 0,
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
    board_json TEXT,
    board_blob BLOB,
    player INTEGER NOT NULL,
    last_move_row INTEGER,
    last_move_col INTEGER,
    status TEXT NOT NULL DEFAULT 'pending',
    worker_id TEXT,
    claimed_at TIMESTAMP,
    empty_cells INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_positions_depth ON positions(depth_remaining);
CREATE INDEX IF NOT EXISTS idx_positions_solved_at ON positions(solved_at);
CREATE INDEX IF NOT EXISTS idx_opening_ply ON opening_book(ply);
CREATE INDEX IF NOT EXISTS idx_work_queue_status ON work_queue(status);
CREATE INDEX IF NOT EXISTS idx_work_queue_claimed ON work_queue(claimed_at);
"""


def connect(db_path: str | Path) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # check_same_thread=False : l'API Flask (serveur multi-thread / plusieurs workers)
    # réutilise une connexion en cache entre threads pour les lectures. En WAL + lecture
    # seule c'est sûr (sqlite3 sérialise en interne). Sans effet pour les scripts solveur
    # mono-thread.
    conn = sqlite3.connect(str(path), check_same_thread=False)
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
    # Compaction : plateau stocké en BLOB (2 bits/cellule) au lieu de board_json TEXT.
    # La colonne board_json est conservée (nullable) pour rétrocompat ; le solveur Rust
    # écrit board_blob et libère board_json. L'API live n'utilise ni l'un ni l'autre
    # (lookup par hash uniquement), donc ces colonnes sont sans impact côté jeu.
    "ALTER TABLE positions ADD COLUMN board_blob BLOB",
    "ALTER TABLE positions ADD COLUMN empty_cells INTEGER",
    "ALTER TABLE work_queue ADD COLUMN board_blob BLOB",
    "ALTER TABLE work_queue ADD COLUMN empty_cells INTEGER",
    "CREATE INDEX IF NOT EXISTS idx_positions_solved_at ON positions(solved_at)",
    # Livre d'ouverture : distinction honnête entre valeur PROUVÉE (exact=1, toutes
    # les feuilles atteintes sont dans la tablebase / terminales) et ESTIMÉE (exact=0,
    # évaluation Minimax limitée en profondeur). Permet la convergence vers le parfait.
    "ALTER TABLE opening_book ADD COLUMN exact INTEGER DEFAULT 0",
    "ALTER TABLE opening_book ADD COLUMN board_json TEXT",
    "ALTER TABLE opening_book ADD COLUMN current_player INTEGER",
    "ALTER TABLE opening_book ADD COLUMN pos_last_move_row INTEGER",
    "ALTER TABLE opening_book ADD COLUMN pos_last_move_col INTEGER",
]


def board_to_blob(board) -> bytes:
    """Compacte un plateau 7x7 (valeurs 0/1/2) en 13 octets (2 bits/cellule)."""
    out = bytearray(13)
    for r in range(7):
        for c in range(7):
            idx = r * 7 + c
            out[idx // 4] |= (int(board[r][c]) & 0b11) << ((idx % 4) * 2)
    return bytes(out)


def board_from_blob(blob: bytes):
    """Reconstruit un plateau 7x7 depuis un BLOB compacté (repli zéros si trop court)."""
    board = [[0] * 7 for _ in range(7)]
    for r in range(7):
        for c in range(7):
            idx = r * 7 + c
            byte = idx // 4
            if byte < len(blob):
                board[r][c] = (blob[byte] >> ((idx % 4) * 2)) & 0b11
    return board


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
