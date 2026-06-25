"""Routes section Apprendre : ouvertures, puzzles, leçons."""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from api.services.opening_explorer import explore_opening
from api.services.puzzle_service import check_puzzle_solution, random_puzzle

learn_bp = Blueprint("learn", __name__)

LESSONS = [
    {
        "id": "intro",
        "title": "Les règles du 4mation",
        "level": "débutant",
        "duration_min": 3,
        "sections": [
            {
                "heading": "Objectif",
                "body": "Aligner 4 pions adjacents (horizontal, vertical ou diagonal) sur un plateau 7×7.",
            },
            {
                "heading": "Connexité",
                "body": "Chaque pion posé doit toucher au moins un pion déjà sur le plateau (8 directions). "
                "Au premier coup, toute case est libre.",
            },
            {
                "heading": "Stratégie",
                "body": "Contrôler le centre, créer des menaces doubles et bloquer les alignements adverses.",
            },
        ],
    },
    {
        "id": "ouvertures",
        "title": "Principes d'ouverture",
        "level": "intermédiaire",
        "duration_min": 5,
        "sections": [
            {
                "heading": "Centre d'abord",
                "body": "Les cases centrales (3,3) et voisines offrent le plus de continuations — "
                "consultez l'explorateur pour comparer les taux de victoire.",
            },
            {
                "heading": "Restez connecté",
                "body": "Un pion isolé est illégal : planifiez toujours la case suivante en gardant la connexité.",
            },
        ],
    },
]


@learn_bp.route("/api/learn/openings/explore", methods=["POST"])
def api_openings_explore():
    """Explore une ligne d'ouverture à partir d'une séquence de coups."""
    data = request.get_json(silent=True) or {}
    raw_moves = data.get("moves") or []
    moves = []
    for m in raw_moves:
        if isinstance(m, dict):
            moves.append((int(m["row"]), int(m["col"])))
        elif isinstance(m, (list, tuple)) and len(m) == 2:
            moves.append((int(m[0]), int(m[1])))
    return jsonify({"success": True, **explore_opening(moves)})


@learn_bp.route("/api/learn/puzzles/random", methods=["GET"])
def api_puzzle_random():
    """Puzzle tactique aléatoire."""
    puzzle = random_puzzle()
    if puzzle is None:
        return jsonify({"success": False, "error": "Aucun puzzle trouvé"}), 503
    return jsonify({"success": True, "puzzle": puzzle})


@learn_bp.route("/api/learn/puzzles/check", methods=["POST"])
def api_puzzle_check():
    """Vérifie la solution d'un puzzle."""
    data = request.get_json(silent=True) or {}
    history = data.get("history") or []
    player = int(data.get("player_to_move", 1))
    move = data.get("move") or {}
    if "row" not in move or "col" not in move:
        return jsonify({"success": False, "error": "Coup manquant"}), 400
    result = check_puzzle_solution(history, player, int(move["row"]), int(move["col"]))
    return jsonify({"success": True, **result})


@learn_bp.route("/api/learn/lessons", methods=["GET"])
def api_lessons():
    """Liste des leçons disponibles."""
    return jsonify({"success": True, "lessons": LESSONS})


@learn_bp.route("/api/learn/lessons/<lesson_id>", methods=["GET"])
def api_lesson_detail(lesson_id: str):
    """Contenu d'une leçon."""
    for lesson in LESSONS:
        if lesson["id"] == lesson_id:
            return jsonify({"success": True, "lesson": lesson})
    return jsonify({"success": False, "error": "Leçon introuvable"}), 404
