"""Routes API de suivi du solveur Phase C (lecture seule)."""

from __future__ import annotations

from flask import Blueprint, jsonify

from api.services.solver_progress import get_solver_progress_service

solver_bp = Blueprint("solver", __name__)


@solver_bp.get("/api/solver/status")
def solver_status():
    data = get_solver_progress_service().get_status()
    return jsonify({"success": True, **data})


@solver_bp.get("/api/solver/position/<hash_key>")
def solver_position(hash_key: str):
    pos = get_solver_progress_service().get_position(hash_key)
    if pos is None:
        return jsonify({"success": False, "error": "Position introuvable"}), 404
    return jsonify({"success": True, "position": pos})
