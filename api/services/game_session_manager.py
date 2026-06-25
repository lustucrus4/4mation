"""Gestion des sessions de partie (une partie par identifiant de session)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from game.game_engine import GameEngine

from .session_store import SessionStore


@dataclass
class SessionData:
    engine: GameEngine
    mode: str = "standard"  # "standard" | "learning"
    meta: Dict[str, Any] = field(default_factory=dict)


class GameSessionManager:
    """Stocke un moteur de jeu, le mode et métadonnées par session."""

    def __init__(self, store: SessionStore | None = None) -> None:
        self._sessions: Dict[str, SessionData] = {}
        self._store = store or SessionStore()

    @staticmethod
    def _fresh_meta(extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        meta: Dict[str, Any] = {
            "started_at": datetime.now(timezone.utc).isoformat(),
            "human_color": 1,
            "game_saved": False,
        }
        if extra:
            meta.update(extra)
        return meta

    def create_session(
        self,
        mode: str = "standard",
        meta: Optional[Dict[str, Any]] = None,
    ) -> str:
        session_id = str(uuid.uuid4())
        engine = GameEngine()
        engine.reset()
        session_meta = self._fresh_meta(meta)
        self._sessions[session_id] = SessionData(
            engine=engine, mode=mode, meta=session_meta
        )
        self._store.save(session_id, mode, engine, session_meta)
        return session_id

    def get_session(self, session_id: str) -> Optional[SessionData]:
        loaded = self._store.load(session_id)
        if loaded is None:
            self._sessions.pop(session_id, None)
            return None

        mode, engine, meta = loaded
        session = SessionData(engine=engine, mode=mode, meta=meta or {})
        self._sessions[session_id] = session
        return session

    def get_engine(self, session_id: str) -> Optional[GameEngine]:
        session = self.get_session(session_id)
        return session.engine if session else None

    def get_mode(self, session_id: str) -> str:
        session = self.get_session(session_id)
        return session.mode if session else "standard"

    def get_meta(self, session_id: str) -> Dict[str, Any]:
        session = self.get_session(session_id)
        return dict(session.meta) if session else {}

    def update_meta(self, session_id: str, **kwargs: Any) -> bool:
        session = self.get_session(session_id)
        if session is None:
            return False
        session.meta.update(kwargs)
        self.persist(session_id)
        return True

    def set_mode(self, session_id: str, mode: str) -> bool:
        session = self.get_session(session_id)
        if session is None:
            return False
        session.mode = mode
        self.persist(session_id)
        return True

    def reset_session(
        self,
        session_id: str,
        mode: Optional[str] = None,
        meta: Optional[Dict[str, Any]] = None,
    ) -> bool:
        session = self.get_session(session_id)
        if session is None:
            return False
        session.engine.reset()
        if mode is not None:
            session.mode = mode
        session.meta = self._fresh_meta(meta)
        self.persist(session_id)
        return True

    def persist(self, session_id: str) -> bool:
        session = self._sessions.get(session_id)
        if session is None:
            return False
        self._store.save(session_id, session.mode, session.engine, session.meta)
        return True

    def delete_session(self, session_id: str) -> bool:
        self._sessions.pop(session_id, None)
        return self._store.delete(session_id)
