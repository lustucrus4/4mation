"""Test rapide et autonome de `scripts/bot_arena.py`.

Valide :
1. la math de l'intervalle de Wilson ;
2. l'ajustement Elo Bradley-Terry (ordre, différence attendue, cas dégénérés) ;
3. une micro-arène réelle (2 bots, 1 partie, sans niveau 6) et la légalité
   des coups joués ;
4. le verdict de monotonie de la courbe de difficulté (fonction pure) ;
5. si `scripts/arena_bots.json` existe, que l'échelle mesurée est bien strictement
   croissante en Elo et strictement décroissante en score de proxy, et que l'Elo
   publié à l'utilisateur (`api/services/elo.py`) correspond à la mesure.

    $env:PYTHONPATH=".;script"; .venv\\Scripts\\python.exe scripts/check_bot_arena.py
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for _path in (str(ROOT), str(ROOT / "script"), str(ROOT / "scripts")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from api.services.bot_registry import BotRegistry  # noqa: E402
from bot_arena import (  # noqa: E402
    PROXY_PROFILES,
    _difficulty_by_profile,
    _game_seed,
    fit_elo,
    probe_monotonicity,
    profile_order,
    run_arena,
    run_difficulty_probe,
    wilson_interval,
)

ARENA_JSON = ROOT / "scripts" / "arena_bots.json"

# Plafond de score du proxy le plus fort (niveau 6) par profil de sonde.
#
# Le niveau 6 n'est **infaillible que dans la zone prouvée** (tablebase exacte + livre
# d'ouverture). Hors de cette zone, c'est le meilleur moteur de l'échelle mais pas un
# mur : plus la sonde joue bien, plus elle marque. Ces plafonds sont donc *déclarés par
# profil* et non un seuil unique, sinon le test mentirait sur la limite réelle.
# Mesures en mode `--fast` (budgets temps divisés par 4) : en production le moteur
# dispose de 4× plus de temps, donc ces valeurs sont pessimistes pour le niveau 6.
INFALLIBLE_MAX_RATE: dict[str, float] = {
    "novice": 0.05,
    "debutant": 0.10,
    "moyen": 0.25,
    "avance": 0.45,
}

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")

FAILURES = 0
CHECKS = 0


def check(condition: bool, label: str) -> None:
    global FAILURES, CHECKS
    CHECKS += 1
    if condition:
        print(f"  [OK]   {label}")
    else:
        FAILURES += 1
        print(f"  [FAIL] {label}")


def test_game_seed() -> None:
    """Les graines dérivées doivent être reproductibles et non corrélées.

    Le bug visé : passer `base + 0`, `base + 1`, … à `random.seed` produit des flux
    corrélés sur leurs premiers tirages, donc des parties non indépendantes.
    """
    print("Graines de partie :")
    check(_game_seed(7, 11) == _game_seed(7, 11), "graine déterministe")
    check(_game_seed(7, 11) != _game_seed(7, 12), "graines différentes pour des parties différentes")
    check(_game_seed(7, 11) != _game_seed(8, 11), "graines différentes pour des bases différentes")

    base = 20260926
    firsts = []
    for i in range(512):
        random.seed(_game_seed(base, i))
        firsts.append(random.random())
    check(len(set(firsts)) > 500, "les premiers tirages ne se répètent pas")

    mean = sum(firsts) / len(firsts)
    check(0.42 < mean < 0.58, f"moyenne des premiers tirages ~0,5 (mesuré {mean:.3f})")

    centered = [x - mean for x in firsts]
    var = sum(x * x for x in centered) / len(centered)
    cov = sum(centered[i] * centered[i + 1] for i in range(len(centered) - 1))
    rho = cov / (var * (len(centered) - 1)) if var > 0 else 1.0
    check(abs(rho) < 0.10, f"autocorrélation lag-1 négligeable (mesuré {rho:+.3f})")


def test_wilson() -> None:
    print("Wilson :")
    check(wilson_interval(0.0, 0) == (0.0, 1.0), "n=0 renvoie l'intervalle plein")

    low, high = wilson_interval(8.0, 10)
    check(0.0 <= low <= 0.8 <= high <= 1.0, "8/10 encadre la proportion 0.8")
    check(abs(low - 0.490) < 0.02 and abs(high - 0.943) < 0.02, "8/10 ~ [0.490, 0.943]")

    lo_n, hi_n = wilson_interval(80.0, 100)
    check((hi_n - lo_n) < (high - low), "100 tirages resserrent l'IC vs 10")
    check(lo_n > 0.0 and hi_n < 1.0, "IC strictement interne pour 80/100")

    check(wilson_interval(1.0, 5)[1] == 1.0 or wilson_interval(5.0, 5)[0] > 0.0,
          "bornes cohérentes pour score extrême")


def test_elo() -> None:
    print("Elo Bradley-Terry :")
    # A (index 0) gagne 8 fois sur 10 contre B (index 1).
    games = [(0, 1, 1.0)] * 8 + [(1, 0, 1.0)] * 2
    elos = fit_elo(games, 2)
    diff = elos[0] - elos[1]
    check(diff > 0, "le vainqueur majoritaire a l'Elo le plus haut")
    # MLE logistique : logit(0.8) * 173.7178 ≈ 240.8 Elo.
    check(180.0 < diff < 280.0, f"différence proche de 241 Elo (obtenu {diff:.0f})")
    check(abs(sum(elos) / 2 - 1500.0) < 1e-6, "moyenne des Elo centrée sur 1500")

    # Chaîne transitive A > B > C.
    chain = [(0, 1, 1.0)] * 5 + [(1, 2, 1.0)] * 5 + [(0, 2, 1.0)] * 5
    elos_chain = fit_elo(chain, 3)
    check(elos_chain[0] > elos_chain[1] > elos_chain[2], "chaîne A > B > C respectée")

    # Que des nulles : tout le monde à égalité.
    draws = [(0, 1, 0.5)] * 4
    elos_draw = fit_elo(draws, 2)
    check(abs(elos_draw[0] - elos_draw[1]) < 1e-6, "que des nulles -> Elo égaux")

    check(fit_elo([], 3) == [1500.0, 1500.0, 1500.0], "aucune partie -> Elo d'ancrage")


def test_micro_arena() -> None:
    print("Micro-arène (level_1 vs level_2, 1 partie) :")
    registry = BotRegistry()
    random.seed(123)
    data = run_arena(
        ["level_1", "level_2"],
        registry,
        games_per_pair=1,
        base_seed=123,
        max_moves=90,
    )
    check(data["meta"]["total_games"] == 1, "exactement 1 partie jouée")
    check(len(data["matrix"]) == 1, "1 paire dans la matrice")
    check(set(data["players"]) == {"level_1", "level_2"}, "2 joueurs agrégés")

    total_games = sum(p["games"] for p in data["players"].values())
    check(total_games == 2, "chaque bot compte la partie (1 + 1)")

    rec = data["records"][0]
    check(rec["winner"] in (None, 0, 1, 2), f"gagnant légal ({rec['winner']})")
    check(rec["moves"] >= 1, f"au moins un coup joué ({rec['moves']})")
    check(rec["p1"] != rec["p2"], "deux adversaires distincts")

    # Chaque bot a joué exactement un des deux sièges.
    seats = {
        bot_id: data["players"][bot_id]["as_p1"]["games"] + data["players"][bot_id]["as_p2"]["games"]
        for bot_id in ("level_1", "level_2")
    }
    check(seats == {"level_1": 1, "level_2": 1}, "un siège joué par bot")

    score_sum = sum(p["score"] for p in data["players"].values())
    check(abs(score_sum - 1.0) < 1e-9, "la somme des scores d'une partie vaut 1")


def _row(profile: str, bot: str, level: int, rate: float, ci: tuple, games: int = 32) -> dict:
    return {
        "profile": profile,
        "bot": bot,
        "level": level,
        "proxy_rate": rate,
        "ci95": list(ci),
        "games": games,
        "proxy_score": rate * games,
        "wins": int(rate * games),
        "draws": 0,
        "losses": games - int(rate * games),
    }


def test_probe_monotonicity() -> None:
    print("Monotonie de l'échelle (multi-profils) :")
    rows = [
        # Bas de l'échelle : saturation à 1.00 pour le profil moyen, séparation par le débutant.
        _row("moyen", "level_1", 1, 1.00, (0.94, 1.00)),
        _row("moyen", "level_2", 2, 1.00, (0.94, 1.00)),
        _row("moyen", "level_3", 3, 0.55, (0.38, 0.71)),
        _row("debutant", "level_1", 1, 0.92, (0.78, 0.98)),
        _row("debutant", "level_2", 2, 0.58, (0.41, 0.73)),
        _row("debutant", "level_3", 3, 0.10, (0.03, 0.26)),
    ]
    verdict = probe_monotonicity(rows)
    check(not verdict["violations"], "échelle décroissante -> aucune violation")
    check(all(c["ok"] for c in verdict["checks"]), "les 2 paires adjacentes sont validées")
    first = verdict["checks"][0]
    check(first["proven_by"] == ["debutant"],
          "la paire saturée sous « moyen » est démontrée par « debutant »")
    check(not first["felt_inversions"], "la saturation à 1.00 n'est pas comptée comme inversion")

    # Inversion franche de la courbe de difficulté sur un seul profil : la force reste
    # validée (un autre profil démontre la séparation), mais l'anomalie est remontée.
    inverted = [
        _row("moyen", "level_1", 1, 1.00, (0.94, 1.00)),
        _row("moyen", "level_2", 2, 0.70, (0.53, 0.83)),
        _row("moyen", "level_3", 3, 0.40, (0.25, 0.57)),
        _row("debutant", "level_1", 1, 0.50, (0.34, 0.66)),
        _row("debutant", "level_2", 2, 0.90, (0.75, 0.96)),
        _row("debutant", "level_3", 3, 0.10, (0.03, 0.26)),
    ]
    verdict_inv = probe_monotonicity(inverted)
    check(not verdict_inv["violations"], "inversion de sonde seule -> force non réfutée")
    check(len(verdict_inv["felt_inversions"]) == 1, "l'inversion de difficulté est remontée")
    check(
        verdict_inv["felt_inversions"][0]["felt_inversions"] == ["debutant"],
        "inversion attribuée au bon profil",
    )
    check(
        verdict_inv["felt_inversions"][0]["ok"],
        "la paire reste validée en force (séparation démontrée par « moyen »)",
    )

    # Égalité partout : ordre non contredit mais difficulté non démontrée différente.
    tied = [
        _row("moyen", "level_1", 1, 1.00, (0.94, 1.00)),
        _row("moyen", "level_2", 2, 1.00, (0.94, 1.00)),
    ]
    verdict_tied = probe_monotonicity(tied)
    check(len(verdict_tied["violations"]) == 1, "égalité partout -> paire réfutée")
    check(verdict_tied["violations"][0]["proven_by"] == [], "aucun profil ne démontre la paire")

    # Inversion apparente mais NON significative sur un profil, séparation démontrée sur
    # un autre : la paire reste validée, mais l'ambiguïté est signalée, pas masquée.
    soft = [
        _row("moyen", "level_1", 1, 0.70, (0.53, 0.83)),
        _row("moyen", "level_2", 2, 0.35, (0.21, 0.52)),
        _row("avance", "level_1", 1, 0.50, (0.34, 0.66)),
        _row("avance", "level_2", 2, 0.58, (0.41, 0.73)),
    ]
    verdict_soft = probe_monotonicity(soft)
    check(not verdict_soft["violations"], "inversion non significative -> paire non réfutée")
    check(
        not verdict_soft.get("felt_inversions"),
        "un écart non significatif n'est pas compté comme difficulté ressentie inversée",
    )
    check(
        verdict_soft["indistinguishable"]
        and verdict_soft["indistinguishable"][0]["soft_inversions"] == ["avance"],
        "l'inversion non significative est signalée comme indiscernable",
    )
    check(
        verdict_soft["checks"][0]["proven_by"] == ["moyen"],
        "la séparation reste attribuée au profil qui la démontre",
    )

    # Instrument « confrontation directe » : si le bot le plus facile bat le plus dur,
    # l'ordre est faux — même quand aucun profil de sonde ne le voit.
    flat = [
        _row("moyen", "level_1", 1, 0.50, (0.34, 0.66)),
        _row("moyen", "level_2", 2, 0.50, (0.34, 0.66)),
    ]
    direct = [{"a": "level_1", "b": "level_2", "games": 40, "score_a": 0.75, "ci95_a": [0.60, 0.86]}]
    verdict_direct = probe_monotonicity(flat, direct)
    check(len(verdict_direct["violations"]) == 1, "confrontation directe inversée -> paire réfutée")
    check(
        verdict_direct["checks"][0]["inversions_direct"] == ["level_1"],
        "l'inversion est attribuée à la confrontation directe",
    )

    # Confrontation directe concluante dans le bon sens : elle suffit à démontrer la
    # séparation même quand toutes les sondes saturent.
    saturated = [
        _row("moyen", "level_1", 1, 1.00, (0.94, 1.00)),
        _row("moyen", "level_2", 2, 1.00, (0.94, 1.00)),
    ]
    direct_ok = [{"a": "level_1", "b": "level_2", "games": 40, "score_a": 0.25, "ci95_a": [0.14, 0.40]}]
    verdict_direct_ok = probe_monotonicity(saturated, direct_ok)
    check(not verdict_direct_ok["violations"], "saturation des sondes -> directe tranche seule")
    check(
        verdict_direct_ok["checks"][0]["direct"]["proven"],
        "la confrontation directe est marquée comme démonstration",
    )


def test_probe_profiles() -> None:
    print("Profils de proxy :")
    check("moyen" in PROXY_PROFILES, "profil moyen déclaré")
    check("avance" in PROXY_PROFILES, "profil avancé déclaré")
    check("debutant" in PROXY_PROFILES, "profil débutant déclaré")
    check("novice" in PROXY_PROFILES, "profil novice déclaré")
    check(
        PROXY_PROFILES["avance"]["blunder_rate"] < PROXY_PROFILES["moyen"]["blunder_rate"],
        "le profil avancé se trompe moins",
    )
    check(
        PROXY_PROFILES["debutant"]["blunder_rate"] > PROXY_PROFILES["moyen"]["blunder_rate"],
        "le profil débutant se trompe plus",
    )
    # Le profil novice existe pour séparer le bas de l'échelle : il doit être plus fort
    # que le débutant mais plus faillible que le joueur moyen.
    check(
        PROXY_PROFILES["novice"]["depth"] > PROXY_PROFILES["debutant"]["depth"],
        "le profil novice voit plus loin que le débutant",
    )
    check(
        PROXY_PROFILES["novice"]["blunder_rate"] < PROXY_PROFILES["debutant"]["blunder_rate"],
        "le profil novice se trompe moins que le débutant",
    )
    check(
        PROXY_PROFILES["novice"]["blunder_rate"] > PROXY_PROFILES["moyen"]["blunder_rate"],
        "le profil novice se trompe plus que le joueur moyen",
    )
    check(
        profile_order() == ["novice", "debutant", "moyen", "avance"],
        "les profils sont ordonnés du plus faible au plus fort",
    )
    try:
        run_difficulty_probe(["level_1"], BotRegistry(), games=0, profiles=["inexistant"])
    except ValueError:
        check(True, "profil inconnu rejeté")
    else:
        check(False, "profil inconnu rejeté")


def test_ladder_contract() -> None:
    """Contrat d'échelle : *que* des niveaux de difficulté, strictement ordonnés.

    Exigence produit : le joueur ne choisit pas un « type » de bot, mais un cran de
    difficulté, du plus facile (niveau 1) à l'impossible (niveau 6), et chaque cran doit
    être franchement distinct du voisin. Ce test verrouille l'invariant pour qu'une
    édition future ne puisse pas, par mégarde, publier deux niveaux indiscernables,
    inverser l'ordre, ou ajouter un bot hors échelle.
    """
    print("Contrat d'échelle (difficultés seules, strictement ordonnées) :")
    registry = BotRegistry()
    bots = registry.list_bots()
    ids = [b["id"] for b in bots]

    check(ids == [f"level_{i}" for i in range(1, 7)],
          "l'API n'expose que les 6 niveaux, dans l'ordre croissant")
    check([b["level"] for b in bots] == list(range(1, 7)),
          "le champ `level` suit l'ordre de l'échelle")

    from api.services.elo import BOT_ELO  # noqa: E402

    elos = [BOT_ELO[i] for i in ids]
    check(all(b > a for a, b in zip(elos, elos[1:])),
          "l'Elo publié est strictement croissant")

    meta = BotRegistry._LEVELS
    depths = [meta[i]["depth"] for i in ids]
    times = [meta[i]["time_budget_ms"] for i in ids]
    check(all(b > a for a, b in zip(depths, depths[1:])),
          "la profondeur de recherche est strictement croissante")
    check(all(b > a for a, b in zip(times, times[1:])),
          "le budget temps est strictement croissant")

    # Levier de faiblesse volontaire : `blunder_rate` (coup au hasard) pour le bas de
    # l'échelle, `inaccuracy_rate` (2ᵉ choix du moteur) pour le haut. Leur somme doit
    # décroître strictement, sinon deux niveaux deviennent indiscernables en duel.
    fallibility = [
        meta[i]["blunder_rate"] + meta[i].get("inaccuracy_rate", 0.0) for i in ids
    ]
    check(all(b < a for a, b in zip(fallibility, fallibility[1:])),
          "le taux d'erreur volontaire décroît strictement")

    check(fallibility[-1] == 0.0 and meta["level_6"]["proven_line"],
          "le niveau 6 est infaillible (preuve jouée, zéro erreur)")
    check(all(meta[i]["proven_line"] for i in ("level_4", "level_5", "level_6")),
          "les niveaux 4 à 6 jouent la preuve (tablebase / livre)")
    check(not any(meta[i]["proven_line"] for i in ("level_1", "level_2", "level_3")),
          "les niveaux 1 à 3 jouent sans raccourci de preuve")

    names = [b["name"] for b in bots]
    check(names[0].startswith("Niveau 1") and names[-1].endswith("Impossible"),
          "les libellés vont du « Très facile » à l'« Impossible »")


def test_measured_ladder() -> None:
    """Contrôle l'échelle réellement mesurée si le rapport d'arène est présent."""
    print("Échelle mesurée (arena_bots.json) :")
    if not ARENA_JSON.exists():
        print("  [skip] aucun rapport mesuré — lancer scripts/bot_arena.py d'abord")
        return
    data = json.loads(ARENA_JSON.read_text(encoding="utf-8"))

    elos = [(bot_id, p["elo"], p["level"]) for bot_id, p in data["players"].items()]
    elos.sort(key=lambda item: item[2])
    pairs = list(zip(elos, elos[1:]))
    check(
        all(b[1] > a[1] for a, b in pairs),
        "Elo strictement croissant avec le niveau (preuve directe head-to-head)",
    )

    difficulty = data.get("difficulty") or []
    if not difficulty:
        print("  [skip] aucune courbe de difficulté dans le rapport")
        return
    verdict = data.get("difficulty_monotonicity") or probe_monotonicity(
        difficulty, data.get("matrix")
    )
    check(bool(verdict.get("checks")), "le rapport contient un verdict de monotonie")
    check(not verdict["violations"], "chaque paire de niveaux adjacents est validée")
    check(
        all(c["ok"] for c in verdict.get("felt_inversions") or []),
        "les inversions de difficulté ressentie restent des paires validées en force "
        "(caveat produit, pas faute d'ordre)",
    )

    # L'Elo affiché à l'utilisateur (`api/services/elo.py`) doit refléter la mesure,
    # sinon le classement du site contredirait la force réelle des bots.
    from api.services.elo import BOT_ELO  # noqa: E402

    for bot_id, entry in data["players"].items():
        check(
            BOT_ELO.get(bot_id) == round(entry["elo"]),
            f"{bot_id} : Elo publié ({BOT_ELO.get(bot_id)}) = Elo mesuré "
            f"({round(entry['elo'])})",
        )
    ordered = [BOT_ELO[f"level_{i}"] for i in range(1, 7)]
    check(
        all(b > a for a, b in zip(ordered, ordered[1:])),
        "l'échelle d'Elo publiée est strictement croissante",
    )

    for profile, rows in _difficulty_by_profile(difficulty).items():
        hardest = max(rows, key=lambda r: r["level"])
        ceiling = INFALLIBLE_MAX_RATE.get(profile, INFALLIBLE_MAX_RATE["avance"])
        check(
            hardest["proxy_rate"] <= ceiling,
            f"le niveau {hardest['level']} est quasi impossible pour le proxy "
            f"(profil {profile}, score {hardest['proxy_rate']:.2f} <= {ceiling:.2f})",
        )


def main() -> int:
    print("=== check_bot_arena ===")
    test_wilson()
    test_game_seed()
    test_elo()
    test_micro_arena()
    test_probe_monotonicity()
    test_probe_profiles()
    test_ladder_contract()
    test_measured_ladder()
    print(f"\n{CHECKS - FAILURES}/{CHECKS} vérifications OK")
    if FAILURES:
        print(f"{FAILURES} échec(s)")
        return 1
    print("Tout est vert.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
