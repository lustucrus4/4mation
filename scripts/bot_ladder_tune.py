"""Calibration de l'échelle de difficulté des bots 4mation.

Fait jouer le proxy humain (siège 1) contre une liste de **configurations candidates**
de bot et affiche son score pour chacune, avec un intervalle de Wilson. Sert à choisir
les réglages des niveaux avant de les inscrire dans `api/services/bot_registry.py` :

- un score élevé du proxy = bot facile à battre ;
- un score qui décroît strictement quand on monte en niveau = échelle graduée.

Pourquoi un outil séparé : mesurer un seul niveau à la fois (comme le fait la sonde de
`bot_arena.py`) oblige à modifier le registre entre chaque essai. Ici, tout est mesuré
dans la même passe, avec la même graine, donc les scores sont comparables.

    $env:PYTHONPATH=".;script;scripts"
    .venv\\Scripts\\python.exe scripts/bot_ladder_tune.py --games 96
    .venv\\Scripts\\python.exe scripts/bot_ladder_tune.py --games 48 --fast --profile avance
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

ROOT = Path(__file__).resolve().parent.parent
for _path in (str(ROOT), str(ROOT / "script"), str(ROOT / "scripts")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from api.services.bot_registry import BotRegistry, DifficultyBot  # noqa: E402
from bot_arena import PROXY_PROFILES, _game_seed, wilson_interval  # noqa: E402
from bot_match import play_game  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")

PROXY_ID = "proxy_humain"

# Configurations candidates : (étiquette, arguments de DifficultyBot).
# Les budgets sont ceux de production ; `--fast` les réduit d'un facteur 4 pour
# itérer vite. `base_*` = niveau actuel (référence), `essai_*` = pistes.
CANDIDATES: List[Tuple[str, Dict[str, Any]]] = [
    # Références actuelles du registre.
    ("base_L1 (b.62 d1 minimax)", dict(depth=1, time_budget_ms=120, use_tablebase=False, blunder_rate=0.62)),
    ("base_L3 (b.24 d4 minimax)", dict(depth=4, time_budget_ms=600, use_tablebase=False, blunder_rate=0.24)),
    ("base_L4 (inacc.16 d8 tb)", dict(depth=8, time_budget_ms=1200, use_tablebase=True, proven_line=True, use_engine=True, blunder_rate=0.0, inaccuracy_rate=0.16)),
    ("base_L5 (inacc.04 d16 tb)", dict(depth=16, time_budget_ms=2000, use_tablebase=True, proven_line=True, use_engine=True, blunder_rate=0.0, inaccuracy_rate=0.04)),
    ("base_L6 (inacc0 d26 tb)", dict(depth=26, time_budget_ms=3000, use_tablebase=True, proven_line=True, use_engine=True, blunder_rate=0.0, inaccuracy_rate=0.0)),
    # Étage « très facile » : le hasard pur est le plancher de difficulté.
    ("cand_L1 (b.80 d1 moteur)", dict(depth=1, time_budget_ms=60, use_tablebase=False, blunder_rate=0.80, use_engine=True)),
    ("cand_L2 (b.60 d1 moteur)", dict(depth=1, time_budget_ms=100, use_tablebase=False, blunder_rate=0.60, use_engine=True)),
    # Étage « très facile » : on cherche le plancher, celui qui perd même contre un débutant.
    ("cand_L0a (b.90 d1 moteur)", dict(depth=1, time_budget_ms=40, use_tablebase=False, blunder_rate=0.90, use_engine=True)),
    ("cand_L0b (aléatoire pur)", dict(depth=1, time_budget_ms=20, use_tablebase=False, blunder_rate=1.0, use_engine=False)),
    ("cand_L1b (b.75 d2 moteur)", dict(depth=2, time_budget_ms=80, use_tablebase=False, blunder_rate=0.75, use_engine=True)),
    ("cand_L2b (b.65 d2 moteur)", dict(depth=2, time_budget_ms=120, use_tablebase=False, blunder_rate=0.65, use_engine=True)),
    ("cand_L2c (b.50 d3 moteur)", dict(depth=3, time_budget_ms=180, use_tablebase=False, blunder_rate=0.50, use_engine=True)),
    # Étage « facile/moyen » : la profondeur du moteur crée l'écart, pas le taux d'erreur.
    ("cand_L3a (b.40 d4 moteur)", dict(depth=4, time_budget_ms=250, use_tablebase=False, blunder_rate=0.40, use_engine=True)),
    ("cand_L3b (b.30 d4 moteur)", dict(depth=4, time_budget_ms=300, use_tablebase=False, blunder_rate=0.30, use_engine=True)),
    ("cand_L3c (b.20 d6 moteur)", dict(depth=6, time_budget_ms=450, use_tablebase=False, blunder_rate=0.20, use_engine=True)),
    # Étage « difficile » : erreur franche rare vs erreur graduée fréquente.
    ("cand_L4a (b.08 d8 tb)", dict(depth=8, time_budget_ms=900, use_tablebase=True, proven_line=True, use_engine=True, blunder_rate=0.08)),
    ("cand_L4b (inacc.30 d8 tb)", dict(depth=8, time_budget_ms=900, use_tablebase=True, proven_line=True, use_engine=True, blunder_rate=0.0, inaccuracy_rate=0.30)),
    ("cand_L5a (inacc.08 d12 tb)", dict(depth=12, time_budget_ms=1500, use_tablebase=True, proven_line=True, use_engine=True, blunder_rate=0.0, inaccuracy_rate=0.08)),
    ("cand_L6a (inacc0 d34 6s)", dict(depth=34, time_budget_ms=6000, use_tablebase=True, proven_line=True, use_engine=True, blunder_rate=0.0, inaccuracy_rate=0.0)),
    # Candidats retenus pour l'échelle finale : un étage = une configuration, et un
    # écart volontairement large entre niveaux voisins pour que la séparation soit
    # démontrable même avec 64 parties par niveau.
    ("final_L1 (b.90 d1 moteur)", dict(depth=1, time_budget_ms=60, use_tablebase=False, blunder_rate=0.90, use_engine=True)),
    ("final_L2 (b.70 d2 moteur)", dict(depth=2, time_budget_ms=120, use_tablebase=False, blunder_rate=0.70, use_engine=True)),
    ("final_L3 (b.40 d4 moteur)", dict(depth=4, time_budget_ms=300, use_tablebase=False, blunder_rate=0.40, use_engine=True)),
    ("final_L4 (inacc.16 d8 tb)", dict(depth=8, time_budget_ms=1200, use_tablebase=True, proven_line=True, use_engine=True, blunder_rate=0.0, inaccuracy_rate=0.16)),
    ("final_L5 (inacc.08 d18 tb)", dict(depth=18, time_budget_ms=2000, use_tablebase=True, proven_line=True, use_engine=True, blunder_rate=0.0, inaccuracy_rate=0.08)),
    ("final_L6 (inacc0 d26 tb)", dict(depth=26, time_budget_ms=3000, use_tablebase=True, proven_line=True, use_engine=True, blunder_rate=0.0, inaccuracy_rate=0.0)),
]


class _SingleRegistry:
    """Registre minimal exposant un bot candidat et le proxy humain à `play_game`."""

    def __init__(self, bot_id: str, bot: DifficultyBot, proxy_id: str, proxy: DifficultyBot) -> None:
        self._bot_id = bot_id
        self._bot = bot
        self._proxy_id = proxy_id
        self._proxy = proxy

    def choose_move(self, bot_id: str, engine: Any) -> Any:
        if bot_id == self._bot_id:
            return self._bot.choose_move(engine)
        if bot_id == self._proxy_id:
            return self._proxy.choose_move(engine)
        raise ValueError(f"Bot inattendu : {bot_id}")

    def is_valid_bot(self, bot_id: str) -> bool:
        return bot_id in (self._bot_id, self._proxy_id)


def measure(
    label: str,
    cfg: Dict[str, Any],
    proxy_cfg: Dict[str, Any],
    games: int,
    base_seed: int,
    fast: bool,
) -> Dict[str, Any]:
    """Score du proxy humain (siège 1) contre un candidat (siège 2)."""
    scaled = dict(cfg)
    if fast:
        scaled["time_budget_ms"] = max(20, int(scaled["time_budget_ms"] * 0.25))
    proxy_args = dict(proxy_cfg)
    if fast:
        proxy_args["time_budget_ms"] = max(20, int(proxy_args["time_budget_ms"] * 0.25))

    bot = DifficultyBot(**scaled)
    proxy = DifficultyBot(**proxy_args)
    registry = _SingleRegistry(label, bot, PROXY_ID, proxy)

    score = 0.0
    wins = draws = losses = 0
    plies = 0
    for g in range(games):
        random.seed(_game_seed(base_seed, label, g))
        result = play_game(PROXY_ID, label, registry, max_moves=90)
        winner = result["winner"]
        winner = None if winner is None else int(winner)
        plies += int(result["moves"])
        if winner == 1:
            score += 1.0
            wins += 1
        elif winner == 2:
            losses += 1
        else:
            score += 0.5
            draws += 1

    ci = wilson_interval(score, games)
    return {
        "label": label,
        "config": cfg,
        "games": games,
        "proxy_score": score,
        "proxy_rate": round(score / games, 3) if games else None,
        "ci95": [round(ci[0], 3), round(ci[1], 3)],
        "wins": wins,
        "draws": draws,
        "losses": losses,
        "avg_plies": round(plies / games, 1) if games else None,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Calibration de l'échelle des bots")
    parser.add_argument("--games", type=int, default=64, help="parties par candidat")
    parser.add_argument("--seed", type=int, default=20260926, help="graine de base")
    parser.add_argument("--profile", default="moyen", choices=sorted(PROXY_PROFILES),
                        help="profil de proxy humain")
    parser.add_argument("--fast", action="store_true", help="budgets réduits (itération rapide)")
    parser.add_argument("--only", nargs="+", default=None,
                        help="filtre les candidats dont l'étiquette contient un de ces motifs")
    parser.add_argument("--json", default=None, help="écrire les mesures dans un fichier JSON")
    args = parser.parse_args(argv)

    candidates = CANDIDATES
    if args.only:
        candidates = [c for c in CANDIDATES if any(mot in c[0] for mot in args.only)]
    if not candidates:
        print("Aucun candidat ne correspond au filtre.")
        return 2

    proxy_cfg = PROXY_PROFILES[args.profile]
    print(
        f"Proxy « {args.profile} » (profondeur {proxy_cfg['depth']}, "
        f"{proxy_cfg['blunder_rate']:.0%} d'erreurs) en siège 1, "
        f"{args.games} parties par candidat, budgets {'réduits' if args.fast else 'nominaux'}."
    )
    print()

    rows: List[Dict[str, Any]] = []
    for label, cfg in candidates:
        row = measure(label, cfg, proxy_cfg, args.games, args.seed, args.fast)
        rows.append(row)
        print(
            f"  {row['proxy_rate']:.3f} [{row['ci95'][0]:.2f}, {row['ci95'][1]:.2f}] "
            f"| V/N/D {row['wins']:>3}/{row['draws']:>2}/{row['losses']:>3} "
            f"| {row['avg_plies']:>4} plies | {label}"
        )

    ordered = sorted(rows, key=lambda r: r["proxy_rate"] or 0.0, reverse=True)
    print()
    print("Classement du plus facile (haut) au plus dur (bas) :")
    for row in ordered:
        print(f"  {row['proxy_rate']:.3f}  {row['label']}")

    if args.json:
        Path(args.json).write_text(
            json.dumps({"profile": args.profile, "fast": args.fast, "rows": rows},
                       ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"\nJSON : {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
