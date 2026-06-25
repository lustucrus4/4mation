"""Persistance utilisateurs, Elo et historique de parties (PostgreSQL)."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from api.services.elo import (
    bot_elo,
    bot_level,
    human_score,
    result_label,
    update_elo,
)
from api.services.lab211_auth import Lab211User
from api.services.postgres import db_conn, init_schema, is_configured

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UserRepository:
    """Accès données compte joueur."""

    def ensure_ready(self) -> bool:
        return is_configured() and init_schema()

    def upsert_user(self, lab211: Lab211User) -> int:
        with db_conn() as conn:
            row = conn.execute(
                """
                INSERT INTO users (lab211_id, username, display_name, email, updated_at)
                VALUES (%s, %s, %s, %s, NOW())
                ON CONFLICT (lab211_id) DO UPDATE SET
                    username = EXCLUDED.username,
                    display_name = EXCLUDED.display_name,
                    email = EXCLUDED.email,
                    updated_at = NOW()
                RETURNING id
                """,
                (lab211.id, lab211.username, lab211.display_name, lab211.email),
            ).fetchone()
            conn.commit()
            return int(row["id"])

    def get_user_by_lab211_id(self, lab211_id: str) -> Optional[Dict[str, Any]]:
        with db_conn() as conn:
            return conn.execute(
                "SELECT * FROM users WHERE lab211_id = %s",
                (lab211_id,),
            ).fetchone()

    def get_or_create_rating(self, user_id: int, mode: str = "bot") -> Dict[str, Any]:
        with db_conn() as conn:
            row = conn.execute(
                """
                INSERT INTO ratings (user_id, mode, elo)
                VALUES (%s, %s, 1200)
                ON CONFLICT (user_id, mode) DO NOTHING
                RETURNING *
                """,
                (user_id, mode),
            ).fetchone()
            if row is None:
                row = conn.execute(
                    "SELECT * FROM ratings WHERE user_id = %s AND mode = %s",
                    (user_id, mode),
                ).fetchone()
            conn.commit()
            return row

    def save_bot_game(
        self,
        user_id: int,
        *,
        game_mode: str,
        bot_id: str,
        human_color: int,
        winner: Optional[int],
        move_count: int,
        history: List[Dict[str, Any]],
        started_at: Optional[datetime] = None,
    ) -> Optional[Dict[str, Any]]:
        """Enregistre une partie terminée vs bot et met à jour l'Elo (mode bot uniquement)."""
        if game_mode != "standard" or not bot_id:
            return None

        opp_elo = bot_elo(bot_id)
        rating = self.get_or_create_rating(user_id, "bot")
        player_elo = int(rating["elo"])
        score = human_score(winner, human_color)
        new_elo, delta = update_elo(player_elo, opp_elo, score)
        res = result_label(winner, human_color)
        started = started_at or _utcnow()
        lvl = bot_level(bot_id)

        with db_conn() as conn:
            game_row = conn.execute(
                """
                INSERT INTO games (
                    user_id, game_mode, bot_id, bot_level, human_color,
                    result, winner, move_count, history,
                    elo_before, elo_after, elo_delta, started_at, finished_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, NOW())
                RETURNING *
                """,
                (
                    user_id,
                    game_mode,
                    bot_id,
                    lvl,
                    human_color,
                    res,
                    winner,
                    move_count,
                    json.dumps(history),
                    player_elo,
                    new_elo,
                    delta,
                    started,
                ),
            ).fetchone()

            win_inc = 1 if res == "win" else 0
            loss_inc = 1 if res == "loss" else 0
            draw_inc = 1 if res == "draw" else 0
            conn.execute(
                """
                UPDATE ratings SET
                    elo = %s,
                    games_played = games_played + 1,
                    wins = wins + %s,
                    losses = losses + %s,
                    draws = draws + %s
                WHERE user_id = %s AND mode = 'bot'
                """,
                (new_elo, win_inc, loss_inc, draw_inc, user_id),
            )
            conn.commit()

        return {
            "game": game_row,
            "elo_before": player_elo,
            "elo_after": new_elo,
            "elo_delta": delta,
        }

    def save_online_game(
        self,
        *,
        red_user_id: int,
        blue_user_id: int,
        winner: Optional[int],
        move_count: int,
        history: List[Dict[str, Any]],
        started_at: Optional[datetime] = None,
        red_elo: int,
        blue_elo: int,
        resign_by: Optional[int] = None,
    ) -> Dict[int, Dict[str, Any]]:
        """Enregistre une partie PvP et met à jour l'Elo online des deux joueurs."""
        started = started_at or _utcnow()
        outcomes: Dict[int, Dict[str, Any]] = {}

        pairs = (
            (red_user_id, 1, red_elo, blue_user_id, blue_elo),
            (blue_user_id, 2, blue_elo, red_user_id, red_elo),
        )

        rating_rows = {
            uid: self.get_or_create_rating(uid, "online") for uid in (red_user_id, blue_user_id)
        }
        elo_map = {red_user_id: int(rating_rows[red_user_id]["elo"]), blue_user_id: int(rating_rows[blue_user_id]["elo"])}

        score_red = human_score(winner, 1)
        score_blue = human_score(winner, 2)
        new_red, delta_red = update_elo(elo_map[red_user_id], elo_map[blue_user_id], score_red)
        new_blue, delta_blue = update_elo(elo_map[blue_user_id], elo_map[red_user_id], score_blue)
        new_elos = {red_user_id: new_red, blue_user_id: new_blue}
        deltas = {red_user_id: delta_red, blue_user_id: delta_blue}

        with db_conn() as conn:
            for user_id, human_color, _seat_elo, opp_id, opp_elo in pairs:
                res = result_label(winner, human_color)
                player_elo = elo_map[user_id]
                new_elo = new_elos[user_id]
                delta = deltas[user_id]

                conn.execute(
                    """
                    INSERT INTO games (
                        user_id, game_mode, human_color, opponent_user_id, opponent_elo,
                        result, winner, move_count, history,
                        elo_before, elo_after, elo_delta, started_at, finished_at
                    )
                    VALUES (%s, 'online', %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, NOW())
                    """,
                    (
                        user_id,
                        human_color,
                        opp_id,
                        opp_elo,
                        res,
                        winner,
                        move_count,
                        json.dumps(history),
                        player_elo,
                        new_elo,
                        delta,
                        started,
                    ),
                )

                win_inc = 1 if res == "win" else 0
                loss_inc = 1 if res == "loss" else 0
                draw_inc = 1 if res == "draw" else 0
                conn.execute(
                    """
                    UPDATE ratings SET
                        elo = %s,
                        games_played = games_played + 1,
                        wins = wins + %s,
                        losses = losses + %s,
                        draws = draws + %s
                    WHERE user_id = %s AND mode = 'online'
                    """,
                    (new_elo, win_inc, loss_inc, draw_inc, user_id),
                )
                outcomes[user_id] = {
                    "elo_before": player_elo,
                    "elo_after": new_elo,
                    "elo_delta": delta,
                    "resign_by": resign_by,
                }
            conn.commit()

        return outcomes

    def list_games(
        self,
        user_id: int,
        *,
        limit: int = 20,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        limit = max(1, min(limit, 100))
        offset = max(0, offset)
        with db_conn() as conn:
            rows = conn.execute(
                """
                SELECT g.id, g.game_mode, g.bot_id, g.bot_level, g.result, g.move_count,
                       g.elo_before, g.elo_after, g.elo_delta, g.started_at, g.finished_at,
                       g.opponent_user_id, g.opponent_elo,
                       u.display_name AS opponent_name, u.username AS opponent_username
                FROM games g
                LEFT JOIN users u ON u.id = g.opponent_user_id
                WHERE g.user_id = %s
                ORDER BY g.finished_at DESC
                LIMIT %s OFFSET %s
                """,
                (user_id, limit, offset),
            ).fetchall()
        return list(rows)

    def get_game(self, user_id: int, game_id: str) -> Optional[Dict[str, Any]]:
        with db_conn() as conn:
            return conn.execute(
                "SELECT * FROM games WHERE id = %s AND user_id = %s",
                (game_id, user_id),
            ).fetchone()

    def profile_payload(self, lab211: Lab211User) -> Dict[str, Any]:
        user_id = self.upsert_user(lab211)
        rating_bot = self.get_or_create_rating(user_id, "bot")
        rating_online = self.get_or_create_rating(user_id, "online")
        recent = self.list_games(user_id, limit=10)
        return {
            "user": {
                "id": user_id,
                "lab211_id": lab211.id,
                "username": lab211.username,
                "display_name": lab211.display_name,
                "email": lab211.email,
            },
            "rating": {
                "mode": "bot",
                "elo": int(rating_bot["elo"]),
                "games_played": int(rating_bot["games_played"]),
                "wins": int(rating_bot["wins"]),
                "losses": int(rating_bot["losses"]),
                "draws": int(rating_bot["draws"]),
            },
            "rating_online": {
                "mode": "online",
                "elo": int(rating_online["elo"]),
                "games_played": int(rating_online["games_played"]),
                "wins": int(rating_online["wins"]),
                "losses": int(rating_online["losses"]),
                "draws": int(rating_online["draws"]),
            },
            "recent_games": [_serialize_game_summary(g) for g in recent],
        }


def _serialize_game_summary(row: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "id": str(row["id"]),
        "game_mode": row["game_mode"],
        "bot_id": row.get("bot_id"),
        "bot_level": row.get("bot_level"),
        "result": row["result"],
        "move_count": int(row["move_count"]),
        "elo_before": row.get("elo_before"),
        "elo_after": row.get("elo_after"),
        "elo_delta": row.get("elo_delta"),
        "started_at": row["started_at"].isoformat() if row.get("started_at") else None,
        "finished_at": row["finished_at"].isoformat() if row.get("finished_at") else None,
    }
    if row.get("game_mode") == "online":
        opp = row.get("opponent_name") or row.get("opponent_username") or "Adversaire"
        out["opponent_name"] = str(opp)
        out["opponent_elo"] = row.get("opponent_elo")
    return out


def _serialize_game_detail(row: Dict[str, Any]) -> Dict[str, Any]:
    out = _serialize_game_summary(row)
    out["human_color"] = int(row.get("human_color") or 1)
    out["winner"] = row.get("winner")
    history = row.get("history")
    if isinstance(history, str):
        history = json.loads(history)
    out["history"] = history or []
    return out


user_repo = UserRepository()
