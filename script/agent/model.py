"""
Modèle d'IA pour jouer à 4mation (observation 149 dims).
"""

from stable_baselines3 import PPO
from stable_baselines3.common.env_util import make_vec_env
from stable_baselines3.common.vec_env import DummyVecEnv
import os

# Détection GPU
try:
    import torch
    HAS_CUDA = torch.cuda.is_available()
    if HAS_CUDA:
        DEVICE_NAME = torch.cuda.get_device_name(0)
        DEVICE = torch.device("cuda")
    else:
        DEVICE_NAME = "CPU"
        DEVICE = torch.device("cpu")
except ImportError:
    HAS_CUDA = False
    DEVICE_NAME = "CPU (PyTorch non installé)"
    DEVICE = None

from agent.env_utils import (
    HAS_MASKABLE_PPO,
    OBSERVATION_DIM,
    LEGACY_OBSERVATION_DIM,
    make_training_env,
    ppo_algorithm_name,
)
from simulator.env import FourMationEnv
from utils.config import config

if HAS_MASKABLE_PPO:
    from sb3_contrib import MaskablePPO


def _ppo_class():
    """Retourne MaskablePPO ou PPO selon la disponibilité de sb3-contrib."""
    return MaskablePPO if HAS_MASKABLE_PPO else PPO


def _check_observation_compat(env, context: str = "chargement") -> None:
    """Avertit si la taille d'observation ne correspond pas au modèle attendu."""
    obs_size = env.observation_space.shape[0]
    if obs_size != OBSERVATION_DIM:
        print(
            f"ATTENTION: observation {obs_size} dims (attendu {OBSERVATION_DIM}). "
            f"Les checkpoints {LEGACY_OBSERVATION_DIM} dims sont incompatibles."
        )


def _build_ppo(env, num_envs: int, use_gpu: bool, **overrides):
    """Instancie PPO ou MaskablePPO avec des hyperparamètres adaptés."""
    algo = _ppo_class()
    algo_label = ppo_algorithm_name()
    common = dict(
        learning_rate=3e-4,
        n_epochs=10,
        gamma=0.99,
        gae_lambda=0.95,
        clip_range=0.2,
        ent_coef=0.01,
        vf_coef=0.5,
        max_grad_norm=0.5,
        tensorboard_log=config.training.log_dir,
        device=DEVICE if use_gpu else "auto",
    )

    if use_gpu and num_envs >= 64:
        print(f"Configuration {algo_label} GPU ultra-optimisee pour {DEVICE_NAME}")
        print(f"   Environnements paralleles: {num_envs}")
        policy_kwargs = dict(net_arch=[dict(pi=[512, 512, 256], vf=[512, 512, 256])])
        params = dict(n_steps=16384, batch_size=4096, verbose=0, policy_kwargs=policy_kwargs)
    elif use_gpu and num_envs >= 32:
        print(f"Configuration {algo_label} GPU optimisee pour {DEVICE_NAME}")
        print(f"   Environnements paralleles: {num_envs}")
        policy_kwargs = dict(net_arch=[dict(pi=[384, 384, 192], vf=[384, 384, 192])])
        params = dict(n_steps=12288, batch_size=3072, verbose=0, policy_kwargs=policy_kwargs)
    elif use_gpu and num_envs >= 8:
        print(f"Configuration {algo_label} GPU optimisee pour {DEVICE_NAME}")
        print(f"   Environnements paralleles: {num_envs}")
        policy_kwargs = dict(net_arch=[dict(pi=[256, 256, 128], vf=[256, 256, 128])])
        params = dict(n_steps=8192, batch_size=2048, verbose=0, policy_kwargs=policy_kwargs)
    elif use_gpu:
        print(f"Configuration {algo_label} GPU pour {DEVICE_NAME}")
        policy_kwargs = dict(net_arch=[dict(pi=[128, 128], vf=[128, 128])])
        params = dict(n_steps=4096, batch_size=1024, verbose=1, policy_kwargs=policy_kwargs)
    else:
        print("Configuration CPU (GPU non disponible)")
        params = dict(n_steps=2048, batch_size=64, verbose=1)

    params.update(overrides)
    params.update(common)
    return algo("MlpPolicy", env, **params)


def create_model(env=None, load_path: str = None, num_envs: int = 1, force_cpu: bool = False):
    """
    Crée ou charge un modèle PPO / MaskablePPO (obs 149 dims).

    Args:
        env: Environnement (si None, crée un nouvel environnement)
        load_path: Chemin vers un modèle existant à charger
        num_envs: Nombre d'environnements parallèles (pour optimiser les paramètres)
        force_cpu: Désactive le GPU

    Returns:
        Modèle PPO ou MaskablePPO
    """
    if env is None:
        env = make_training_env(opponent_type="random", track_games=False)

    _check_observation_compat(env)
    use_gpu = HAS_CUDA and not force_cpu
    algo = _ppo_class()

    if load_path and os.path.exists(load_path):
        try:
            model = algo.load(load_path, env=env)
            print(f"Modele charge depuis {load_path} ({ppo_algorithm_name()})")
            if use_gpu and hasattr(model.policy, "to"):
                model.policy.to(DEVICE)
            return model
        except Exception as exc:
            print(
                f"ERREUR chargement {load_path}: {exc}\n"
                f"   Les checkpoints Phase 1 ({LEGACY_OBSERVATION_DIM} dims) sont "
                f"incompatibles avec l'observation {OBSERVATION_DIM} dims.\n"
                f"   Relancez avec --new-model pour un entrainement from scratch."
            )
            raise

    print(f"Creation d'un nouveau modele {ppo_algorithm_name()} (obs {OBSERVATION_DIM} dims)")
    if HAS_MASKABLE_PPO:
        print("   Masquage d'actions: MaskablePPO (sb3-contrib)")
    else:
        print("   Masquage d'actions: ActionMaskWrapper (installez sb3-contrib pour MaskablePPO)")

    return _build_ppo(env, num_envs=num_envs, use_gpu=use_gpu)


def create_vec_env(num_envs: int = 1, opponent_type: str = "random", track_games: bool = True):
    """
    Crée un environnement vectorisé avec obs 149 dims et masquage d'actions.
    """
    def make_env():
        return make_training_env(opponent_type=opponent_type, track_games=track_games)

    if num_envs == 1:
        return DummyVecEnv([make_env])
    return make_vec_env(make_env, n_envs=num_envs)
