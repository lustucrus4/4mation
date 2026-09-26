"""Vérification autonome de la revue de partie « profonde ».

Rejoue une partie courte jouée par des bots, construit la revue (mêmes services que la
route `/api/me/games/<id>/review`) puis contrôle la cohérence des nouveaux champs :

- ``nature`` prouvée / estimée strictement alignée sur ``exact`` (aucun mélange) ;
- précision par phase (humain ET bot) ;
- ``bot_accuracy`` calculée ;
- moments clés et résumé présents et cohérents ;
- rétrocompatibilité des champs historiques.

Le script ne publie rien et ne touche à aucune donnée : il sort en erreur (code 1) si un
contrôle échoue, en imprimant la raison exacte.
"""

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for p in (str(ROOT), str(ROOT / "script")):
    if p not in sys.path:
        sys.path.insert(0, p)

from api.services.bot_registry import BotRegistry  # noqa: E402
from api.services.engine_client import get_engine_client  # noqa: E402
from api.services.game_review import build_game_review  # noqa: E402
from api.services.game_review_insights import (  # noqa: E402
    move_verdict,
    nature_of,
    outcome_status,
    proven_stats,
)
from game.game_engine import GameEngine  # noqa: E402

PHASES = ("opening", "middlegame", "endgame")
KNOWN_CLASSES = (
    "best",
    "excellent",
    "good",
    "inaccuracy",
    "mistake",
    "blunder",
    "unknown",
)
THRESHOLDS = (
    ("best", 0.01),
    ("excellent", 0.03),
    ("good", 0.08),
    ("inaccuracy", 0.15),
    ("mistake", 0.30),
)

failures: list[str] = []


def check(condition: bool, message: str) -> None:
    if not condition:
        failures.append(message)


def classify(loss: float, is_best: bool) -> str:
    if is_best:
        return "best"
    for label, max_loss in THRESHOLDS:
        if loss <= max_loss:
            return label
    return "blunder"


client = get_engine_client()
print("moteur disponible :", client.is_available(), "|", client.binary)
print()

registry = BotRegistry()
engine = GameEngine()
engine.reset()
history = []

start = time.perf_counter()
while not engine.is_terminal() and len(history) < 30:
    player = int(engine.get_current_player())
    move = registry.choose_move("level_5" if player == 1 else "level_4", engine)
    if move is None:
        break
    applied, _, _ = engine.step(move)
    if not applied:
        break
    history.append({
        "index": len(history) + 1,
        "player": player,
        "row": int(move[0]),
        "col": int(move[1]),
    })
play_secs = time.perf_counter() - start
print(f"partie : {len(history)} coups en {play_secs:.0f} s | gagnant = {engine.get_winner()}")
print()

start = time.perf_counter()
review = build_game_review(history, human_color=1)
review_secs = time.perf_counter() - start
print(f"revue  : {review['move_count']} coups en {review_secs:.1f} s")
print()

moves = review["moves"]

# --- Rétrocompatibilité -----------------------------------------------------
legacy_fields = (
    "classification",
    "accuracy",
    "source",
    "exact",
    "win_rate_before",
    "win_rate_played",
    "win_rate_best",
    "best_move",
)
for m in moves:
    for field in legacy_fields:
        check(field in m, f"champ historique manquant : {field} (coup #{m.get('index')})")

# --- Comptage / cohérence des coups ----------------------------------------
check(review["move_count"] == len(moves), "move_count != len(moves)")
check(len(moves) == len(history), "len(moves) != len(history)")

counts: dict[str, int] = {}
for m in moves:
    counts[m["classification"]] = counts.get(m["classification"], 0) + 1
check(sum(counts.values()) == review["move_count"], "somme des classifications != move_count")
for c in counts:
    check(c in KNOWN_CLASSES, f"classification inconnue : {c}")

# --- Non-mélange prouvé / estimé -------------------------------------------
incoherences: list[str] = []
for m in moves:
    nature = m["nature"]
    check(nature in ("proven", "estimated", "unknown"), f"nature invalide : {nature}")
    value_exact = bool(m.get("value_exact"))
    # Invariant de confiance : un coup n'est « proven » que si l'analyse ET la valeur du
    # coup joué sont prouvées. Rien ne peut être prouvé d'un seul côté.
    if nature == "proven":
        if not (m["exact"] and value_exact):
            incoherences.append(
                f"coup #{m['index']}: nature=proven mais exact={m['exact']} "
                f"value_exact={value_exact}"
            )
    elif nature == "estimated":
        if m["exact"] and value_exact:
            incoherences.append(
                f"coup #{m['index']}: nature=estimated alors que exact+value_exact"
            )
    if m["source"] and nature == "unknown":
        incoherences.append(f"coup #{m['index']}: analysé (source={m['source']}) mais nature=unknown")
check("value_exact" in moves[0], "champ value_exact manquant")

# --- Cohérence de la classification ----------------------------------------
for m in moves:
    loss = round(max(0.0, m["win_rate_best"] - m["win_rate_played"]), 4)
    check(
        abs(loss - float(m["win_rate_loss"])) < 1e-6,
        f"coup #{m['index']}: win_rate_loss incohérent ({m['win_rate_loss']} vs {loss})",
    )
    is_best = m["win_rate_played"] >= m["win_rate_best"] - 0.001
    expected = classify(loss, is_best)
    check(
        m["classification"] == expected,
        f"coup #{m['index']}: classification {m['classification']} != attendu {expected}",
    )
    if m["missed_forced_win"]:
        check(
            m["nature"] == "proven"
            and m["win_rate_best"] >= 0.995
            and m["win_rate_played"] < 0.995,
            f"coup #{m['index']}: missed_forced_win incohérent",
        )
    if m["proven_error"]:
        check(
            m["nature"] == "proven" and m["classification"] in ("mistake", "blunder"),
            f"coup #{m['index']}: proven_error incohérent",
        )
    check(isinstance(m["verdict"], str) and m["verdict"], f"coup #{m['index']}: verdict vide")
    check(m["phase"] in PHASES, f"coup #{m['index']}: phase invalide {m['phase']}")

check(not incoherences, "mélange prouvé/estimé : " + " | ".join(incoherences))

# --- Précision --------------------------------------------------------------
check(review["human_accuracy"] is not None, "human_accuracy None")
if any(m["player"] == 2 and m["source"] for m in moves):
    check(review["bot_accuracy"] is not None, "bot_accuracy None alors que des coups bot sont analysés")

abp = review["accuracy_by_phase"]
check(set(abp.get("human", {})) == set(PHASES), "accuracy_by_phase.human incomplet")
check(set(abp.get("bot", {})) == set(PHASES), "accuracy_by_phase.bot incomplet")
check(set(abp.get("counts", {}).get("human", {})) == set(PHASES), "counts.human incomplet")
check(set(abp.get("counts", {}).get("bot", {})) == set(PHASES), "counts.bot incomplet")
for who in ("human", "bot"):
    for phase in PHASES:
        n = abp["counts"][who][phase]
        val = abp[who][phase]
        check(
            (val is None) == (n == 0),
            f"accuracy_by_phase.{who}.{phase} : valeur={val} mais {n} coup(s)",
        )

# --- Moments clés -----------------------------------------------------------
moments = review["key_moments"]
check(isinstance(moments, list), "key_moments absent")
for km in moments:
    check(
        {"index", "player", "delta_p1", "nature", "description", "best_move"} <= set(km),
        f"moment clé incomplet : {km}",
    )
    check(bool(km["description"]), f"moment clé sans description : {km.get('index')}")
    check(km["nature"] in ("proven", "estimated", "unknown"), "moment clé : nature invalide")
expected_moments = sum(1 for m in moves if (m["win_rate_loss"] or 0) >= 0.03)
check(
    len(moments) == min(5, expected_moments),
    f"key_moments : {len(moments)} != min(5, {expected_moments})",
)

# --- Résumé -----------------------------------------------------------------
summary = review["summary"]
for who in ("human", "bot"):
    block = summary.get(who) or {}
    check(isinstance(block.get("text"), str) and len(block["text"]) > 10,
          f"summary.{who}.text manquant")
    check("strengths" in block and "errors" in block, f"summary.{who} incomplet")

# --- Compteurs prouvé/estimé ------------------------------------------------
stats = review["proven_stats"]
check(
    stats["proven_moves"] + stats["estimated_moves"] + stats["unknown_moves"] == review["move_count"],
    "proven_stats : somme des natures != move_count",
)
check(stats["mixed"] is False, "proven_stats.mixed doit être False")
for phase in PHASES:
    expected = {"proven": 0, "estimated": 0, "unknown": 0}
    for m in moves:
        if m["phase"] == phase:
            expected[m["nature"]] += 1
    check(
        stats["by_phase"][phase] == expected,
        f"proven_stats.by_phase[{phase}] {stats['by_phase'][phase]} != {expected}",
    )

# --- Contrôles unitaires de la règle de confiance ---------------------------
check(nature_of(analyzed=True, exact=True) == "proven", "nature_of : exact=True")
check(nature_of(analyzed=True, exact=False) == "estimated", "nature_of : exact=False")
check(nature_of(analyzed=False, exact=True) == "unknown", "nature_of : non analysé")
check(outcome_status(1.0, exact=True) == "proven_win", "outcome_status : gain prouvé")
check(outcome_status(0.5, exact=True) == "proven_draw", "outcome_status : nulle prouvée")
check(outcome_status(0.0, exact=True) == "proven_loss", "outcome_status : perte prouvée")
check(outcome_status(0.42, exact=False) == "estimated", "outcome_status : estimé")

missed_verdict = move_verdict(
    analyzed=True,
    classification="blunder",
    nature="proven",
    missed_forced_win=True,
    played_outcome="proven_draw",
)
check(
    "Mat forcé manqué" in missed_verdict and "prouv" in missed_verdict.lower(),
    f"verdict « mat manqué » inattendu : {missed_verdict}",
)
est_verdict = move_verdict(
    analyzed=True,
    classification="blunder",
    nature="estimated",
    missed_forced_win=False,
    played_outcome="estimated",
)
check("estimation" in est_verdict, f"verdict estimé inattendu : {est_verdict}")

fake_moves = [
    {
        "nature": "proven", "phase": "endgame", "proven_error": True,
        "classification": "blunder", "missed_forced_win": True, "accuracy": 0.0,
        "player": 1, "is_human": True, "win_rate_before": 1.0,
        "win_rate_played": 0.0, "win_rate_best": 1.0, "best_move": [0, 0],
        "index": 1, "row": 0, "col": 0, "verdict": "Faute prouvée",
        "win_rate_loss": 1.0,
    },
    {
        "nature": "estimated", "phase": "middlegame", "classification": "mistake",
        "accuracy": 60.0, "player": 2, "is_human": False, "win_rate_before": 0.6,
        "win_rate_played": 0.4, "win_rate_best": 0.6, "best_move": [1, 1],
        "index": 2, "row": 1, "col": 1, "verdict": "Erreur (estimation)",
        "win_rate_loss": 0.2,
    },
]
fake_stats = proven_stats(fake_moves)
check(
    fake_stats["proven_moves"] == 1 and fake_stats["estimated_moves"] == 1,
    "proven_stats : séparation des natures incorrecte",
)
check(
    fake_stats["proven_errors"] == 1 and fake_stats["estimated_errors"] == 1,
    "proven_stats : erreurs prouvées/estimées confondues",
)
check(fake_stats["missed_forced_wins"] == 1, "proven_stats : mat forcé manqué non compté")
check(fake_stats["mixed"] is False, "proven_stats.mixed doit rester False")
check(
    fake_stats["by_phase"]["endgame"]["proven"] == 1
    and fake_stats["by_phase"]["middlegame"]["estimated"] == 1,
    "proven_stats.by_phase incohérent",
)

# --- Sérialisation JSON (la route fait json.dumps de la revue) --------------
try:
    json.dumps(review, ensure_ascii=False)
except TypeError as exc:  # pragma: no cover - garde-fou
    failures.append(f"revue non sérialisable en JSON : {exc}")

# --- Restitution ------------------------------------------------------------
print("classifications :", counts)
print("précision       :", f"humain {review['human_accuracy']} %", "|", f"bot {review['bot_accuracy']} %")
print("par phase       :", abp["human"], "|", abp["bot"])
print("prouvé/estimé   :", {k: stats[k] for k in
      ("proven_moves", "estimated_moves", "unknown_moves", "proven_errors",
       "estimated_errors", "missed_forced_wins")})
print()
print("moments clés :")
for km in moments:
    print("  -", km["description"])
print()
print("résumé humain :", summary["human"]["text"])
print("résumé bot    :", summary["bot"]["text"])
print()

if failures:
    print(f"ÉCHEC : {len(failures)} contrôle(s) invalide(s)")
    for f in failures:
        print("  -", f)
    sys.exit(1)

print("OK : revue profonde cohérente (0 incohérence, prouvé/estimé jamais mélangés).")
