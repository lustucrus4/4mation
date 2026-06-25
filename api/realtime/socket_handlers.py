"""Handlers Socket.IO — multijoueur en ligne (Phase 5)."""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, Optional, Tuple

from flask import request
from flask_socketio import disconnect, emit, join_room

from api.realtime.extensions import socketio
from api.services.lab211_auth import resolve_user
from api.services.online_guest import (
    GUEST_DEFAULT_ELO,
    is_guest_id,
    next_guest_id,
    sanitize_guest_name,
)
from api.services.online_matchmaking import MatchPair, QueuePlayer, matchmaking_queue
from api.services.online_private import private_rooms
from api.services.online_room_manager import OnlineRoom, RoomPlayer, room_manager
from api.services.postgres import is_configured
from api.services.user_repository import user_repo

logger = logging.getLogger(__name__)

# sid -> (user_id, display_name, elo, is_guest)
_connected: Dict[str, Tuple[int, str, int, bool]] = {}


def _resolve_connect(auth: Optional[Dict[str, Any]]) -> Tuple[int, str, int, bool]:
    """Compte Lab211 si connecté, sinon invité."""
    user = resolve_user(request)
    if user is not None and is_configured() and user_repo.ensure_ready():
        user_id = user_repo.upsert_user(user)
        rating = user_repo.get_or_create_rating(user_id, "online")
        name = user.display_name or user.username or "Joueur"
        return user_id, name, int(rating["elo"]), False

    guest_name = sanitize_guest_name((auth or {}).get("guest_name"))
    return next_guest_id(), guest_name, GUEST_DEFAULT_ELO, True


def _finish_room(room: OnlineRoom) -> None:
    history = room_manager.history(room)
    move_count = len(history)
    winner = room.winner
    started_at = room.started_at

    p1 = room.players[1]
    p2 = room.players[2]
    saved: Dict[int, Dict[str, Any]] = {}

    both_registered = not is_guest_id(p1.user_id) and not is_guest_id(p2.user_id)
    if both_registered:
        try:
            saved = user_repo.save_online_game(
                red_user_id=p1.user_id,
                blue_user_id=p2.user_id,
                winner=winner,
                move_count=move_count,
                history=history,
                started_at=started_at,
                red_elo=p1.elo,
                blue_elo=p2.elo,
                resign_by=room.resign_by,
            )
        except Exception:
            logger.exception("Échec sauvegarde partie online room=%s", room.room_id)

    for _color, player in room.players.items():
        opp = room.opponent_of(player)
        stats = saved.get(player.user_id, {})
        emit_payload = {
            "room_id": room.room_id,
            "winner": winner,
            "your_color": player.color,
            "resign_by": room.resign_by,
            "elo_delta": stats.get("elo_delta"),
            "elo_after": stats.get("elo_after"),
            "is_guest": is_guest_id(player.user_id),
            "opponent": {"display_name": opp.display_name, "elo": opp.elo},
        }
        socketio.emit("online:game_over", emit_payload, to=player.sid)


@socketio.on("connect")
def on_connect(auth: Optional[Dict[str, Any]] = None) -> None:
    user_id, name, elo, is_guest = _resolve_connect(auth)
    _connected[request.sid] = (user_id, name, elo, is_guest)

    if not is_guest:
        room = room_manager.update_sid(user_id, request.sid)
        if room and not room.finished:
            join_room(room.room_id)
            player = room.player_by_user(user_id)
            if player:
                emit("online:state", room.serialize_for(player.color))
                return

    emit(
        "online:connected",
        {
            "user_id": user_id,
            "display_name": name,
            "elo": elo,
            "is_guest": is_guest,
        },
    )


@socketio.on("disconnect")
def on_disconnect() -> None:
    info = _connected.pop(request.sid, None)
    matchmaking_queue.leave_sid(request.sid)
    private_rooms.remove_by_sid(request.sid)
    if info is None:
        return
    user_id, _, _, _ = info
    room = room_manager.get_room_for_user(user_id)
    if room and not room.finished:
        player = room.player_by_user(user_id)
        if player:
            room.finished = True
            room.resign_by = player.color
            room.winner = 2 if player.color == 1 else 1
            _finish_room(room)
            room_manager.close_room(room.room_id)


@socketio.on("online:queue_join")
def on_queue_join() -> None:
    auth = _connected.get(request.sid)
    if auth is None:
        emit("online:error", {"message": "Non connecté au serveur"})
        return

    user_id, name, elo, _is_guest = auth
    if room_manager.get_room_for_user(user_id):
        emit("online:error", {"message": "Partie déjà en cours"})
        return

    matchmaking_queue.leave_user(user_id)
    pair = matchmaking_queue.join(
        QueuePlayer(user_id=user_id, sid=request.sid, elo=elo, display_name=name)
    )

    if pair is None:
        emit("online:queued", {"position": matchmaking_queue.queue_size()})
        return

    _start_match(pair)


@socketio.on("online:queue_leave")
def on_queue_leave() -> None:
    matchmaking_queue.leave_sid(request.sid)
    private_rooms.remove_by_sid(request.sid)
    emit("online:queue_left", {})


def _player_from_auth() -> Optional[QueuePlayer]:
    auth = _connected.get(request.sid)
    if auth is None:
        return None
    user_id, name, elo, _ = auth
    return QueuePlayer(user_id=user_id, sid=request.sid, elo=elo, display_name=name)


@socketio.on("online:private_create")
def on_private_create() -> None:
    player = _player_from_auth()
    if player is None:
        emit("online:error", {"message": "Non connecté au serveur"})
        return
    if room_manager.get_room_for_user(player.user_id):
        emit("online:error", {"message": "Partie déjà en cours"})
        return
    matchmaking_queue.leave_user(player.user_id)
    try:
        code = private_rooms.create(player)
    except RuntimeError:
        emit("online:error", {"message": "Impossible de créer une salle"})
        return
    emit("online:private_created", {"code": code})


@socketio.on("online:private_cancel")
def on_private_cancel(data: Dict[str, Any]) -> None:
    code = str(data.get("code") or "")
    lobby = private_rooms.get(code)
    if lobby and lobby.host.sid == request.sid:
        private_rooms.remove_code(code)
    emit("online:private_cancelled", {})


@socketio.on("online:private_join")
def on_private_join(data: Dict[str, Any]) -> None:
    player = _player_from_auth()
    if player is None:
        emit("online:error", {"message": "Non connecté au serveur"})
        return
    if room_manager.get_room_for_user(player.user_id):
        emit("online:error", {"message": "Partie déjà en cours"})
        return

    code = str(data.get("code") or "").upper().strip()
    if len(code) != 6:
        emit("online:error", {"message": "Code invalide (6 caractères)"})
        return

    lobby = private_rooms.pop(code)
    if lobby is None:
        emit("online:error", {"message": "Salle introuvable ou expirée"})
        return
    if lobby.host.sid == player.sid or lobby.host.user_id == player.user_id:
        emit("online:error", {"message": "Vous ne pouvez pas rejoindre votre propre salle"})
        return

    matchmaking_queue.leave_user(player.user_id)
    room_id = uuid.uuid4().hex[:12]
    if lobby.host.elo >= player.elo:
        white, black = lobby.host, player
    else:
        white, black = player, lobby.host
    _start_match(MatchPair(room_id=room_id, white=white, black=black))


def _start_match(pair: MatchPair) -> None:
    white = RoomPlayer(
        user_id=pair.white.user_id,
        sid=pair.white.sid,
        color=1,
        display_name=pair.white.display_name,
        elo=pair.white.elo,
    )
    black = RoomPlayer(
        user_id=pair.black.user_id,
        sid=pair.black.sid,
        color=2,
        display_name=pair.black.display_name,
        elo=pair.black.elo,
    )
    room = room_manager.create_room(pair.room_id, white, black)

    for player in (white, black):
        join_room(pair.room_id, sid=player.sid)
        socketio.emit(
            "online:match_found",
            {
                "room_id": pair.room_id,
                "your_color": player.color,
                "opponent": {
                    "display_name": room.opponent_of(player).display_name,
                    "elo": room.opponent_of(player).elo,
                },
            },
            to=player.sid,
        )
        socketio.emit("online:state", room.serialize_for(player.color), to=player.sid)


@socketio.on("online:play_move")
def on_play_move(data: Dict[str, Any]) -> None:
    room_id = str(data.get("room_id") or "")
    row = data.get("row")
    col = data.get("col")
    if row is None or col is None:
        emit("online:error", {"message": "Coup manquant"})
        return

    room, err = room_manager.play_move(room_id, request.sid, int(row), int(col))
    if err:
        emit("online:error", {"message": err})
        return
    assert room is not None

    for color in (1, 2):
        socketio.emit("online:state", room.serialize_for(color), to=room.players[color].sid)

    if room.finished:
        _finish_room(room)
        room_manager.close_room(room.room_id)


@socketio.on("online:resign")
def on_resign(data: Dict[str, Any]) -> None:
    room_id = str(data.get("room_id") or "")
    room, err = room_manager.resign(room_id, request.sid)
    if err:
        emit("online:error", {"message": err})
        return
    assert room is not None
    _finish_room(room)
    room_manager.close_room(room.room_id)
