"""Cherche un plateau 7x7 plein, sans alignement de 4, et le plus lisible possible.

Le schema « match nul » des pages d'apprentissage doit montrer une position pleine ou
personne n'aligne 4 pions. On ne l'ecrit pas a la main : on la cherche, puis on la
verifie.

Deux exigences :
  - **dure** : aucun alignement de 4 (sinon la position ne serait pas nulle) ;
  - **douce** : le moins de menaces a 3 possible et des couleurs equilibrees, sinon le
    schema montre un plateau truffe de quasi-victoires, ce qui se lit mal.

    python scripts/check_learn_diagrams.py --draw-board

Sortie : la grille au format TypeScript, a coller dans diagrams.ts.
"""

from __future__ import annotations

import argparse
import random

TAILLE = 7
DIRECTIONS = ((0, 1), (1, 0), (1, 1), (1, -1))


def _fenetres() -> list[list[tuple[int, int]]]:
    """Toutes les fenetres de 4 cases alignees du plateau."""
    fenetres = []
    for ligne in range(TAILLE):
        for col in range(TAILLE):
            for dl, dc in DIRECTIONS:
                cells = [(ligne + dl * pas, col + dc * pas) for pas in range(4)]
                if all(0 <= l < TAILLE and 0 <= c < TAILLE for l, c in cells):
                    fenetres.append(cells)
    return fenetres


FENETRES = _fenetres()


def _bilan(grille: list[list[int]]) -> tuple[int, int]:
    """Renvoie (nombre d'alignements de 4, nombre de fenetres a 3+1 vide)."""
    quatre = 0
    trois = 0
    for cells in FENETRES:
        valeurs = [grille[l][c] for l, c in cells]
        for couleur in (1, 2):
            n = valeurs.count(couleur)
            if n == 4:
                quatre += 1
            elif n == 3 and 0 in valeurs:
                trois += 1
    return quatre, trois


def _score(grille: list[list[int]]) -> tuple[int, int, int]:
    """Score a minimiser : (alignements de 4, menaces a 3, desequilibre des couleurs)."""
    quatre, trois = _bilan(grille)
    rouge = sum(ligne.count(1) for ligne in grille)
    return quatre, trois, abs(rouge - (TAILLE * TAILLE - rouge))


def cherche_plateau_nul(essais: int = 60, iterations: int = 4000) -> list[list[int]]:
    """Recherche locale : meilleure grille pleine sans alignement de 4 trouvee."""
    meilleure: list[list[int]] | None = None
    meilleur_score: tuple[int, int, int] | None = None
    aleatoire = random.Random(20260929)

    for _ in range(essais):
        grille = [
            [aleatoire.choice((1, 2)) for _ in range(TAILLE)] for _ in range(TAILLE)
        ]
        score = _score(grille)
        for _ in range(iterations):
            ligne = aleatoire.randrange(TAILLE)
            col = aleatoire.randrange(TAILLE)
            grille[ligne][col] = 3 - grille[ligne][col]
            nouveau = _score(grille)
            if nouveau <= score:
                score = nouveau
            else:
                grille[ligne][col] = 3 - grille[ligne][col]
            if score[0] == 0 and score[1] == 0:
                break
        if meilleur_score is None or score < meilleur_score:
            meilleur_score = score
            meilleure = [ligne[:] for ligne in grille]
        if meilleur_score[0] == 0 and meilleur_score[1] == 0:
            break

    assert meilleure is not None
    return meilleure


def verifie_plateau_nul(grille: list[list[int]]) -> list[str]:
    """Liste des problemes de la grille (vide = grille valide pour un match nul)."""
    problemes: list[str] = []
    if len(grille) != TAILLE or any(len(ligne) != TAILLE for ligne in grille):
        return [f"la grille doit faire {TAILLE}x{TAILLE}"]
    if any(case not in (1, 2) for ligne in grille for case in ligne):
        problemes.append("la grille doit etre pleine (aucune case vide)")
    for cells in FENETRES:
        valeurs = [grille[l][c] for l, c in cells]
        if valeurs.count(1) == 4:
            problemes.append(f"alignement de 4 rouge : {cells}")
        if valeurs.count(2) == 4:
            problemes.append(f"alignement de 4 bleu : {cells}")
    return problemes


def format_ts(grille: list[list[int]]) -> str:
    lignes = ",\n".join("  [" + ", ".join(str(c) for c in ligne) + "]" for ligne in grille)
    return "[\n" + lignes + ",\n]"


def affiche_fenetres() -> int:
    """Nombre d'alignements de 4 qui traversent une case : centre, bord, coin."""
    compte = [[0] * TAILLE for _ in range(TAILLE)]
    for cells in FENETRES:
        for ligne, col in cells:
            compte[ligne][col] += 1
    for nom, ligne, col in (("centre", 3, 3), ("bord (milieu)", 0, 3), ("coin", 0, 0)):
        print(f"  {nom:<16} ({ligne},{col}) : {compte[ligne][col]} alignement(s) de 4")
    print()
    print("   Plateau (nombre d'alignements de 4 passant par chaque case) :")
    for ligne in compte:
        print("   " + " ".join(f"{n:>3}" for n in ligne))
    return 0


def principal() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--draw-board",
        action="store_true",
        help="cherche et affiche une grille pleine sans alignement de 4",
    )
    parser.add_argument(
        "--windows",
        action="store_true",
        help="compte les alignements de 4 passant par chaque case",
    )
    args = parser.parse_args()
    if args.windows:
        return affiche_fenetres()
    if not args.draw_board:
        parser.print_help()
        return 0

    grille = cherche_plateau_nul()
    problemes = verifie_plateau_nul(grille)
    quatre, trois = _bilan(grille)
    print(format_ts(grille))
    print()
    print(f"Bilan : {quatre} alignement(s) de 4, {trois} fenetre(s) a 3+1 vide")
    print("Verification :", "OK (aucun alignement de 4)" if not problemes else problemes)
    return 0 if not problemes else 1


if __name__ == "__main__":
    raise SystemExit(principal())
