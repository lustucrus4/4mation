"""Gestion des sessions de partie (une partie par identifiant de session)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Dict, Optional

from game.game_engine import GameEngine


@dataclass
class SessionData:
    engine: GameEngine
    mode: str = "standard"  # "standard" | "learning"


class GameSessionManager:
    """Stocke un moteur de jeu et le mode par session."""

    def __init__(self) -> None:
        self._sessions: Dict[str, SessionData] = {}

    def create_session(self, mode: str = "standard") -> str:
        session_id = str(uuid.uuid4())
        engine = GameEngine()
        engine.reset()
        self._sessions[session_id] = SessionData(engine=engine, mode=mode)
        return session_id

    def get_session(self, session_id: str) -> Optional[SessionData]:
        return self._sessions.get(session_id)

    def get_engine(self, session_id: str) -> Optional[GameEngine]:
        session = self._sessions.get(session_id)
        return session.engine if session else None

    def get_mode(self, session_id: str) -> str:
        session = self._sessions.get(session_id)
        return session.mode if session else "standard"

    def set_mode(self, session_id: str, mode: str) -> bool:
        session = self._sessions.get(session_id)
        if session is None:
            return False
        session.mode = mode
        return True

    def reset_session(self, session_id: str, mode: Optional[str] = None) -> bool:
        session = self._sessions.get(session_id)
        if session is None:
            return False
        session.engine.reset()
        if mode is not None:
            session.mode = mode
        return True

    def delete_session(self, session_id: str) -> bool:
        if session_id not in self._sessions:
            return False
        del self._sessions[session_id]
        return True
