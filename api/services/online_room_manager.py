"""Salles de parties en ligne (2 joueurs, moteur autoritaire)."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from game.game_engine import GameEngine

from api.services.game_state import serialize_board_state


@dataclass
class RoomPlayer:
    user_id: int
    sid: str
    color: int  # 1 rouge, 2 bleu
    display_name: str
    elo: int


@dataclass
class OnlineRoom:
    room_id: str
    engine: GameEngine
    players: Dict[int, RoomPlayer]  # color -> player
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    finished: bool = False
    winner: Optional[int] = None
    resign_by: Optional[int] = None
    end_reason: Optional[str] = None

    def player_by_sid(self, sid: str) -> Optional[RoomPlayer]:
        for p in self.players.values():
            if p.sid == sid:
                return p
        return None

    def player_by_user(self, user_id: int) -> Optional[RoomPlayer]:
        for p in self.players.values():
            if p.user_id == user_id:
                return p
        return None

    def opponent_of(self, player: RoomPlayer) -> RoomPlayer:
        other_color = 2 if player.color == 1 else 1
        return self.players[other_color]

    def serialize_for(self, color: int) -> Dict[str, Any]:
        state = serialize_board_state(self.engine, mode="online")
        state["your_color"] = color
        state["room_id"] = self.room_id
        opp = self.players[2 if color == 1 else 1]
        you = self.players[color]
        state["you"] = {
            "display_name": you.display_name,
            "elo": you.elo,
            "color": you.color,
        }
        state["opponent"] = {
            "display_name": opp.display_name,
            "elo": opp.elo,
            "color": opp.color,
        }
        return state


class OnlineRoomManager:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._rooms: Dict[str, OnlineRoom] = {}
        self._user_room: Dict[int, str] = {}
        self._sid_room: Dict[str, str] = {}

    def create_room(
        self,
        room_id: str,
        white: RoomPlayer,
        black: RoomPlayer,
        *,
        starting_player: int = 1,
    ) -> OnlineRoom:
        engine = GameEngine()
        engine.reset()
        if starting_player in (1, 2):
            engine.get_state().current_player = starting_player
        room = OnlineRoom(
            room_id=room_id,
            engine=engine,
            players={1: white, 2: black},
        )
        with self._lock:
            self._rooms[room_id] = room
            self._user_room[white.user_id] = room_id
            self._user_room[black.user_id] = room_id
            self._sid_room[white.sid] = room_id
            self._sid_room[black.sid] = room_id
        return room

    def get_room(self, room_id: str) -> Optional[OnlineRoom]:
        with self._lock:
            return self._rooms.get(room_id)

    def get_room_for_sid(self, sid: str) -> Optional[OnlineRoom]:
        with self._lock:
            rid = self._sid_room.get(sid)
            return self._rooms.get(rid) if rid else None

    def get_room_for_user(self, user_id: int) -> Optional[OnlineRoom]:
        with self._lock:
            rid = self._user_room.get(user_id)
            return self._rooms.get(rid) if rid else None

    def update_sid(self, user_id: int, new_sid: str) -> Optional[OnlineRoom]:
        """Reconnexion : rattache un nouveau socket à la room en cours."""
        with self._lock:
            rid = self._user_room.get(user_id)
            if not rid:
                return None
            room = self._rooms.get(rid)
            if room is None or room.finished:
                return None
            player = room.player_by_user(user_id)
            if player is None:
                return None
            old_sid = player.sid
            player.sid = new_sid
            self._sid_room.pop(old_sid, None)
            self._sid_room[new_sid] = rid
            return room

    def play_move(
        self, room_id: str, sid: str, row: int, col: int
    ) -> Tuple[Optional[OnlineRoom], Optional[str]]:
        with self._lock:
            room = self._rooms.get(room_id)
            if room is None:
                return None, "Partie introuvable"
            if room.finished:
                return None, "Partie terminée"
            player = room.player_by_sid(sid)
            if player is None:
                return None, "Vous n'êtes pas dans cette partie"
            state = room.engine.get_state()
            if int(state.current_player) != player.color:
                return None, "Ce n'est pas votre tour"
            _, ok, winner = room.engine.step((int(row), int(col)))
            if not ok:
                return None, "Coup illégal"
            if room.engine.is_terminal():
                room.finished = True
                room.winner = int(winner) if winner is not None else None
            return room, None

    def resign(self, room_id: str, sid: str) -> Tuple[Optional[OnlineRoom], Optional[str]]:
        with self._lock:
            room = self._rooms.get(room_id)
            if room is None:
                return None, "Partie introuvable"
            if room.finished:
                return None, "Partie terminée"
            player = room.player_by_sid(sid)
            if player is None:
                return None, "Vous n'êtes pas dans cette partie"
            room.finished = True
            room.resign_by = player.color
            room.winner = 2 if player.color == 1 else 1
            return room, None

    def close_room(self, room_id: str) -> None:
        with self._lock:
            room = self._rooms.pop(room_id, None)
            if room is None:
                return
            for p in room.players.values():
                self._user_room.pop(p.user_id, None)
                self._sid_room.pop(p.sid, None)

    def history(self, room: OnlineRoom) -> List[Dict[str, Any]]:
        return room.engine.get_move_history()


room_manager = OnlineRoomManager()
