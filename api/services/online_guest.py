"""Identité invité pour le multijoueur sans compte."""

from __future__ import annotations

import random
import threading

GUEST_DEFAULT_ELO = 1200

_guest_seq = 0
_guest_lock = threading.Lock()

# Prénoms français (genre m/f) — aligné sur le front pour les fallbacks serveur.
_GUEST_NAMES: list[tuple[str, str]] = [
    ("Paul", "m"),
    ("Pierre", "m"),
    ("Jacques", "m"),
    ("Nicolas", "m"),
    ("Thomas", "m"),
    ("Julien", "m"),
    ("Lucas", "m"),
    ("Hugo", "m"),
    ("Louis", "m"),
    ("Gabriel", "m"),
    ("Arthur", "m"),
    ("Léo", "m"),
    ("Raphaël", "m"),
    ("Adam", "m"),
    ("Nathan", "m"),
    ("Clément", "m"),
    ("Benjamin", "m"),
    ("Florian", "m"),
    ("Romain", "m"),
    ("Adrien", "m"),
    ("Jean", "m"),
    ("Marie", "f"),
    ("Sophie", "f"),
    ("Julie", "f"),
    ("Camille", "f"),
    ("Laura", "f"),
    ("Léa", "f"),
    ("Manon", "f"),
    ("Chloé", "f"),
    ("Emma", "f"),
    ("Jade", "f"),
    ("Louise", "f"),
    ("Alice", "f"),
    ("Inès", "f"),
    ("Clara", "f"),
    ("Juliette", "f"),
    ("Élise", "f"),
    ("Anaïs", "f"),
    ("Pauline", "f"),
    ("Aurélie", "f"),
    ("Charlotte", "f"),
    ("Amélie", "f"),
    ("Lucie", "f"),
    ("Margaux", "f"),
    ("Jeanne", "f"),
    ("Anne", "f"),
    ("Romane", "f"),
    ("Capucine", "f"),
    ("Océane", "f"),
    ("Zoé", "f"),
]


def next_guest_id() -> int:
    """Identifiant négatif unique par session invité."""
    global _guest_seq
    with _guest_lock:
        _guest_seq -= 1
        return _guest_seq


def is_guest_id(user_id: int) -> bool:
    return user_id < 0


def _format_guest_name(first_name: str, gender: str) -> str:
    suffix = "invitée" if gender == "f" else "invité"
    prenom = first_name.strip()[:1].upper() + first_name.strip()[1:].lower()
    return f"{prenom} ({suffix})"


def generate_random_guest_name() -> str:
    pool = list(_GUEST_NAMES)
    random.shuffle(pool)
    for first_name, gender in pool:
        formatted = _format_guest_name(first_name, gender)
        if len(formatted) <= 24:
            return formatted
    return "Léo (invité)"


def sanitize_guest_name(raw: object) -> str:
    name = str(raw or "").strip()
    generic = name.lower() in ("", "invité", "invitée", "invite", "invitee")
    if generic:
        return generate_random_guest_name()
    return name[:24]
