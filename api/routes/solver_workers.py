"""Routes API workers solveur distribués (claim / submit / stats)."""

from __future__ import annotations

import hmac
import os
from functools import wraps
from typing import Any, Callable

from flask import Blueprint, jsonify, request

from api.services.work_queue_service import get_work_queue_service

solver_workers_bp = Blueprint("solver_workers", __name__)

WORKER_TOKEN = os.environ.get("SOLVER_WORKER_TOKEN", "").strip()
# Sans jeton, les routes d'écriture restent fermées : un appel anonyme pourrait sinon
# injecter de faux résultats dans la tablebase, que les bots et l'analyse « prouvée »
# lisent ensuite. Seul un poste de développement peut les rouvrir explicitement.
ALLOW_NO_TOKEN = os.environ.get("SOLVER_ALLOW_NO_TOKEN", "").strip().lower() in {
    "1",
    "true",
    "yes",
}


def _require_worker_auth(handler: Callable) -> Callable:
    @wraps(handler)
    def wrapper(*args: Any, **kwargs: Any):
        if not WORKER_TOKEN:
            if ALLOW_NO_TOKEN:
                return handler(*args, **kwargs)
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "Workers solveur désactivés : SOLVER_WORKER_TOKEN non configuré",
                    }
                ),
                503,
            )
        token = request.headers.get("X-Solver-Worker-Token", "").strip()
        if not hmac.compare_digest(token.encode(), WORKER_TOKEN.encode()):
            return jsonify({"success": False, "error": "Token worker invalide"}), 401
        return handler(*args, **kwargs)

    return wrapper


@solver_workers_bp.post("/api/solver/work/claim")
@_require_worker_auth
def claim_work():
    data = request.get_json(silent=True) or {}
    worker_id = str(data.get("worker_id") or "").strip()
    count = data.get("count", 1)

    positions, error = get_work_queue_service().claim(worker_id, count)
    if error:
        status = 429 if "rate limit" in error.lower() else 400
        return jsonify({"success": False, "error": error}), status

    return jsonify(
        {
            "success": True,
            "worker_id": worker_id,
            "count": len(positions),
            "positions": positions,
        }
    )


@solver_workers_bp.post("/api/solver/work/submit")
@_require_worker_auth
def submit_work():
    data = request.get_json(silent=True) or {}
    ok, error = get_work_queue_service().submit(data)
    if not ok:
        return jsonify({"success": False, "error": error}), 400
    return jsonify({"success": True, "hash": data.get("hash")})


@solver_workers_bp.post("/api/solver/work/submit-batch")
@_require_worker_auth
def submit_work_batch():
    data = request.get_json(silent=True) or {}
    worker_id = str(data.get("worker_id") or "").strip()
    results = data.get("results")
    if not isinstance(results, list):
        return jsonify({"success": False, "error": "results (liste) requis"}), 400

    ok_count, fail_count, errors = get_work_queue_service().submit_batch(worker_id, results)
    return jsonify(
        {
            "success": fail_count == 0 or ok_count > 0,
            "submitted": ok_count,
            "failed": fail_count,
            "errors": errors[:20],
        }
    )


@solver_workers_bp.post("/api/solver/work/release")
@_require_worker_auth
def release_work():
    data = request.get_json(silent=True) or {}
    ok, error = get_work_queue_service().release(
        str(data.get("worker_id") or ""),
        str(data.get("hash") or ""),
    )
    if not ok:
        return jsonify({"success": False, "error": error}), 400
    return jsonify({"success": True})


@solver_workers_bp.get("/api/solver/work/stats")
def work_stats():
    stats = get_work_queue_service().get_stats()
    return jsonify({"success": True, **stats})
