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

from api.routes.learn import LESSONS, all_lessons  # noqa: E402

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


def test_corps_servis_textuels():
    """Ce que le site sert vraiment (`all_lessons()`) doit être textuel.

    Les leçons regénérées depuis le solveur remplacent les leçons écrites à la main.
    Un corps de section accidentellement écrit sous forme de tuple (virgule en trop
    dans un littéral) arrive en tableau JSON côté API et s'affiche tel quel sur le
    site. Les tests ne regardaient que les leçons écrites à la main : le bug passait.
    """
    servies = all_lessons()
    assert servies, "aucune leçon servie"
    for lesson in servies:
        for section in lesson["sections"]:
            body = section.get("body")
            assert isinstance(body, str), (
                f"{lesson['id']} / {section.get('heading')} : corps non textuel "
                f"({type(body).__name__}) — le site afficherait du JSON brut"
            )
    print(f"[OK] {len(servies)} leçons servies, tous les corps textuels")


def _toutes_les_versions():
    """Toutes les leçons susceptibles d'être affichées.

    Le site sert les leçons regénérées *à la place* des leçons écrites à la main ; mais
    si le fichier généré manque, la version écrite à la main reprend la main. Les deux
    chemins doivent donc rester justes.
    """
    servies = all_lessons()
    ids_servis = {lesson["id"] for lesson in servies}
    return servies + [lesson for lesson in LESSONS if lesson["id"] not in ids_servis]


def test_pas_de_classement_fragile():
    """Aucune version d'une leçon ne doit publier de classement chiffré des ouvertures.

    Mesure du 2026-09-25 : deux passes de la sonde donnent des scores qui changent de
    signe sur la même ouverture (`compare_probe_passes.py`). Un tableau de taux de
    victoire serait donc un faux enseignement. Le centre doit en revanche y apparaître
    comme démontré.
    """
    for lesson in _toutes_les_versions():
        for section in lesson["sections"]:
            body = section.get("body", "")
            assert "Second joueur" not in body, (
                f"{lesson['id']} / {section.get('heading')} : classement par taux de victoire, "
                "non reproductible d'une passe à l'autre"
            )
            # Formulations absolues devenues fausses depuis la preuve du centre : elles
            # affirmaient qu'aucun gain forcé n'existe près de l'ouverture. Un texte qui
            # nuance (en dehors du centre) s'écrit autrement, donc ces marqueurs restent
            # des signaux fiables.
            for marqueur in ("aucune victoire forcée", "le gain, s'il existe, est long"):
                assert marqueur not in body, (
                    f"{lesson['id']} / {section.get('heading')} : affirmation périmée "
                    f"({marqueur!r}) — le centre est prouvé gagnant (voir forced_win_33.json)"
                )

    servies = {lesson["id"]: lesson for lesson in all_lessons()}
    ouvertures = servies.get("ouvertures")
    assert ouvertures, "leçon « ouvertures » absente des leçons servies"
    texte = "\n".join(section.get("body", "") for section in ouvertures["sections"])
    assert "démontré" in texte, "la leçon « ouvertures » ne signale plus le centre démontré"
    print("[OK] Aucune version ne publie de classement fragile, centre signalé démontré")


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
    test_corps_servis_textuels()
    test_pas_de_classement_fragile()
    test_pas_de_reference_au_moteur_retire()
    print("[OK] Tous les tests de leçons passent")
