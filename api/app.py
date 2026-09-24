"""
API Flask pour le jeu 4mation.

Usage local:
    cd 4mation
    set PYTHONPATH=.
    python api/app.py

Production (Gunicorn):
    gunicorn -c api/gunicorn_config.py api.app:app
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Désactiver le chargement automatique du .env Flask
os.environ.setdefault("FLASK_SKIP_DOTENV", "1")

ROOT = Path(__file__).resolve().parent.parent
SCRIPT_DIR = ROOT / "script"

for path in (str(ROOT), str(SCRIPT_DIR)):
    if path not in sys.path:
        sys.path.insert(0, path)

from flask import Flask
from flask_cors import CORS

from api.realtime.extensions import socketio
import api.realtime  # noqa: F401 — enregistre les handlers Socket.IO
from api.routes import account_bp, game_bp, learn_bp, rl_bp, solver_bp, solver_workers_bp
from api.services.postgres import init_schema, is_configured

def _parse_origins(raw: str) -> list[str]:
    return [item.strip().rstrip("/") for item in raw.split(",") if item.strip()]


def _is_local_origin(origin: str) -> bool:
    return origin.startswith("http://localhost:") or origin.startswith("http://127.0.0.1:")


def resolve_allowed_origins() -> list[str]:
    """Whitelist CORS prod-safe : localhost seulement si ALLOW_LOCAL_CORS=true."""
    configured = _parse_origins(
        os.environ.get("CORS_ORIGINS", "https://4mation.lab211.fr")
    )
    allow_local = os.environ.get("ALLOW_LOCAL_CORS", "").strip().lower() in {
        "1",
        "true",
        "yes",
    } or os.environ.get("FLASK_ENV", "").strip().lower() == "development"
    local_defaults = ["http://localhost:5173", "http://127.0.0.1:5173"]
    if allow_local:
        return list(dict.fromkeys([*configured, *local_defaults]))
    return [o for o in configured if not _is_local_origin(o)]


ALLOWED_ORIGINS = resolve_allowed_origins()


def create_app() -> Flask:
    app = Flask(__name__)
    CORS(
        app,
        origins=ALLOWED_ORIGINS,
        supports_credentials=True,
        allow_headers=["Content-Type", "X-Session-Id", "X-Solver-Worker-Token"],
        expose_headers=["X-Session-Id"],
    )
    app.register_blueprint(game_bp)
    app.register_blueprint(account_bp)
    app.register_blueprint(learn_bp)
    app.register_blueprint(rl_bp)
    app.register_blueprint(solver_bp)
    app.register_blueprint(solver_workers_bp)

    if is_configured():
        init_schema()

    socketio.init_app(app)
    return app


app = create_app()


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="API 4mation")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5000)
    args = parser.parse_args()

    print(f"API 4mation — http://{args.host}:{args.port}")
    socketio.run(app, host=args.host, port=args.port, debug=False, allow_unsafe_werkzeug=True)


if __name__ == "__main__":
    main()
