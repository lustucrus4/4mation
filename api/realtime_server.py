"""Serveur temps réel dédié (Socket.IO) — 1 processus pour le matchmaking in-memory."""

from __future__ import annotations

import argparse

from api.app import app
from api.realtime.extensions import socketio
import api.realtime  # noqa: F401


def main() -> None:
    parser = argparse.ArgumentParser(description="4mation realtime (Socket.IO)")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8098)
    args = parser.parse_args()
    print(f"Realtime 4mation — http://{args.host}:{args.port}")
    socketio.run(app, host=args.host, port=args.port, debug=False, allow_unsafe_werkzeug=True)


if __name__ == "__main__":
    main()
