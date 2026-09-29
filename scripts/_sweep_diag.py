"""Diagnostic de complétude de la couche 7 (espace board, joueur, dernier coup).

Objectif : comprendre pourquoi le balayage 7 → 8 ne résout presque rien. Pour un
échantillon de positions de la couche 7, on régénère leurs parents (couche 8) puis on
vérifie, enfant par enfant, s'il est présent dans la base **avec le dernier coup attendu**.

Trois verdicts par enfant manquant :
  - ``alias`` : le plateau de l'enfant est présent en base sous un autre dernier coup ;
  - ``trou``  : le plateau de l'enfant est totalement absent de la base ;
  - ``absent``: ni l'un ni l'autre (ne devrait pas arriver).

Reproduit fidèlement les règles de ``game.rs`` (voisinage du dernier coup, repli sur les
pions adverses) et le format ``board_blob`` (16 cases × 2 bits).
"""

from __future__ import annotations

import sqlite3
import sys
from collections import Counter
from pathlib import Path

N = 7
WIN = 4
DB = Path(__file__).resolve().parents[1] / "script" / "solver" / "data" / "tablebase.db"


def blob_of(cells: list[int]) -> bytes:
    out = bytearray(13)
    for idx, v in enumerate(cells):
        out[idx // 4] |= (v & 0b11) << ((idx % 4) * 2)
    return bytes(out)


def blob_to_cells(blob: bytes) -> list[int]:
    cells = []
    for idx in range(N * N):
        cells.append((blob[idx // 4] >> ((idx % 4) * 2)) & 0b11)
    return cells


def frontier(cells: list[int], lm: int | None, player: int) -> list[int]:
    if all(c == 0 for c in cells):
        return [i for i in range(N * N) if cells[i] == 0]
    valid: list[int] = []
    seen: set[int] = set()

    def add(i: int) -> None:
        if i not in seen:
            seen.add(i)
            valid.append(i)

    def neighbours(i: int, color: int, want_empty: bool) -> None:
        r0, c0 = divmod(i, N)
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if dr == 0 and dc == 0:
                    continue
                r, c = r0 + dr, c0 + dc
                if 0 <= r < N and 0 <= c < N:
                    j = r * N + c
                    if want_empty and cells[j] == 0:
                        add(j)
                    elif not want_empty and cells[j] == color:
                        pass

    if lm is not None:
        neighbours(lm, 0, True)
    if not valid:
        opp = 3 - player
        for i in range(N * N):
            if cells[i] == opp:
                neighbours(i, opp, True)
    return valid


def is_winning(cells: list[int], mv: int, player: int) -> bool:
    test = list(cells)
    test[mv] = player
    r0, c0 = divmod(mv, N)
    for dr, dc in ((0, 1), (1, 0), (1, 1), (1, -1)):
        count = 1
        for step in (1, -1):
            r, c = r0 + dr * step, c0 + dc * step
            while 0 <= r < N and 0 <= c < N and test[r * N + c] == player:
                count += 1
                r += dr * step
                c += dc * step
        if count >= WIN:
            return True
    return False


def is_connected(cells: list[int]) -> bool:
    stones = [i for i, c in enumerate(cells) if c != 0]
    if not stones:
        return True
    seen = {stones[0]}
    stack = [stones[0]]
    while stack:
        i = stack.pop()
        r0, c0 = divmod(i, N)
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if dr == 0 and dc == 0:
                    continue
                r, c = r0 + dr, c0 + dc
                if 0 <= r < N and 0 <= c < N:
                    j = r * N + c
                    if cells[j] != 0 and j not in seen:
                        seen.add(j)
                        stack.append(j)
    return len(seen) == len(stones)


def main() -> int:
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    try:
        rows = conn.execute(
            "select board_blob, current_player, pos_last_move_row, pos_last_move_col"
            " from positions where empty_cells=7 order by hash limit ?",
            (250,),
        ).fetchall()

        layer7: set[tuple[bytes, int, int | None]] = set()
        blob_cache = {b for (b, _, _, _) in rows}
        parent_jobs = []
        for blob, player, lmr, lmc in rows:
            cells = blob_to_cells(blob)
            if lmr is None or lmc is None:
                continue
            lmr, lmc = int(lmr), int(lmc)
            if not (0 <= lmr < N and 0 <= lmc < N):
                continue
            lmi = lmr * N + lmc
            mover = cells[lmi]
            if mover == 0 or mover != 3 - player:
                continue
            parent = list(cells)
            parent[lmi] = 0
            if not is_connected(parent):
                continue
            parent_player = mover
            for j in range(N * N):
                if parent[j] != 3 - parent_player:
                    continue
                lm2 = (j,)
                if lmi in frontier(parent, j, parent_player):
                    parent_jobs.append((tuple(parent), parent_player, j))

        print(f"Couche 7 : {len(rows)} lignes lues | {len(parent_jobs)} parents générés")

        # Première passe : énumérer les enfants de chaque parent (ordre identique à
        # `resolve_via_children`) et collecter les plateaux à vérifier.
        plans: list[tuple[tuple[int, ...], int, list[int]]] = []
        for parent, player, plm in parent_jobs:
            order = frontier(list(parent), plm, player)
            plans.append((parent, player, order))
            for mv in order:
                if not is_winning(list(parent), mv, player):
                    child = list(parent)
                    child[mv] = player
                    blob_cache.add(blob_of(child))

        # Chargement en masse des plateaux enfants présents en base.
        known: dict[tuple[bytes, int], set[int]] = {}
        blobs = sorted(blob_cache)
        for start in range(0, len(blobs), 400):
            chunk = blobs[start : start + 400]
            marks = ",".join("?" * len(chunk))
            q = (
                f"select board_blob, current_player, pos_last_move_row, pos_last_move_col"
                f" from positions where board_blob in ({marks})"
            )
            for blob, player, lmr, lmc in conn.execute(q, chunk):
                if lmr is None or lmc is None:
                    lm = None
                elif 0 <= int(lmr) < N and 0 <= int(lmc) < N:
                    lm = int(lmr) * N + int(lmc)
                else:
                    lm = None
                known.setdefault((blob, player), set()).add(lm)

        # Seconde passe : reproduire exactement la sémantique du solveur Rust.
        stats = Counter()
        samples = []
        for parent, player, order in plans:
            for mv in order:
                if is_winning(list(parent), mv, player):
                    stats["resolu_coup_gagnant"] += 1
                    break
                child = list(parent)
                child[mv] = player
                variants = known.get((blob_of(child), 3 - player))
                if variants is not None and mv in variants:
                    continue
                # Premier enfant manquant rencontré : Rust renvoie None ici.
                stats["parent_irresoluble"] += 1
                if variants is None:
                    stats["trou"] += 1
                    kind = "trou"
                else:
                    stats["alias"] += 1
                    kind = "alias"
                if len(samples) < 5:
                    samples.append((kind, child, 3 - player, mv))
                break
            else:
                stats["resolu_tous_enfants"] += 1

        print(f"Enfants uniques examinés : {len(known)}")
        for k, v in stats.most_common():
            print(f"  {k:>8} : {v}")
        for kind, child, player, mv in samples:
            print(f"  exemple {kind}: joueur {player}, coup attendu {divmod(mv, N)}")
            for r in range(N):
                print("      " + " ".join(".XO"[child[r * N + c]] for c in range(N)))
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
