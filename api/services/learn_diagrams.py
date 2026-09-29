"""Catalogue de schémas pédagogiques, miroir de `components/learn/diagrams.ts`.

Pourquoi deux catalogues ? Les pages React dessinent leurs schémas depuis
`diagrams.ts`, sans passer par le serveur. Les **leçons**, elles, sont servies par
l'API : leur schéma doit voyager dans le JSON (`section.diagram`) et être rendu par
`RuleDiagram` tel quel. Le serveur ne peut donc pas se contenter d'un identifiant.

Les deux catalogues décrivent volontairement les **mêmes positions** — un schéma
corrigé d'un côté doit l'être de l'autre. Chaque schéma est produit par une fonction
(un dict neuf à chaque appel) pour qu'aucune leçon ne puisse muter le schéma d'une
autre. `script/test_lessons.py` relit chaque schéma embarqué avec `validate_diagram`.

Repères : indices `row, col` de 0 à 6, `1` = rouge (premier joueur), `2` = bleu,
`0` = case vide ; `valid` = case jouable, `invalid` = case refusée, `focus` = case clé,
`last` = dernier coup, `best` = meilleur coup suggéré.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Tuple

from .lesson_diagrams import (
    BOARD_SIZE,
    build_diagram,
    empty_board,
    legal_move_highlights,
    line,
)

Cell = Tuple[int, int]
Piece = Tuple[int, int, int]


def _board(pieces: Iterable[Piece]) -> List[List[int]]:
    grille = empty_board(BOARD_SIZE)
    for row, col, player in pieces:
        grille[row][col] = player
    return grille


def _merge(*maps: Dict[str, str]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for carte in maps:
        out.update(carte)
    return out


def _row_cells(row: int) -> List[Cell]:
    return [(row, col) for col in range(BOARD_SIZE)]


def _col_cells(col: int) -> List[Cell]:
    return [(row, col) for row in range(BOARD_SIZE)]


_MAIN_DIAGONAL: List[Cell] = [(i, i) for i in range(BOARD_SIZE)]
_ANTI_DIAGONAL: List[Cell] = [(i, BOARD_SIZE - 1 - i) for i in range(BOARD_SIZE)]


def frontier(
    *,
    pieces: Iterable[Piece],
    last: Cell,
    player: int,
    caption: str,
    extra: Optional[Dict[str, str]] = None,
    labels: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Schéma dont les cases jouables sont **calculées**, jamais écrites à la main.

    `player` est le camp au trait : c'est sa frontière qui est dessinée, avec la règle
    de secours si les huit voisins du dernier coup sont occupés.
    """
    board = _board(pieces)
    jouables = legal_move_highlights(board, player, last)
    highlights = _merge(jouables, {f"{last[0]},{last[1]}": "last"}, extra or {})
    return build_diagram(
        caption=caption, board=board, highlights=highlights, labels=labels
    )


# --------------------------------------------------------------------------
# Alignements gagnants
# --------------------------------------------------------------------------

_HORIZONTAL: List[Cell] = [(3, 1), (3, 2), (3, 3), (3, 4)]
_VERTICAL: List[Cell] = [(1, 3), (2, 3), (3, 3), (4, 3)]
_DIAGONAL: List[Cell] = [(1, 1), (2, 2), (3, 3), (4, 4)]
_ANTI_DIAGONAL: List[Cell] = [(1, 5), (2, 4), (3, 3), (4, 2)]


def win_horizontal() -> Dict[str, Any]:
    return build_diagram(
        caption="Quatre pions rouges sur la même ligne : le rouge gagne.",
        pieces=[(row, col, 1) for row, col in _HORIZONTAL],
        highlights=line(_HORIZONTAL, "win"),
        win_line=[_HORIZONTAL[0], _HORIZONTAL[-1]],
    )


def win_vertical() -> Dict[str, Any]:
    return build_diagram(
        caption="Quatre pions bleus sur la même colonne : le bleu gagne.",
        pieces=[(row, col, 2) for row, col in _VERTICAL],
        highlights=line(_VERTICAL, "win"),
        win_line=[_VERTICAL[0], _VERTICAL[-1]],
    )


def win_diagonal() -> Dict[str, Any]:
    return build_diagram(
        caption="Diagonale descendante : quatre rouges de (1,1) à (4,4).",
        pieces=[(row, col, 1) for row, col in _DIAGONAL],
        highlights=line(_DIAGONAL, "win"),
        win_line=[_DIAGONAL[0], _DIAGONAL[-1]],
    )


def win_anti_diagonal() -> Dict[str, Any]:
    return build_diagram(
        caption="Anti-diagonale : quatre bleus de (1,5) à (4,2).",
        pieces=[(row, col, 2) for row, col in _ANTI_DIAGONAL],
        highlights=line(_ANTI_DIAGONAL, "win"),
        win_line=[_ANTI_DIAGONAL[0], _ANTI_DIAGONAL[-1]],
    )


# --------------------------------------------------------------------------
# La frontière et sa règle de secours
# --------------------------------------------------------------------------


def first_move() -> Dict[str, Any]:
    return build_diagram(
        caption="Coup nº 1 : le plateau est vide, les 49 cases sont jouables.",
        highlights=legal_move_highlights(empty_board(BOARD_SIZE), 1, None),
    )


def frontier_center() -> Dict[str, Any]:
    return frontier(
        pieces=[(3, 3, 1)],
        last=(3, 3),
        player=2,
        caption=(
            "Le rouge ouvre au centre (3,3). Le bleu doit répondre sur l'une des 8 cases "
            "voisines (contour vert)."
        ),
        extra={"1,1": "invalid", "5,5": "invalid"},
    )


def frontier_midgame() -> Dict[str, Any]:
    return frontier(
        pieces=[(3, 3, 1), (3, 4, 2)],
        last=(3, 4),
        player=1,
        caption=(
            "Seul le dernier coup compte : (3,2) touche un vieux pion rouge, mais pas le "
            "dernier coup → case refusée."
        ),
        extra={"3,2": "invalid", "0,0": "invalid"},
    )


def rescue_rule() -> Dict[str, Any]:
    """Les 8 voisins du dernier coup sont occupés → règle de secours."""
    return frontier(
        pieces=[
            (2, 2, 1),
            (2, 3, 2),
            (2, 4, 1),
            (3, 2, 2),
            (3, 3, 2),
            (3, 4, 1),
            (4, 2, 1),
            (4, 3, 2),
            (4, 4, 1),
        ],
        last=(3, 3),
        player=1,
        caption=(
            "Les 8 voisins du dernier coup bleu (3,3) sont occupés → règle de secours : le "
            "rouge peut jouer toute case vide touchant un pion bleu."
        ),
        extra={"0,0": "invalid", "6,6": "invalid"},
    )


def corner_frontier() -> Dict[str, Any]:
    return frontier(
        pieces=[(0, 0, 1)],
        last=(0, 0),
        player=2,
        caption="Après un coup en coin, la frontière ne laisse que 3 réponses au lieu de 8.",
    )


# --------------------------------------------------------------------------
# Fenêtres de 4
# --------------------------------------------------------------------------


def four_window() -> Dict[str, Any]:
    """Une fenêtre de 4 en surbrillance, sur un plateau vide."""
    fenetre = [(3, 1), (3, 2), (3, 3), (3, 4)]
    return build_diagram(
        caption=(
            "Une fenêtre de 4 : quatre cases consécutives. Le plateau 7×7 en contient 88 — "
            "28 horizontales, 28 verticales, 32 en diagonale."
        ),
        highlights=line(fenetre, "focus"),
    )


def polluted_window() -> Dict[str, Any]:
    """Fenêtre horizontale contenant les deux couleurs : elle ne compte pour personne."""
    return build_diagram(
        caption=(
            "Fenêtre (2,1)-(2,4) : elle contient du rouge ET du bleu, donc elle est ignorée. "
            "Poser au milieu d'une ligne adverse la neutralise."
        ),
        pieces=[(2, 2, 1), (2, 3, 1), (2, 4, 2)],
        highlights=line([(2, 1), (2, 2), (2, 3), (2, 4)], "focus"),
    )


def polluted_window_vertical() -> Dict[str, Any]:
    """Même idée à la verticale, pour ne pas réduire la règle à l'horizontale."""
    return build_diagram(
        caption=(
            "Fenêtre verticale (1,3)-(4,3) : les deux couleurs y cohabitent, la ligne est "
            "morte dans les deux sens."
        ),
        pieces=[(1, 3, 1), (2, 3, 1), (3, 3, 2)],
        highlights=line([(1, 3), (2, 3), (3, 3), (4, 3)], "focus"),
    )


# --------------------------------------------------------------------------
# Menaces
# --------------------------------------------------------------------------

_THREAT: List[Cell] = [(3, 1), (3, 2), (3, 3)]


def threat_on_frontier() -> Dict[str, Any]:
    return frontier(
        pieces=[(row, col, 1) for row, col in _THREAT],
        last=(3, 3),
        player=2,
        caption=(
            "Le rouge vient de jouer (3,3) : (3,4) est sur la frontière et complète le 4 → "
            "le bleu doit bloquer là. (3,0) compléterait aussi, mais hors frontière."
        ),
        extra={"3,4": "focus", "3,0": "invalid"},
    )


def ghost_threat() -> Dict[str, Any]:
    return frontier(
        pieces=[(row, col, 1) for row, col in _THREAT] + [(1, 1, 2)],
        last=(1, 1),
        player=1,
        caption=(
            "Trois rouges alignés, mais le dernier coup bleu (1,1) est loin : les deux cases "
            "de complétion sortent de la frontière — menace fantôme."
        ),
        extra={"3,0": "invalid", "3,4": "invalid"},
    )


def ghost_threat_diagonal() -> Dict[str, Any]:
    """Même leçon sur une diagonale : la case de complétion est hors frontière."""
    return frontier(
        pieces=[(1, 1, 1), (2, 2, 1), (3, 3, 1), (0, 0, 2)],
        last=(0, 0),
        player=1,
        caption=(
            "Trois rouges en diagonale (1,1)-(3,3), mais le dernier coup bleu (0,0) est à "
            "l'autre bout : (4,4) n'est pas jouable, la diagonale ne menace rien."
        ),
        extra={"4,4": "invalid"},
    )


_DOUBLE_THREAT: List[Cell] = [(3, 1), (3, 2), (3, 3), (1, 3), (2, 3)]
def double_threat() -> Dict[str, Any]:
    """Deux lignes de 3 qui se croisent, sans revendiquer de frontière."""
    return build_diagram(
        caption=(
            "Deux lignes de 3 qui se croisent : quatre cases de complétion. Si deux d'entre "
            "elles sont jouables au même tour, l'adversaire n'en bloque qu'une."
        ),
        pieces=[(row, col, 1) for row, col in _DOUBLE_THREAT],
        highlights=line([(3, 0), (3, 4), (0, 3), (4, 3)], "focus"),
    )


def double_threat_playable() -> Dict[str, Any]:
    """Les deux cases de complétion sont réellement jouables après le dernier coup bleu."""
    return frontier(
        pieces=[(row, col, 1) for row, col in _DOUBLE_THREAT] + [(4, 4, 2)],
        last=(4, 4),
        player=1,
        caption=(
            "Le dernier coup bleu (4,4) rend (3,4) et (4,3) jouables au même tour : le rouge "
            "menace dans deux directions, le bleu ne peut en bloquer qu'une."
        ),
        extra={"3,4": "focus", "4,3": "focus"},
    )


def block_required() -> Dict[str, Any]:
    """Le seul coup qui éteint la menace adverse est marqué comme coup à jouer."""
    return frontier(
        pieces=[(row, col, 1) for row, col in _THREAT],
        last=(3, 3),
        player=2,
        caption=(
            "Le rouge menace (3,4). Le bleu n'a qu'un coup qui l'empêche de gagner tout de "
            "suite : occuper (3,4) — joué ici d'un ★."
        ),
        extra={"3,4": "best", "3,0": "invalid"},
    )


def threat_345() -> Dict[str, Any]:
    """Le rouge complète (3,2)-(3,5) après le coup bleu (2,4) : gain immédiat."""
    return frontier(
        pieces=[(3, 2, 1), (3, 3, 1), (3, 4, 1), (2, 4, 2)],
        last=(2, 4),
        player=1,
        caption=(
            "Le bleu vient de jouer (2,4) : (3,5) est jouable et termine l'alignement rouge "
            "(3,2)-(3,5). Si (3,5) était sortie de la frontière, la menace serait éteinte."
        ),
        extra={"3,5": "best"},
        labels={"3,5": "1"},
    )


def double_threat_scored() -> Dict[str, Any]:
    """La même fourchette, avec la valeur que le moteur attribue à chaque menace."""
    return frontier(
        pieces=[(row, col, 1) for row, col in _DOUBLE_THREAT] + [(4, 4, 2)],
        last=(4, 4),
        player=1,
        caption=(
            "Le moteur compte deux menaces réelles : 60 + 60 = 120 points, plus que tout ce "
            "qu'une position peut rapporter par ailleurs."
        ),
        extra={"3,4": "best", "4,3": "best"},
        labels={"3,4": "60", "4,3": "60"},
    )


def percent_legend() -> Dict[str, Any]:
    """Pourcentages par case : les valeurs sont des exemples, pas une évaluation figée."""
    return frontier(
        pieces=[(3, 3, 1), (4, 4, 2)],
        last=(4, 4),
        player=1,
        caption=(
            "Chaque case jouable porte un taux de victoire estimé, du point de vue du rouge : "
            "vert = favorable, rouge = défavorable. Les nombres ici sont des exemples."
        ),
        extra={"3,4": "best"},
        labels={"3,4": "71", "4,3": "52", "2,3": "38", "5,5": "24"},
    )


def balanced_position() -> Dict[str, Any]:
    """Position de milieu de partie sans avantage net : la barre reste autour de 50 %."""
    return build_diagram(
        caption=(
            "Position équilibrée : la barre de probabilité reste proche de 50 %. Elle se "
            "déplace après chaque coup, dans un sens comme dans l'autre."
        ),
        pieces=[(3, 3, 1), (3, 4, 2), (2, 4, 1), (4, 3, 2), (2, 3, 1)],
        highlights={"2,3": "last"},
    )


def immediate_win() -> Dict[str, Any]:
    return frontier(
        pieces=[(5, 2, 1), (5, 3, 1), (5, 4, 1), (4, 5, 2)],
        last=(4, 5),
        player=1,
        caption=(
            "Priorité nº 1 : gagner tout de suite. Le dernier coup bleu (4,5) rend (5,5) "
            "jouable — et (5,5) termine l'alignement rouge."
        ),
        extra={"5,5": "best"},
        labels={"5,5": "1"},
    )


# --------------------------------------------------------------------------
# Centralité
# --------------------------------------------------------------------------


def center_lines() -> Dict[str, Any]:
    return build_diagram(
        caption=(
            "Le pion central (3,3) appartient à 4 lignes de 7 cases : c'est la case la plus "
            "connectée du plateau."
        ),
        pieces=[(3, 3, 1)],
        highlights=_merge(
            line(_row_cells(3), "focus"),
            line(_col_cells(3), "focus"),
            line(_MAIN_DIAGONAL, "focus"),
            line(_ANTI_DIAGONAL, "focus"),
            {"3,3": "win"},
        ),
    )


def corner_lines() -> Dict[str, Any]:
    return build_diagram(
        caption="Un coin n'appartient qu'à 3 lignes : deux directions sur quatre y sont perdues.",
        pieces=[(0, 0, 1)],
        highlights=_merge(
            line(_row_cells(0), "focus"),
            line(_col_cells(0), "focus"),
            line(_MAIN_DIAGONAL, "focus"),
            {"0,0": "win"},
        ),
    )


# Nombre d'alignements de 4 traversant chaque case. Produit par
# `python scripts/check_learn_diagrams.py --windows` ; identique à `centerHeatmapDiagram`.
_CENTER_HEATMAP: Dict[str, str] = {
    "0,0": "3", "0,1": "4", "0,2": "5", "0,3": "7", "0,4": "5", "0,5": "4", "0,6": "3",
    "1,0": "4", "1,1": "6", "1,2": "8", "1,3": "10", "1,4": "8", "1,5": "6", "1,6": "4",
    "2,0": "5", "2,1": "8", "2,2": "11", "2,3": "13", "2,4": "11", "2,5": "8", "2,6": "5",
    "3,0": "7", "3,1": "10", "3,2": "13", "3,3": "16", "3,4": "13", "3,5": "10", "3,6": "7",
    "4,0": "5", "4,1": "8", "4,2": "11", "4,3": "13", "4,4": "11", "4,5": "8", "4,6": "5",
    "5,0": "4", "5,1": "6", "5,2": "8", "5,3": "10", "5,4": "8", "5,5": "6", "5,6": "4",
    "6,0": "3", "6,1": "4", "6,2": "5", "6,3": "7", "6,4": "5", "6,5": "4", "6,6": "3",
}


def center_heatmap() -> Dict[str, Any]:
    return build_diagram(
        caption=(
            "Nombre d'alignements de 4 qui traversent chaque case : 16 au centre (3,3), "
            "3 seulement dans un coin."
        ),
        highlights={"3,3": "focus"},
        labels=dict(_CENTER_HEATMAP),
    )


# --------------------------------------------------------------------------
# Fin de partie
# --------------------------------------------------------------------------

# Grille pleine sans aucun alignement de 4, cherchée par
# `python scripts/check_learn_diagrams.py --draw-board` ; identique à `drawDiagram`.
_DRAW_BOARD: List[List[int]] = [
    [1, 2, 2, 1, 2, 1, 1],
    [2, 1, 1, 1, 2, 2, 1],
    [2, 2, 1, 1, 2, 2, 2],
    [1, 2, 2, 2, 1, 1, 1],
    [1, 2, 1, 1, 1, 2, 2],
    [1, 1, 2, 1, 2, 2, 1],
    [2, 1, 2, 2, 1, 1, 1],
]


def draw_board() -> Dict[str, Any]:
    return build_diagram(
        caption="Plateau plein et aucun alignement de 4 : la partie est nulle (cas rare, mais possible).",
        board=_DRAW_BOARD,
    )


# --------------------------------------------------------------------------
# Ouvertures
# --------------------------------------------------------------------------

# Les 10 premiers coups distincts (orbites sous les symétries), mêmes que `ORBITS`
# de `script/solver/build_lessons.py`.
_ORBITS: List[Cell] = [
    (0, 0), (0, 1), (0, 2), (0, 3), (1, 1), (1, 2), (1, 3), (2, 2), (2, 3), (3, 3)
]


def distinct_first_moves() -> Dict[str, Any]:
    return build_diagram(
        caption=(
            "Seulement 10 premiers coups vraiment différents : les 39 autres cases sont une "
            "rotation ou un miroir."
        ),
        highlights=line(_ORBITS, "focus"),
        labels={f"{row},{col}": str(index + 1) for index, (row, col) in enumerate(_ORBITS)},
    )


def shifted_opening() -> Dict[str, Any]:
    return build_diagram(
        caption=(
            "(3,3) et (2,2) sont deux ouvertures distinctes, pas une copie décalée : leurs "
            "continuations et leur valeur diffèrent."
        ),
        highlights={"3,3": "focus", "2,2": "focus"},
        labels={"3,3": "A", "2,2": "B"},
    )


# --------------------------------------------------------------------------
# Lire l'interface (entraîneur, puzzles)
# --------------------------------------------------------------------------


def trainer_legend() -> Dict[str, Any]:
    """Légende du plateau d'entraînement, calquée sur le rendu réel de `Board.tsx`."""
    return frontier(
        pieces=[(3, 3, 1), (3, 4, 2)],
        last=(3, 4),
        player=1,
        caption=(
            "Lecture du plateau : liseré accent = dernier coup · contour vert = coup jouable "
            "· ★ or = meilleur coup · nombre = % de victoire (valeurs d'exemple)."
        ),
        extra={"2,4": "best"},
        labels={"2,4": "62", "4,3": "41"},
    )


def puzzle_unique_win() -> Dict[str, Any]:
    return frontier(
        pieces=[(3, 1, 1), (3, 2, 1), (3, 3, 1), (2, 4, 2)],
        last=(2, 4),
        player=1,
        caption=(
            "Le dernier coup bleu (2,4) rend (3,4) jouable — et (3,4) referme l'alignement "
            "rouge : c'est le coup à trouver."
        ),
        extra={"3,4": "best"},
        labels={"3,4": "1"},
    )
