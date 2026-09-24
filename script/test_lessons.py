"""
Tests du contenu pédagogique (section Apprendre : leçons).

Ces leçons alimentent les cours du site : une leçon vide, un identifiant dupliqué ou
un champ manquant casse l'affichage côté frontend sans autre signal. Ils sont donc
vérifiés ici.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "script"))

from api.routes.learn import LESSONS  # noqa: E402

MIN_BODY = 80


def test_structure():
    """Chaque leçon a les champs attendus par le frontend."""
    assert LESSONS, "aucune leçon"
    for lesson in LESSONS:
        for field in ("id", "title", "level", "duration_min", "sections"):
            assert lesson.get(field) is not None, f"leçon {lesson.get('id')} : {field} manquant"
        assert isinstance(lesson["duration_min"], int), f"{lesson['id']} : duration_min non entier"
        assert lesson["sections"], f"{lesson['id']} : aucune section"
    print(f"[OK] Structure des {len(LESSONS)} leçons")


def test_ids_uniques():
    """Les identifiants de leçon servent d'URL : ils doivent être uniques et propres."""
    ids = [lesson["id"] for lesson in LESSONS]
    doublons = {i for i in ids if ids.count(i) > 1}
    assert not doublons, f"identifiants dupliqués : {sorted(doublons)}"
    for lesson_id in ids:
        assert lesson_id == lesson_id.strip().lower(), f"identifiant mal formé : {lesson_id!r}"
        assert " " not in lesson_id, f"espace dans l'identifiant : {lesson_id!r}"
    print(f"[OK] {len(ids)} identifiants uniques")


def test_contenu_non_vide():
    """Aucune section vide : une leçon sans texte ne sert à rien."""
    for lesson in LESSONS:
        for section in lesson["sections"]:
            heading = section.get("heading")
            body = section.get("body", "")
            assert heading, f"{lesson['id']} : section sans titre"
            assert len(body) >= MIN_BODY, (
                f"{lesson['id']} / {heading} : corps trop court ({len(body)} caractères)"
            )
    total = sum(len(s["body"]) for l in LESSONS for s in l["sections"])
    print(f"[OK] Contenu non vide — {total} caractères au total")


def test_pas_de_reference_au_moteur_retire():
    """Le site ne calcule plus au MCTS ni au Minimax : les leçons ne doivent plus
    l'annoncer, sous peine de décrire un moteur qui n'existe plus."""
    interdits = ("MCTS", "Minimax")
    for lesson in LESSONS:
        for section in lesson["sections"]:
            body = section["body"]
            for mot in interdits:
                assert mot not in body, (
                    f"{lesson['id']} / {section['heading']} : référence obsolète à {mot}"
                )
    print("[OK] Aucune référence obsolète au MCTS ou au Minimax")


if __name__ == "__main__":
    print("TESTS LEÇONS 4MATION")
    print("=" * 40)
    test_structure()
    test_ids_uniques()
    test_contenu_non_vide()
    test_pas_de_reference_au_moteur_retire()
    print("[OK] Tous les tests de leçons passent")
