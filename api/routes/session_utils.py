"""Utilitaires de résolution de session HTTP."""

from __future__ import annotations

from flask import Request, make_response


SESSION_HEADER = "X-Session-Id"
SESSION_COOKIE = "4mation_session"


def get_session_id(request: Request) -> str | None:
    """Lit l'identifiant de session depuis l'en-tête ou le cookie."""
    header_value = request.headers.get(SESSION_HEADER)
    if header_value:
        return header_value.strip()
    cookie_value = request.cookies.get(SESSION_COOKIE)
    if cookie_value:
        return cookie_value.strip()
    return None


def attach_session_cookie(response, session_id: str):
    """Associe le cookie de session à une réponse Flask (cross-origin API)."""
    response.set_cookie(
        SESSION_COOKIE,
        session_id,
        httponly=True,
        samesite="None",
        secure=True,
        max_age=60 * 60 * 24 * 7,
    )
    return response


def json_with_session(payload, session_id: str, status: int = 200):
    """Réponse JSON avec cookie de session."""
    from flask import jsonify

    response = make_response(jsonify(payload), status)
    attach_session_cookie(response, session_id)
    response.headers[SESSION_HEADER] = session_id
    return response
