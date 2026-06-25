"""Persistance automatique des parties terminées (comptes connectés)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from api.services.lab211_auth import Lab211User
from api.services.postgres import is_configured
from api.services.user_repository import user_repo
from game.game_engine import GameEngine

logger = logging.getLogger(__name__)


def try_save_finished_game(
    lab211_user: Optional[Lab211User],
    *,
    mode: str,
    bot_id: Optional[str],
    meta: Dict[str, Any],
    engine: GameEngine,
) -> Optional[Dict[str, Any]]:
    """Sauvegarde une partie vs bot si l'utilisateur est connecté et la partie est finie."""
    if lab211_user is None or not is_configured():
        return None
    if meta.get("game_saved"):
        return None
    if mode != "standard" or not bot_id:
        return None
    if not engine.is_terminal():
        return None

    if not user_repo.ensure_ready():
        return None

    state = engine.get_state()
    winner = int(state.winner) if state.winner is not None else None
    started_raw = meta.get("started_at")
    started_at: Optional[datetime] = None
    if isinstance(started_raw, str):
        try:
            started_at = datetime.fromisoformat(started_raw.replace("Z", "+00:00"))
        except ValueError:
            started_at = None

    try:
        user_id = user_repo.upsert_user(lab211_user)
        saved = user_repo.save_bot_game(
            user_id,
            game_mode=mode,
            bot_id=bot_id,
            human_color=int(meta.get("human_color") or 1),
            winner=winner,
            move_count=int(state.move_count),
            history=engine.get_move_history(),
            started_at=started_at,
        )
        if saved:
            meta["game_saved"] = True
            logger.info(
                "Partie sauvegardée user=%s bot=%s result delta=%s",
                lab211_user.id,
                bot_id,
                saved.get("elo_delta"),
            )
        return saved
    except Exception:
        logger.exception("Échec sauvegarde partie")
        return None
