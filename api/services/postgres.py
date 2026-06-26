"""Connexion PostgreSQL et initialisation du schéma utilisateur (phase 2)."""

from __future__ import annotations

import logging
import os
import threading
from contextlib import contextmanager
from typing import Any, Generator, Optional

logger = logging.getLogger(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()

_pool: Any = None
_pool_lock = threading.Lock()
_schema_ready = False


def is_configured() -> bool:
    return bool(DATABASE_URL)


def _get_pool():
    global _pool
    if _pool is not None:
        return _pool
    with _pool_lock:
        if _pool is not None:
            return _pool
        if not is_configured():
            return None
        import psycopg
        from psycopg.rows import dict_row
        from psycopg_pool import ConnectionPool

        _pool = ConnectionPool(
            conninfo=DATABASE_URL,
            min_size=1,
            max_size=8,
            kwargs={"row_factory": dict_row},
            open=True,
        )
        logger.info("Pool PostgreSQL initialisé")
        return _pool


@contextmanager
def db_conn() -> Generator[Any, None, None]:
    pool = _get_pool()
    if pool is None:
        raise RuntimeError("DATABASE_URL non configurée")
    with pool.connection() as conn:
        yield conn


def init_schema() -> bool:
    """Crée les tables si absentes. Retourne False si Postgres indisponible."""
    global _schema_ready
    if _schema_ready:
        return True
    if not is_configured():
        logger.warning("DATABASE_URL absente — comptes/parties désactivés")
        return False
    try:
        with db_conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    lab211_id TEXT NOT NULL UNIQUE,
                    username TEXT,
                    display_name TEXT,
                    email TEXT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );

                CREATE TABLE IF NOT EXISTS ratings (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    mode TEXT NOT NULL DEFAULT 'bot',
                    elo INTEGER NOT NULL DEFAULT 1200,
                    games_played INTEGER NOT NULL DEFAULT 0,
                    wins INTEGER NOT NULL DEFAULT 0,
                    losses INTEGER NOT NULL DEFAULT 0,
                    draws INTEGER NOT NULL DEFAULT 0,
                    UNIQUE (user_id, mode)
                );

                CREATE TABLE IF NOT EXISTS games (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    game_mode TEXT NOT NULL,
                    bot_id TEXT,
                    bot_level INTEGER,
                    human_color INTEGER NOT NULL DEFAULT 1,
                    result TEXT NOT NULL,
                    winner INTEGER,
                    move_count INTEGER NOT NULL DEFAULT 0,
                    history JSONB NOT NULL DEFAULT '[]'::jsonb,
                    elo_before INTEGER,
                    elo_after INTEGER,
                    elo_delta INTEGER,
                    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    finished_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );

                CREATE INDEX IF NOT EXISTS idx_games_user_finished
                    ON games (user_id, finished_at DESC);
                """
            )
            conn.execute(
                """
                ALTER TABLE games ADD COLUMN IF NOT EXISTS opponent_user_id INTEGER
                    REFERENCES users(id) ON DELETE SET NULL;
                ALTER TABLE games ADD COLUMN IF NOT EXISTS opponent_elo INTEGER;
                ALTER TABLE games ADD COLUMN IF NOT EXISTS opponent_label TEXT;
                """
            )
            conn.commit()
        _schema_ready = True
        logger.info("Schéma PostgreSQL prêt")
        return True
    except Exception:
        logger.exception("Échec initialisation schéma PostgreSQL")
        return False
