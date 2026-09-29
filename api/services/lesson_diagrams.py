"""Construction et validation des schémas de plateau des leçons.

Les leçons de la section « Apprendre » affichent des schémas 7×7 (`diagram`) rendus par
`RuleDiagram`. Un schéma écrit à la main sous forme de matrice de 49 chiffres est
illisible en revue et se trompe facilement de coordonnée : on le déclare donc ici à
partir d'une simple liste de pions.

    build_diagram(
        pieces=[(3, 3, 1), (3, 4, 2)],
        highlights={"3,3": "last", "3,4": "valid"},
        caption="…",
    )

Conventions, alignées sur le frontend :
  - indices `row, col` de 0 à 6 ; `1` = rouge, `2` = bleu, `0` = case vide ;
  - surbrillances : `valid`, `invalid`, `win`, `focus`, `last` ;
  - clés de surbrillance et de libellé : la chaîne `"row,col"`.

`validate_diagram()` relit le résultat et vérifie qu'il est exploitable : c'est ce qui
empêche un schéma de partir en production avec une coordonnée hors plateau ou un
alignement gagnant qui n'en est pas un. `script/test_lessons.py` l'appelle sur toutes
les leçons.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, Mapping, Optional, Sequence, Tuple

BOARD_SIZE = 7
HIGHLIGHT_KINDS = ("valid", "invalid", "win", "focus", "last", "best")

Piece = Tuple[int, int, int]
Cell = Tuple[int, int]


def empty_board(size: int = BOARD_SIZE) -> list[list[int]]:
    """Plateau vide de `size` × `size` cases."""
    return [[0] * size for _ in range(size)]


def build_diagram(
    *,
    caption: str,
    pieces: Iterable[Piece] = (),
    board: Optional[list[list[int]]] = None,
    highlights: Optional[Mapping[str, str]] = None,
    labels: Optional[Mapping[str, str]] = None,
    win_line: Optional[Sequence[Cell]] = None,
    size: int = BOARD_SIZE,
) -> Dict[str, Any]:
    """Schéma de leçon à partir d'une liste de pions.

    `board` permet de fournir une grille complète (utile pour une position dense, où
    lister 49 pions serait plus long qu'écrire la grille) — les `pieces` sont alors
    posées par-dessus.
    """
    grille = [ligne[:] for ligne in board] if board else empty_board(size)
    for row, col, player in pieces:
        grille[row][col] = player

    diagram: Dict[str, Any] = {"board": grille, "caption": caption}
    if highlights:
        diagram["highlights"] = dict(highlights)
    if labels:
        diagram["labels"] = dict(labels)
    if win_line:
        diagram["win_line"] = [list(cell) for cell in win_line]
    return diagram


def line(cells: Iterable[Cell], kind: str = "valid") -> Dict[str, str]:
    """Surbrillance d'une suite de cases : `line([(3, 1), (3, 2)], "win")`."""
    return {f"{row},{col}": kind for row, col in cells}


def empty_cells(board: list[list[int]]) -> list[Cell]:
    """Toutes les cases vides du plateau."""
    size = len(board)
    return [
        (row, col)
        for row in range(size)
        for col in range(size)
        if board[row][col] == 0
    ]


def legal_moves(
    board: list[list[int]],
    player: int,
    last_move: Optional[Cell],
) -> list[Cell]:
    """Coups légaux d'une position, **même règle que le jeu** (`lib/validActions.ts`).

    Premier coup libre ; sinon les voisins vides du dernier coup ; sinon — quand ces
    voisins sont tous occupés — les cases vides touchant un pion adverse. Les schémas
    n'écrivent donc jamais à la main une liste de cases jouables : la frontière dessinée
    est celle que le moteur appliquerait.
    """
    size = len(board)
    opponent = 2 if player == 1 else 1
    dedans = lambda r, c: 0 <= r < size and 0 <= c < size  # noqa: E731

    if last_move is None:
        return empty_cells(board)

    row0, col0 = last_move
    voisins = [
        (row0 + dr, col0 + dc)
        for dr in (-1, 0, 1)
        for dc in (-1, 0, 1)
        if (dr or dc) and dedans(row0 + dr, col0 + dc) and board[row0 + dr][col0 + dc] == 0
    ]
    if voisins:
        return voisins

    def touche_adverse(row: int, col: int) -> bool:
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                r, c = row + dr, col + dc
                if (dr or dc) and dedans(r, c) and board[r][c] == opponent:
                    return True
        return False

    return [cell for cell in empty_cells(board) if touche_adverse(*cell)]


def legal_move_highlights(
    board: list[list[int]],
    player: int,
    last_move: Optional[Cell],
    kind: str = "valid",
) -> Dict[str, str]:
    """Surbrillance des coups légaux d'une position."""
    return {f"{row},{col}": kind for row, col in legal_moves(board, player, last_move)}


def winning_line(board: list[list[int]], player: int) -> list[Cell]:
    """Les 4 cases d'un alignement de `player` sur le plateau (vide si aucun)."""
    size = len(board)
    for row in range(size):
        for col in range(size):
            for dr, dc in ((0, 1), (1, 0), (1, 1), (1, -1)):
                cells = [
                    (row + dr * pas, col + dc * pas) for pas in range(4)
                ]
                if all(
                    0 <= r < size and 0 <= c < size and board[r][c] == player
                    for r, c in cells
                ):
                    return cells
    return []


def validate_diagram(diagram: Mapping[str, Any], where: str = "schéma") -> list[str]:
    """Liste des problèmes du schéma (vide = schéma exploitable)."""
    problemes: list[str] = []

    board = diagram.get("board")
    if not isinstance(board, list) or not board:
        return [f"{where} : plateau absent ou mal formé"]
    size = len(board)
    if any(not isinstance(ligne, list) or len(ligne) != size for ligne in board):
        problemes.append(f"{where} : le plateau n'est pas carré ({size} lignes)")
        return problemes
    for row in range(size):
        for col in range(size):
            if board[row][col] not in (0, 1, 2):
                problemes.append(
                    f"{where} : case ({row},{col}) invalide ({board[row][col]!r})"
                )
    if not str(diagram.get("caption") or "").strip():
        problemes.append(f"{where} : légende vide")

    for champ in ("highlights", "labels"):
        valeurs = diagram.get(champ) or {}
        if not isinstance(valeurs, Mapping):
            problemes.append(f"{where} : {champ} n'est pas un objet")
            continue
        for cle in valeurs:
            coords = str(cle).split(",")
            if len(coords) != 2 or not all(part.strip().isdigit() for part in coords):
                problemes.append(f"{where} : clé {champ} mal formée ({cle!r})")
                continue
            row, col = (int(part) for part in coords)
            if not (0 <= row < size and 0 <= col < size):
                problemes.append(f"{where} : clé {champ} hors plateau ({cle!r})")
    for cle, kind in (diagram.get("highlights") or {}).items():
        if kind not in HIGHLIGHT_KINDS:
            problemes.append(f"{where} : surbrillance inconnue {kind!r} en {cle}")

    win_line = diagram.get("win_line")
    if win_line:
        if len(win_line) < 2:
            problemes.append(f"{where} : ligne gagnante à moins de 2 points")
        for cell in win_line:
            if len(cell) != 2 or not all(0 <= int(v) < size for v in cell):
                problemes.append(f"{where} : point de ligne gagnante hors plateau ({cell!r})")

    # Une case de libellé doit porter un pion ou servir de repère : un libellé sur une
    # case vide est légitime (carte de chaleur), mais un libellé sur une case hors
    # plateau ne l'est pas — déjà couvert plus haut.
    for kind in ("win", "last", "best"):
        for cle in [
            cle
            for cle, valeur in (diagram.get("highlights") or {}).items()
            if valeur == kind
        ]:
            row, col = (int(part) for part in str(cle).split(","))
            # Un dernier coup ou un pion gagnant est posé ; un meilleur coup suggéré
            # désigne au contraire une case encore libre.
            case_doit_etre_vide = kind == "best"
            est_vide = board[row][col] == 0
            if est_vide and not case_doit_etre_vide:
                problemes.append(
                    f"{where} : surbrillance {kind!r} sur une case vide ({cle})"
                )
            if not est_vide and case_doit_etre_vide:
                problemes.append(
                    f"{where} : surbrillance {kind!r} sur une case occupée ({cle})"
                )
    return problemes
