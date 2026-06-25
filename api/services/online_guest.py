"""Identité invité pour le multijoueur sans compte."""

from __future__ import annotations

import threading

GUEST_DEFAULT_ELO = 1200

_guest_seq = 0
_guest_lock = threading.Lock()


def next_guest_id() -> int:
    """Identifiant négatif unique par session invité."""
    global _guest_seq
    with _guest_lock:
        _guest_seq -= 1
        return _guest_seq


def is_guest_id(user_id: int) -> bool:
    return user_id < 0


def sanitize_guest_name(raw: object) -> str:
    name = str(raw or "").strip()
    if not name:
        return "Invité"
    return name[:24]
