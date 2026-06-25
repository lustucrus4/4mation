"""Décorateurs et helpers d'authentification Lab211 pour Flask."""

from __future__ import annotations

from functools import wraps
from typing import Any, Callable, Optional

from flask import g, jsonify, request

from api.services.lab211_auth import Lab211User, resolve_user
from api.services.postgres import is_configured
from api.services.user_repository import user_repo


def get_lab211_user() -> Optional[Lab211User]:
    if hasattr(g, "lab211_user"):
        return g.lab211_user
    user = resolve_user(request)
    g.lab211_user = user
    return user


def optional_auth(view: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(view)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        get_lab211_user()
        return view(*args, **kwargs)

    return wrapper


def require_auth(view: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(view)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        user = get_lab211_user()
        if user is None:
            return jsonify({"success": False, "error": "Connexion requise"}), 401
        if not is_configured():
            return jsonify({"success": False, "error": "Base de données indisponible"}), 503
        if not user_repo.ensure_ready():
            return jsonify({"success": False, "error": "Base de données indisponible"}), 503
        g.db_user_id = user_repo.upsert_user(user)
        return view(*args, **kwargs)

    return wrapper
