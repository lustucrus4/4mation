"""Instance Flask-SocketIO partagée (évite les imports circulaires)."""

from __future__ import annotations

from flask_socketio import SocketIO

socketio = SocketIO(
    cors_allowed_origins=[
        "https://4mation.lab211.fr",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    async_mode="threading",
    manage_session=False,
    logger=False,
    engineio_logger=False,
)
