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


def _private_session_for_room(room: OnlineRoom) -> Optional[Any]:
    for player in room.players.values():
        session = private_rooms.get_session_for_user(player.user_id)
        if session is not None:
            return session
    return None


def _notify_private_opponent_left(opponent: QueuePlayer, *, reason: str) -> None:
    socketio.emit(
        "online:private_opponent_left",
        {"reason": reason},
        to=opponent.sid,
    )


def _dissolve_private_session(room: OnlineRoom, *, leaver_user_id: int, reason: str) -> None:
    session = _private_session_for_room(room)
    if session is None:
        return
    opponent = session.opponent_of(leaver_user_id)
    private_rooms.dissolve_session(session.code)
    if opponent is not None and opponent.user_id != leaver_user_id:
        _notify_private_opponent_left(opponent, reason=reason)


def _forfeit_player(room: OnlineRoom, player: RoomPlayer, *, end_reason: str) -> None:
    """Déclare le joueur perdant (abandon ou déconnexion)."""
    if room.finished:
        return
    room.finished = True
    room.resign_by = player.color
    room.winner = 2 if player.color == 1 else 1
    room.end_reason = end_reason
    if end_reason == "disconnect":
        _dissolve_private_session(room, leaver_user_id=player.user_id, reason="disconnect")
    _finish_room(room)
    room_manager.close_room(room.room_id)


def _finish_room(room: OnlineRoom) -> None:
    history = room_manager.history(room)
    move_count = len(history)
    winner = room.winner
    started_at = room.started_at

    p1 = room.players[1]
    p2 = room.players[2]
    saved: Dict[int, Dict[str, Any]] = {}

    if user_repo.ensure_ready():
        for _color, player in room.players.items():
            if is_guest_id(player.user_id):
                continue
            opp = room.opponent_of(player)
            try:
                row = user_repo.save_online_game_for_user(
                    player.user_id,
                    human_color=player.color,
                    opponent_user_id=opp.user_id if not is_guest_id(opp.user_id) else None,
                    opponent_label=opp.display_name if is_guest_id(opp.user_id) else None,
                    opponent_elo=opp.elo,
                    winner=winner,
                    move_count=move_count,
                    history=history,
                    started_at=started_at,
                )
                if row:
                    saved[player.user_id] = row
            except Exception:
                logger.exception("Échec sauvegarde partie online room=%s user=%s", room.room_id, player.user_id)

    session = _private_session_for_room(room)
    for _color, player in room.players.items():
        opp = room.opponent_of(player)
        stats = saved.get(player.user_id, {})
        emit_payload = {
            "room_id": room.room_id,
            "winner": winner,
            "your_color": player.color,
            "resign_by": room.resign_by,
            "end_reason": room.end_reason,
            "elo_delta": stats.get("elo_delta"),
            "elo_after": stats.get("elo_after"),
            "saved_game_id": stats.get("game_id"),
            "is_guest": is_guest_id(player.user_id),
            "opponent": {"display_name": opp.display_name, "elo": opp.elo},
        }
        if session is not None:
            emit_payload["is_private"] = True
            emit_payload["private_code"] = session.code
            private_rooms.clear_rematch_ready(session.code)
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

    session = private_rooms.update_sid(user_id, request.sid)
    if session is not None and not room_manager.get_room_for_user(user_id):
        opp = session.opponent_of(user_id)
        emit(
            "online:private_session_restored",
            {
                "code": session.code,
                "opponent": {
                    "display_name": opp.display_name if opp else "?",
                    "elo": opp.elo if opp else 0,
                },
                "rematch_ready": user_id in session.rematch_ready,
                "opponent_rematch_ready": bool(
                    opp and opp.user_id in session.rematch_ready
                ),
            },
        )
        emit(
            "online:connected",
            {
                "user_id": user_id,
                "display_name": name,
                "elo": elo,
                "is_guest": is_guest,
            },
        )
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
    sid = request.sid
    info = _connected.pop(sid, None)
    matchmaking_queue.leave_sid(sid)
    private_rooms.remove_by_sid(sid)

    room = room_manager.get_room_for_sid(sid)
    if room and not room.finished:
        player = room.player_by_sid(sid)
        if player:
            _forfeit_player(room, player, end_reason="disconnect")
            return

    if info is None:
        return
    user_id, _, _, _ = info
    room = room_manager.get_room_for_user(user_id)
    if room and not room.finished:
        player = room.player_by_user(user_id)
        if player:
            _forfeit_player(room, player, end_reason="disconnect")
            return

    session, opponent = private_rooms.leave_user(user_id)
    if opponent is not None:
        _notify_private_opponent_left(opponent, reason="disconnect")


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
    if private_rooms.user_in_private(user_id):
        emit("online:error", {"message": "Quittez la salle privée avant de lancer une recherche"})
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


def _player_from_user_id(user_id: int) -> Optional[QueuePlayer]:
    for sid, info in _connected.items():
        if info[0] == user_id:
            _, name, elo, _ = info
            return QueuePlayer(user_id=user_id, sid=sid, elo=elo, display_name=name)
    return None


def _refresh_session_players(session) -> list[QueuePlayer]:
    """Met à jour sid / Elo depuis les connexions actives."""
    refreshed: list[QueuePlayer] = []
    for uid, stored in session.players.items():
        live = _player_from_user_id(uid)
        player = live if live is not None else stored
        session.players[uid] = player
        refreshed.append(player)
    return refreshed


@socketio.on("online:private_create")
def on_private_create() -> None:
    player = _player_from_auth()
    if player is None:
        emit("online:error", {"message": "Non connecté au serveur"})
        return
    if room_manager.get_room_for_user(player.user_id):
        emit("online:error", {"message": "Partie déjà en cours"})
        return
    if private_rooms.user_in_private(player.user_id):
        emit("online:error", {"message": "Quittez la salle privée avant d'en créer une nouvelle"})
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
    if private_rooms.user_in_private(player.user_id):
        emit("online:error", {"message": "Quittez votre salle privée actuelle avant d'en rejoindre une autre"})
        return

    code = str(data.get("code") or "").upper().strip()
    if len(code) != 6:
        emit("online:error", {"message": "Code invalide (6 caractères)"})
        return

    lobby = private_rooms.get(code)
    if lobby is None:
        emit("online:error", {"message": "Salle introuvable ou expirée"})
        return
    if lobby.host.sid == player.sid or lobby.host.user_id == player.user_id:
        emit("online:error", {"message": "Vous ne pouvez pas rejoindre votre propre salle"})
        return

    lobby = private_rooms.pop(code)
    assert lobby is not None

    matchmaking_queue.leave_user(player.user_id)
    session = private_rooms.open_session(lobby.host, player, code)
    _start_private_match(session)


def _start_private_match(session) -> None:
    players = _refresh_session_players(session)
    if len(players) != 2:
        return
    p1, p2 = players
    red, blue, starting_player = private_rooms.prepare_private_match(session, p1, p2)
    room_id = uuid.uuid4().hex[:12]
    _start_match(
        MatchPair(room_id=room_id, white=red, black=blue),
        private_code=session.code,
        starting_player=starting_player,
    )


def _start_match(
    pair: MatchPair,
    *,
    private_code: Optional[str] = None,
    starting_player: int = 1,
) -> None:
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
    room = room_manager.create_room(
        pair.room_id, white, black, starting_player=starting_player
    )

    for player in (white, black):
        join_room(pair.room_id, sid=player.sid)
        payload: Dict[str, Any] = {
            "room_id": pair.room_id,
            "your_color": player.color,
            "opponent": {
                "display_name": room.opponent_of(player).display_name,
                "elo": room.opponent_of(player).elo,
            },
        }
        if private_code:
            payload["private_code"] = private_code
        socketio.emit("online:match_found", payload, to=player.sid)
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
    player = room.player_by_sid(request.sid)
    room.end_reason = "resign"
    _finish_room(room)
    room_manager.close_room(room.room_id)
    if player and data.get("leave_private"):
        session, opponent = private_rooms.leave_user(player.user_id)
        if opponent is not None:
            _notify_private_opponent_left(opponent, reason="leave")
        emit("online:private_left", {})


@socketio.on("online:private_rematch")
def on_private_rematch() -> None:
    player = _player_from_auth()
    if player is None:
        emit("online:error", {"message": "Non connecté au serveur"})
        return
    if room_manager.get_room_for_user(player.user_id):
        emit("online:error", {"message": "Partie déjà en cours"})
        return

    session, both_ready = private_rooms.mark_rematch_ready(player.user_id)
    if session is None:
        emit("online:error", {"message": "Pas dans une salle privée"})
        return

    opponent = session.opponent_of(player.user_id)
    if opponent is None:
        emit("online:error", {"message": "Adversaire absent"})
        return

    if not both_ready:
        emit("online:private_rematch_waiting", {})
        socketio.emit(
            "online:private_rematch_opponent_ready",
            {"opponent_name": player.display_name},
            to=opponent.sid,
        )
        return

    private_rooms.clear_rematch_ready(session.code)
    _start_private_match(session)


@socketio.on("online:private_leave")
def on_private_leave(data: Optional[Dict[str, Any]] = None) -> None:
    player = _player_from_auth()
    if player is None:
        emit("online:error", {"message": "Non connecté au serveur"})
        return

    room = room_manager.get_room_for_user(player.user_id)
    if room and not room.finished:
        room, err = room_manager.resign(room.room_id, request.sid)
        if err:
            emit("online:error", {"message": err})
            return
        assert room is not None
        room.end_reason = "resign"
        _dissolve_private_session(room, leaver_user_id=player.user_id, reason="leave")
        _finish_room(room)
        room_manager.close_room(room.room_id)
        emit("online:private_left", {})
        return

    session, opponent = private_rooms.leave_user(player.user_id)
    if session is None and opponent is None:
        code = str((data or {}).get("code") or "")
        lobby = private_rooms.get(code)
        if lobby and lobby.host.sid == player.sid:
            private_rooms.remove_code(code)
            emit("online:private_cancelled", {})
            return
        emit("online:error", {"message": "Pas dans une salle privée"})
        return

    if opponent is not None:
        _notify_private_opponent_left(opponent, reason="leave")
    emit("online:private_left", {})
