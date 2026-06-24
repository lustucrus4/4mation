"""
Modèle d'IA pour jouer à 4mation
"""

from stable_baselines3 import PPO
from stable_baselines3.common.env_util import make_vec_env
from stable_baselines3.common.callbacks import EvalCallback, CheckpointCallback
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

from simulator.env import FourMationEnv
from utils.config import config


def create_model(env=None, load_path: str = None, num_envs: int = 1, force_cpu: bool = False):
    """
    Crée ou charge un modèle PPO optimisé pour GPU.
    
    Args:
        env: Environnement (si None, crée un nouvel environnement)
        load_path: Chemin vers un modèle existant à charger
        num_envs: Nombre d'environnements parallèles (pour optimiser les paramètres)
    
    Returns:
        Modèle PPO
    """
    if env is None:
        env = FourMationEnv()
    
    # Détecter le GPU et optimiser les paramètres
    use_gpu = HAS_CUDA and not force_cpu  # Désactiver GPU si force_cpu=True
    device_str = "CPU (force)" if force_cpu else (DEVICE_NAME if HAS_CUDA else "CPU")
    
    # Paramètres optimisés selon le nombre d'environnements et la présence du GPU
    if use_gpu and num_envs >= 64:
        # Configuration ultra-optimisée pour beaucoup d'environnements (64+)
        print(f"Configuration GPU ultra-optimisee pour {device_str}")
        print(f"   Environnements paralleles: {num_envs}")
        print(f"   Parametres: batch_size=4096, n_steps=16384, reseau [512,512,256]")
        
        policy_kwargs = dict(
            net_arch=[dict(pi=[512, 512, 256], vf=[512, 512, 256])]
        )
        
        model = PPO(
            "MlpPolicy",
            env,
            learning_rate=3e-4,
            n_steps=16384,  # Encore plus de pas pour maximiser le GPU
            batch_size=4096,  # Batch très grand pour GPU
            n_epochs=10,
            gamma=0.99,
            gae_lambda=0.95,
            clip_range=0.2,
            ent_coef=0.01,
            vf_coef=0.5,
            max_grad_norm=0.5,
            tensorboard_log=config.training.log_dir,
            verbose=0,  # Réduit pour éviter la duplication
            policy_kwargs=policy_kwargs,
            device=DEVICE if use_gpu else "auto"
        )
    elif use_gpu and num_envs >= 32:
        # Configuration optimisée pour beaucoup d'environnements (32-63)
        print(f"Configuration GPU optimisee pour {device_str}")
        print(f"   Environnements paralleles: {num_envs}")
        print(f"   Parametres: batch_size=3072, n_steps=12288, reseau [384,384,192]")
        
        policy_kwargs = dict(
            net_arch=[dict(pi=[384, 384, 192], vf=[384, 384, 192])]
        )
        
        model = PPO(
            "MlpPolicy",
            env,
            learning_rate=3e-4,
            n_steps=12288,  # Plus de pas pour mieux utiliser le GPU
            batch_size=3072,  # Batch plus grand pour GPU
            n_epochs=10,
            gamma=0.99,
            gae_lambda=0.95,
            clip_range=0.2,
            ent_coef=0.01,
            vf_coef=0.5,
            max_grad_norm=0.5,
            tensorboard_log=config.training.log_dir,
            verbose=0,  # Réduit pour éviter la duplication
            policy_kwargs=policy_kwargs,
            device=DEVICE if use_gpu else "auto"
        )
    elif use_gpu and num_envs >= 8:
        # Optimisé pour RTX 5070 et GPU similaires avec plusieurs environnements
        print(f"Configuration GPU optimisee pour {device_str}")
        print(f"   Environnements paralleles: {num_envs}")
        print(f"   Parametres: batch_size=2048, n_steps=8192, reseau [256,256,128]")
        
        policy_kwargs = dict(
            net_arch=[dict(pi=[256, 256, 128], vf=[256, 256, 128])]
        )
        
        model = PPO(
            "MlpPolicy",
            env,
            learning_rate=3e-4,
            n_steps=8192,  # Plus de pas pour mieux utiliser le GPU
            batch_size=2048,  # Batch plus grand pour GPU
            n_epochs=10,
            gamma=0.99,
            gae_lambda=0.95,
            clip_range=0.2,
            ent_coef=0.01,
            vf_coef=0.5,
            max_grad_norm=0.5,
            tensorboard_log=config.training.log_dir,
            verbose=0,  # Réduit pour éviter la duplication (notre callback gère l'affichage)
            policy_kwargs=policy_kwargs,
            device=DEVICE if use_gpu else "auto"
        )
    elif use_gpu:
        # GPU avec peu d'environnements
        print(f"Configuration GPU pour {device_str}")
        print(f"   Parametres: batch_size=1024, n_steps=4096, reseau [128,128]")
        
        policy_kwargs = dict(
            net_arch=[dict(pi=[128, 128], vf=[128, 128])]
        )
        
        model = PPO(
            "MlpPolicy",
            env,
            learning_rate=3e-4,
            n_steps=4096,
            batch_size=1024,
            n_epochs=10,
            gamma=0.99,
            gae_lambda=0.95,
            clip_range=0.2,
            ent_coef=0.01,
            vf_coef=0.5,
            max_grad_norm=0.5,
            tensorboard_log=config.training.log_dir,
            verbose=1,
            policy_kwargs=policy_kwargs,
            device=DEVICE
        )
    else:
        # CPU - paramètres conservateurs
        print(f"Configuration CPU (GPU non disponible)")
        print(f"   Parametres: batch_size=64, n_steps=2048, reseau [64,64]")
        
        model = PPO(
            "MlpPolicy",
            env,
            learning_rate=3e-4,
            n_steps=2048,
            batch_size=64,
            n_epochs=10,
            gamma=0.99,
            gae_lambda=0.95,
            clip_range=0.2,
            ent_coef=0.01,
            vf_coef=0.5,
            max_grad_norm=0.5,
            tensorboard_log=config.training.log_dir,
            verbose=1,
            device="auto"
        )
    
    # Charger un modèle existant si spécifié
    if load_path and os.path.exists(load_path):
        model = PPO.load(load_path, env=env)
        print(f"Modele charge depuis {load_path}")
        # S'assurer que le modèle utilise le GPU si disponible
        if use_gpu and hasattr(model.policy, 'device'):
            model.policy.to(DEVICE)
    
    return model


def create_vec_env(num_envs: int = 1, opponent_type: str = "random", track_games: bool = True):
    """
    Crée un environnement vectorisé (plusieurs environnements en parallèle).
    Utile pour accélérer l'entraînement.
    
    Args:
        num_envs: Nombre d'environnements parallèles
        opponent_type: Type d'adversaire
        track_games: Si True, enveloppe les environnements avec GameTrackerWrapper
    
    Returns:
        Environnement vectorisé
    """
    def make_env():
        env = FourMationEnv(opponent_type=opponent_type)
        if track_games:
            from simulator.game_tracker_wrapper import GameTrackerWrapper
            env = GameTrackerWrapper(env)
        return env
    
    if num_envs == 1:
        return DummyVecEnv([make_env])
    else:
        return make_vec_env(make_env, n_envs=num_envs)

