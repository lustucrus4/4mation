"""Vérification de session SSO Lab211 (introspection cookie)."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional

import requests
from flask import Request

logger = logging.getLogger(__name__)

LAB211_AUTH_BASE = os.environ.get("LAB211_AUTH_BASE", "https://auth.lab211.fr").rstrip("/")
LAB211_SITE_KEY = os.environ.get("LAB211_SITE_KEY", "4mation")
SESSION_TIMEOUT = float(os.environ.get("LAB211_SESSION_TIMEOUT", "5"))


@dataclass(frozen=True)
class Lab211User:
    id: str
    username: str
    email: str
    display_name: str


def resolve_user(request: Request) -> Optional[Lab211User]:
    """Interroge auth.lab211.fr avec les cookies du navigateur. Retourne None si invité."""
    cookie_header = request.headers.get("Cookie")
    if not cookie_header:
        return None
    url = f"{LAB211_AUTH_BASE}/api/auth/session"
    try:
        resp = requests.get(
            url,
            params={"site_key": LAB211_SITE_KEY},
            headers={"Cookie": cookie_header},
            timeout=SESSION_TIMEOUT,
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        if not data.get("authenticated"):
            return None
        user = data.get("user") or {}
        uid = str(user.get("id") or "").strip()
        if not uid:
            return None
        return Lab211User(
            id=uid,
            username=str(user.get("username") or ""),
            email=str(user.get("email") or ""),
            display_name=str(user.get("display_name") or user.get("username") or ""),
        )
    except Exception:
        logger.debug("Introspection Lab211 échouée", exc_info=True)
        return None


def user_to_dict(user: Lab211User) -> Dict[str, Any]:
    return {
        "lab211_id": user.id,
        "username": user.username,
        "email": user.email,
        "display_name": user.display_name,
    }
