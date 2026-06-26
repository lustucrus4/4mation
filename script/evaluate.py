"""
Benchmark du taux de victoire d'un adversaire contre les bots Minimax (niveaux 1 à 5).

Usage (depuis le dossier 4mation/) :
    set PYTHONPATH=.;script
    python script/evaluate.py --games 100 --opponent random
    python script/evaluate.py --games 50 --opponent ppo
    python script/evaluate.py --games 20 --opponent random --bot level_3
    python script/evaluate.py --games 10 --opponent ppo --model script/models/best/best_model.zip

Options :
    --games N          Nombre de parties par bot (défaut : 20)
    --opponent TYPE    random | ppo (défaut : random)
    --bot ID           Un seul bot (level_1 … level_5) ; sinon tous
    --model PATH       Checkpoint PPO (défaut : meilleur modèle trouvé)
    --seed N           Graine aléatoire (défaut : 42)
"""

from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "script"))

from agent.bot_eval import (
    evaluate_bot,
    make_ppo_choose_fn,
    play_game,
)
from api.services.bot_registry import BotRegistry
from game.game_engine import GameEngine

Move = Tuple[int, int]
MODEL_DIR = ROOT / "script" / "models"
DEFAULT_MODEL_NAMES = ("best/best_model.zip", "fourmation_ppo_final.zip")

# Réexport pour compatibilité
__all__ = [
    "play_game",
    "evaluate_bot",
    "run_benchmark",
    "make_random_opponent",
    "make_ppo_opponent",
]


def _default_ppo_path() -> Optional[Path]:
    for rel in DEFAULT_MODEL_NAMES:
        candidate = MODEL_DIR / rel
        if candidate.exists():
            return candidate
    return None


def make_random_opponent(rng: random.Random) -> Callable[[GameEngine], Move]:
    def choose(engine: GameEngine) -> Move:
        valid = engine.get_valid_actions()
        if not valid:
            raise RuntimeError("Aucun coup légal")
        return rng.choice(valid)

    return choose


def make_ppo_opponent(model_path: Path) -> Callable[[GameEngine], Move]:
    from agent.model import create_model
    from simulator.env import FourMationEnv

    env = FourMationEnv(opponent_type="none")
    model = create_model(env=env, load_path=str(model_path))
    return make_ppo_choose_fn(model, env)


def run_benchmark(
    num_games: int,
    opponent_type: str,
    bot_ids: List[str],
    model_path: Optional[Path],
    seed: int,
) -> None:
    rng = random.Random(seed)
    registry = BotRegistry()

    if opponent_type == "random":
        opponent_choose = make_random_opponent(rng)
        opponent_label = "aléatoire"
    elif opponent_type == "ppo":
        path = model_path or _default_ppo_path()
        if path is None or not path.exists():
            print("ERREUR: Aucun checkpoint PPO trouve. Entrainez un modele ou passez --model.")
            sys.exit(1)
        print(f"Modele PPO : {path}")
        opponent_choose = make_ppo_opponent(path)
        opponent_label = f"PPO ({path.name})"
    else:
        print(f"ERREUR: Adversaire inconnu : {opponent_type}")
        sys.exit(1)

    print(f"Benchmark — adversaire {opponent_label} vs bots Minimax")
    print(f"   {num_games} parties par bot · graine {seed}")
    print("=" * 60)

    for bot_id in bot_ids:
        meta = next((b for b in registry.list_bots() if b["id"] == bot_id), None)
        name = meta["name"] if meta else bot_id
        stats = evaluate_bot(bot_id, opponent_choose, registry, num_games, rng)
        completed = num_games - int(stats["incomplete"])
        print(
            f"{name} ({bot_id}): "
            f"{stats['wins']}V / {stats['losses']}D / {stats['draws']}N "
            f"({stats['win_rate']:.1f}% victoires adversaire, {completed} parties complètes)"
        )

    print("=" * 60)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Benchmark adversaire vs bots 4mation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--games", type=int, default=20, help="Parties par bot")
    parser.add_argument(
        "--opponent",
        choices=("random", "ppo"),
        default="random",
        help="Type d'adversaire",
    )
    parser.add_argument(
        "--bot",
        type=str,
        default=None,
        help="Bot cible (level_1 … level_5) ; défaut : tous",
    )
    parser.add_argument("--model", type=str, default=None, help="Chemin checkpoint PPO")
    parser.add_argument("--seed", type=int, default=42, help="Graine aléatoire")

    args = parser.parse_args()
    bot_ids = [args.bot] if args.bot else [f"level_{i}" for i in range(1, 6)]

    registry = BotRegistry()
    for bot_id in bot_ids:
        if not registry.is_valid_bot(bot_id):
            print(f"ERREUR: Bot inconnu : {bot_id}")
            sys.exit(1)

    model_path = Path(args.model) if args.model else None
    run_benchmark(args.games, args.opponent, bot_ids, model_path, args.seed)


if __name__ == "__main__":
    main()
