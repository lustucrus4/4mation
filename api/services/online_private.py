"""Salles privées (code d'invitation 6 caractères)."""

from __future__ import annotations

import random
import string
import threading
from dataclasses import dataclass
from typing import Dict, Optional

from api.services.online_matchmaking import QueuePlayer

_CODE_CHARS = string.ascii_uppercase + string.digits


@dataclass
class PrivateLobby:
    code: str
    host: QueuePlayer


class PrivateRoomRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._lobbies: Dict[str, PrivateLobby] = {}

    def create(self, host: QueuePlayer) -> str:
        with self._lock:
            self.remove_by_sid(host.sid)
            for _ in range(30):
                code = "".join(random.choices(_CODE_CHARS, k=6))
                if code not in self._lobbies:
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
        with self._lock:
            to_drop = [c for c, lob in self._lobbies.items() if lob.host.sid == sid]
            for c in to_drop:
                del self._lobbies[c]

    def remove_code(self, code: str) -> None:
        with self._lock:
            self._lobbies.pop(code.upper().strip(), None)


private_rooms = PrivateRoomRegistry()
