"""Salles privées (code d'invitation 6 caractères) et sessions multijoueur."""

from __future__ import annotations

import random
import string
import threading
from dataclasses import dataclass, field
from typing import Dict, Optional, Set, Tuple

from api.services.online_matchmaking import QueuePlayer

_CODE_CHARS = string.ascii_uppercase + string.digits


@dataclass
class PrivateLobby:
    code: str
    host: QueuePlayer


@dataclass
class PrivateSession:
    """Salle privée active : deux joueurs, plusieurs parties possibles."""

    code: str
    players: Dict[int, QueuePlayer]  # user_id -> joueur
    rematch_ready: Set[int] = field(default_factory=set)
    games_started: int = 0
    red_user_id: Optional[int] = None

    def opponent_of(self, user_id: int) -> Optional[QueuePlayer]:
        for uid, p in self.players.items():
            if uid != user_id:
                return p
        return None

    def update_sid(self, user_id: int, new_sid: str) -> None:
        player = self.players.get(user_id)
        if player is not None:
            player.sid = new_sid


class PrivateRoomRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._lobbies: Dict[str, PrivateLobby] = {}
        self._sessions: Dict[str, PrivateSession] = {}
        self._user_session: Dict[int, str] = {}

    def _remove_by_sid_unlocked(self, sid: str) -> None:
        to_drop = [c for c, lob in self._lobbies.items() if lob.host.sid == sid]
        for c in to_drop:
            del self._lobbies[c]

    def create(self, host: QueuePlayer) -> str:
        with self._lock:
            self._remove_by_sid_unlocked(host.sid)
            self._leave_user_unlocked(host.user_id)
            for _ in range(30):
                code = "".join(random.choices(_CODE_CHARS, k=6))
                if code not in self._lobbies and code not in self._sessions:
                    self._lobbies[code] = PrivateLobby(code=code, host=host)
                    return code
            raise RuntimeError("Impossible de générer un code")

    def pop(self, code: str) -> Optional[PrivateLobby]:
        with self._lock:
            return self._lobbies.pop(code.upper().strip(), None)

    def get(self, code: str) -> Optional[PrivateLobby]:
        with self._lock:
            return self._lobbies.get(code.upper().strip())

    def remove_by_sid(self, sid: str) -> None:
        """Retire les lobbies en attente dont l'hôte correspond au socket."""
        with self._lock:
            self._remove_by_sid_unlocked(sid)

    def remove_code(self, code: str) -> None:
        with self._lock:
            self._lobbies.pop(code.upper().strip(), None)

    def open_session(self, host: QueuePlayer, guest: QueuePlayer, code: str) -> PrivateSession:
        with self._lock:
            session = PrivateSession(
                code=code,
                players={host.user_id: host, guest.user_id: guest},
            )
            self._sessions[code] = session
            self._user_session[host.user_id] = code
            self._user_session[guest.user_id] = code
            return session

    def get_session(self, code: str) -> Optional[PrivateSession]:
        with self._lock:
            return self._sessions.get(code.upper().strip())

    def get_session_for_user(self, user_id: int) -> Optional[PrivateSession]:
        with self._lock:
            code = self._user_session.get(user_id)
            if not code:
                return None
            return self._sessions.get(code)

    def user_in_private(self, user_id: int) -> bool:
        with self._lock:
            if user_id in self._user_session:
                return True
            return any(lob.host.user_id == user_id for lob in self._lobbies.values())

    def update_sid(self, user_id: int, new_sid: str) -> Optional[PrivateSession]:
        with self._lock:
            code = self._user_session.get(user_id)
            if not code:
                return None
            session = self._sessions.get(code)
            if session is None:
                return None
            session.update_sid(user_id, new_sid)
            return session

    def mark_rematch_ready(self, user_id: int) -> Tuple[Optional[PrivateSession], bool]:
        """Marque le joueur prêt ; retourne (session, les_deux_pret)."""
        with self._lock:
            code = self._user_session.get(user_id)
            if not code:
                return None, False
            session = self._sessions.get(code)
            if session is None:
                return None, False
            session.rematch_ready.add(user_id)
            both = len(session.rematch_ready) >= 2
            return session, both

    def clear_rematch_ready(self, code: str) -> None:
        with self._lock:
            session = self._sessions.get(code.upper().strip())
            if session is not None:
                session.rematch_ready.clear()

    def prepare_private_match(
        self, session: PrivateSession, p1: QueuePlayer, p2: QueuePlayer
    ) -> Tuple[QueuePlayer, QueuePlayer, int]:
        """Couleurs fixes ; alterne seulement le premier joueur (rouge, bleu, rouge…)."""
        with self._lock:
            if session.red_user_id is None:
                red = p1 if p1.elo >= p2.elo else p2
                session.red_user_id = red.user_id
            else:
                red = p1 if p1.user_id == session.red_user_id else p2
            blue = p2 if red.user_id == p1.user_id else p1
            starting_player = 1 if session.games_started % 2 == 0 else 2
            session.games_started += 1
            return red, blue, starting_player

    def _leave_user_unlocked(self, user_id: int) -> Optional[PrivateSession]:
        code = self._user_session.pop(user_id, None)
        if not code:
            return None
        session = self._sessions.get(code)
        if session is None:
            return None
        session.players.pop(user_id, None)
        session.rematch_ready.discard(user_id)
        if len(session.players) < 2:
            for uid in list(session.players.keys()):
                self._user_session.pop(uid, None)
            self._sessions.pop(code, None)
        return session

    def leave_user(self, user_id: int) -> Tuple[Optional[PrivateSession], Optional[QueuePlayer]]:
        """Retire un joueur ; retourne (session restante ou dissoute, adversaire)."""
        with self._lock:
            code = self._user_session.get(user_id)
            if not code:
                return None, None
            session = self._sessions.get(code)
            if session is None:
                self._user_session.pop(user_id, None)
                return None, None
            opponent = session.opponent_of(user_id)
            self._leave_user_unlocked(user_id)
            return session, opponent

    def dissolve_session(self, code: str) -> None:
        with self._lock:
            session = self._sessions.pop(code.upper().strip(), None)
            if session is None:
                return
            for uid in session.players:
                self._user_session.pop(uid, None)


private_rooms = PrivateRoomRegistry()
