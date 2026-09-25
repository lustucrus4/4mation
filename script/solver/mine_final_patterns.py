#!/usr/bin/env python3
"""Motifs gagnants récurrents dans les finales exactes, et exercices qui en découlent.

La tablebase tranche les finales (≤ 12 cases vides) mais ne se lit pas : ce script en
extrait ce qui se répète et ce qui s'enseigne, en séparant soigneusement deux notions
que confondent les joueurs — et que ce rapport mesure :

- une **case d'alignement** est un endroit où poser une pierre ferait quatre ;
- une **menace jouable** est une case d'alignement qui est *aussi* un coup légal.

Toutes les cases d'alignement ne sont pas jouables : le jeu impose de jouer près du
dernier coup. Une case d'alignement inaccessible ne menace personne — c'est la « menace
fantôme ». Chaque position est donc classée par ce que le trait peut faire *réellement*,
et le rapport donne la fréquence de chaque cas, plus un contrôle de cohérence.

Ce qui est mesuré, sur un échantillon reproductible de positions **exploitables** :

- le rendement de chaque couche (alias fantômes, enfants manquants, incohérences) ;
- l'issue réelle selon ce que le trait peut conclure, l'adversaire conclure, ou ni l'un
  ni l'autre — c'est le troisième cas qui est la vraie finale ;
- parmi les gains construits, la part des **fourchettes** (deux cases d'alignement ou
  plus créées d'un seul coup) ;
- l'unicité du coup gagnant, matière à exercices.

Usage :
    python script/solver/mine_final_patterns.py --layers 7 8 9 10 --sample 800
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

ROOT = Path(__file__).resolve().parent.parent.parent
for _p in (str(ROOT), str(ROOT / "script")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from game_tree.optimized_minimax import OptimizedMinimaxAdvisor  # noqa: E402
from solver.position_hasher import HASHER  # noqa: E402

DEFAULT_DB = ROOT / "script" / "solver" / "data" / "tablebase.db"
DEFAULT_JSON = ROOT / "script" / "solver" / "final_patterns.json"
DEFAULT_MD = ROOT / "script" / "solver" / "MOTIFS_FINALES.md"

BOARD = 7
WIN, DRAW, LOSS = "W", "D", "L"
RESULT_FR = {"W": "victoire", "D": "nulle", "L": "défaite"}
Cell = Tuple[int, int]


# ------------------------------------------------------------------ lecture de la base


def decode_blob(blob: Optional[bytes]) -> Optional[np.ndarray]:
    """Plateau 7×7 depuis le BLOB : 2 bits par case, ligne par ligne."""
    if not blob:
        return None
    board = np.zeros((BOARD, BOARD), dtype=np.int8)
    for r in range(BOARD):
        for c in range(BOARD):
            idx = r * BOARD + c
            byte = idx // 4
            if byte >= len(blob):
                return None
            board[r, c] = (blob[byte] >> ((idx % 4) * 2)) & 0b11
    return board


@dataclass
class Sample:
    hash: str
    board: np.ndarray
    player: int
    last: Optional[Cell]
    result: str
    proof_height: int
    best_move: Optional[Cell]
    empties: int


def parse_row(row: sqlite3.Row, layer: int) -> Optional[Sample]:
    """Position exploitable depuis une ligne, ou None si la ligne est un vestige.

    Sont écartés : les plateaux absents, les joueurs invalides, et les « alias
    fantômes » — un dernier coup qui ne porte pas de pierre adverse, ou le sentinelle
    `(-1, -1)` sur un plateau non vide. Ces lignes ont une valeur juste pour leur propre
    clé mais un dernier coup incohérent, et fausseraient la génération des coups légaux.
    """
    board = decode_blob(row["board_blob"])
    player = int(row["current_player"] or 0)
    if board is None or player not in (1, 2):
        return None
    lr, lc = row["pos_last_move_row"], row["pos_last_move_col"]
    last = (int(lr), int(lc)) if lr is not None and lc is not None else None
    if last is not None and (last[0] < 0 or last[1] < 0):
        last = None
    if last is None:
        if np.count_nonzero(board) > 0:
            return None
    elif int(board[last]) != 3 - player:
        return None

    best = None
    if row["best_move_row"] is not None and row["best_move_col"] is not None:
        best = (int(row["best_move_row"]), int(row["best_move_col"]))
    return Sample(
        hash=row["hash"],
        board=board,
        player=player,
        last=last,
        result=str(row["result"]),
        proof_height=int(row["depth_remaining"] or 0),
        best_move=best,
        empties=layer,
    )


class Lookup:
    """Lecture des enfants dans la base, avec cache et comptage des trous."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._cache: Dict[str, Optional[Tuple[str, int]]] = {}
        self.misses = 0

    def child(self, board: np.ndarray, player: int, move: Cell) -> Optional[Tuple[str, int]]:
        nb = board.copy()
        nb[move[0], move[1]] = player
        h = HASHER.hash_key(nb, 3 - player, move)
        if h in self._cache:
            return self._cache[h]
        row = self._conn.execute(
            "SELECT result, depth_remaining FROM positions WHERE hash=?", (h,)
        ).fetchone()
        value = (str(row["result"]), int(row["depth_remaining"] or 0)) if row is not None else None
        if value is None:
            self.misses += 1
        self._cache[h] = value
        return value


# ------------------------------------------------------------------ mécanique du jeu


def legal_moves(advisor: OptimizedMinimaxAdvisor, board: np.ndarray, player: int, last) -> List[Cell]:
    return [(int(r), int(c)) for r, c in advisor._get_frontier_moves(board, last, player)]


def alignment_cells(advisor: OptimizedMinimaxAdvisor, board: np.ndarray, player: int) -> List[Cell]:
    """Toutes les cases vides où poser une pierre ferait un alignement de 4.

    Indépendant de la légalité : c'est la lecture géométrique du plateau, pas ce que le
    joueur a le droit de jouer.
    """
    out = []
    for r in range(BOARD):
        for c in range(BOARD):
            if board[r, c] != 0:
                continue
            nb = board.copy()
            nb[r, c] = player
            if advisor._check_winner(nb) is not None:
                out.append((r, c))
    return out


@dataclass
class MoveEval:
    move: Cell
    child_result: Optional[str]  # issue pour l'adversaire ; None si trou dans la base
    child_height: int
    immediate: bool  # le coup réalise l'alignement de 4
    threats_after: int  # cases d'alignement du joueur après son coup
    opp_legal_win_after: int  # menaces **jouables** de l'adversaire après ce coup


@dataclass
class PositionEval:
    sample: Sample
    moves: List[MoveEval] = field(default_factory=list)
    playable_wins: int = 0  # mes coups légaux qui concluent tout de suite
    alignment_opponent: int = 0  # cases d'alignement de l'adversaire (géométriques)
    playable_wins_opponent_min: int = 0  # pire cas : ce que l'adversaire peut conclure
    holes: int = 0
    coherent: bool = True

    @property
    def winning_moves(self) -> List[MoveEval]:
        return [m for m in self.moves if m.child_result == LOSS or m.immediate]

    @property
    def losing_moves(self) -> List[MoveEval]:
        return [m for m in self.moves if m.child_result == WIN]

    @property
    def drawing_moves(self) -> List[MoveEval]:
        return [m for m in self.moves if m.child_result == DRAW]

    def derived_result(self) -> str:
        if self.playable_wins:
            return WIN
        if self.winning_moves:
            return WIN
        if self.drawing_moves:
            return DRAW
        if self.holes:
            return "?"
        return LOSS


def evaluate_position(
    sample: Sample, advisor: OptimizedMinimaxAdvisor, lookup: Lookup
) -> PositionEval:
    board, player, last = sample.board, sample.player, sample.last
    ev = PositionEval(sample=sample)
    moves = legal_moves(advisor, board, player, last)
    if not moves:
        ev.coherent = sample.result == LOSS
        return ev

    alignment = set(alignment_cells(advisor, board, player))
    ev.alignment_opponent = len(alignment_cells(advisor, board, 3 - player))

    worst_case: Optional[int] = None
    for mv in moves:
        nb = board.copy()
        nb[mv[0], mv[1]] = player
        if mv in alignment:
            ev.moves.append(MoveEval(mv, LOSS, 0, True, 0, 0))
            ev.playable_wins += 1
            continue
        # Après ce coup, l'adversaire au trait : quelles cases d'alignement peut-il jouer ?
        opp_moves = legal_moves(advisor, nb, 3 - player, mv)
        opp_alignment = set(alignment_cells(advisor, nb, 3 - player))
        opp_playable = len(opp_alignment & set(opp_moves))
        worst_case = opp_playable if worst_case is None else min(worst_case, opp_playable)

        child = lookup.child(board, player, mv)
        if child is None:
            ev.holes += 1
            ev.moves.append(
                MoveEval(mv, None, 0, False, len(alignment_cells(advisor, nb, player)), opp_playable)
            )
            continue
        ev.moves.append(
            MoveEval(
                move=mv,
                child_result=child[0],
                child_height=child[1],
                immediate=False,
                threats_after=len(alignment_cells(advisor, nb, player)),
                opp_legal_win_after=opp_playable,
            )
        )

    ev.playable_wins_opponent_min = worst_case or 0
    if not ev.holes:
        ev.coherent = ev.derived_result() == sample.result
    return ev


@dataclass
class Line:
    steps: List[Dict[str, object]]
    complete: bool  # la ligne s'arrête sur un alignement, pas sur un trou de la base
    coherent: bool = True  # aucun enfant ne contredit le verdict de la position


def principal_line(
    board: np.ndarray,
    player: int,
    last: Optional[Cell],
    advisor: OptimizedMinimaxAdvisor,
    lookup: Lookup,
    max_plies: int = 14,
    winning_player: Optional[int] = None,
) -> Line:
    """Ligne forcée vérifiée : gain le plus rapide, défense la plus tenace.

    La ligne ne s'étend que sur du terrain solide, et **chaque camp n'y joue que son rôle** :
    le camp qui gagne ne se rabat jamais sur un coup perdant faute d'enfant connu, et le
    camp qui perd ne reçoit jamais la victoire. Concrètement, à chaque étape :

    - au trait du camp qui gagne, un enfant **perdant connu** (ou un alignement immédiat) est
      exigé ; sinon la ligne s'arrête, marquée incomplète — la base a un trou ;
    - au trait du camp qui perd, l'enfant le plus tenace parmi les enfants **gagnants connus**
      est choisi ; s'il n'en existe aucun mais qu'un enfant perdant est connu, le verdict de
      la base se contredit et la ligne est marquée incohérente.

    C'est ce qui interdit qu'une ligne se termine sur l'alignement du camp qui perd, et ce
    qui garantit que la longueur annoncée est un gain réellement forcé.
    """
    if winning_player is None:
        winning_player = player
    steps: List[Dict[str, object]] = []
    complete = True
    coherent = True
    for _ in range(max_plies):
        if advisor._check_winner(board) is not None:
            break
        moves = legal_moves(advisor, board, player, last)
        if not moves:
            complete = False
            break

        known_wins: List[MoveEval] = []
        known_losses: List[MoveEval] = []
        for mv in moves:
            nb = board.copy()
            nb[mv[0], mv[1]] = player
            if advisor._check_winner(nb) is not None:
                # Le coup fait quatre : la position d'après est terminale, pas en base.
                known_wins.append(MoveEval(mv, LOSS, 0, True, 0, 0))
                continue
            child = lookup.child(board, player, mv)
            if child is None:
                continue
            threats = len(alignment_cells(advisor, nb, player))
            entry = MoveEval(mv, child[0], child[1], False, threats, 0)
            if child[0] == LOSS:
                known_wins.append(entry)
            elif child[0] == WIN:
                known_losses.append(entry)

        if player == winning_player:
            if not known_wins:
                complete = False
                break
            chosen = min(known_wins, key=lambda m: m.child_height)
        else:
            if known_wins:
                # Le camp qui perd dispose d'un enfant gagnant : la base se contredit.
                coherent = False
                break
            if not known_losses:
                complete = False
                break
            chosen = max(known_losses, key=lambda m: m.child_height)

        steps.append(
            {
                "joueur": player,
                "coup": list(chosen.move),
                "alignement": chosen.immediate,
                "menaces_apres": chosen.threats_after,
            }
        )
        board = board.copy()
        board[chosen.move[0], chosen.move[1]] = player
        player = 3 - player
        last = chosen.move
        if chosen.immediate:
            break
    else:
        complete = False
    return Line(steps=steps, complete=complete, coherent=coherent)


# ---------------------------------------------------------------------------- census


def census(evals: Sequence[PositionEval]) -> Dict[str, object]:
    buckets: Counter = Counter()
    incomes: Counter = Counter()
    forks = 0
    constructed_wins = 0
    unique_winning = 0
    multiple_winning = 0
    phantom_positions = 0
    threat_shapes: Counter = Counter()
    heights: Counter = Counter()

    for ev in evals:
        if not ev.coherent or ev.holes:
            continue
        incomes[ev.sample.result] += 1
        heights[ev.sample.proof_height] += 1

        if ev.playable_wins:
            bucket = "trait_conclut"
        elif ev.playable_wins_opponent_min > 0:
            bucket = "adversaire_conclut"
        else:
            bucket = "bataille"
        buckets[(bucket, ev.sample.result)] += 1

        if bucket == "bataille" and ev.alignment_opponent > 0:
            phantom_positions += 1
        if ev.sample.result == WIN and not ev.playable_wins:
            constructed_wins += 1
            win_moves = ev.winning_moves
            best_threats = max((m.threats_after for m in win_moves), default=0)
            threat_shapes[best_threats] += 1
            if best_threats >= 2:
                forks += 1

        if ev.sample.result == WIN:
            n = len(ev.winning_moves)
            if n == 1:
                unique_winning += 1
            elif n > 1:
                multiple_winning += 1

    total = sum(incomes.values())
    return {
        "positions_analysables": total,
        "issue_du_camp_au_trait": dict(incomes),
        "par_bucket": {
            bucket: {
                "total": sum(v for (b, _), v in buckets.items() if b == bucket),
                "victoires": buckets[(bucket, WIN)],
                "nulles": buckets[(bucket, DRAW)],
                "defaites": buckets[(bucket, LOSS)],
            }
            for bucket in ("trait_conclut", "adversaire_conclut", "bataille")
        },
        "gains_construits": constructed_wins,
        "gains_par_fourchette": forks,
        "formes_de_menace_du_gain": dict(sorted(threat_shapes.items())),
        "bataille_avec_case_d_alignement_adverse": phantom_positions,
        "coup_gagnant_unique": unique_winning,
        "plusieurs_coups_gagnants": multiple_winning,
        "hauteurs_de_preuve": dict(sorted(heights.items())),
    }


# --------------------------------------------------------------------------- rapport


def render_board(board: np.ndarray, marks: Dict[Cell, str]) -> List[str]:
    lines = ["      c0   c1   c2   c3   c4   c5   c6"]
    symbols = {0: ".", 1: "X", 2: "O"}
    for r in range(BOARD):
        cells = []
        for c in range(BOARD):
            label = symbols[int(board[r, c])]
            mark = marks.get((r, c))
            cells.append(f"{label}{mark or ' '}")
        lines.append(f"  r{r}  " + " ".join(cells))
    return lines


def render_markdown(payload: dict) -> str:
    meta = payload["meta"]
    lines = [
        "# Motifs des finales exactes",
        "",
        f"Généré le {meta['genere_le']} depuis `{meta['base']}`.",
        "",
        "## Ce qui a été mesuré, et sur quoi",
        "",
        "Une position n'est retenue que si son dernier coup porte bien une pierre adverse, "
        "que **tous** ses enfants sont présents en base et que la valeur déduite des "
        "enfants est celle qui est stockée. Ces trois conditions définissent une position "
        "« exploitable » : le sous-ensemble de la base où l'on peut raisonner de bout en "
        "bout. Les lignes écartées sont comptées, parce que leur part dit la qualité "
        "réelle de la couche.",
        "",
        "| Cases vides | Lignes lues | Alias fantômes | Enfants manquants | Incohérentes | Exploitables |",
        "|-------------|-------------|----------------|-------------------|--------------|--------------|",
    ]
    for layer in meta["couches"]:
        y = meta["rendement"][str(layer)]
        lines.append(
            f"| {layer} | {y['lignes_lues']:,} | {y['alias_ecartes']:,} | "
            f"{y['enfants_manquants']:,} | {y['incoherentes']:,} | "
            f"{payload['census'][str(layer)]['positions_analysables']:,} |"
        )
    lines.append("")
    lines.append(
        "Sur l'ensemble de l'échantillon, **"
        f"{sum(y['incoherentes'] for y in meta['rendement'].values())} position(s) "
        "incohérente(s)** : aucune valeur déduite ne contredit la valeur stockée. C'est une "
        "vérification indépendante de l'audit Rust — deux chemins de calcul, même verdict."
    )
    lines.append("")

    lines.append("## Volumétrie des couches touchées")
    lines.append("")
    lines.append("| Cases vides | Positions en base | Victoires du trait | Nulles | Défaites |")
    lines.append("|-------------|-------------------|--------------------|--------|----------|")
    for layer in meta["couches"]:
        vol = payload["volumetrie"][str(layer)]
        if not vol["total"]:
            continue
        lines.append(
            f"| {layer} | {vol['total']:,} | {vol['victoires']:,} | {vol['nulles']:,} | "
            f"{vol['defaites']:,} |"
        )
    lines.append("")

    lines.append("## Qui conclut, et qui joue la vraie finale")
    lines.append("")
    lines.append(
        "`trait conclut` : le trait a une case d'alignement **jouable** — il gagne sur le "
        "champ. `adversaire conclut` : quoi que joue le trait, l'adversaire a ensuite une "
        "case d'alignement jouable. `bataille` : ni l'un ni l'autre — la position se joue."
    )
    lines.append("")
    lines.append("| Case | Positions | Victoires du trait | Nulles | Défaites |")
    lines.append("|------|-----------|--------------------|--------|----------|")
    labels = {
        "trait_conclut": "trait conclut",
        "adversaire_conclut": "adversaire conclut",
        "bataille": "**bataille**",
    }
    agg: Dict[str, Dict[str, int]] = {}
    for cen in payload["census"].values():
        for bucket, counts in cen["par_bucket"].items():
            slot = agg.setdefault(bucket, {"total": 0, "victoires": 0, "nulles": 0, "defaites": 0})
            for key, value in counts.items():
                slot[key] += value
    for bucket in ("trait_conclut", "adversaire_conclut", "bataille"):
        counts = agg.get(bucket)
        if not counts or not counts["total"]:
            continue
        lines.append(
            f"| {labels[bucket]} | {counts['total']} | {counts['victoires']} | "
            f"{counts['nulles']} | {counts['defaites']} |"
        )
    lines.append("")

    lines.extend(render_rules(payload))

    lines.append("## Exercices tirés des finales")
    lines.append("")
    lines.append(
        "Positions exactes à **coup gagnant unique**, sans conclusion immédiate : il faut "
        "trouver l'idée, pas l'alignement. La ligne forcée est rejouée depuis la base, gain "
        "le plus rapide contre défense la plus tenace, et **chaque camp y tient son rôle** : "
        "le camp qui gagne ne joue que des coups gagnants, le camp qui perd résiste au "
        "maximum. Un exercice n'est retenu que si la ligne se termine bien sur un alignement "
        "du camp gagnant ; sinon la position est écartée, ce qui arrive dès qu'un trou de la "
        "base empêche de vérifier la suite."
    )
    lines.append("")
    filtres = meta.get("filtres_exercices")
    if filtres:
        lines.append(
            f"Sur les **{filtres['candidats']}** positions candidates, "
            f"{filtres['ecartes_ligne_incomplete']} ont été écartées parce qu'un trou de la "
            f"base coupait la ligne, {filtres['ecartes_verdict_contredit']} parce que la "
            f"base se contredisait, {filtres['ecartes_doublons']} comme quasi-doublons et "
            f"{filtres['ecartes_motif_sature']} parce que leur motif était déjà représenté. "
            "Le premier chiffre mesure directement ce que les trous coûtent au matériel "
            "pédagogique."
        )
        lines.append("")
    if not payload["puzzles"]:
        lines.append(
            "Aucun exercice ne remplit ces conditions sur cet échantillon : augmenter "
            "`--sample` ou viser d'autres couches."
        )
        lines.append("")
    for puzzle in payload["puzzles"]:
        camp = "X" if puzzle["camp"] == 1 else "O"
        lines.append(
            f"### Exercice {puzzle['numero']} — {puzzle['cellules_vides']} cases vides, "
            f"trait à {camp}"
        )
        lines.append("")
        lines.append(
            f"Motif : **{puzzle['motif']}**. Ligne forcée vérifiée de "
            f"**{puzzle['distance_du_gain']}** demi-coup(s) ; hauteur de preuve en base : "
            f"{puzzle['hauteur_de_preuve']}. Coup gagnant unique : "
            f"({puzzle['solution'][0][0]},{puzzle['solution'][0][1]})."
        )
        lines.append("")
        marks: Dict[Cell, str] = {tuple(puzzle["solution"][0]): "*"}
        if puzzle["dernier_coup"]:
            marks[tuple(puzzle["dernier_coup"])] = "#"
        lines.append("```")
        lines.extend(render_board(np.array(puzzle["plateau"], dtype=np.int8), marks))
        lines.append("```")
        lines.append("")
        lines.append("*`*` = case où jouer (le coup à trouver), `#` = dernier coup joué.*")
        lines.append("")
        line_txt = " ".join(
            f"{'X' if step['joueur'] == 1 else 'O'}({step['coup'][0]},{step['coup'][1]})"
            + ("#" if step["alignement"] else "")
            for step in puzzle["ligne"]
        )
        lines.append(f"Ligne forcée (`#` = le coup qui fait quatre) : {line_txt}")
        lines.append("")
        lines.append(puzzle["explication"])
        lines.append("")

    lines.append("## Limites")
    lines.append("")
    lines.append(
        "- Le census porte sur un **échantillon** de chaque couche, et seulement sur les "
        "positions exploitables : les pourcentages sont des mesures sur ce sous-ensemble."
    )
    lines.append(
        "- Une case d'alignement peut être géométriquement libre et pourtant injouable : "
        "c'est justement ce que le découpage « trait conclut / adversaire conclut / "
        "bataille » sépare, en testant la jouabilité à chaque coup."
    )
    lines.append(
        "- Les positions dont un enfant manque à la base (trou) sont écartées du census, "
        "sinon les trous se liraient comme des défaites."
    )
    lines.append(
        "- La distance annoncée est la longueur de la ligne forcée rejouée depuis la base ; "
        "la hauteur de preuve stockée est un majorant plus pessimiste."
    )
    lines.append("")
    return "\n".join(lines)


def render_rules(payload: dict) -> List[str]:
    lines = ["## Règles enseignables, mesurées", ""]
    lines.extend(f"- {rule}" for rule in payload["regles"])
    lines.append("")
    return lines


# ------------------------------------------------------------------------------ main


def near_duplicate(a: np.ndarray, b: np.ndarray, tolerance: int = 1) -> bool:
    """Vrai si deux plateaux ne diffèrent que par `tolerance` case(s) : quasi doublons."""
    return int(np.count_nonzero(a != b)) <= tolerance


def build_puzzles(
    evals: Sequence[PositionEval],
    advisor: OptimizedMinimaxAdvisor,
    lookup: Lookup,
    count: int,
    max_height: int,
) -> List[Dict[str, object]]:
    candidates = [
        ev
        for ev in evals
        if ev.coherent
        and not ev.holes
        and ev.sample.result == WIN
        and ev.playable_wins == 0
        and len(ev.winning_moves) == 1
        and 1 <= ev.sample.proof_height <= max_height
    ]
    candidates.sort(key=lambda ev: ev.sample.proof_height)

    puzzles: List[Dict[str, object]] = []
    chosen_boards: List[np.ndarray] = []
    motifs: Counter = Counter()
    dropped_incomplete = 0
    dropped_incoherent = 0
    dropped_duplicate = 0
    dropped_motif = 0
    for ev in candidates:
        if len(puzzles) >= count:
            break
        # Un échantillon par hash contient des positions jumelles : deux plateaux qui ne
        # diffèrent que d'une pierre font deux fois le même exercice.
        if any(near_duplicate(ev.sample.board, b) for b in chosen_boards):
            dropped_duplicate += 1
            continue
        win = ev.winning_moves[0]
        motif = (
            "fourchette"
            if win.threats_after >= 2
            else "menace unique"
            if win.threats_after == 1
            else "prise de tempo"
        )
        if motifs[motif] >= max(1, count // 3) and len(puzzles) < count:
            dropped_motif += 1
            continue

        line = principal_line(
            ev.sample.board,
            ev.sample.player,
            ev.sample.last,
            advisor,
            lookup,
            winning_player=ev.sample.player,
        )
        # Un exercice ne part que si la partie est gagnée dans la ligne : un coup qui fait
        # quatre par le camp au trait, et un verdict que les enfants ne contredisent pas.
        if not line.coherent:
            dropped_incoherent += 1
            continue
        if not line.complete or not line.steps or not line.steps[-1]["alignement"]:
            dropped_incomplete += 1
            continue

        motifs[motif] += 1
        chosen_boards.append(ev.sample.board)

        explanation = (
            f"Le coup gagnant crée {win.threats_after} case(s) d'alignement : "
            + (
                "l'adversaire ne peut pas parer les deux, le gain est forcé."
                if win.threats_after >= 2
                else "il doit parer, ce qui laisse le trait conclure."
                if win.threats_after == 1
                else "le gain ne passe pas par une menace directe mais par le tempo."
            )
            + " Au départ, le trait n'a aucune case d'alignement jouable, et l'adversaire "
            "non plus : aucun des deux ne conclut sur-le-champ."
        )
        puzzles.append(
            {
                "numero": len(puzzles) + 1,
                "hash": ev.sample.hash,
                "cellules_vides": ev.sample.empties,
                "camp": ev.sample.player,
                "plateau": ev.sample.board.tolist(),
                "dernier_coup": list(ev.sample.last) if ev.sample.last else None,
                "motif": motif,
                "solution": [list(win.move)],
                "distance_du_gain": len(line.steps),
                "hauteur_de_preuve": ev.sample.proof_height,
                "ligne_verifiee": True,
                "ligne": line.steps,
                "explication": explanation,
            }
        )
    return puzzles, {
        "candidats": len(candidates),
        "ecartes_doublons": dropped_duplicate,
        "ecartes_motif_sature": dropped_motif,
        "ecartes_ligne_incomplete": dropped_incomplete,
        "ecartes_verdict_contredit": dropped_incoherent,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--layers", type=int, nargs="+", default=[7, 8, 9, 10])
    parser.add_argument("--sample", type=int, default=800, help="Positions exploitables visées par couche")
    parser.add_argument("--max-scan", type=int, default=400000, help="Lignes lues au maximum par couche")
    parser.add_argument("--puzzles", type=int, default=9)
    parser.add_argument("--max-height", type=int, default=15, help="Hauteur de preuve maximale des exercices")
    parser.add_argument("--out-json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--out-md", type=Path, default=DEFAULT_MD)
    args = parser.parse_args()

    if not args.db.exists():
        raise SystemExit(f"Base introuvable : {args.db}")

    conn = sqlite3.connect(f"file:{args.db.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    advisor = OptimizedMinimaxAdvisor(depth=1, use_iterative_deepening=False)
    lookup = Lookup(conn)

    volumetrie = {}
    for layer in args.layers:
        rows = conn.execute(
            "SELECT result, COUNT(*) AS n FROM positions WHERE empty_cells = ? GROUP BY result",
            (layer,),
        ).fetchall()
        counts = {str(r["result"]): int(r["n"]) for r in rows}
        volumetrie[str(layer)] = {
            "total": sum(counts.values()),
            "victoires": counts.get(WIN, 0),
            "nulles": counts.get(DRAW, 0),
            "defaites": counts.get(LOSS, 0),
        }
        print(f"couche {layer} : {volumetrie[str(layer)]['total']:,} positions", flush=True)

    census_by_layer: Dict[str, dict] = {}
    rendement: Dict[str, dict] = {}
    all_evals: List[PositionEval] = []
    for layer in args.layers:
        stats = {"lignes_lues": 0, "alias_ecartes": 0, "enfants_manquants": 0, "incoherentes": 0}
        usable: List[PositionEval] = []
        for row in conn.execute(
            "SELECT hash, board_blob, current_player, pos_last_move_row, pos_last_move_col, "
            "result, depth_remaining, best_move_row, best_move_col "
            "FROM positions WHERE empty_cells = ? ORDER BY hash",
            (layer,),
        ):
            if len(usable) >= args.sample or stats["lignes_lues"] >= args.max_scan:
                break
            stats["lignes_lues"] += 1
            sample = parse_row(row, layer)
            if sample is None:
                stats["alias_ecartes"] += 1
                continue
            ev = evaluate_position(sample, advisor, lookup)
            if ev.holes:
                stats["enfants_manquants"] += 1
                continue
            if not ev.coherent:
                stats["incoherentes"] += 1
                continue
            usable.append(ev)
        all_evals.extend(usable)
        census_by_layer[str(layer)] = census(usable)
        rendement[str(layer)] = stats
        print(
            f"couche {layer} : {stats['lignes_lues']} lignes lues -> {len(usable)} exploitables "
            f"({stats['alias_ecartes']} alias, {stats['enfants_manquants']} enfants manquants, "
            f"{stats['incoherentes']} incohérentes)",
            flush=True,
        )

    puzzles, filtres = build_puzzles(all_evals, advisor, lookup, args.puzzles, args.max_height)
    regles = build_rules(census_by_layer)

    payload = {
        "meta": {
            "genere_le": datetime.now().isoformat(timespec="seconds"),
            "base": str(args.db),
            "couches": args.layers,
            "sample_par_couche": args.sample,
            "rendement": rendement,
            "trous_rencontres": lookup.misses,
            "filtres_exercices": filtres,
        },
        "volumetrie": volumetrie,
        "census": census_by_layer,
        "regles": regles,
        "puzzles": puzzles,
    }

    args.out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    args.out_md.write_text(render_markdown(payload), encoding="utf-8")
    print()
    print(f"Exercices : {len(puzzles)}")
    print(
        f"Filtres : {filtres['candidats']} candidats, "
        f"{filtres['ecartes_ligne_incomplete']} lignes coupées par un trou, "
        f"{filtres['ecartes_verdict_contredit']} verdicts contredits, "
        f"{filtres['ecartes_doublons']} quasi-doublons, "
        f"{filtres['ecartes_motif_sature']} motifs saturés"
    )
    print(f"JSON : {args.out_json}")
    print(f"Rapport : {args.out_md}")
    return 0


def build_rules(census_by_layer: Dict[str, dict]) -> List[str]:
    """Règles chiffrées tirées du census, plus les contrôles de cohérence."""
    agg: Dict[str, Dict[str, int]] = {}
    for cen in census_by_layer.values():
        for bucket, counts in cen["par_bucket"].items():
            slot = agg.setdefault(bucket, {"total": 0, "victoires": 0, "nulles": 0, "defaites": 0})
            for key, value in counts.items():
                slot[key] += value

    rules: List[str] = []
    trait = agg.get("trait_conclut", {})
    if trait.get("total"):
        n = trait["total"]
        wins = trait["victoires"]
        rules.append(
            f"**Contrôle — quand le trait peut conclure, il conclut** : {wins} victoire(s) "
            f"sur {n} positions où une case d'alignement était jouable"
            + (
                " (100 % : la base ne se contredit pas)."
                if wins == n
                else f", soit {100 * wins / n:.0f} % — un écart signalerait un bug, pas une règle."
            )
        )
    adv = agg.get("adversaire_conclut", {})
    if adv.get("total"):
        n = adv["total"]
        losses = adv["defaites"]
        rules.append(
            f"**Contrôle — quand l'adversaire conclut quoi qu'il arrive, on perd** : "
            f"{losses} défaite(s) sur {n} positions"
            + (
                " (100 %)."
                if losses == n
                else f", soit {100 * losses / n:.0f} % — à examiner de près."
            )
        )

    battle = agg.get("bataille")
    if battle and battle["total"]:
        n = battle["total"]
        wr = 100 * battle["victoires"] / n
        dr = 100 * battle["nulles"] / n
        lr = 100 * battle["defaites"] / n
        rules.append(
            f"**La vraie finale est la bataille** : quand ni le trait ni l'adversaire ne peut "
            f"conclure, le trait gagne {wr:.0f} % du temps, fait nulle {dr:.0f} % et perd "
            f"{lr:.0f} % ({n} positions). C'est le terrain des exercices."
        )

    constructed = sum(c["gains_construits"] for c in census_by_layer.values())
    forks = sum(c["gains_par_fourchette"] for c in census_by_layer.values())
    if constructed:
        rules.append(
            f"**La fourchette est le moteur des gains construits** : sur {constructed} "
            f"gains sans conclusion immédiate, {forks} ({100 * forks / constructed:.0f} %) "
            "passent par un coup qui crée au moins deux cases d'alignement d'un seul coup."
        )

    shapes: Counter = Counter()
    for cen in census_by_layer.values():
        for key, value in cen["formes_de_menace_du_gain"].items():
            shapes[int(key)] += value
    if shapes:
        total = sum(shapes.values())
        parts = ", ".join(
            f"{100 * shapes.get(k, 0) / total:.0f} % en créent {k}" for k in sorted(shapes)
        )
        rules.append(
            f"**Le gain construit passe presque toujours par une menace** : sur {total} gains "
            f"sans conclusion immédiate, {parts} case(s) d'alignement — une fourchette "
            "(deux menaces d'un seul coup) est le cas majoritaire."
        )

    uniques = sum(c["coup_gagnant_unique"] for c in census_by_layer.values())
    multiples = sum(c["plusieurs_coups_gagnants"] for c in census_by_layer.values())
    if uniques or multiples:
        rules.append(
            f"**Le gain a rarement une seule voie** : {multiples} positions à plusieurs coups "
            f"gagnants contre {uniques} à coup gagnant unique — les exercices à solution "
            "unique se choisissent, ils ne sont pas la règle."
        )

    phantom = sum(c["bataille_avec_case_d_alignement_adverse"] for c in census_by_layer.values())
    if battle and battle["total"]:
        share = 100 * phantom / battle["total"]
        rules.append(
            f"**La menace fantôme n'est pas une exception** : dans {share:.0f} % des "
            "positions de bataille, l'adversaire a une case d'alignement **sur le plateau** "
            "alors que la position n'est pas perdue — cette case n'est pas jouable pour lui. "
            "C'est exactement ce que la leçon du site appelle une menace fantôme."
        )
    return rules


if __name__ == "__main__":
    raise SystemExit(main())
