"""Routes API suivi entraînement RL Rust."""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from api.services.rl_progress import get_rl_progress_service

rl_bp = Blueprint("rl", __name__)


@rl_bp.get("/api/rl/status")
def rl_status():
    data = get_rl_progress_service().get_status()
    return jsonify({"success": True, **data})


@rl_bp.get("/api/rl/metrics")
def rl_metrics():
    limit = request.args.get("limit", 500, type=int)
    limit = max(1, min(limit, 5000))
    rows = get_rl_progress_service().get_metrics(limit=limit)
    return jsonify({"success": True, "metrics": rows, "count": len(rows)})
