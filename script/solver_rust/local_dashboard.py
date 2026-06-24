#!/usr/bin/env python3
"""
Serveur HTTP local pour visualiser l'avancement du solveur Rust.

Expose les mêmes endpoints que l'API prod :
  GET /api/solver/status
  GET /api/solver/work/stats

Sert la page statique script/solver_rust/web/ (auto-refresh 2,5 s).
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
WEB_DIR = Path(__file__).resolve().parent / "web"
DEFAULT_DB = ROOT / "script" / "solver" / "data" / "tablebase.db"
DEFAULT_PORT = 8765

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "script"))


def create_app(db_path: Path):
    from flask import Flask, jsonify, send_from_directory
    from flask_cors import CORS

    from api.services.solver_progress import SolverProgressService
    from api.services.work_queue_service import WorkQueueService

    os.environ["TABLEBASE_DB_PATH"] = str(db_path)

    app = Flask(__name__)
    CORS(app)

    progress = SolverProgressService(db_path=db_path)
    queue = WorkQueueService(db_path=db_path)

    @app.get("/")
    def index():
        return send_from_directory(WEB_DIR, "index.html")

    @app.get("/style.css")
    def style():
        return send_from_directory(WEB_DIR, "style.css")

    @app.get("/solver.js")
    def solver_js():
        return send_from_directory(WEB_DIR, "solver.js")

    @app.get("/api/solver/status")
    def solver_status():
        data = progress.get_status()
        return jsonify({"success": True, **data})

    @app.get("/api/solver/work/stats")
    def work_stats():
        stats = queue.get_stats()
        return jsonify({"success": True, **stats})

    @app.get("/health")
    def health():
        return jsonify(
            {
                "ok": True,
                "db_path": str(db_path),
                "db_exists": db_path.exists(),
            }
        )

    return app


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Dashboard local solveur 4mation (lecture SQLite)"
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DB,
        help=f"Chemin tablebase.db (défaut : {DEFAULT_DB})",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("SOLVER_DASHBOARD_PORT", DEFAULT_PORT)),
        help=f"Port HTTP (défaut : {DEFAULT_PORT})",
    )
    parser.add_argument(
        "--host",
        default=os.environ.get("SOLVER_DASHBOARD_HOST", "127.0.0.1"),
        help="Interface d'écoute (défaut : 127.0.0.1)",
    )
    args = parser.parse_args()

    if not WEB_DIR.is_dir():
        print(f"Dossier web introuvable : {WEB_DIR}", file=sys.stderr)
        return 1

    app = create_app(args.db.resolve())
    url = f"http://{args.host}:{args.port}/"
    print("=" * 50)
    print("  4mation — Dashboard solveur LOCAL")
    print("=" * 50)
    print(f"URL      : {url}")
    print(f"Base     : {args.db}")
    print(f"Existe   : {'oui' if args.db.exists() else 'non — lancez seed_initial_tablebase.py'}")
    print("Ctrl+C pour arrêter.")
    print()
    app.run(host=args.host, port=args.port, debug=False, threaded=True, load_dotenv=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
