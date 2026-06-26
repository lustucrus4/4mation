"""Routes compte utilisateur : profil, Elo, historique de parties."""

from __future__ import annotations

from flask import Blueprint, Response, g, jsonify, request, stream_with_context

from api.middleware.auth import get_lab211_user, require_auth
from api.services.user_repository import _serialize_game_detail, _serialize_game_summary, user_repo

account_bp = Blueprint("account", __name__)


@account_bp.route("/api/me", methods=["GET"])
@require_auth
def api_me():
    """Profil + Elo + 10 dernières parties."""
    user = get_lab211_user()
    assert user is not None
    return jsonify({"success": True, **user_repo.profile_payload(user)})


@account_bp.route("/api/me/games", methods=["GET"])
@require_auth
def api_me_games():
    """Liste paginée des parties enregistrées."""
    limit = int(request.args.get("limit", 20))
    offset = int(request.args.get("offset", 0))
    user_id = g.db_user_id
    games = user_repo.list_games(user_id, limit=limit, offset=offset)

    return jsonify({
        "success": True,
        "games": [_serialize_game_summary(g) for g in games],
        "limit": max(1, min(limit, 100)),
        "offset": max(0, offset),
    })


@account_bp.route("/api/me/games/<game_id>", methods=["GET"])
@require_auth
def api_me_game_detail(game_id: str):
    """Détail d'une partie (coups rejouables)."""
    row = user_repo.get_game(g.db_user_id, game_id)
    if row is None:
        return jsonify({"success": False, "error": "Partie introuvable"}), 404
    return jsonify({"success": True, "game": _serialize_game_detail(row)})


@account_bp.route("/api/me/games/<game_id>/review", methods=["GET"])
@require_auth
def api_me_game_review(game_id: str):
    """Game Review : précision, classification des coups, courbe d'évaluation."""
    import json

    from api.services.game_review import build_game_review, iter_build_game_review

    row = user_repo.get_game(g.db_user_id, game_id)
    if row is None:
        return jsonify({"success": False, "error": "Partie introuvable"}), 404

    history = row.get("history")
    if isinstance(history, str):
        history = json.loads(history)
    if not history:
        return jsonify({"success": False, "error": "Partie sans historique"}), 400

    human_color = int(row.get("human_color") or 1)
    game_payload = _serialize_game_detail(row)

    if request.args.get("stream") == "1":

        def generate():
            yield json.dumps({"type": "start", "game": game_payload}, ensure_ascii=False) + "\n"
            for event in iter_build_game_review(history, human_color=human_color):
                if event.get("type") == "complete":
                    payload = {
                        "type": "complete",
                        "success": True,
                        "game_id": str(row["id"]),
                        "game": game_payload,
                        "review": event["review"],
                    }
                else:
                    payload = event
                yield json.dumps(payload, ensure_ascii=False) + "\n"

        return Response(
            stream_with_context(generate()),
            mimetype="application/x-ndjson",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    review = build_game_review(history, human_color=human_color)

    return jsonify({
        "success": True,
        "game_id": str(row["id"]),
        "game": game_payload,
        "review": review,
    })
