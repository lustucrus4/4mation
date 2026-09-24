#!/usr/bin/env python3
"""Calibre l'échelle score → taux de victoire du moteur `4mation-engine`.

Le moteur renvoie un score entier, dont l'unité est la « menace immédiate » (voir
`evaluate` dans `engine.rs` : une menace vaut 60 points, une ligne potentielle 1, le
centre 3). Ce n'est pas un taux de victoire. Pour l'afficher dans le site (livre
d'ouverture, revue de partie) il faut une conversion, et la seule constante à choisir
est l'échelle de la sigmoïde :

    taux = 1 / (1 + exp(-score / échelle))

Ce script mesure cette échelle au lieu de la deviner. La vérité terrain est la
**tablebase exacte** : on tire des positions de finale (8 à 12 cases vides) dont le
résultat est prouvé (W/D/L), on demande au moteur son score **sans tablebase** (sinon
il lirait la réponse), et on cherche l'échelle qui prédit le mieux ces résultats.

    python script/solver/calibrate_engine_scale.py --samples 200 --depth 8

Le résultat est écrit dans `script/solver/data/engine_scale.json`, que l'API lit au
démarrage. Deux réserves, assumées et affichées dans le rapport :

- l'échelle est ajustée sur des finales, pas des milieux de partie ;
- la sigmoïde reste une convention d'affichage, pas un modèle probabiliste : elle sert
  à rendre les écarts de score lisibles, pas à mesurer une fréquence de victoire.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sqlite3
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT / "script") not in sys.path:
    sys.path.insert(0, str(ROOT / "script"))

from solver.db_schema import board_from_blob  # noqa: E402

DEFAULT_DB = ROOT / "script" / "solver" / "data" / "tablebase.db"
DEFAULT_OUT = ROOT / "script" / "solver" / "data" / "engine_scale.json"

# Cible de la sigmoïde pour chaque résultat prouvé de la tablebase.
TARGET = {"W": 1.0, "D": 0.5, "L": 0.0}

DEFAULT_SCALE = 120.0


def _binary() -> Path:
    name = "4mation-engine.exe" if sys.platform == "win32" else "4mation-engine"
    return ROOT / "script" / "solver_rust" / "target" / "release" / name


class RawEngine:
    """Moteur en sous-processus, protocole JSON ligne à ligne, sans tablebase."""

    def __init__(self, depth: int, tt_mb: int = 128) -> None:
        binary = _binary()
        if not binary.exists():
            raise SystemExit(
                f"Moteur introuvable : {binary}\n"
                "Compiler avec : cd script/solver_rust && cargo build --release"
            )
        # Volontairement PAS de `--tb` : le moteur doit estimer, pas lire la réponse.
        self.proc = subprocess.Popen(
            [str(binary), "--tt-mb", str(tt_mb), "--depth", str(depth), "--time-ms", "0"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            bufsize=1,
            cwd=str(ROOT),
        )
        self.depth = depth
        self.calls = 0

    def ask(self, board: Sequence[Sequence[int]], player: int, last_move: Optional[Tuple[int, int]]) -> Optional[Dict[str, Any]]:
        assert self.proc.stdin is not None and self.proc.stdout is not None
        req = {
            "board": [[int(c) for c in row] for row in board],
            "current_player": int(player),
            "last_move": [int(last_move[0]), int(last_move[1])] if last_move else None,
            "depth": self.depth,
            "time_ms": 0,
        }
        self.proc.stdin.write(json.dumps(req, separators=(",", ":")) + "\n")
        self.proc.stdin.flush()
        line = self.proc.stdout.readline()
        if not line:
            return None
        self.calls += 1
        return json.loads(line)

    def close(self) -> None:
        try:
            if self.proc.stdin:
                self.proc.stdin.write('{"type":"quit"}\n')
                self.proc.stdin.flush()
            self.proc.wait(timeout=3)
        except Exception:
            try:
                self.proc.kill()
            except Exception:
                pass


def sample_positions(
    conn: sqlite3.Connection,
    layers: Sequence[int],
    per_result: int,
    seed: int = 20260924,
) -> List[Dict[str, Any]]:
    """Échantillonne des positions prouvées, équilibrées par résultat (W/D/L).

    Les lignes sont tirées par `rowid` (accès direct, pas de tri aléatoire sur 24 M de
    lignes). Un même plateau apparaît plusieurs fois dans la base avec des `last_move`
    différents (alias) : on déduplique sur (plateau, joueur) pour ne pas pondérer
    artificiellement les mêmes positions.
    """
    rng = random.Random(seed)
    bounds: Dict[int, Tuple[int, int]] = {}
    for layer in layers:
        row = conn.execute(
            "SELECT MIN(rowid), MAX(rowid) FROM positions WHERE depth_remaining = ?",
            (layer,),
        ).fetchone()
        if row and row[0] is not None:
            bounds[layer] = (int(row[0]), int(row[1]))
    if not bounds:
        raise SystemExit("Aucune ligne exploitable : la tablebase est vide ?")

    out: List[Dict[str, Any]] = []
    seen: set[Tuple[bytes, int]] = set()
    counts: Dict[str, int] = defaultdict(int)
    attempts = 0
    max_attempts = per_result * 3 * len(TARGET) * 40

    layers_list = list(bounds.keys())
    while len(out) < per_result * len(TARGET) and attempts < max_attempts:
        attempts += 1
        layer = rng.choice(layers_list)
        lo, hi = bounds[layer]
        rowid = rng.randint(lo, hi)
        row = conn.execute(
            """
            SELECT rowid, result, board_blob, current_player,
                   pos_last_move_row, pos_last_move_col, empty_cells, depth_remaining
            FROM positions WHERE rowid = ?
            """,
            (rowid,),
        ).fetchone()
        if row is None or row["board_blob"] is None:
            continue
        if int(row["depth_remaining"] or -1) != layer:
            continue
        result = str(row["result"])
        if result not in TARGET or counts[result] >= per_result:
            continue
        player = int(row["current_player"] or 0)
        if player not in (1, 2):
            continue
        lmr, lmc = row["pos_last_move_row"], row["pos_last_move_col"]
        if lmr is None or lmc is None or int(lmr) < 0 or int(lmc) < 0:
            continue
        blob = bytes(row["board_blob"])
        key = (blob, player)
        if key in seen:
            continue
        seen.add(key)

        board = board_from_blob(blob)
        last = (int(lmr), int(lmc))
        if board[last[0]][last[1]] == 0:
            continue  # dernier coup incohérent : ligne fantôme
        stones = sum(1 for r in board for c in r if c)
        if stones == 0 or board[last[0]][last[1]] == player:
            continue  # le dernier coup doit être celui de l'adversaire
        counts[result] += 1
        out.append(
            {
                "layer": layer,
                "board": board,
                "player": player,
                "last_move": last,
                "result": result,
                "target": TARGET[result],
            }
        )
    return out


def sigmoid(score: float, scale: float) -> float:
    z = max(-60.0, min(60.0, score / scale))
    return 1.0 / (1.0 + math.exp(-z))


def brier(samples: Sequence[Tuple[float, float]], scale: float) -> float:
    return sum((sigmoid(s, scale) - y) ** 2 for s, y in samples) / max(len(samples), 1)


def fit_scale(samples: Sequence[Tuple[float, float]]) -> Tuple[float, float]:
    """Échelle minimisant le score de Brier, par recherche sur grille puis raffinement."""
    best_scale, best_score = DEFAULT_SCALE, brier(samples, DEFAULT_SCALE)
    lo, hi = 5.0, 4000.0
    for _ in range(6):
        grid = [lo + (hi - lo) * i / 200.0 for i in range(201)]
        for scale in grid:
            b = brier(samples, scale)
            if b < best_score:
                best_scale, best_score = scale, b
        lo, hi = max(5.0, best_scale * 0.5), best_scale * 2.0
    return best_scale, best_score


def reliability_table(samples: Sequence[Tuple[float, float]], scale: float) -> List[Dict[str, Any]]:
    """Table de fiabilité : score annoncé vs résultat réellement observé."""
    buckets = [
        (-10**9, -400), (-400, -200), (-200, -100), (-100, -40), (-40, 40),
        (40, 100), (100, 200), (200, 400), (400, 10**9),
    ]
    rows: List[Dict[str, Any]] = []
    for lo, hi in buckets:
        sel = [s for s in samples if lo <= s[0] < hi]
        if not sel:
            continue
        predicted = sum(sigmoid(s[0], scale) for s in sel) / len(sel)
        observed = sum(s[1] for s in sel) / len(sel)
        rows.append(
            {
                "score_min": None if lo < -10**8 else lo,
                "score_max": None if hi > 10**8 else hi,
                "n": len(sel),
                "predicted": round(predicted, 3),
                "observed": round(observed, 3),
            }
        )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Calibre l'échelle des scores du moteur")
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--samples", type=int, default=200, help="positions par résultat (W/D/L)")
    parser.add_argument("--depth", type=int, default=8, help="profondeur de recherche (sans tablebase)")
    parser.add_argument("--layers", type=int, nargs="*", default=[8, 9, 10, 11, 12])
    parser.add_argument("--seed", type=int, default=20260924)
    args = parser.parse_args()

    db = Path(args.db)
    if not db.exists():
        raise SystemExit(f"Tablebase introuvable : {db}")
    conn = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row

    print(f"Échantillonnage ({args.samples} par résultat, couches {args.layers})...")
    picked = sample_positions(conn, args.layers, args.samples, seed=args.seed)
    counts: Dict[str, int] = defaultdict(int)
    for p in picked:
        counts[p["result"]] += 1
    print(f"  {len(picked)} positions : {dict(counts)}")

    engine = RawEngine(depth=args.depth)
    print(f"Moteur : profondeur {args.depth}, sans tablebase, {args.samples * 3} requêtes...")

    samples: List[Tuple[float, float]] = []
    skipped_proven = 0
    skipped_error = 0
    started = time.perf_counter()
    for i, p in enumerate(picked, 1):
        resp = engine.ask(p["board"], p["player"], p["last_move"])
        if resp is None or "score" not in resp:
            skipped_error += 1
            continue
        # Le moteur a trouvé le mat (ou une valeur forcée) : ce n'est plus une
        # estimation heuristique, la position ne dit rien sur l'échelle.
        if resp.get("proven") != "aucune preuve":
            skipped_proven += 1
            continue
        samples.append((float(resp["score"]), float(p["target"])))
        if i % 50 == 0:
            rate = i / max(time.perf_counter() - started, 0.001)
            print(f"  {i}/{len(picked)} ({rate:.1f} pos/s) | {len(samples)} estimations exploitables")

    engine.close()
    if len(samples) < 30:
        print(f"Trop peu d'estimations exploitables ({len(samples)}) : rien à ajuster.")
        return 1

    scale, score_brier = fit_scale(samples)
    brier_default = brier(samples, DEFAULT_SCALE)
    table = reliability_table(samples, scale)

    print()
    print(f"Échantillon exploitable : {len(samples)} positions "
          f"({skipped_proven} déjà prouvées par le moteur, {skipped_error} sans réponse)")
    print(f"Échelle ajustée         : {scale:.1f}  (Brier {score_brier:.4f})")
    print(f"Échelle par défaut 120  : Brier {brier_default:.4f}")
    print()
    print("Table de fiabilité (score → taux annoncé vs taux réellement observé) :")
    print(f"  {'score':>16} {'n':>5} {'annoncé':>8} {'observé':>8}")
    for row in table:
        lo = "-inf" if row["score_min"] is None else f"{row['score_min']}"
        hi = "+inf" if row["score_max"] is None else f"{row['score_max']}"
        print(f"  {lo:>7}..{hi:<8} {row['n']:>5} {row['predicted']:>8.3f} {row['observed']:>8.3f}")

    payload = {
        "scale": round(scale, 2),
        "brier": round(score_brier, 5),
        "brier_default_120": round(brier_default, 5),
        "samples": len(samples),
        "skipped_proven": skipped_proven,
        "engine_depth": args.depth,
        "layers": list(args.layers),
        "reliability": table,
        "method": "sigmoide ajustee par Brier sur finales exactes, moteur sans tablebase",
        "calibrated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print()
    print(f"Écrit : {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
