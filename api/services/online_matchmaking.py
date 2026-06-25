"""File d'attente matchmaking (mémoire, thread-safe)."""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


MAX_ELO_GAP = 350


@dataclass
class QueuePlayer:
    user_id: int
    sid: str
    elo: int
    display_name: str


@dataclass
class MatchPair:
    room_id: str
    white: QueuePlayer
    black: QueuePlayer


class MatchmakingQueue:
    """Appariement par proximité d'Elo (MVP in-memory, un worker)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._waiting: List[QueuePlayer] = []
        self._sid_to_user: Dict[str, int] = {}

    def _leave_sid_unlocked(self, sid: str) -> None:
        uid = self._sid_to_user.pop(sid, None)
        self._waiting = [p for p in self._waiting if p.sid != sid]
        if uid is not None:
            self._waiting = [p for p in self._waiting if p.user_id != uid]

    def join(self, player: QueuePlayer) -> Optional[MatchPair]:
        with self._lock:
            self._leave_sid_unlocked(player.sid)
            self._waiting.append(player)
            self._sid_to_user[player.sid] = player.user_id
            return self._try_pair_unlocked()

    def leave_sid(self, sid: str) -> None:
        with self._lock:
            self._leave_sid_unlocked(sid)

    def leave_user(self, user_id: int) -> None:
        with self._lock:
            self._waiting = [p for p in self._waiting if p.user_id != user_id]
            self._sid_to_user = {
                sid: uid for sid, uid in self._sid_to_user.items() if uid != user_id
            }

    def queue_size(self) -> int:
        with self._lock:
            return len(self._waiting)

    def _try_pair_unlocked(self) -> Optional[MatchPair]:
        if len(self._waiting) < 2:
            return None

        best: Optional[Tuple[int, int, int]] = None  # gap, i, j
        for i in range(len(self._waiting)):
            for j in range(i + 1, len(self._waiting)):
                gap = abs(self._waiting[i].elo - self._waiting[j].elo)
                if gap <= MAX_ELO_GAP and (best is None or gap < best[0]):
                    best = (gap, i, j)

        # Secours : apparier les deux premiers si personne ne correspond au gap Elo
        if best is None:
            best = (9999, 0, 1)

        _, i, j = best
        a = self._waiting.pop(j)
        b = self._waiting.pop(i)
        self._sid_to_user.pop(a.sid, None)
        self._sid_to_user.pop(b.sid, None)

        room_id = uuid.uuid4().hex[:12]
        if a.elo >= b.elo:
            white, black = a, b
        else:
            white, black = b, a
        return MatchPair(room_id=room_id, white=white, black=black)


matchmaking_queue = MatchmakingQueue()
