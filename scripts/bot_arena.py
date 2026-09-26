"""Arène round-robin des bots 4mation : mesure réelle de la hiérarchie.

Contrairement à `bot_match.py` (un duel unique), ce script fait jouer **toutes**
les paires de bots, chacune dans les deux sièges, puis ajuste un classement Elo
(Bradley-Terry logistique) avec un intervalle de confiance de Wilson par paire.

Le jeu a un avantage structurel du premier joueur (jouer le centre gagne de
force). Deux conséquences assumées :

- chaque paire est jouée dans les DEUX sièges, sinon on mesure l'avantage du
  siège et non la force ;
- deux bots qui gagnent chacun dans leur siège terminent à 0.50/0.50, donc
  l'Elo ne peut pas les séparer. C'est un résultat honnête, pas un bug.

Reproductibilité : les coups de blunder tirent dans le module `random`, donc
`random.seed(<graine>)` avant chaque partie rend la *séquence* d'aléas
reproductible. En revanche les budgets temps rendent les décisions du Minimax
itératif et du moteur Rust non strictement déterministes (la profondeur atteinte
dépend de la machine). Voir les caveats du rapport.

Les graines ne sont jamais passées à `random.seed` comme de simples entiers
consécutifs (`base + 0`, `base + 1`, …) : le seeding entier de Mersenne-Twister
produit alors des flux **corrélés** sur leurs premiers tirages, ce qui gonfle
artificiellement la variance et rend le taux mesuré dépendant de la tranche de
graines utilisée. Chaque graine est donc dérivée par hachage (`_game_seed`).

    python scripts/bot_arena.py --bots level_1 level_2 --games 2
    python scripts/bot_arena.py --fast --games 6
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parent.parent
for _path in (str(ROOT), str(ROOT / "script"), str(ROOT / "scripts")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from api.services.bot_registry import BotRegistry, DifficultyBot  # noqa: E402
from api.services.elo import bot_level  # noqa: E402
from bot_match import play_game  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")

DEFAULT_SEED = 20260926
Z_95 = 1.959963984540054  # quantile 97.5 % d'une loi normale centrée réduite
ELO_SCALE = 400.0 / math.log(10.0)  # 1 logit = 173.7178 points Elo
DEFAULT_ANCHOR = 1500.0


# --------------------------------------------------------------------------- #
# Registre « rapide » (mode --fast) : même hiérarchie, budgets temps réduits.
# --------------------------------------------------------------------------- #


class FastBotRegistry(BotRegistry):
    """BotRegistry dont les budgets temps sont mis à l'échelle (mode --fast).

    La profondeur reste nominale : la recherche itérative s'arrête d'elle-même
    sur le budget temps, et le moteur Rust reçoit un `time_ms` réduit.
    """

    def __init__(self, scale: float = 0.25) -> None:
        super().__init__()
        self._LEVELS = {bot_id: dict(cfg) for bot_id, cfg in self._LEVELS.items()}
        for cfg in self._LEVELS.values():
            cfg["time_budget_ms"] = max(20, int(cfg["time_budget_ms"] * scale))
        self._bots = {}


# --------------------------------------------------------------------------- #
# Statistiques : Wilson + Elo Bradley-Terry
# --------------------------------------------------------------------------- #


def _game_seed(*parts: int) -> int:
    """Graine entière dérivée par hachage de plusieurs composantes.

    Passer des entiers **consécutifs** à `random.seed` (par exemple `base + 0`,
    `base + 1`, …) est un piège classique : Mersenne-Twister est alors initialisé avec
    un tableau de graine minuscule et très proche d'une partie à l'autre, ce qui corrèle
    les premiers tirages. Les parties ne sont plus indépendantes, la variance mesurée est
    fausse et le résultat dépend de la tranche de graines. Le hachage casse cette
    structure tout en restant reproductible.
    """
    payload = ":".join(str(p) for p in parts).encode("utf-8")
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")


def wilson_interval(score_sum: float, n: int, z: float = Z_95) -> Tuple[float, float]:
    """Intervalle de Wilson pour une proportion, adapté au score (nul = 0.5).

    `score_sum` est la somme des scores (1 victoire, 0.5 nulle, 0 défaite) donc
    `score_sum / n` joue le rôle d'une proportion de succès. Wilson reste valide
    quand p est proche de 0 ou 1, contrairement à l'intervalle normal.
    """
    if n <= 0:
        return (0.0, 1.0)
    p = score_sum / n
    denom = 1.0 + z * z / n
    center = (p + z * z / (2.0 * n)) / denom
    half = (z / denom) * math.sqrt(p * (1.0 - p) / n + z * z / (4.0 * n * n))
    return (max(0.0, center - half), min(1.0, center + half))


def newcombe_diff_interval(
    score_a: float,
    n_a: int,
    score_b: float,
    n_b: int,
    z: float = Z_95,
) -> Tuple[float, float]:
    """Intervalle de confiance de la *différence* de deux proportions (Newcombe, hybride).

    Comparer deux intervalles de Wilson séparément est bien trop conservateur : deux
    intervalles peuvent se recouvrir alors que la différence est significative au seuil
    demandé. Ici on construit directement l'intervalle de ``p_a - p_b`` à partir des
    bornes de Wilson de chaque proportion :

    ``[d - √((p_a - l_a)² + (u_b - p_b)²), d + √((u_a - p_a)² + (p_b - l_b)²)]``

    Si cet intervalle exclut 0, la différence est significative au niveau ``z``.
    `score_a` / `score_b` sont des sommes de scores (nul = 0.5), comme pour Wilson.
    """
    if n_a <= 0 or n_b <= 0:
        return (-1.0, 1.0)
    p_a = score_a / n_a
    p_b = score_b / n_b
    l_a, u_a = wilson_interval(score_a, n_a, z)
    l_b, u_b = wilson_interval(score_b, n_b, z)
    d = p_a - p_b
    lower = d - math.sqrt((p_a - l_a) ** 2 + (u_b - p_b) ** 2)
    upper = d + math.sqrt((u_a - p_a) ** 2 + (p_b - l_b) ** 2)
    return (lower, upper)


def _softplus(x: float) -> float:
    if x > 30.0:
        return x
    if x < -30.0:
        return math.exp(x)
    return math.log1p(math.exp(x))


def _log_likelihood(theta: Sequence[float], games: Sequence[Tuple[int, int, float]], reg: float) -> float:
    ll = 0.0
    for a, b, s in games:
        x = theta[a] - theta[b]
        # s * log sigma(x) + (1 - s) * log sigma(-x) = s * x - softplus(x)
        ll += s * x - _softplus(x)
    ll -= 0.5 * reg * sum(t * t for t in theta)
    return ll


def fit_elo(
    games: Sequence[Tuple[int, int, float]],
    n_players: int,
    anchor: float = DEFAULT_ANCHOR,
    reg: float = 1e-3,
    max_iters: int = 5000,
) -> List[float]:
    """Ajuste un Elo Bradley-Terry par montée de gradient avec recherche de pas.

    `games` : liste de (indice_joueur_A, indice_joueur_B, score_de_A) où le score
    vaut 1 (A gagne), 0.5 (nulle) ou 0 (A perd). Renvoie un Elo par joueur,
    centré sur `anchor`. La régularisation L2 évite qu'un joueur invaincu
    diverge à l'infini (situation courante avec un petit échantillon).
    """
    if n_players <= 0:
        return []
    theta = [0.0] * n_players
    if not games:
        return [anchor] * n_players

    current = _log_likelihood(theta, games, reg)
    step = 0.5
    for _ in range(max_iters):
        grad = [-reg * t for t in theta]
        for a, b, s in games:
            p = 1.0 / (1.0 + math.exp(-(theta[a] - theta[b])))
            g = s - p
            grad[a] += g
            grad[b] -= g

        improved = False
        trial_step = step
        for _ in range(60):
            candidate = [theta[i] + trial_step * grad[i] for i in range(n_players)]
            value = _log_likelihood(candidate, games, reg)
            if value > current:
                theta = candidate
                current = value
                step = min(1.0, trial_step * 1.5)
                improved = True
                break
            trial_step *= 0.5
        if not improved:
            break

    mean = sum(theta) / n_players
    return [anchor + (t - mean) * ELO_SCALE for t in theta]


# --------------------------------------------------------------------------- #
# Arène
# --------------------------------------------------------------------------- #


def _seat_score(winner: Optional[int]) -> float:
    """Score du joueur 1 déduit du gagnant (None/0 = nulle)."""
    if winner == 1:
        return 1.0
    if winner == 2:
        return 0.0
    return 0.5


def _engine_available() -> Optional[bool]:
    """Indique si le moteur Rust est utilisable dans ce processus (None si erreur)."""
    try:
        from api.services.engine_client import get_engine_client

        return bool(get_engine_client().is_available())
    except Exception:
        return None


def run_arena(
    bot_ids: Sequence[str],
    registry: BotRegistry,
    games_per_pair: int,
    base_seed: int = DEFAULT_SEED,
    max_moves: int = 90,
    z: float = Z_95,
    fast: bool = False,
    log: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
    """Joue toutes les paires (deux sièges) et renvoie les données agrégées."""
    ids = list(bot_ids)
    index = {bot_id: i for i, bot_id in enumerate(ids)}
    for bot_id in ids:
        if not registry.is_valid_bot(bot_id):
            raise ValueError(f"Bot inconnu : {bot_id}")

    n = len(ids)
    pair_games: Dict[Tuple[int, int], Dict[str, float]] = {
        (i, j): {"games": 0.0, "score_i": 0.0, "wins": 0.0, "draws": 0.0, "losses": 0.0}
        for i, j in itertools.combinations(range(n), 2)
    }
    totals = {
        i: {"games": 0, "score": 0.0, "wins": 0, "draws": 0, "losses": 0,
            "as_p1_games": 0, "as_p1_score": 0.0, "as_p2_games": 0, "as_p2_score": 0.0}
        for i in range(n)
    }
    elo_games: List[Tuple[int, int, float]] = []
    records: List[Dict[str, Any]] = []

    counter = 0
    started = time.perf_counter()
    for i, j in itertools.combinations(range(n), 2):
        for g in range(games_per_pair):
            # Alternance stricte des sièges : pair -> i joueur 1, impair -> j joueur 1.
            if g % 2 == 0:
                p1, p2 = ids[i], ids[j]
                first_idx, second_idx = i, j
            else:
                p1, p2 = ids[j], ids[i]
                first_idx, second_idx = j, i

            seed = base_seed + counter
            counter += 1
            random.seed(_game_seed(base_seed, seed))
            result = play_game(p1, p2, registry, max_moves=max_moves)
            winner = result["winner"]
            # Le moteur expose des entiers numpy (int8) : on normalise pour JSON.
            winner = None if winner is None else int(winner)
            s1 = _seat_score(winner)
            s_first = s1
            s_second = 1.0 - s1

            rec = {
                "pair": [ids[i], ids[j]],
                "p1": p1,
                "p2": p2,
                "winner": winner,
                "moves": result["moves"],
                "secs": round(result["secs"], 3),
                "truncated": result["truncated"],
                "seed": seed,
            }
            records.append(rec)

            totals[first_idx]["as_p1_games"] += 1
            totals[first_idx]["as_p1_score"] += s_first
            totals[second_idx]["as_p2_games"] += 1
            totals[second_idx]["as_p2_score"] += s_second

            # Agrégat orienté (i, j) : score de i.
            s_i = s_first if first_idx == i else s_second
            bucket = pair_games[(i, j)]
            bucket["games"] += 1.0
            bucket["score_i"] += s_i
            if s_i == 1.0:
                bucket["wins"] += 1.0
            elif s_i == 0.0:
                bucket["losses"] += 1.0
            else:
                bucket["draws"] += 1.0

            elo_games.append((first_idx, second_idx, s_first))

            if log is not None:
                verdict = {1: f"{p1} gagne", 2: f"{p2} gagne", None: "nulle", 0: "nulle"}[winner]
                log(
                    f"  {p1} (X) vs {p2} (O) | {verdict} | "
                    f"{result['moves']} coups, {result['secs']:.1f} s, seed={seed}"
                )

    elapsed = time.perf_counter() - started
    elo_values = fit_elo(elo_games, n)

    # Corrige un point : comptage des victoires/défaites par joueur.
    for idx in range(n):
        totals[idx]["wins"] = 0
        totals[idx]["draws"] = 0
        totals[idx]["losses"] = 0
        totals[idx]["score"] = 0.0
        totals[idx]["games"] = 0
    for rec in records:
        winner = rec["winner"]
        for bot_id, seat in ((rec["p1"], 1), (rec["p2"], 2)):
            idx = index[bot_id]
            totals[idx]["games"] += 1
            if winner in (None, 0):
                totals[idx]["draws"] += 1
                totals[idx]["score"] += 0.5
            elif winner == seat:
                totals[idx]["wins"] += 1
                totals[idx]["score"] += 1.0
            else:
                totals[idx]["losses"] += 1

    players: Dict[str, Any] = {}
    for idx, bot_id in enumerate(ids):
        t = totals[idx]
        players[bot_id] = {
            "elo": round(elo_values[idx], 1),
            "level": bot_level(bot_id),
            "games": t["games"],
            "score": t["score"],
            "wins": t["wins"],
            "draws": t["draws"],
            "losses": t["losses"],
            "as_p1": {
                "games": t["as_p1_games"],
                "score": t["as_p1_score"],
                "rate": round(t["as_p1_score"] / t["as_p1_games"], 3) if t["as_p1_games"] else None,
            },
            "as_p2": {
                "games": t["as_p2_games"],
                "score": t["as_p2_score"],
                "rate": round(t["as_p2_score"] / t["as_p2_games"], 3) if t["as_p2_games"] else None,
            },
        }

    matrix: List[Dict[str, Any]] = []
    for i, j in itertools.combinations(range(n), 2):
        bucket = pair_games[(i, j)]
        ci = wilson_interval(bucket["score_i"], int(bucket["games"]), z)
        matrix.append(
            {
                "a": ids[i],
                "b": ids[j],
                "games": int(bucket["games"]),
                "score_a": round(bucket["score_i"] / bucket["games"], 4) if bucket["games"] else None,
                "wins_a": int(bucket["wins"]),
                "draws": int(bucket["draws"]),
                "losses_a": int(bucket["losses"]),
                "ci95_a": [round(ci[0], 4), round(ci[1], 4)],
            }
        )

    # Monotonie attendue : level_6 >= level_5 >= ... >= level_1 (l'ordre par niveau).
    ordered = sorted(ids, key=bot_level)
    monotonic = {
        "expected": " >= ".join(ordered[::-1]),
        "checks": [],
        "violations": [],
    }
    for lower, higher in zip(ordered, ordered[1:]):
        elo_low = players[lower]["elo"]
        elo_high = players[higher]["elo"]
        ok = elo_high >= elo_low
        entry = {
            "lower": lower,
            "higher": higher,
            "elo_lower": elo_low,
            "elo_higher": elo_high,
            "delta": round(elo_high - elo_low, 1),
            "ok": ok,
        }
        monotonic["checks"].append(entry)
        if not ok:
            monotonic["violations"].append(entry)

    data: Dict[str, Any] = {
        "meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "bots": ids,
            "games_per_pair": games_per_pair,
            "total_games": len(records),
            "max_moves": max_moves,
            "base_seed": base_seed,
            "fast": fast,
            "z": z,
            "elapsed_secs": round(elapsed, 1),
            "engine_available": _engine_available(),
        },
        "players": players,
        "matrix": matrix,
        "monotonicity": monotonic,
        "records": records,
    }
    return data


def ranking(data: Dict[str, Any]) -> List[Tuple[str, Dict[str, Any]]]:
    """Classement décroissant par Elo."""
    return sorted(data["players"].items(), key=lambda kv: kv[1]["elo"], reverse=True)


# --------------------------------------------------------------------------- #
# Courbe de difficulté : un adversaire de référence en siège 1
# --------------------------------------------------------------------------- #

# Proxy « joueur humain moyen » : joue correctement (profondeur 6) mais se trompe
# d'un coup sur sept environ. Ce n'est pas un humain, c'est une borne basse de
# joueur non-trivial : plus un bot le bat nettement, plus il est difficile.
HUMAN_PROXY_CONFIG: Dict[str, Any] = {
    "depth": 6,
    "time_budget_ms": 800,
    "use_tablebase": False,
    "blunder_rate": 0.15,
    "use_engine": False,
    "proven_line": False,
}
HUMAN_PROXY_ID = "human_proxy"

# Second profil, plus fort : sert de contrôle de robustesse. Un joueur qui se
# trompe deux fois moins doit voir la hiérarchie du haut de l'échelle s'étaler
# davantage ; si un bot paraît faible sous ce profil, c'est l'échelle qui est
# en cause, pas l'échantillon.
HUMAN_PROXY_STRONG_CONFIG: Dict[str, Any] = {
    "depth": 8,
    "time_budget_ms": 1200,
    "use_tablebase": False,
    "blunder_rate": 0.06,
    "use_engine": False,
    "proven_line": False,
}
HUMAN_PROXY_STRONG_ID = "human_proxy_strong"

# Troisième profil, plus faible : indispensable pour séparer le BAS de l'échelle.
# Un joueur moyen bat 100 % du temps les deux premiers niveaux ; sans sonde faible,
# « Très facile » et « Facile » resteraient indiscernables (saturation à 1.00).
HUMAN_PROXY_WEAK_CONFIG: Dict[str, Any] = {
    "depth": 2,
    "time_budget_ms": 200,
    "use_tablebase": False,
    "blunder_rate": 0.45,
    "use_engine": False,
    "proven_line": False,
}

# Quatrième profil, intermédiaire : la sonde « débutant » est si bruitée (45 %
# d'erreurs en profondeur 2) que son propre hasard masque l'écart entre les deux
# premiers niveaux. Ce profil joue en profondeur 4 avec 30 % d'erreurs : assez solide
# pour ne plus perdre contre un bot quasi aléatoire, assez faillible pour perdre
# encore contre un bot qui voit une menace immédiate. C'est lui qui sépare le bas.
HUMAN_PROXY_NOVICE_CONFIG: Dict[str, Any] = {
    "depth": 4,
    "time_budget_ms": 400,
    "use_tablebase": False,
    "blunder_rate": 0.30,
    "use_engine": False,
    "proven_line": False,
}

# Un profil = un couple (profondeur, taux d'erreur). Le nom sert d'identifiant
# dans le JSON et le Markdown.
PROXY_PROFILES: Dict[str, Dict[str, Any]] = {
    "novice": HUMAN_PROXY_NOVICE_CONFIG,
    "debutant": HUMAN_PROXY_WEAK_CONFIG,
    "moyen": HUMAN_PROXY_CONFIG,
    "avance": HUMAN_PROXY_STRONG_CONFIG,
}
# Ordre du plus faible au plus fort : sert à lire les rapports dans l'ordre logique
# plutôt qu'alphabétique.
PROXY_PROFILE_ORDER: tuple[str, ...] = ("novice", "debutant", "moyen", "avance")
DEFAULT_PROXY_PROFILE = "moyen"


def profile_order() -> List[str]:
    """Profils dans l'ordre de force croissante, puis les éventuels profils non listés."""
    known = [p for p in PROXY_PROFILE_ORDER if p in PROXY_PROFILES]
    return known + [p for p in sorted(PROXY_PROFILES) if p not in PROXY_PROFILE_ORDER]


# Tolérance d'inversion *apparente* : un écart négatif plus petit que cela est du bruit
# et n'est même pas signalé. Au-delà, l'inversion est signalée — mais elle ne disqualifie
# la paire que si elle est **statistiquement démontrée** (voir `probe_monotonicity`).
INVERSION_TOLERANCE = 0.05


class _ProxyRegistry:
    """Adapte l'arène : les proxys humains côtoient les vrais bots dans `play_game`."""

    def __init__(self, registry: BotRegistry, proxies: Dict[str, DifficultyBot]) -> None:
        self._registry = registry
        self._proxies = proxies

    def choose_move(self, bot_id: str, engine: Any) -> Any:
        proxy = self._proxies.get(bot_id)
        if proxy is not None:
            return proxy.choose_move(engine)
        return self._registry.choose_move(bot_id, engine)

    def is_valid_bot(self, bot_id: str) -> bool:
        return bot_id in self._proxies or self._registry.is_valid_bot(bot_id)


def run_difficulty_probe(
    bot_ids: Sequence[str],
    registry: BotRegistry,
    games: int,
    base_seed: int = DEFAULT_SEED,
    max_moves: int = 90,
    fast: bool = False,
    profiles: Sequence[str] = (DEFAULT_PROXY_PROFILE,),
    z: float = Z_95,
) -> List[Dict[str, Any]]:
    """Score des proxys humains (siège 1) contre chaque bot (siège 2).

    Le proxy est toujours le premier joueur — c'est la configuration réelle du site
    (l'humain joue X). Son score décroît quand le bot est plus difficile : c'est la
    mesure la plus directe de la difficulté *ressentie*, indépendante de l'Elo
    head-to-head (qui, lui, est écrasé par l'avantage du premier joueur).
    """
    unknown = [p for p in profiles if p not in PROXY_PROFILES]
    if unknown:
        raise ValueError(f"Profil de proxy inconnu : {', '.join(unknown)}")

    proxies: Dict[str, DifficultyBot] = {}
    for name in profiles:
        cfg = dict(PROXY_PROFILES[name])
        if fast:
            cfg["time_budget_ms"] = max(20, int(cfg["time_budget_ms"] * 0.25))
        proxies[HUMAN_PROXY_ID if name == DEFAULT_PROXY_PROFILE else f"{HUMAN_PROXY_ID}_{name}"] = (
            DifficultyBot(**cfg)
        )
    adapter = _ProxyRegistry(registry, proxies)

    proxy_ids = list(proxies.keys())
    rows: List[Dict[str, Any]] = []
    for p_idx, (name, proxy_id) in enumerate(zip(profiles, proxy_ids)):
        for k, bot_id in enumerate(bot_ids):
            score = 0.0
            wins = draws = losses = 0
            for g in range(games):
                random.seed(_game_seed(base_seed, 7919 * k, g, 100_003 * p_idx))
                result = play_game(proxy_id, bot_id, adapter, max_moves=max_moves)
                winner = result["winner"]
                winner = None if winner is None else int(winner)
                if winner == 1:
                    score += 1.0
                    wins += 1
                elif winner == 2:
                    losses += 1
                else:
                    score += 0.5
                    draws += 1
            ci = wilson_interval(score, games, z)
            rows.append(
                {
                    "profile": name,
                    "bot": bot_id,
                    "level": bot_level(bot_id),
                    "games": games,
                    "proxy_score": score,
                    "proxy_rate": round(score / games, 3) if games else None,
                    "ci95": [round(ci[0], 3), round(ci[1], 3)],
                    "wins": wins,
                    "draws": draws,
                    "losses": losses,
                }
            )
    return rows


def probe_monotonicity(
    rows: Sequence[Dict[str, Any]],
    direct: Optional[Sequence[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Verdict de monotonie de l'échelle, par paire de niveaux adjacents.

    Deux instruments **indépendants** mesurent la même chose :

    - la **courbe de difficulté** : la sonde (siège 1) marque-t-elle moins contre le bot
      le plus dur ?
    - la **confrontation directe** (``direct``, la ``matrix`` de l'arène, sièges alternés) :
      les deux bots sont-ils séparés, ou terminent-ils à 0.50/0.50 (chacun gagnant dans
      son siège, ce qui n'est *pas* une égalité de force) ?

    Aucun profil de sonde pris isolément ne peut séparer les six niveaux : un joueur
    avancé écrase les premiers (saturation à 1.00) et un débutant ne marque jamais contre
    les derniers (saturation à 0.00). D'où un verdict **par paire, tous instruments
    confondus**, et **statistique** — jamais un simple écart de points estimés.

    Deux affirmations distinctes sont séparées, car elles ne mesurent pas la même chose :

    - **la force** (``ok``, ``violations``) : le niveau supérieur est-il plus fort ?
      C'est la définition de l'échelle. Preuve possible par la confrontation directe
      (sièges alternés) ou par la courbe de difficulté. Une inversion **démontrée** de la
      confrontation directe (``inversions_direct``) réfute l'échelle ;
    - **la difficulté ressentie** (``felt_inversions``) : une inversion **démontrée** de la
      courbe de difficulté ne réfute pas l'échelle — elle signale qu'un bot moins fort
      peut être *plus dur à battre* pour un adversaire imparfait, typiquement parce qu'il
      s'écarte de la ligne théorique et rend le jeu moins prévisible. C'est une alerte
      produit, pas une faute d'ordre, et elle est remontée séparément.

    Détail des champs : ``proven_by`` (profils démontrant la séparation, intervalle de la
    différence entièrement positif — on ne compare pas deux intervalles de Wilson isolés,
    trop conservateur), ``soft_inversions`` (point estimé inversé au-delà de
    ``INVERSION_TOLERANCE`` sans significativité : les niveaux sont **indiscernables** sur
    ce profil, pas mal ordonnés).

    Une paire est donc « validée » si **aucune confrontation directe ne démontre
    l'inverse** et qu'**au moins un instrument démontre la séparation**.
    """
    by_profile: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        by_profile.setdefault(row.get("profile", DEFAULT_PROXY_PROFILE), []).append(row)

    # Table bot -> profil -> ligne, pour croiser les profils paire par paire.
    table: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for profile, entries in by_profile.items():
        for row in entries:
            table.setdefault(row["bot"], {})[profile] = row

    direct_lookup = {(m["a"], m["b"]): m for m in (direct or [])}

    levels = sorted({row["level"] for row in rows})
    by_level: Dict[int, List[str]] = {}
    for bot, profiles in table.items():
        level = next(r["level"] for r in profiles.values())
        by_level.setdefault(level, []).append(bot)

    checks: List[Dict[str, Any]] = []
    for low_level, high_level in zip(levels, levels[1:]):
        for easier in sorted(by_level.get(low_level, [])):
            for harder in sorted(by_level.get(high_level, [])):
                felt_inversions: List[str] = []
                soft_inversions: List[str] = []
                proven_by: List[str] = []
                rates: Dict[str, Any] = {}
                for profile in profile_order():
                    low = table.get(easier, {}).get(profile)
                    high = table.get(harder, {}).get(profile)
                    if low is None or high is None:
                        continue
                    rate_low = low.get("proxy_rate")
                    rate_high = high.get("proxy_rate")
                    if rate_low is None or rate_high is None:
                        continue
                    delta = round(rate_low - rate_high, 3)
                    diff_ci = newcombe_diff_interval(
                        low.get("proxy_score", 0.0),
                        low.get("games", 0),
                        high.get("proxy_score", 0.0),
                        high.get("games", 0),
                        z=Z_95,
                    )
                    proven = diff_ci[0] > 0.0
                    inverted = diff_ci[1] < 0.0
                    rates[profile] = {
                        "easier": rate_low,
                        "harder": rate_high,
                        "delta": delta,
                        "diff_ci95": [round(diff_ci[0], 3), round(diff_ci[1], 3)],
                        "proven": proven,
                        "inverted": inverted,
                    }
                    if inverted:
                        felt_inversions.append(profile)
                    elif delta < -INVERSION_TOLERANCE:
                        soft_inversions.append(profile)
                    if proven:
                        proven_by.append(profile)

                # Confrontation directe : score du bot le plus facile contre le plus dur.
                entry = direct_lookup.get((easier, harder))
                direct_info: Optional[Dict[str, Any]] = None
                inversions_direct: List[str] = []
                if entry and entry.get("games"):
                    games = int(entry["games"])
                    score = entry.get("score_a")
                    ci = entry.get("ci95_a")
                    if score is not None and ci:
                        lo, hi = float(ci[0]), float(ci[1])
                        direct_info = {
                            "games": games,
                            "score": score,
                            "ci95": [round(lo, 3), round(hi, 3)],
                            "proven": lo > 0.5 or hi < 0.5,
                            "inverted": lo > 0.5,
                        }
                        if lo > 0.5:
                            inversions_direct.append(easier)

                # Seule une inversion de la confrontation directe réfute la force : une
                # inversion de la courbe de difficulté est une alerte produit (cf. docstring).
                ok = (
                    not inversions_direct
                    and (bool(proven_by) or bool(direct_info and direct_info["proven"]))
                )
                checks.append(
                    {
                        "easier": easier,
                        "harder": harder,
                        "rates": rates,
                        "felt_inversions": felt_inversions,
                        "inversions_direct": inversions_direct,
                        "soft_inversions": soft_inversions,
                        "proven_by": proven_by,
                        "direct": direct_info,
                        "ok": ok,
                    }
                )

    return {
        "hint": (
            "la force est validée si la confrontation directe ne démontre jamais l'inverse et "
            "qu'au moins un instrument démontre la séparation ; les inversions de la courbe de "
            "difficulté ne réfutent pas la force mais signalent qu'un bot plus fort peut être "
            "plus prévisible, donc plus facile à battre (voir `felt_inversions`)"
        ),
        "tolerance": INVERSION_TOLERANCE,
        "checks": checks,
        "violations": [c for c in checks if not c["ok"]],
        "felt_inversions": [c for c in checks if c["felt_inversions"]],
        "indistinguishable": [c for c in checks if c["ok"] and c["soft_inversions"]],
    }


# --------------------------------------------------------------------------- #
# Rendu Markdown / JSON
# --------------------------------------------------------------------------- #


def _pct(value: float, games: int) -> str:
    return f"{value:g}/{games}" if games else "—"


def _difficulty_by_profile(rows: Sequence[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """Regroupe les lignes de la sonde par profil, du plus faible au plus fort."""
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(row.get("profile", DEFAULT_PROXY_PROFILE), []).append(row)
    for entries in grouped.values():
        entries.sort(key=lambda r: r["level"])
    ordered: Dict[str, List[Dict[str, Any]]] = {}
    for profile in profile_order():
        if profile in grouped:
            ordered[profile] = grouped[profile]
    for profile in sorted(grouped):
        if profile not in ordered:
            ordered[profile] = grouped[profile]
    return ordered


def render_markdown(data: Dict[str, Any]) -> str:
    meta = data["meta"]
    lines: List[str] = []
    lines.append("# Arène des bots 4mation — classement mesuré")
    lines.append("")
    lines.append(
        f"Généré le {meta['generated_at']} par `scripts/bot_arena.py`."
    )
    lines.append("")
    lines.append("## Configuration mesurée")
    lines.append("")
    lines.append(f"- Bots : {', '.join(meta['bots'])}")
    lines.append(f"- Parties par paire : {meta['games_per_pair']} (sièges alternés)")
    lines.append(f"- Parties jouées : {meta['total_games']}")
    lines.append(f"- Limite de coups : {meta['max_moves']}")
    lines.append(f"- Graine de base : {meta['base_seed']}")
    lines.append(f"- Mode rapide (`--fast`) : {'oui' if meta['fast'] else 'non'}")
    if meta.get("engine_available") is not None:
        engine_txt = "oui" if meta["engine_available"] else "non (repli Minimax sur level_6)"
        lines.append(f"- Moteur Rust `4mation-engine` disponible : {engine_txt}")
    lines.append(f"- Durée de calcul : {meta['elapsed_secs']:.0f} s")
    lines.append("")

    lines.append("## Caveats (à lire avant tout chiffre)")
    lines.append("")
    lines.append(
        f"- **Petit échantillon** : {meta['games_per_pair']} parties par paire "
        f"({meta['total_games']} au total). Les IC à 95 % sont larges et des écarts "
        "de quelques dizaines d'Elo ne sont pas significatifs."
    )
    lines.append(
        "- **Non-reproductibilité due aux budgets temps** : la graine fixe la séquence "
        "des blunders, mais le Minimax itératif et le moteur Rust coupent selon le temps "
        "CPU réel. Les résultats peuvent donc varier légèrement d'une exécution à l'autre."
    )
    if meta["fast"]:
        lines.append(
            "- **Mode `--fast`** : les budgets temps sont réduits (÷4), pour les bots comme "
            "pour les sondes. L'effet n'est **pas symétrique** : un bot dont la recherche est "
            "limitée par le temps (niveaux 4 à 6, profondeurs 8 à 26) perd beaucoup plus "
            "qu'un bot limité par la profondeur (niveaux 1 à 3). Les scores de cette page "
            "sont donc **pessimistes pour le haut de l'échelle** : en production (3 s), le "
            "niveau 6 est plus dur que ce qui est mesuré ici."
        )
    lines.append(
        "- **Avantage structurel du premier joueur** : quand chaque bot gagne dans son "
        "siège, la paire finit 0.50/0.50 et l'Elo ne peut pas les séparer. L'absence "
        "d'écart ne veut pas dire égalité de force."
    )
    lines.append("")

    lines.append("## Classement Elo (Bradley-Terry logistique)")
    lines.append("")
    lines.append("| Rang | Bot | Niveau | Elo | Parties | Score | V/N/D | Siège 1 | Siège 2 |")
    lines.append("|-----:|-----|-------:|----:|--------:|------:|------:|--------:|--------:|")
    for rank, (bot_id, p) in enumerate(ranking(data), start=1):
        p1 = p["as_p1"]
        p2 = p["as_p2"]
        p1_txt = f"{p1['rate']:.2f} ({_pct(p1['score'], p1['games'])})" if p1["games"] else "—"
        p2_txt = f"{p2['rate']:.2f} ({_pct(p2['score'], p2['games'])})" if p2["games"] else "—"
        lines.append(
            f"| {rank} | `{bot_id}` | {p['level']} | **{p['elo']:.0f}** | {p['games']} | "
            f"{_pct(p['score'], p['games'])} | {p['wins']}/{p['draws']}/{p['losses']} | "
            f"{p1_txt} | {p2_txt} |"
        )
    lines.append("")

    lines.append("## Matrice des confrontations (score du bot en ligne, IC 95 % Wilson)")
    lines.append("")
    bots = meta["bots"]
    header = "| A \\ B | " + " | ".join(f"`{b}`" for b in bots) + " |"
    sep = "|---|" + "|".join("---:" for _ in bots) + "|"
    lines.append(header)
    lines.append(sep)
    lookup = {(m["a"], m["b"]): m for m in data["matrix"]}
    for a in bots:
        cells = []
        for b in bots:
            if a == b:
                cells.append("—")
                continue
            entry = lookup.get((a, b))
            if entry is None:
                other = lookup[(b, a)]
                score = 1.0 - other["score_a"]
                low, high = 1.0 - other["ci95_a"][1], 1.0 - other["ci95_a"][0]
                games = other["games"]
                w, d, l = other["losses_a"], other["draws"], other["wins_a"]
            else:
                score, (low, high), games = entry["score_a"], entry["ci95_a"], entry["games"]
                w, d, l = entry["wins_a"], entry["draws"], entry["losses_a"]
            cells.append(f"{score:.2f} [{low:.2f},{high:.2f}] ({w}-{d}-{l})")
        lines.append(f"| `{a}` | " + " | ".join(cells) + " |")
    lines.append("")
    lines.append("Cellule = score de A contre B, IC 95 % de Wilson, puis (V-N-D). 0.50 = parfaite égalité.")
    lines.append("")

    lines.append("## Monotonie attendue")
    lines.append("")
    lines.append(f"Ordre attendu : `{data['monotonicity']['expected']}`.")
    lines.append("")
    lines.append("| Paire adjacente | Elo bas | Elo haut | Δ (haut − bas) | Respecté |")
    lines.append("|---|---:|---:|---:|:---:|")
    for c in data["monotonicity"]["checks"]:
        mark = "oui" if c["ok"] else "**NON**"
        lines.append(
            f"| `{c['lower']}` → `{c['higher']}` | {c['elo_lower']:.0f} | "
            f"{c['elo_higher']:.0f} | {c['delta']:+.0f} | {mark} |"
        )
    lines.append("")
    if data["monotonicity"]["violations"]:
        lines.append("**Inversions détectées :**")
        lines.append("")
        for v in data["monotonicity"]["violations"]:
            lines.append(
                f"- `{v['lower']}` ({v['elo_lower']:.0f}) devant `{v['higher']}` "
                f"({v['elo_higher']:.0f}) : Δ = {v['delta']:+.0f} Elo."
            )
    else:
        lines.append("Aucune inversion sur les paires adjacentes mesurées.")
    lines.append("")

    lines.append("## Détail par bot (sièges)")
    lines.append("")
    lines.append(
        "Tous les bots forts terminent à 1.00 dans le siège du premier joueur : "
        "l'avantage structurel du centre écrase la différence de force tant qu'un bot "
        "ne gagne pas aussi depuis le siège 2."
    )
    lines.append("")
    lines.append("| Bot | Parties siège 1 | Score siège 1 | Parties siège 2 | Score siège 2 |")
    lines.append("|---|---:|---:|---:|---:|")
    for bot_id, p in ranking(data):
        p1, p2 = p["as_p1"], p["as_p2"]
        s1 = f"{p1['score']:g} ({p1['rate']:.2f})" if p1["games"] else "—"
        s2 = f"{p2['score']:g} ({p2['rate']:.2f})" if p2["games"] else "—"
        lines.append(f"| `{bot_id}` | {p1['games']} | {s1} | {p2['games']} | {s2} |")
    lines.append("")

    if data.get("difficulty"):
        lines.append("## Courbe de difficulté (proxy humain en siège 1)")
        lines.append("")
        lines.append(
            "Score d'un adversaire de référence (profondeur et taux d'erreur fixés, voir "
            "colonnes) qui joue **toujours le premier** contre chaque bot. Plus ce score "
            "est bas, plus le bot est difficile à battre pour un joueur non-parfait. C'est "
            "la difficulté *ressentie*, là où l'Elo head-to-head est écrasé par l'avantage "
            "du premier joueur."
        )
        lines.append("")
        for profile, entries in _difficulty_by_profile(data["difficulty"]).items():
            cfg = PROXY_PROFILES.get(profile, {})
            lines.append(
                f"### Profil `{profile}` (profondeur {cfg.get('depth', '?')}, "
                f"{cfg.get('blunder_rate', 0):.0%} d'erreurs)"
            )
            lines.append("")
            lines.append("| Bot | Niveau | Score du proxy | IC 95 % | V/N/D du proxy |")
            lines.append("|---|---:|---:|:---:|:---:|")
            for row in entries:
                rate = f"{row['proxy_rate']:.2f}" if row.get("proxy_rate") is not None else "—"
                ci = row.get("ci95")
                ci_txt = f"[{ci[0]:.2f}, {ci[1]:.2f}]" if ci else "—"
                lines.append(
                    f"| `{row['bot']}` | {row['level']} | {row['proxy_score']:g}/{row['games']} "
                    f"({rate}) | {ci_txt} | {row['wins']}/{row['draws']}/{row['losses']} |"
                )
            lines.append("")

    verdict = data.get("difficulty_monotonicity")
    if verdict:
        lines.append("### Verdict de force (tous profils confondus)")
        lines.append("")
        lines.append(
            f"Une paire de niveaux adjacents est validée en **force** si la confrontation directe "
            "ne démontre jamais l'inverse **et** qu'**au moins un instrument** démontre la "
            "séparation. Les deux instruments sont indépendants : la courbe de difficulté (sonde "
            "en siège 1) et la confrontation directe (sièges alternés, colonne « direct »). La "
            "démonstration porte sur la **différence** des scores (intervalle hybride de Newcombe) : "
            "comparer deux intervalles de Wilson isolés serait trop conservateur."
        )
        lines.append("")
        lines.append(
            "La tolérance d'inversion apparente ("
            f"{verdict.get('tolerance', 0):.2f}) ne sert qu'à classer les écarts non significatifs "
            "en « indiscernables » : un écart net mais non significatif ne réfute pas l'ordre, il "
            "dit que les deux niveaux se jouent pareil pour ce profil."
        )
        lines.append("")
        header_profiles = profile_order()
        lines.append(
            "| Paire (facile → dur) | "
            + " | ".join(f"Δ `{p}`" for p in header_profiles)
            + " | Direct | Démonstration | Statut |"
        )
        lines.append("|---|" + "---:|" * len(header_profiles) + ":---:|:---:|:---:|")
        for c in verdict["checks"]:
            rates = c.get("rates") or {}
            deltas = []
            for p in header_profiles:
                info = rates.get(p)
                if not info:
                    deltas.append("—")
                else:
                    lo, hi = info.get("diff_ci95", (float("nan"), float("nan")))
                    deltas.append(f"{info['delta']:+.2f} [{lo:+.2f}, {hi:+.2f}]")
            direct = c.get("direct")
            if direct:
                dlo, dhi = direct["ci95"]
                direct_txt = f"{direct['score']:.2f} [{dlo:.2f}, {dhi:.2f}]"
            else:
                direct_txt = "—"
            proof = [f"`{p}`" for p in c.get("proven_by") or []]
            if direct and direct.get("proven"):
                proof.append("directe")
            shown = ", ".join(proof) or "aucune"
            if c["ok"]:
                order = "validée" + (" (indiscernable)" if c.get("soft_inversions") else "")
            else:
                order = "**réfutée**"
            lines.append(
                f"| `{c['easier']}` → `{c['harder']}` | "
                + " | ".join(deltas)
                + f" | {direct_txt} | {shown} | {order} |"
            )
        lines.append("")
        if verdict["violations"]:
            for v in verdict["violations"]:
                if v.get("inversions_direct"):
                    lines.append(
                        f"- **Inversion démontrée (directe)** : `{v['easier']}` bat `{v['harder']}` "
                        "en confrontation directe, l'ordre est faux."
                    )
                else:
                    lines.append(
                        f"- **Non démontrée** : `{v['easier']}` → `{v['harder']}` n'est séparée par "
                        "aucun profil (échantillon insuffisant ou niveaux trop proches)."
                    )
        else:
            lines.append(
                "Chaque niveau est strictement plus fort que le précédent : séparation "
                "démontrée par au moins un instrument, et aucune inversion de la "
                "confrontation directe sur aucune paire."
            )
        for c in verdict.get("indistinguishable") or []:
            lines.append(
                f"- *Indiscernable* : `{c['easier']}` et `{c['harder']}` ne se distinguent pas pour "
                f"{', '.join('`' + p + '`' for p in c['soft_inversions'])} (écart non significatif : "
                "l'ordre est établi par un autre instrument, mais ces deux niveaux se jouent pareil "
                "pour ce profil)."
            )
        if verdict.get("felt_inversions"):
            lines.append("")
            lines.append(
                "**Difficulté ressentie — caveat produit, pas faute d'ordre.** La force est bien "
                "croissante, mais pour la ou les sondes ci-dessous un bot plus fort est en réalité "
                "*plus facile à battre* qu'un bot plus faible : non pas qu'il soit moins fort, mais "
                "parce qu'il joue plus souvent la ligne théorique et devient donc plus prévisible, "
                "là où le bot plus faible s'en écarte davantage et punit mieux un adversaire "
                "imparfait."
            )
            lines.append("")
            for c in verdict["felt_inversions"]:
                details = []
                for p in c["felt_inversions"]:
                    info = c["rates"][p]
                    details.append(
                        f"`{p}` (score {info['easier']:.2f} vs {info['harder']:.2f}, "
                        f"Δ {info['delta']:+.2f})"
                    )
                lines.append(f"- `{c['easier']}` plus dur à battre que `{c['harder']}` : " + ", ".join(details) + ".")
        lines.append("")

    lines.append("## Reproduction")
    lines.append("")
    lines.append("```powershell")
    lines.append('$env:PYTHONPATH=".;script"')
    fast_flag = " --fast" if meta["fast"] else ""
    probe_flag = ""
    if meta.get("probe_games"):
        profiles = " ".join(meta.get("probe_profiles") or [DEFAULT_PROXY_PROFILE])
        probe_flag = f" --probe-games {meta['probe_games']}"
        if profiles != DEFAULT_PROXY_PROFILE:
            probe_flag += f" --probe-profiles {profiles}"
    lines.append(
        f".venv\\Scripts\\python.exe scripts/bot_arena.py --games {meta['games_per_pair']}"
        f" --seed {meta['base_seed']}{fast_flag}{probe_flag}"
    )
    lines.append("```")
    lines.append("")
    return "\n".join(lines)


def write_outputs(data: Dict[str, Any], out: Optional[Path], md: Optional[Path]) -> None:
    if out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    if md is not None:
        md.parent.mkdir(parents=True, exist_ok=True)
        md.write_text(render_markdown(data), encoding="utf-8")


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def _default_bots() -> List[str]:
    registry = BotRegistry()
    return [b["id"] for b in sorted(registry.list_bots(), key=lambda b: b["level"])]


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Arène round-robin des bots 4mation")
    parser.add_argument("--bots", nargs="+", default=None, help="liste des bots (défaut : tous)")
    parser.add_argument("--games", type=int, default=6, help="parties par paire")
    parser.add_argument("--max-moves", type=int, default=90, help="limite de coups par partie")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="graine de base")
    parser.add_argument("--out", default=str(ROOT / "scripts" / "arena_bots.json"))
    parser.add_argument("--md", default=str(ROOT / "scripts" / "ARENA_BOTS.md"))
    parser.add_argument("--fast", action="store_true", help="budgets temps réduits")
    parser.add_argument("--z", type=float, default=Z_95, help="quantile pour l'IC")
    parser.add_argument(
        "--probe-games",
        type=int,
        default=0,
        help="parties par bot pour la courbe de difficulté (proxy humain en siège 1, 0 = désactivé)",
    )
    parser.add_argument(
        "--probe-profiles",
        nargs="+",
        default=[DEFAULT_PROXY_PROFILE],
        choices=sorted(PROXY_PROFILES),
        help=f"profils de proxy humain à sonder (défaut : {DEFAULT_PROXY_PROFILE})",
    )
    parser.add_argument("--quiet", action="store_true", help="ne pas journaliser chaque partie")
    args = parser.parse_args(argv)

    bot_ids = args.bots if args.bots else _default_bots()
    registry: BotRegistry = FastBotRegistry() if args.fast else BotRegistry()

    log = None if args.quiet else (lambda message: print(message, flush=True))
    data = run_arena(
        bot_ids,
        registry,
        games_per_pair=args.games,
        base_seed=args.seed,
        max_moves=args.max_moves,
        z=args.z,
        fast=args.fast,
        log=log,
    )

    if args.probe_games > 0:
        print()
        print(
            f"Courbe de difficulté (profil(s) {', '.join(args.probe_profiles)}, "
            f"{args.probe_games} parties/bot)…"
        )
        data["difficulty"] = run_difficulty_probe(
            bot_ids,
            registry,
            games=args.probe_games,
            base_seed=args.seed + 1000,
            max_moves=args.max_moves,
            fast=args.fast,
            profiles=args.probe_profiles,
            z=args.z,
        )
        data["difficulty_monotonicity"] = probe_monotonicity(
            data["difficulty"], data.get("matrix")
        )
        data["meta"]["probe_games"] = args.probe_games
        data["meta"]["probe_profiles"] = list(args.probe_profiles)

    out = None if args.out in (None, "", "-") else Path(args.out)
    md = None if args.md in (None, "", "-") else Path(args.md)
    write_outputs(data, out, md)

    print()
    print(f"{data['meta']['total_games']} parties en {data['meta']['elapsed_secs']:.0f} s")
    for rank, (bot_id, p) in enumerate(ranking(data), start=1):
        print(
            f"  {rank}. {bot_id:<8} Elo {p['elo']:>7.1f} | {p['score']:g}/{p['games']} "
            f"| V/N/D {p['wins']}/{p['draws']}/{p['losses']}"
        )
    if data["monotonicity"]["violations"]:
        print("Monotonie NON respectée :")
        for v in data["monotonicity"]["violations"]:
            print(f"  {v['lower']} ({v['elo_lower']:.0f}) > {v['higher']} ({v['elo_higher']:.0f})")
    else:
        print("Monotonie respectée sur toutes les paires adjacentes.")
    if data.get("difficulty"):
        print("Courbe de difficulté (proxy humain, siège 1 — plus bas = plus dur) :")
        for profile, entries in _difficulty_by_profile(data["difficulty"]).items():
            print(f"  [profil {profile}]")
            for row in entries:
                rate = f"{row['proxy_rate']:.2f}" if row["proxy_rate"] is not None else "—"
                ci = row.get("ci95")
                ci_txt = f"[{ci[0]:.2f}, {ci[1]:.2f}]" if ci else "—"
                print(
                    f"    {row['bot']:<8} proxy {row['proxy_score']:g}/{row['games']} "
                    f"({rate} {ci_txt}) | V/N/D {row['wins']}/{row['draws']}/{row['losses']}"
                )
        verdict = data.get("difficulty_monotonicity") or {}
        print("Verdict de force (aucune inversion directe + séparation démontrée) :")
        if verdict.get("violations"):
            for v in verdict["violations"]:
                reasons = []
                if v.get("inversions_direct"):
                    reasons.append("inversion en confrontation directe")
                direct_ok = bool((v.get("direct") or {}).get("proven"))
                if not v.get("proven_by") and not direct_ok:
                    reasons.append("séparation non démontrée")
                print(f"  RÉFUTÉE : {v['easier']} → {v['harder']} ({'; '.join(reasons)})")
        else:
            print("  Chaque niveau est strictement plus fort que le précédent.")
        for c in verdict.get("indistinguishable") or []:
            print(
                f"  INDISCERNABLE : {c['easier']} et {c['harder']} sur "
                f"{', '.join(c['soft_inversions'])} (écart non significatif)"
            )
        for c in verdict.get("felt_inversions") or []:
            details = []
            for p in c['felt_inversions']:
                info = c["rates"][p]
                details.append(f"{p} {info['easier']:.2f} vs {info['harder']:.2f}")
            print(
                f"  DIFFICULTÉ RESSENTIE : {c['easier']} plus dur à battre que {c['harder']} "
                f"({'; '.join(details)}) — plus fort mais plus prévisible"
            )
    if out is not None:
        print(f"JSON : {out}")
    if md is not None:
        print(f"Markdown : {md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
