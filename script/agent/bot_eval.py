"""
Évaluation inline du modèle PPO contre les bots Minimax (level_1 … level_5).
"""

from __future__ import annotations

import random
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple, Union

import numpy as np

from api.services.bot_registry import BotRegistry
from game.game_engine import GameEngine

Move = Tuple[int, int]
DEFAULT_EVAL_BOTS = ["level_1", "level_3", "level_5"]
ALL_BOTS = [f"level_{i}" for i in range(1, 6)]


def _sync_env_engine(env, engine: GameEngine) -> None:
    env.engine.state = engine.get_state().copy()


def make_ppo_choose_fn(model, env) -> Callable[[GameEngine], Move]:
    """Construit une fonction de choix de coup à partir d'un modèle SB3 en mémoire."""
    width = env.engine.board_width

    def choose(engine: GameEngine) -> Move:
        _sync_env_engine(env, engine)
        obs = env._get_observation()
        action, _ = model.predict(obs, deterministic=True)
        row = int(action) // width
        col = int(action) % width
        move = (row, col)
        valid = engine.get_valid_actions()
        if move not in valid and valid:
            return valid[0]
        return move

    return choose


def play_game(
    opponent_choose: Callable[[GameEngine], Move],
    bot_id: str,
    registry: BotRegistry,
    opponent_player: int,
    rng: random.Random,
) -> Optional[int]:
    engine = GameEngine()
    engine.reset()
    max_plies = engine.board_width * engine.board_height + 4

    for _ in range(max_plies):
        if engine.is_terminal():
            break
        player = engine.get_current_player()
        if player == opponent_player:
            move = opponent_choose(engine)
        else:
            move = registry.choose_move(bot_id, engine)
            if move is None:
                break
        _, success, _ = engine.step(move)
        if not success:
            break

    if not engine.is_terminal():
        return None
    return engine.get_winner()


def evaluate_bot(
    bot_id: str,
    opponent_choose: Callable[[GameEngine], Move],
    registry: BotRegistry,
    num_games: int,
    rng: random.Random,
) -> Dict[str, float]:
    wins = losses = draws = incomplete = 0

    for game_idx in range(num_games):
        opponent_player = 1 if game_idx % 2 == 0 else 2
        winner = play_game(opponent_choose, bot_id, registry, opponent_player, rng)

        if winner is None:
            incomplete += 1
        elif winner == 0:
            draws += 1
        elif winner == opponent_player:
            wins += 1
        else:
            losses += 1

    completed = num_games - incomplete
    win_rate = (wins / completed * 100.0) if completed else 0.0
    return {
        "wins": wins,
        "losses": losses,
        "draws": draws,
        "incomplete": incomplete,
        "win_rate": win_rate,
    }


def run_model_vs_bots(
    model,
    env,
    num_games: int = 10,
    bot_ids: Optional[List[str]] = None,
    seed: int = 42,
    verbose: bool = True,
) -> Dict[str, Dict[str, float]]:
    """
    Benchmark un modèle SB3 (en mémoire) contre les bots Minimax.

    Returns:
        Dict bot_id -> stats
    """
    bot_ids = bot_ids or DEFAULT_EVAL_BOTS
    rng = random.Random(seed)
    registry = BotRegistry()
    opponent_choose = make_ppo_choose_fn(model, env)
    results: Dict[str, Dict[str, float]] = {}

    if verbose:
        print(f"\n{'=' * 60}")
        print(f"Benchmark bots — {num_games} parties/bot (graine {seed})")
        print(f"{'=' * 60}")

    for bot_id in bot_ids:
        meta = next((b for b in registry.list_bots() if b["id"] == bot_id), None)
        name = meta["name"] if meta else bot_id
        stats = evaluate_bot(bot_id, opponent_choose, registry, num_games, rng)
        results[bot_id] = stats
        if verbose:
            completed = num_games - int(stats["incomplete"])
            print(
                f"  {name} ({bot_id}): "
                f"{stats['wins']}V / {stats['losses']}D / {stats['draws']}N "
                f"({stats['win_rate']:.1f}% victoires PPO, {completed} complètes)"
            )

    if verbose:
        print(f"{'=' * 60}\n")

    return results


def run_checkpoint_vs_bots(
    model_path: Union[str, Path],
    num_games: int = 10,
    bot_ids: Optional[List[str]] = None,
    seed: int = 42,
    verbose: bool = True,
) -> Dict[str, Dict[str, float]]:
    """Benchmark un checkpoint .zip contre les bots."""
    from agent.model import create_model
    from simulator.env import FourMationEnv

    env = FourMationEnv(opponent_type="none")
    model = create_model(env=env, load_path=str(model_path))
    return run_model_vs_bots(
        model, env, num_games=num_games, bot_ids=bot_ids, seed=seed, verbose=verbose
    )
