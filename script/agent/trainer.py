"""
Script d'entraînement pour l'agent IA (Phase 2 — obs 149 dims).
"""

import os
from stable_baselines3.common.callbacks import EvalCallback, CheckpointCallback
from stable_baselines3.common.monitor import Monitor

from agent.model import create_model, create_vec_env, _ppo_class
from agent.callbacks import TrainingProgressCallback, EvalBotsCallback
from agent.env_utils import (
    HAS_MASKABLE_PPO,
    OBSERVATION_DIM,
    LEGACY_OBSERVATION_DIM,
    make_training_env,
    wrap_env_for_ppo,
    ppo_algorithm_name,
)
from simulator.env import FourMationEnv
from simulator.game_tracker_wrapper import GameTrackerWrapper
from utils.config import config


def _make_eval_env(opponent_type: str = "random"):
    """Environnement d'évaluation (obs 149 + masque)."""
    env = FourMationEnv(opponent_type=opponent_type)
    env = GameTrackerWrapper(env)
    return wrap_env_for_ppo(env)


def train_agent(
    total_timesteps: int = None,
    save_freq: int = None,
    eval_freq: int = None,
    eval_episodes: int = None,
    model_name: str = None,
    load_model: str = None,
    num_envs: int = 1,
    opponent_type: str = "random",
    force_cpu: bool = False,
    elite_games: int = 2,
    games_per_generation: int = 100,
    enable_elite_tracking: bool = True,
    use_minimax_teacher: bool = False,
    minimax_depth: int = 4,
    imitation_ratio: float = 0.5,
    eval_bots: bool = False,
    eval_bots_games: int = 10,
    eval_bots_freq: int = None,
    expert_games: int = 150,
    expert_depth: int = 6,
):
    """
    Entraîne un agent IA à jouer à 4mation.

    Observation : {OBSERVATION_DIM} dims (board + last_move + action_mask).
    Les checkpoints Phase 1 ({LEGACY_OBSERVATION_DIM} dims) sont incompatibles.
    """
    if total_timesteps is None:
        total_timesteps = config.training.total_timesteps
    if save_freq is None:
        save_freq = config.training.save_freq
    if eval_freq is None:
        eval_freq = config.training.eval_freq
    if eval_episodes is None:
        eval_episodes = config.training.eval_episodes
    if model_name is None:
        model_name = config.training.model_name
    if eval_bots_freq is None:
        eval_bots_freq = eval_freq

    print(f"Algorithme: {ppo_algorithm_name()} | Observation: {OBSERVATION_DIM} dims")
    if not HAS_MASKABLE_PPO:
        print("Astuce: pip install sb3-contrib pour MaskablePPO (masquage natif)")

    print("Creation de l'environnement...")

    if use_minimax_teacher:
        from simulator.minimax_opponent_wrapper import MinimaxOpponentWrapper

        def make_minimax_env():
            env_base = FourMationEnv(opponent_type="none")
            env_base = MinimaxOpponentWrapper(env_base, minimax_depth=minimax_depth)
            env_base = GameTrackerWrapper(env_base)
            return wrap_env_for_ppo(env_base)

        if num_envs > 1:
            from stable_baselines3.common.vec_env import DummyVecEnv
            env = DummyVecEnv([make_minimax_env for _ in range(num_envs)])
        else:
            env = make_minimax_env()

        eval_env = make_minimax_env()
        print(f"Minimax activé comme adversaire (profondeur: {minimax_depth})")
    else:
        if num_envs > 1:
            env = create_vec_env(num_envs=num_envs, opponent_type=opponent_type, track_games=True)
            eval_env = _make_eval_env(opponent_type=opponent_type)
        else:
            env = make_training_env(opponent_type=opponent_type, track_games=True)
            eval_env = _make_eval_env(opponent_type=opponent_type)

    eval_env = Monitor(eval_env)

    print("Creation du modele...")
    algo = _ppo_class()
    if load_model:
        try:
            model = algo.load(load_model, env=env)
            print(f"Modele charge depuis {load_model}")
            if not force_cpu:
                try:
                    import torch
                    if torch.cuda.is_available() and hasattr(model.policy, "to"):
                        model.policy.to(torch.device("cuda"))
                        print(f"Modele deplace sur GPU: {torch.cuda.get_device_name(0)}")
                except Exception:
                    pass
        except Exception as exc:
            print(
                f"ERREUR: impossible de charger {load_model} ({exc}).\n"
                f"   Checkpoints {LEGACY_OBSERVATION_DIM} dims incompatibles "
                f"avec obs {OBSERVATION_DIM} dims — utilisez --new-model."
            )
            raise
    else:
        model = create_model(env=env, num_envs=num_envs, force_cpu=force_cpu)

    callbacks = []

    progress_callback = TrainingProgressCallback(verbose=1)
    callbacks.append(progress_callback)

    if use_minimax_teacher:
        from agent.expert_data_generator import ExpertDataGenerator
        from agent.imitation_callback import ImitationCallback
        from agent.curriculum_callback import CurriculumCallback

        print(
            f"Generation des donnees expert avec Minimax "
            f"({expert_games} parties, profondeur {expert_depth})..."
        )
        expert_gen = ExpertDataGenerator(minimax_depth=expert_depth)
        expert_data = expert_gen.generate(num_games=expert_games, player1_minimax=True)

        imitation_callback = ImitationCallback(
            expert_data=expert_data,
            imitation_ratio=imitation_ratio,
            verbose=1,
        )
        callbacks.append(imitation_callback)
        print(f"Imitation Learning active (ratio: {imitation_ratio * 100:.0f}%)")

        curriculum_callback = CurriculumCallback(
            initial_depth=2,
            max_depth=8,
            verbose=1,
        )
        callbacks.append(curriculum_callback)
        print("Curriculum Learning active (profondeur: 2→4→6→8)")

    if enable_elite_tracking:
        from agent.elite_generations import EliteGenerationCallback
        elite_callback = EliteGenerationCallback(
            games_per_generation=games_per_generation,
            elite_size=elite_games,
            save_dir="elite_generations",
            verbose=1,
        )
        callbacks.append(elite_callback)
        print("Systeme elitiste par generations active")

    if eval_bots:
        bots_callback = EvalBotsCallback(
            eval_freq=eval_bots_freq,
            num_games=eval_bots_games,
            verbose=1,
        )
        callbacks.append(bots_callback)
        print(
            f"Eval bots active: level_1/3/5, {eval_bots_games} parties/bot "
            f"tous les {eval_bots_freq} steps"
        )

    eval_callback = EvalCallback(
        eval_env,
        best_model_save_path=os.path.join(config.training.model_dir, "best"),
        log_path=os.path.join(config.training.log_dir, "evaluations"),
        eval_freq=eval_freq,
        n_eval_episodes=eval_episodes,
        deterministic=True,
        render=False,
        verbose=0,
    )
    callbacks.append(eval_callback)

    checkpoint_callback = CheckpointCallback(
        save_freq=save_freq,
        save_path=os.path.join(config.training.model_dir, "checkpoints"),
        name_prefix=model_name,
    )
    callbacks.append(checkpoint_callback)

    print(f"Demarrage de l'entrainement pour {total_timesteps} pas...")
    print(f"Logs TensorBoard: {config.training.log_dir}")
    print(f"Modeles sauvegardes dans: {config.training.model_dir}")

    try:
        import tqdm  # noqa: F401
        import rich  # noqa: F401
        use_progress_bar = True
    except ImportError:
        use_progress_bar = False
        print("tqdm/rich non installes — barre de progression desactivee")

    model.learn(
        total_timesteps=total_timesteps,
        callback=callbacks,
        progress_bar=use_progress_bar,
    )

    final_model_path = os.path.join(config.training.model_dir, f"{model_name}_final")
    model.save(final_model_path)
    print(f"Modele final sauvegarde dans: {final_model_path}")

    return model


if __name__ == "__main__":
    print("=== Entrainement de l'agent IA pour 4mation (Phase 2) ===")
    model = train_agent(total_timesteps=100000, opponent_type="random")
    print("Entrainement termine!")
