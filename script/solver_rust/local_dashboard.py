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
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
WEB_DIR = Path(__file__).resolve().parent / "web"
SCRIPTS_DIR = ROOT / "scripts"
DEFAULT_DB = ROOT / "script" / "solver" / "data" / "tablebase.db"
DEFAULT_PORT = 8765
SOLVER_PROCESS_NAME = "4mation-local.exe"
LOCAL_API_VERSION = 1

# Scripts autorisés — aucune commande arbitraire
ALLOWED_LOCAL_SCRIPTS: dict[str, Path] = {
    "solver": SCRIPTS_DIR / "run_local_solver_rust.bat",
    "stack": SCRIPTS_DIR / "run_local_solver_stack.bat",
}

LOCALHOST_ADDRS = frozenset({"127.0.0.1", "::1"})

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "script"))


def _is_localhost_request(remote_addr: str | None) -> bool:
    return remote_addr in LOCALHOST_ADDRS


def is_solver_running() -> bool:
    """Indique si 4mation-local.exe tourne sur cette machine (Windows)."""
    if sys.platform != "win32":
        return False
    try:
        result = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {SOLVER_PROCESS_NAME}", "/NH"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    output = (result.stdout or "").lower()
    return SOLVER_PROCESS_NAME.lower() in output and "aucune tâche" not in output and "no tasks" not in output


def launch_local_script(script_key: str, window_title: str) -> Path:
    """Lance un .bat whitelisté dans une nouvelle fenêtre cmd /k."""
    bat_path = ALLOWED_LOCAL_SCRIPTS.get(script_key)
    if bat_path is None:
        raise ValueError(f"Script inconnu : {script_key}")
    resolved = bat_path.resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"Script introuvable : {resolved}")
    # Vérifie que le chemin reste sous scripts/
    try:
        resolved.relative_to(SCRIPTS_DIR.resolve())
    except ValueError as exc:
        raise ValueError("Chemin de script non autorisé") from exc

    # CREATE_NEW_CONSOLE : évite start "titre" où Windows interprète le titre comme exe
    if sys.platform != "win32":
        raise OSError("Lancement de scripts locaux réservé à Windows")
    subprocess.Popen(
        ["cmd.exe", "/k", f'title {window_title} & call "{resolved}"'],
        cwd=str(ROOT),
        creationflags=subprocess.CREATE_NEW_CONSOLE,
    )
    return resolved


def stop_solver_process() -> bool:
    """Arrête 4mation-local.exe (Windows). Retourne True si une commande a été envoyée."""
    if sys.platform != "win32" or not is_solver_running():
        return False
    subprocess.run(
        ["taskkill", "/IM", SOLVER_PROCESS_NAME, "/F"],
        capture_output=True,
        timeout=10,
        check=False,
    )
    return True


def create_app(db_path: Path):
    from flask import Flask, jsonify, request, send_from_directory
    from flask_cors import CORS

    from api.services.solver_progress import SolverProgressService
    from api.services.work_queue_service import WorkQueueService

    os.environ["TABLEBASE_DB_PATH"] = str(db_path)

    app = Flask(__name__)
    CORS(app)

    progress = SolverProgressService(db_path=db_path)
    queue = WorkQueueService(db_path=db_path)

    def _require_localhost():
        if not _is_localhost_request(request.remote_addr):
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "Endpoints locaux réservés à 127.0.0.1",
                    }
                ),
                403,
            )
        return None

    def _api_json_error(status: int, error: str):
        if request.path.startswith("/api/"):
            return jsonify({"success": False, "error": error}), status
        return None

    @app.errorhandler(404)
    def not_found(exc):
        payload = _api_json_error(404, f"Route introuvable : {request.path}")
        return payload if payload is not None else exc

    @app.errorhandler(403)
    def forbidden(exc):
        payload = _api_json_error(403, "Accès refusé")
        return payload if payload is not None else exc

    @app.errorhandler(500)
    def internal_error(exc):
        payload = _api_json_error(500, "Erreur interne du serveur")
        return payload if payload is not None else exc

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
                "local_controls": True,
                "local_api_version": LOCAL_API_VERSION,
            }
        )

    @app.get("/api/local/process-status")
    def local_process_status():
        denied = _require_localhost()
        if denied is not None:
            return denied
        running = is_solver_running()
        return jsonify(
            {
                "success": True,
                "running": running,
                "process_name": SOLVER_PROCESS_NAME,
                "status_label": "actif" if running else "arrêté",
            }
        )

    @app.post("/api/local/start-solver")
    def local_start_solver():
        denied = _require_localhost()
        if denied is not None:
            return denied
        if is_solver_running():
            return jsonify(
                {
                    "success": False,
                    "error": "Le solveur est déjà en cours d'exécution.",
                    "running": True,
                }
            ), 409
        try:
            script_path = launch_local_script("solver", "4mation-solver")
        except (ValueError, FileNotFoundError) as exc:
            return jsonify({"success": False, "error": str(exc)}), 400
        return jsonify(
            {
                "success": True,
                "message": "Solveur lancé dans une nouvelle fenêtre.",
                "script": str(script_path),
            }
        )

    @app.post("/api/local/start-stack")
    def local_start_stack():
        denied = _require_localhost()
        if denied is not None:
            return denied
        try:
            script_path = launch_local_script("stack", "4mation-stack")
        except (ValueError, FileNotFoundError) as exc:
            return jsonify({"success": False, "error": str(exc)}), 400
        return jsonify(
            {
                "success": True,
                "message": "Stack locale lancée (dashboard + solveur).",
                "script": str(script_path),
            }
        )

    @app.post("/api/local/stop-solver")
    def local_stop_solver():
        denied = _require_localhost()
        if denied is not None:
            return denied
        if not is_solver_running():
            return jsonify(
                {
                    "success": False,
                    "error": "Aucun solveur en cours d'exécution.",
                    "running": False,
                }
            ), 404
        stop_solver_process()
        return jsonify(
            {
                "success": True,
                "message": "Arrêt du solveur demandé.",
                "running": False,
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
