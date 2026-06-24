"""Gestion des sessions de partie (une partie par identifiant de session)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Dict, Optional

from game.game_engine import GameEngine

from .session_store import SessionStore


@dataclass
class SessionData:
    engine: GameEngine
    mode: str = "standard"  # "standard" | "learning"


class GameSessionManager:
    """Stocke un moteur de jeu et le mode par session (mémoire + SQLite)."""

    def __init__(self, store: SessionStore | None = None) -> None:
        self._sessions: Dict[str, SessionData] = {}
        self._store = store or SessionStore()

    def create_session(self, mode: str = "standard") -> str:
        session_id = str(uuid.uuid4())
        engine = GameEngine()
        engine.reset()
        self._sessions[session_id] = SessionData(engine=engine, mode=mode)
        self._store.save(session_id, mode, engine)
        return session_id

    def get_session(self, session_id: str) -> Optional[SessionData]:
        loaded = self._store.load(session_id)
        if loaded is None:
            self._sessions.pop(session_id, None)
            return None

        mode, engine = loaded
        session = SessionData(engine=engine, mode=mode)
        self._sessions[session_id] = session
        return session

    def get_engine(self, session_id: str) -> Optional[GameEngine]:
        session = self.get_session(session_id)
        return session.engine if session else None

    def get_mode(self, session_id: str) -> str:
        session = self.get_session(session_id)
        return session.mode if session else "standard"

    def set_mode(self, session_id: str, mode: str) -> bool:
        session = self.get_session(session_id)
        if session is None:
            return False
        session.mode = mode
        self.persist(session_id)
        return True

    def reset_session(self, session_id: str, mode: Optional[str] = None) -> bool:
        session = self.get_session(session_id)
        if session is None:
            return False
        session.engine.reset()
        if mode is not None:
            session.mode = mode
        self.persist(session_id)
        return True

    def persist(self, session_id: str) -> bool:
        session = self.get_session(session_id)
        if session is None:
            return False
        self._store.save(session_id, session.mode, session.engine)
        return True

    def delete_session(self, session_id: str) -> bool:
        self._sessions.pop(session_id, None)
        return self._store.delete(session_id)
