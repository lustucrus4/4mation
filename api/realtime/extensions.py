"""Instance Flask-SocketIO partagée (évite les imports circulaires)."""

from __future__ import annotations

import os

from flask_socketio import SocketIO


def _socketio_origins() -> list[str]:
    configured = [
        item.strip().rstrip("/")
        for item in os.environ.get("CORS_ORIGINS", "https://4mation.lab211.fr").split(",")
        if item.strip()
    ]
    allow_local = os.environ.get("ALLOW_LOCAL_CORS", "").strip().lower() in {
        "1",
        "true",
        "yes",
    } or os.environ.get("FLASK_ENV", "").strip().lower() == "development"
    local_defaults = ["http://localhost:5173", "http://127.0.0.1:5173"]
    if allow_local:
        return list(dict.fromkeys([*configured, *local_defaults]))
    return [
        o
        for o in configured
        if not (o.startswith("http://localhost:") or o.startswith("http://127.0.0.1:"))
    ]


socketio = SocketIO(
    cors_allowed_origins=_socketio_origins(),
    async_mode="threading",
    manage_session=False,
    logger=False,
    engineio_logger=False,
)
