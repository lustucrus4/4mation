"""Routes API du jeu 4mation."""



from __future__ import annotations



from typing import Any, Dict, Optional, Tuple



from flask import Blueprint, jsonify, request



from api.middleware.auth import get_lab211_user, optional_auth
from api.services import BotRegistry, GameSessionManager, serialize_board_state
from api.services.game_persistence import try_save_finished_game
from api.services.coach_move_resolver import choose_coach_move
from api.services.tablebase_lookup import get_tablebase_lookup

from api.routes.session_utils import get_session_id, json_with_session

from game_tree.mcts_advisor import MCTSAdvisor



game_bp = Blueprint("game", __name__)



session_manager = GameSessionManager()

bot_registry = BotRegistry()

mcts_advisor = MCTSAdvisor(time_budget_ms=600)





def _require_engine():

    session_id = get_session_id(request)

    if not session_id:

        return None, None, None, (jsonify({"success": False, "error": "Session requise"}), 401)



    session = session_manager.get_session(session_id)

    if session is None:

        return None, None, None, (jsonify({"success": False, "error": "Session introuvable"}), 404)



    return session_id, session.engine, session.mode, None





def _serialize(session_id: str, engine) -> Dict[str, Any]:

    return serialize_board_state(engine, mode=session_manager.get_mode(session_id))





def _last_move_from_engine(engine) -> Optional[Tuple[int, int]]:

    state = engine.get_state()

    if state.action_history:

        _, last_row, last_col = state.action_history[-1]

        return (int(last_row), int(last_col))

    return None





def _normalize_move(raw: Any) -> Optional[Tuple[int, int]]:
    """Convertit best_move / coup API en (row, col)."""
    if raw is None:
        return None
    if isinstance(raw, (list, tuple)) and len(raw) >= 2:
        return (int(raw[0]), int(raw[1]))
    if isinstance(raw, dict) and "row" in raw and "col" in raw:
        return (int(raw["row"]), int(raw["col"]))
    return None


def _resolve_coach_action(engine, analysis: Dict[str, Any]) -> Optional[Tuple[int, int]]:
    """Choisit un coup coach légal à partir de l'analyse (best_move ou liste moves)."""
    valid = list(engine.get_valid_actions())
    if not valid:
        return None
    valid_set = set(valid)

    best = _normalize_move(analysis.get("best_move"))
    if best is not None and best in valid_set:
        return best

    for m in analysis.get("moves") or []:
        action = _normalize_move(m.get("move", m))
        if action is not None and action in valid_set:
            return action

    return None


def _play_coach_move(session_id: str, engine) -> Optional[Dict[str, Any]]:
    """En mode learning, joue le meilleur coup (livre, tablebase, secours Minimax 6 plies)."""
    import logging

    logger = logging.getLogger(__name__)

    if engine.is_terminal():
        return None

    state = engine.get_state()
    last_move = _last_move_from_engine(engine)
    valid = list(engine.get_valid_actions())
    if not valid:
        logger.warning("Coach: aucun coup légal session=%s", session_id)
        return None

    action, meta = choose_coach_move(
        state.board,
        int(state.current_player),
        last_move,
        valid,
    )
    if action is None:
        logger.warning("Coach: impossible de choisir un coup session=%s", session_id)
        return None

    if meta.get("source") == "backup_minimax":
        logger.info(
            "Coach: secours Minimax session=%s move=%s label=%s",
            session_id,
            action,
            meta.get("label"),
        )

    _, success, _ = engine.step(action)
    if not success:
        logger.warning("Coach: step échoué session=%s move=%s", session_id, action)
        return None

    return {"row": action[0], "col": action[1]}





def _meta_from_request(data: dict) -> dict:
    meta: dict = {}
    bot_id = data.get("bot_id")
    if bot_id:
        meta["bot_id"] = str(bot_id)
    return meta


def _maybe_persist_game(session_id: str, engine, mode: str) -> dict | None:
    session = session_manager.get_session(session_id)
    if session is None:
        return None
    saved = try_save_finished_game(
        get_lab211_user(),
        mode=mode,
        bot_id=session.meta.get("bot_id"),
        meta=session.meta,
        engine=engine,
    )
    if saved:
        session_manager.persist(session_id)
    return saved


@game_bp.route("/api/session", methods=["POST"])
@optional_auth
def create_session():
    """Crée une nouvelle session de partie."""
    data = request.get_json(silent=True) or {}
    mode = data.get("mode", "standard")
    if mode not in ("standard", "learning"):
        return jsonify({"success": False, "error": "Mode invalide"}), 400

    session_id = session_manager.create_session(mode=mode, meta=_meta_from_request(data))

    engine = session_manager.get_engine(session_id)

    return json_with_session(

        {

            "success": True,

            "session_id": session_id,

            "mode": mode,

            "state": serialize_board_state(engine, mode=mode),

        },

        session_id,

        201,

    )





@game_bp.route("/api/state", methods=["GET"])
@optional_auth
def api_state():

    """Retourne l'état courant sans recalcul Minimax/MCTS."""

    session_id, engine, mode, error = _require_engine()

    if error:

        return error

    return jsonify(serialize_board_state(engine, mode=mode))





@game_bp.route("/api/reset", methods=["POST"])
@optional_auth
def api_reset():
    """Réinitialise la partie de la session courante."""
    session_id, engine, mode, error = _require_engine()
    if error:
        return error

    data = request.get_json(silent=True) or {}
    new_mode = data.get("mode", mode)
    session_manager.reset_session(
        session_id,
        mode=new_mode,
        meta=_meta_from_request(data),
    )

    engine = session_manager.get_engine(session_id)

    return jsonify({

        "success": True,

        "mode": session_manager.get_mode(session_id),

        "state": serialize_board_state(engine, mode=session_manager.get_mode(session_id)),

    })





def _saved_payload(saved: dict | None) -> dict | None:
    if not saved:
        return None
    game = saved.get("game") or {}
    return {
        "game_id": str(game.get("id", "")),
        "elo_before": saved.get("elo_before"),
        "elo_after": saved.get("elo_after"),
        "elo_delta": saved.get("elo_delta"),
        "result": game.get("result"),
    }


@game_bp.route("/api/move", methods=["POST"])
@optional_auth
def api_move():

    """Joue un coup humain."""

    session_id, engine, mode, error = _require_engine()

    if error:

        return error



    data = request.get_json(silent=True) or {}

    action_data = data.get("action")

    if action_data is None:

        return jsonify({"success": False, "error": "Action manquante"}), 400



    if isinstance(action_data, dict):

        action = (action_data.get("row"), action_data.get("col"))

    elif isinstance(action_data, list) and len(action_data) == 2:

        action = (int(action_data[0]), int(action_data[1]))

    else:

        return jsonify({"success": False, "error": "Format d'action invalide"}), 400



    if None in action:

        return jsonify({"success": False, "error": "Coordonnées invalides"}), 400



    action = (int(action[0]), int(action[1]))

    cp = int(engine.get_current_player())
    if mode == "learning" and cp == 2:
        recovered = _play_coach_move(session_id, engine)
        if recovered is None:
            return jsonify({
                "success": False,
                "error": "Session bloquée (tour du coach). Nouvelle partie ou Annuler.",
            }), 409
        cp = int(engine.get_current_player())

    if mode == "learning" and cp != 1:
        return jsonify({"success": False, "error": "Ce n'est pas votre tour."}), 400

    valid_actions = engine.get_valid_actions()

    if action not in valid_actions:

        return jsonify({"success": False, "error": "Coup invalide"}), 400



    _, success, _ = engine.step(action)

    if not success:

        return jsonify({"success": False, "error": "Impossible de jouer ce coup"}), 400



    coach_action = None

    if mode == "learning" and not engine.is_terminal():

        coach_action = _play_coach_move(session_id, engine)



    session_manager.persist(session_id)

    winner_result = engine.get_winner()
    winner_int = int(winner_result) if winner_result is not None else None
    saved = _maybe_persist_game(session_id, engine, mode) if engine.is_terminal() else None

    return jsonify(
        {
            "success": True,
            "terminal": bool(engine.is_terminal()),
            "winner": winner_int,
            "next_player": int(engine.get_current_player()),
            "coach_action": coach_action,
            "state": _serialize(session_id, engine),
            "saved_game": _saved_payload(saved),
        }
    )





@game_bp.route("/api/ai_move", methods=["POST"])
@optional_auth
def api_ai_move():
    """Joue un coup pour l'IA selon le bot sélectionné."""
    import logging
    import time

    logger = logging.getLogger(__name__)
    session_id, engine, mode, error = _require_engine()
    if error:
        return error

    if engine.is_terminal():
        return jsonify({"success": False, "error": "Partie terminée"}), 400

    data = request.get_json(silent=True) or {}
    bot_id = data.get("bot_id", BotRegistry.DEFAULT_BOT_ID)
    if not bot_registry.is_valid_bot(bot_id):
        return jsonify({"success": False, "error": f"Bot inconnu: {bot_id}"}), 400

    session_manager.update_meta(session_id, bot_id=bot_id)
    cached = session_manager.get_cached_session(session_id)
    if cached is not None:
        engine = cached.engine

    started = time.perf_counter()
    try:
        action = bot_registry.choose_move(bot_id, engine)
    except Exception as exc:
        logger.exception("ai_move bot=%s session=%s", bot_id, session_id)
        return jsonify({"success": False, "error": str(exc)}), 500
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    logger.info("ai_move bot=%s session=%s elapsed_ms=%d", bot_id, session_id, elapsed_ms)



    if action is None:

        return jsonify({"success": False, "error": "Aucune action valide"}), 400



    valid_actions = engine.get_valid_actions()

    if action not in valid_actions and valid_actions:

        action = valid_actions[0]



    _, success, _ = engine.step(action)

    if not success:

        return jsonify({"success": False, "error": "Impossible de jouer ce coup"}), 400



    session_manager.persist(session_id)

    winner_result = engine.get_winner()
    winner_int = int(winner_result) if winner_result is not None else None
    state = engine.get_state()
    saved = _maybe_persist_game(session_id, engine, mode) if engine.is_terminal() else None

    return jsonify(
        {
            "success": True,
            "bot_id": bot_id,
            "action": {"row": int(action[0]), "col": int(action[1])},
            "action_encoded": int(action[0] * state.board_width + action[1]),
            "terminal": bool(engine.is_terminal()),
            "winner": winner_int,
            "state": _serialize(session_id, engine),
            "saved_game": _saved_payload(saved),
        }
    )





@game_bp.route("/api/analyze", methods=["POST"])

def api_analyze():

    """Analyse MCTS on-demand de la position courante."""

    session_id, engine, mode, error = _require_engine()

    if error:

        return error



    if engine.is_terminal():

        return jsonify({"success": False, "error": "Partie terminée"}), 400



    data = request.get_json(silent=True) or {}

    state = engine.get_state()

    last_move = _last_move_from_engine(engine)



    tablebase = get_tablebase_lookup()
    tb_analysis = tablebase.analyze_position(
        state.board,
        current_player=int(state.current_player),
        last_move=last_move,
    )

    if tb_analysis is not None:
        analysis = tb_analysis
    else:
        time_budget_ms = int(data.get("time_budget_ms", 600))
        time_budget_ms = max(300, min(time_budget_ms, 3000))

        advisor = mcts_advisor
        if time_budget_ms != advisor.time_budget_ms:
            advisor = MCTSAdvisor(time_budget_ms=time_budget_ms)

        analysis = advisor.analyze_position(
            state.board,
            current_player=int(state.current_player),
            last_move=last_move,
        )
        analysis["source"] = "mcts"
        analysis["exact"] = False
        analysis["label"] = "Estimé (MCTS)"

    tablebase._enrich_analysis_meta(analysis)

    # Normalisation : toujours exposer position_win_rate (perspective du joueur au
    # trait) + win_rate_p1 (perspective stable du joueur 1, pour la barre W/L côté UI).
    cp = int(state.current_player)
    pwr = analysis.get("position_win_rate")
    if pwr is None:
        _moves = analysis.get("moves") or []
        pwr = float(_moves[0]["win_rate"]) if _moves else 0.5
        analysis["position_win_rate"] = pwr
    analysis["current_player"] = cp
    analysis["win_rate_p1"] = pwr if cp == 1 else 1.0 - pwr

    return jsonify({

        "success": True,

        "analysis": analysis,

        "state": _serialize(session_id, engine),

    })





@game_bp.route("/api/undo", methods=["POST"])

def api_undo():

    """Annule N coups (défaut 1)."""

    session_id, engine, mode, error = _require_engine()

    if error:

        return error



    data = request.get_json(silent=True) or {}

    count = int(data.get("count", 1))

    if count < 1:

        return jsonify({"success": False, "error": "count doit être >= 1"}), 400



    if not engine.undo(count):

        return jsonify({"success": False, "error": "Impossible d'annuler"}), 400



    session_manager.persist(session_id)



    return jsonify({

        "success": True,

        "state": _serialize(session_id, engine),

    })





@game_bp.route("/api/undo_to", methods=["POST"])

def api_undo_to():

    """Revient au coup N (0 = début de partie)."""

    session_id, engine, mode, error = _require_engine()

    if error:

        return error



    data = request.get_json(silent=True) or {}

    if "move_index" not in data:

        return jsonify({"success": False, "error": "move_index requis"}), 400



    move_index = int(data["move_index"])

    if not engine.undo_to(move_index):

        return jsonify({"success": False, "error": "move_index invalide"}), 400



    session_manager.persist(session_id)



    return jsonify({

        "success": True,

        "state": _serialize(session_id, engine),

    })





@game_bp.route("/api/bots", methods=["GET"])

def api_bots():

    """Liste les bots disponibles."""

    return jsonify({"success": True, "bots": bot_registry.list_bots()})





@game_bp.route("/api/health", methods=["GET"])

def api_health():

    """Point de santé pour vérifier que l'API répond."""

    tb_stats = get_tablebase_lookup().stats()
    from api.services.postgres import is_configured, init_schema

    db_ok = is_configured() and init_schema()
    return jsonify({
        "status": "ok",
        "service": "4mation-api",
        "tablebase": tb_stats,
        "postgres": {"configured": is_configured(), "ready": db_ok},
    })

