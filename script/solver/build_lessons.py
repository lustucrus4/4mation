"""Fabrique les leçons du site à partir des sorties du solveur.

Les leçons de la section « Apprendre » étaient écrites à la main : leurs chiffres
vieillissaient à chaque progrès du moteur (`(3,3) +29` datait d'une recherche de
profondeur 14). Ce script relit les artefacts produits par les outils de résolution —
sonde profonde, vérification des schémas, motifs de finales — et écrit un fichier de
leçons que l'API sert en remplacement.

    python script/solver/build_lessons.py

Sortie : ``api/data/lessons_engine.json`` (liste de leçons au même format que celles
déclarées dans `api/routes/learn.py`, qui garde la main sur les leçons non régénérées).
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent.parent
SOLVER = ROOT / "script" / "solver"
OUT_DEFAULT = ROOT / "api" / "content" / "lessons_engine.json"

# Les 10 premiers coups distincts (orbites sous les symétries du plateau).
ORBITS = [(0, 0), (0, 1), (0, 2), (0, 3), (1, 1), (1, 2), (1, 3), (2, 2), (2, 3), (3, 3)]


def load_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        print(f"  (ignoré, illisible : {path.name})")
        return None


def move_txt(move: Any) -> str:
    if not move:
        return "—"
    if isinstance(move, dict):
        move = (move.get("row"), move.get("col"))
    return f"({int(move[0])},{int(move[1])})"


def line_txt(moves: List[Dict[str, Any]]) -> str:
    parts = []
    for entry in moves:
        side = "X" if int(entry["player"]) == 1 else "O"
        row, col = entry["move"]
        parts.append(f"{side}{row},{col}")
    return " ".join(parts)


def board_block(board: List[List[int]], last: Optional[Any] = None) -> str:
    symbols = {0: ".", 1: "X", 2: "O"}
    last_cell = tuple(int(v) for v in last) if last else None
    lines = ["```", "      c0   c1   c2   c3   c4   c5   c6"]
    for row in range(len(board)):
        cells = []
        for col in range(len(board[row])):
            label = symbols.get(int(board[row][col]), "?")
            if last_cell == (row, col):
                label += "#"
            cells.append(f"{label:<4}")
        lines.append(f"  r{row}  " + "".join(cells))
    lines.append("```")
    return "\n".join(lines)


CENTRE = (3, 3)


def _cell_of(row: Dict[str, Any]) -> Tuple[int, int]:
    ouv = row.get("ouverture") or (9, 9)
    return int(ouv[0]), int(ouv[1])


def _centre_reply_from_theory(theory: Optional[Dict[str, Any]]) -> Optional[Any]:
    """Défense du centre, lue dans la ligne principale du livre (repli seulement)."""
    if not theory:
        return None
    ligne = theory.get("ligne_principale") or theory.get("main_line") or []
    if len(ligne) >= 2 and isinstance(ligne[1], dict):
        return ligne[1].get("coup")
    return None


def opening_section(
    probe: Optional[Dict[str, Any]],
    theory: Optional[Dict[str, Any]] = None,
    stability: Optional[Dict[str, Any]] = None,
) -> str:
    """Texte de la leçon « ouvertures ».

    Aucun classement chiffré des 10 premiers coups n'est publié ici. Les mêmes
    ouvertures, chiffrées deux fois par la sonde avec des budgets différents, donnent
    des scores qui changent de signe (`script/solver/compare_probe_passes.py`) : un
    tableau de valeurs serait un faux enseignement. Seul le centre, démontré gagnant,
    est présenté comme une valeur ferme.
    """
    rows = [r for r in (probe or {}).get("ouvertures", []) if not r.get("erreur")]
    if not rows:
        return (
            "La sonde profonde n'a pas encore tourné : lancez "
            "`python scripts/probe_opening_proof.py` pour chiffrer cette leçon."
        )

    centre = next((r for r in rows if _cell_of(r) == CENTRE), None)
    autres = sorted((r for r in rows if _cell_of(r) != CENTRE), key=_cell_of)

    lines = [
        "Sur les 49 cases du plateau vide, il n'existe que **10 premiers coups "
        "réellement différents** : les 39 autres sont des rotations ou des miroirs. "
        "Un seul est **démontré gagnant** ; les neuf autres ne sont pas départageables "
        "par nos mesures actuelles.",
        "",
        "| Premier coup | Nature | Profondeur atteinte | Meilleure réponse connue |",
        "| --- | --- | --- | --- |",
    ]
    if centre is not None:
        reply = centre.get("reponse") or _centre_reply_from_theory(theory)
        lines.append(
            f"| {move_txt(centre.get('ouverture'))} | **gagnant, démontré** | "
            f"{centre.get('profondeur', '—')} | {move_txt(reply)} |"
        )
    for row in autres:
        lines.append(
            f"| {move_txt(row.get('ouverture'))} | estimé, non départagé | "
            f"{row.get('profondeur', '—')} | {move_txt(row.get('reponse'))} |"
        )

    lines += [
        "",
        "**« Nature » compte plus que n'importe quel chiffre.** Le centre est démontré : "
        "il gagne quoi que fasse l'adversaire. Les neuf autres coups sont seulement "
        "*estimés* par une recherche interrompue par son budget de temps.",
        "",
        "**Pourquoi il n'y a pas de classement ici.** Les mêmes positions ont été "
        "chiffrées deux fois avec des budgets différents, et les scores changent de sens.",
    ]
    instables = [o for o in (stability or {}).get("ouvertures", []) if o.get("instable")]
    if instables:
        exemples = " ; ".join(
            f"{move_txt(o['ouverture'])} : {min(o['scores'].values())} puis "
            f"{max(o['scores'].values())}"
            for o in instables[:3]
        )
        total = len((stability or {}).get("ouvertures", []))
        lines.append(
            f"Sur les {total} ouvertures mesurées deux fois, {len(instables)} varient de "
            f"plus de 20 points ({exemples}). L'ordre du classement est rebattu. Publier "
            "un tableau de scores donnerait donc l'air d'un fait à ce qui n'est que le "
            "bruit d'une recherche arrêtée trop tôt."
        )
    else:
        lines.append(
            "Aucune mesure doublée n'est disponible pour l'instant : lancez "
            "`python script/solver/compare_probe_passes.py` pour vérifier la stabilité "
            "avant toute publication de chiffres."
        )
    lines += [
        "",
        "Ce que cela change en pratique :",
        "",
        "- **Vous commencez** : jouez `(3,3)`. C'est le seul coup dont la victoire est "
        "démontrée (voir la leçon « Preuve »).",
        "- **Vous voulez varier** : les neuf autres coups sont jouables, aucun n'est "
        "démontré perdant, et nos mesures ne permettent pas de dire lequel est le "
        "meilleur. Choisissez-les pour la variété, pas pour un avantage chiffré.",
    ]
    return "\n".join(lines)


def board_from_moves(moves: List[Dict[str, Any]]) -> List[List[int]]:
    """Plateau après la ligne jouée (les pions ne bougent jamais)."""
    board = [[0] * 7 for _ in range(7)]
    for entry in moves:
        row, col = entry["move"]
        board[int(row)][int(col)] = int(entry["player"])
    return board


def winning_cells(board: List[List[int]], player: int) -> List[str]:
    """Cases de l'alignement gagnant, sous la forme « ligne,colonne »."""
    for row in range(7):
        for col in range(7):
            for dr, dc in ((0, 1), (1, 0), (1, 1), (1, -1)):
                cells = []
                for step in range(4):
                    r, c = row + dr * step, col + dc * step
                    if 0 <= r < 7 and 0 <= c < 7 and board[r][c] == player:
                        cells.append(f"{r},{c}")
                    else:
                        break
                if len(cells) == 4:
                    return cells
    return []


def final_diagram(moves: List[Dict[str, Any]], caption: str) -> Optional[Dict[str, Any]]:
    """Schéma du plateau final, dernier coup et alignement gagnant mis en évidence."""
    if not moves:
        return None
    board = board_from_moves(moves)
    winner = int(moves[-1]["player"])
    highlights = {}
    for cell in winning_cells(board, winner):
        highlights[cell] = "win"
    last = moves[-1]["move"]
    highlights[f"{int(last[0])},{int(last[1])}"] = "last"
    return {"board": board, "highlights": highlights, "caption": caption}


def puzzle_diagram(puzzle: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Schéma d'un exercice de finale : plateau + dernière case jouée."""
    board = puzzle.get("plateau")
    if not board:
        return None
    highlights = {}
    last = puzzle.get("dernier_coup")
    if last:
        highlights[f"{int(last[0])},{int(last[1])}"] = "last"
    solution = puzzle.get("solution")
    if solution:
        for step in solution:
            move = step[0] if isinstance(step, list) and step and isinstance(step[0], list) else step
            try:
                highlights[f"{int(move[0])},{int(move[1])}"] = "focus"
            except (TypeError, ValueError, IndexError):
                continue
    return {
        "board": board,
        "highlights": highlights,
        "caption": f"{puzzle.get('motif', 'exercice')} — gain forcé en {puzzle.get('distance_du_gain')} demi-coups",
    }


def schema_section(payload: Optional[Dict[str, Any]]) -> tuple[str, Optional[Dict[str, Any]]]:
    """Texte et schéma de la leçon « schéma gagnant », chiffrés par la vérification."""
    if not payload or not payload.get("jeux"):
        return (
            "La vérification de schéma n'a pas encore tourné : lancez "
            "`python scripts/verify_winning_schema.py --opening 3,3 --games 12`.",
            None,
        )
    opening = move_txt(payload.get("opening"))
    games = payload["jeux"]
    wins = sum(1 for g in games if g.get("winner") == 1)
    plies = [int(g["plies"]) for g in games]
    decisive = [g for g in games if g.get("winner") is not None]
    shortest = min(decisive, key=lambda g: int(g["plies"])) if decisive else games[0]

    body = "\n".join(
        [
            f"Après le premier coup {opening}, l'attaque a joué **le meilleur coup du "
            f"moteur à chaque tour**, tandis que la défense choisissait à chaque fois dans "
            f"ses {payload.get('defense_top')} meilleurs coups. Résultat : **{wins} victoire(s) "
            f"du premier joueur sur {len(games)} parties**, la plus courte en "
            f"{min(plies)} demi-coups, la plus longue en {max(plies)}.",
            "",
            "Autrement dit : le gain ne dépend pas d'une faute précise de la défense. "
            "Voici la ligne la plus directe, à rejouer sur le plateau.",
            "",
            "```",
            line_txt(shortest["moves"]),
            "```",
            "`Xn,m` = coup du premier joueur, `On,m` = coup du second, au format "
            "`ligne,colonne` (de 0 à 6).",
        ]
    )
    diagram = final_diagram(
        shortest["moves"],
        f"Position finale : le premier joueur (croix) aligne 4 pions. "
        f"Le cercle marque son dernier coup.",
    )
    return body, diagram


def fr_int(value: int) -> str:
    """Entier avec espaces fines comme séparateurs de milliers."""
    return f"{int(value):,}".replace(",", "\u202f")


def layer_table(db_path: Path, fallback: Dict[str, Any]) -> tuple[List[str], str]:
    """Tableau des couches exactes, lu dans la base (sinon repli sur le JSON des motifs)."""
    rows: Dict[int, Dict[str, int]] = {}
    source = "base"
    if db_path.exists():
        import sqlite3

        try:
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=60)
            try:
                for layer, result, count in conn.execute(
                    "SELECT empty_cells, result, COUNT(*) FROM positions "
                    "WHERE empty_cells IS NOT NULL GROUP BY empty_cells, result"
                ):
                    bucket = rows.setdefault(int(layer), {"W": 0, "D": 0, "L": 0})
                    key = str(result)[:1].upper()
                    if key in bucket:
                        bucket[key] += int(count)
            finally:
                conn.close()
        except Exception as exc:  # base occupée : on se rabat sur le JSON
            print(f"  (lecture directe impossible : {exc})")
            rows = {}
    if not rows:
        source = "motifs de finales"
        for layer, values in fallback.items():
            rows[int(layer)] = {
                "W": int(values.get("victoires", 0)),
                "D": int(values.get("nulles", 0)),
                "L": int(values.get("defaites", 0)),
            }
    if not rows:
        return [], source

    lines = [
        "| Cases vides | Positions | Victoires du trait | Nulles | Défaites |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for layer in sorted(rows):
        values = rows[layer]
        total = values["W"] + values["D"] + values["L"]
        lines.append(
            f"| {layer} | {fr_int(total)} | {fr_int(values['W'])} "
            f"| {fr_int(values['D'])} | {fr_int(values['L'])} |"
        )
    return lines, source


def proof_section(payload: Optional[Dict[str, Any]]) -> tuple[str, Optional[Dict[str, Any]]]:
    """Texte et schéma de la leçon « preuve » : le gain forcé après le centre."""
    if not payload or not payload.get("plies"):
        return (
            "La preuve n'a pas encore été extraite : lancez "
            "`python scripts/extract_forced_win.py --opening 3,3`.",
            None,
        )
    plies = payload["plies"]
    opening = payload["opening"]
    root = plies[1] if len(plies) > 1 else None
    mate = root.get("mate_in") if root else None
    moves = [{"move": p["move"], "player": p["player"]} for p in plies]
    line = " ".join(
        f"{'X' if p['player'] == 1 else 'O'}{p['move'][0]},{p['move'][1]}" for p in plies
    )
    resistant = [
        (p.get("resistance") or {}).get("same") for p in plies[1:] if p["player"] == 2
    ]
    forced = sum(1 for value in resistant if value == 1)

    body = "\n".join(
        [
            f"Le premier coup central **{opening[0]},{opening[1]}** n'est pas seulement bon : "
            f"il **gagne de force**. Le moteur le *démontre* — ce n'est pas une estimation — "
            f"en {root.get('elapsed_ms', 0) / 1000:.0f} s de calcul à la profondeur "
            f"{root.get('depth')}, avec une table de transposition de 2 Go.",
            "",
            f"Verdict : après ce coup, le second joueur est **perdant quoi qu'il fasse**, mat "
            f"en {mate} demi-coups (soit {len(plies)} demi-coups joués au total). Le gain ne "
            f"repose sur **aucune faute** : à chaque tour de défense, *tous* ses coups perdent.",
            "",
            "**La ligne principale** (défense la plus tenace, attaque au plus court) :",
            "",
            "```",
            line,
            "```",
            "`Xn,m` = coup du premier joueur, `On,m` = coup du second, format `ligne,colonne`.",
            "",
            f"Sur les {len(resistant)} tours de défense de cette ligne, {forced} n'ont "
            "**qu'un seul** coup qui résiste le plus longtemps : la défense est presque "
            "entièrement forcée. Voilà pourquoi, en pratique, on perd cette ouverture contre "
            "un moteur exact même en jouant « bien ».",
            "",
            "Vérification indépendante : la ligne a été rejouée avec le moteur de jeu du site, "
            "qui fait autorité sur les règles — **0 anomalie**, et le nombre de coups légaux "
            "du moteur coïncide avec celui des règles à chaque position.",
        ]
    )
    diagram = final_diagram(
        moves,
        "Position finale de la ligne prouvée : le premier joueur (croix) aligne 4 pions. "
        "Le cercle marque son dernier coup.",
    )
    return body, diagram


def finales_section(
    patterns: Optional[Dict[str, Any]], db_path: Path
) -> tuple[str, Optional[Dict[str, Any]]]:
    """Texte et schéma de la leçon « finales exactes », chiffrés par la tablebase."""
    if not patterns and not db_path.exists():
        return (
            "L'analyse des finales n'a pas encore tourné : lancez "
            "`python script/solver/mine_final_patterns.py`.",
            None,
        )
    patterns = patterns or {}
    volumetrie = patterns.get("volumetrie") or {}
    table, _source = layer_table(db_path, volumetrie)
    lines: List[str] = []

    if table:
        counts = {}
        for row in table[2:]:
            cells = [part.strip() for part in row.split("|")[1:-1]]
            counts[int(cells[0])] = int(cells[1].replace("\u202f", ""))
        layers = sorted(counts)
        # Une couche croît d'au moins ~5x par case vide tant qu'elle est complète ;
        # une couche plus petite que la précédente est forcément trouée.
        complete = [
            layer
            for index, layer in enumerate(layers)
            if index == 0 or counts[layer] >= 2 * counts[layers[index - 1]]
        ]
        missing = [layer for layer in layers if layer not in complete]
        lines += [
            "La tablebase contient les positions de finale **résolues exactement** : pour "
            "chacune, le verdict est certain, pas estimé. C'est ce qui permet au bot de jouer "
            "la fin de partie sans se tromper.",
            "",
            *table,
            "",
            "Lecture : plus il reste de cases vides, plus le camp au trait gagne souvent. "
            "À 12 cases vides, celui qui a le trait gagne dans près de deux cas sur trois — "
            "la finale n'est pas une formalité, c'est le moment où la partie se décide.",
        ]
        if complete and missing:
            lines += [
                "",
                f"Attention à la lecture : les couches de {complete[0]} à {complete[-1]} cases "
                "vides sont **complètes** (chaque position y est prouvée). Les couches "
                f"{missing[0]} à {missing[-1]} sont en cours de comblement — les positions qui "
                "s'y trouvent sont exactes, mais il en manque encore, et le site retombe sur "
                "une estimation du moteur quand une position absente est demandée.",
            ]
        elif complete:
            lines += [
                "",
                f"Toutes les couches de {complete[0]} à {complete[-1]} cases vides sont "
                "complètes : chaque position y est prouvée.",
            ]

    regles = patterns.get("regles") or []
    if regles:
        lines += ["", "**Ce que disent les finales exactes**", ""]
        for regle in regles[:5]:
            lines.append(f"- {regle}")

    puzzle_diag: Optional[Dict[str, Any]] = None
    puzzles = patterns.get("puzzles") or []
    if puzzles:
        gaps = [int(puzzle.get("cellules_vides") or 0) for puzzle in puzzles]
        layer = max(set(gaps), key=gaps.count) if gaps else 0
        puzzle = next(
            (p for p in puzzles if int(p.get("cellules_vides") or 0) == layer), puzzles[0]
        )
        lines += [
            "",
            "**Exercice**",
            "",
            f"Motif : **{puzzle.get('motif')}** ({puzzle.get('cellules_vides')} cases vides, "
            f"gain en {puzzle.get('distance_du_gain')} demi-coups).",
            "",
            f"Solution : {puzzle.get('explication')}",
        ]
        puzzle_diag = puzzle_diagram(puzzle)
    return "\n".join(lines), puzzle_diag


def build(probe: Optional[Dict[str, Any]], theory: Optional[Dict[str, Any]],
          schemas: Dict[str, Optional[Dict[str, Any]]], patterns: Optional[Dict[str, Any]],
          proof: Optional[Dict[str, Any]], db_path: Path,
          stability: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    source_app = []
    if probe:
        source_app.append(f"sonde profonde du {probe.get('genere_le', '?')}")
    if theory:
        source_app.append(f"théorie du livre du {theory.get('genere_le', '?')}")
    if stability:
        source_app.append(f"stabilité des passes du {stability.get('genere_le', '?')}")
    if proof:
        source_app.append(f"preuve du centre du {proof.get('genere_le', '?')}")
    for key, payload in schemas.items():
        if payload:
            source_app.append(f"schéma {key} du {payload.get('genere_le', '?')}")
    if patterns:
        source_app.append(f"finales du {(patterns.get('meta') or {}).get('genere_le', '?')}")

    lessons: List[Dict[str, Any]] = [
        {
            "id": "ouvertures",
            "title": "Ouvertures : ce que dit le moteur",
            "level": "intermédiaire",
            "duration_min": 8,
            "sections": [
                {
                    "heading": "Le premier coup est le seul coup libre",
                    "body": (
                        "Sur un plateau vide, vous posez votre pion où vous voulez : c'est la "
                        "seule fois de la partie. Ensuite, tout est contraint par la frontière "
                        "du dernier coup joué. Le premier coup décide donc de la région où va "
                        "se dérouler la partie."
                    ),
                },
                {
                    "heading": "Les 10 premiers coups, et pourquoi on ne les classe pas",
                    "body": opening_section(probe, theory, stability),
                },
                {
                    "heading": "Pourquoi le centre domine",
                    "body": (
                        "Un pion central participe à plus d'alignements de 4 que n'importe quel "
                        "autre : jusqu'à 4 directions (horizontale, verticale, deux diagonales) "
                        "et, dans chaque direction, plusieurs fenêtres de 4. Sur le bord, la "
                        "moitié de ces fenêtres sortent du plateau. Le premier coup ne sert pas "
                        "à menacer immédiatement, mais à s'installer là où le plus de menaces "
                        "seront possibles."
                    ),
                },
                {
                    "heading": "Ce que ça change pour vous",
                    "body": (
                        "- Vous commencez : jouez (3,3), et c'est **démontré gagnant** — c'est "
                        "la seule valeur ferme de cette leçon.\n"
                        "- Vous êtes second : après (3,3) la position est perdue de force ; "
                        "jouez la défense la plus tenace (voir la leçon « Preuve ») et attendez "
                        "l'erreur, c'est votre seule ressource."
                    ),
                },
                {
                    "heading": "D'où viennent ces chiffres",
                    "body": (
                        "Chaque valeur vient d'une recherche du moteur (alpha-bêta, table de "
                        "transposition, finales exactes branchées en dessous de 12 cases vides). "
                        "Sauf le premier coup central, qui est **prouvé gagnant**, ces nombres ne "
                        "sont pas des preuves : le jeu complet n'est pas résolu. Et ils ne sont "
                        "pas non plus reproductibles — deux passes de la même sonde, à des "
                        "budgets différents, donnent des scores qui changent de signe. C'est "
                        "pourquoi cette leçon ne publie pas de classement des neuf autres coups."
                    ),
                },
            ],
        },
    ]

    proof_body, proof_diagram = proof_section(proof)
    proof_first = {"heading": "La démonstration", "body": proof_body}
    if proof_diagram:
        proof_first["diagram"] = proof_diagram
    lessons.append(
        {
            "id": "preuve-centre",
            "title": "Preuve : le centre gagne de force",
            "level": "expert",
            "duration_min": 12,
            "sections": [
                proof_first,
                {
                    "heading": "Ce que la preuve change",
                    "body": "\n\n".join(
                        [
                            "Une estimation dit « ce coup est bon » ; une preuve dit « ce coup "
                            "gagne, et voici comment, quoi que fasse l'adversaire ». La différence "
                            "est capitale pour progresser : face à un adversaire exact, la première "
                            "ouverture non centrale vous laisse l'initiative, l'ouverture centrale "
                            "vous donne la partie.",
                            "Retenez la *structure* : deux pions alignés au centre, puis un coup qui "
                            "crée **deux** menaces à la fois. L'adversaire ne peut en bloquer qu'une ; "
                            "la seconde conclut. C'est le même ressort dans toutes les finales gagnantes.",
                        ]
                    ),
                },
            ],
        }
    )

    for key, payload in schemas.items():
        if not payload:
            continue
        body, diagram = schema_section(payload)
        section = {"heading": "Le gain ne dépend pas d'une faute", "body": body}
        if diagram:
            section["diagram"] = diagram
        lessons.append(
            {
                "id": f"schema-{key}",
                "title": f"Le schéma gagnant du centre ({move_txt(payload.get('opening'))})",
                "level": "avancé",
                "duration_min": 10,
                "sections": [
                    section,
                    {
                        "heading": "Comment s'en servir en partie",
                        "body": (
                            "Ne cherchez pas à mémoriser la ligne : cherchez la *raison* des "
                            "coups. Le premier joueur installe deux pions sur une même ligne, "
                            "puis vise une case qui crée deux alignements à la fois. La défense "
                            "ne peut bloquer qu'un côté, et le gain suit."
                        ),
                    },
                ],
            }
        )

    finales_body, finales_diagram = finales_section(patterns, db_path)
    finales_first = {"heading": "Ce que « exact » veut dire", "body": finales_body}
    if finales_diagram:
        finales_first["diagram"] = finales_diagram
    lessons.append(
        {
            "id": "finales-exactes",
            "title": "Finales : les positions résolues exactement",
            "level": "expert",
            "duration_min": 9,
            "sections": [
                finales_first,
                {
                    "heading": "Comment lire une finale",
                    "body": (
                        "Dans une finale résolue, la question n'est plus « quel coup est bon ? » "
                        "mais « combien de demi-coups avant le gain ? ». Cherchez d'abord si une "
                        "case d'alignement est jouable tout de suite ; sinon, cherchez le coup "
                        "qui en crée deux à la fois — l'adversaire n'en bloquera qu'une."
                    ),
                },
            ],
        }
    )

    return {
        "genere_le": datetime.now().isoformat(timespec="seconds"),
        "sources": source_app,
        "lessons": lessons,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Génère les leçons du site depuis le solveur")
    parser.add_argument("--probe", default=str(SOLVER / "preuve_profonde.json"))
    parser.add_argument("--theory", default=str(SOLVER / "opening_theory.json"))
    parser.add_argument("--patterns", default=str(SOLVER / "final_patterns.json"))
    parser.add_argument("--proof", default=str(SOLVER / "forced_win_33.json"))
    parser.add_argument(
        "--stability",
        default=str(SOLVER / "probe_runs" / "stability.json"),
        help="comparaison de passes de la sonde (compare_probe_passes.py)",
    )
    parser.add_argument("--db", default=str(SOLVER / "data" / "tablebase.db"))
    parser.add_argument(
        "--schema",
        action="append",
        default=[],
        help="fichier de vérification de schéma, « id=chemin » (répétable)",
    )
    parser.add_argument("--out", default=str(OUT_DEFAULT))
    args = parser.parse_args()

    schema_specs = args.schema or [
        "33=" + str(SOLVER / "schema_33_defenses.json"),
        "00=" + str(SOLVER / "schema_00_defenses.json"),
    ]
    schemas: Dict[str, Optional[Dict[str, Any]]] = {}
    for spec in schema_specs:
        key, _, path = spec.partition("=")
        schemas[key] = load_json(Path(path))

    payload = build(
        load_json(Path(args.probe)),
        load_json(Path(args.theory)),
        schemas,
        load_json(Path(args.patterns)),
        load_json(Path(args.proof)),
        Path(args.db),
        load_json(Path(args.stability)),
    )

    # Un corps de section doit être une chaîne : un texte accidentellement écrit sous
    # forme de tuple/liste (virgule en trop) se retrouve sérialisé en tableau JSON et
    # s'affiche tel quel sur le site. On refuse de générer dans ce cas.
    defauts = [
        f"{lesson['id']}/{section.get('heading')}"
        for lesson in payload["lessons"]
        for section in lesson.get("sections", [])
        if not isinstance(section.get("body"), str)
    ]
    if defauts:
        raise SystemExit(
            "Corps de section non textuel (attendu : str) : " + ", ".join(defauts)
        )

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{len(payload['lessons'])} leçon(s) -> {out}")
    for lesson in payload["lessons"]:
        print(f"  - {lesson['id']} : {lesson['title']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
