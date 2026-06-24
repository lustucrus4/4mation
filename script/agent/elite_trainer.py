"""
Système d'entraînement élitiste utilisant les meilleures parties
"""

from pathlib import Path
from stable_baselines3 import PPO
from stable_baselines3.common.callbacks import EvalCallback, CheckpointCallback
from stable_baselines3.common.monitor import Monitor
import os
import numpy as np

from agent.model import create_model, create_vec_env
from agent.callbacks import TrainingProgressCallback
from agent.elite_callback import EliteGameCallback
from agent.elite_tracker import EliteGameTracker
from simulator.env import FourMationEnv
from simulator.game_tracker_wrapper import GameTrackerWrapper
from utils.config import config


def train_with_elite_games(total_timesteps: int = None,
                          num_envs: int = 1,
                          opponent_type: str = "random",
                          force_cpu: bool = False,
                          elite_games_dir: str = "elite_games",
                          use_elite_for_training: bool = True):
    """
    Entraîne le modèle en utilisant les meilleures parties pour améliorer l'apprentissage
    
    Args:
        total_timesteps: Nombre total de pas d'entraînement
        num_envs: Nombre d'environnements parallèles
        opponent_type: Type d'adversaire
        force_cpu: Forcer l'utilisation du CPU
        elite_games_dir: Répertoire contenant les meilleures parties
        use_elite_for_training: Si True, utilise les meilleures parties pour l'entraînement
    """
    if total_timesteps is None:
        total_timesteps = config.training.total_timesteps
    
    # Charger les meilleures parties si disponibles
    elite_tracker = EliteGameTracker(top_n=10, save_dir=elite_games_dir)
    elite_file = Path(elite_games_dir) / "elite_games.json"
    
    if elite_file.exists() and use_elite_for_training:
        print(f"Chargement des meilleures parties depuis {elite_file}")
        if elite_tracker.load_elite_games(str(elite_file)):
            elite_games = elite_tracker.get_elite_games()
            print(f"   {len(elite_games)} meilleures parties chargees")
            print(f"   Meilleure recompense: {elite_games[0]['reward']:.2f}")
        else:
            print("   Aucune partie elite trouvee")
    else:
        print("   Aucune partie elite existante - demarrage normal")
    
    # Créer l'environnement avec tracking
    print("Creation de l'environnement...")
    if num_envs > 1:
        env = create_vec_env(num_envs=num_envs, opponent_type=opponent_type, track_games=True)
        eval_env = FourMationEnv(opponent_type=opponent_type)
        eval_env = GameTrackerWrapper(eval_env)
    else:
        env_base = FourMationEnv(opponent_type=opponent_type)
        env = GameTrackerWrapper(env_base)
        eval_env = FourMationEnv(opponent_type=opponent_type)
        eval_env = GameTrackerWrapper(eval_env)
    
    eval_env = Monitor(eval_env)
    
    # Créer le modèle
    print("Creation du modele...")
    model = create_model(env=env, num_envs=num_envs, force_cpu=force_cpu)
    
    # Créer les callbacks
    callbacks = []
    
    # Callback de progression
    progress_callback = TrainingProgressCallback(verbose=1)
    callbacks.append(progress_callback)
    
    # Callback élitiste (track et sauvegarde les meilleures parties)
    elite_callback = EliteGameCallback(top_n=10, save_dir=elite_games_dir, verbose=1)
    callbacks.append(elite_callback)
    
    # Callback d'évaluation
    eval_callback = EvalCallback(
        eval_env,
        best_model_save_path=os.path.join(config.training.model_dir, "best"),
        log_path=os.path.join(config.training.log_dir, "evaluations"),
        eval_freq=config.training.eval_freq,
        n_eval_episodes=config.training.eval_episodes,
        deterministic=True,
        render=False,
        verbose=0
    )
    callbacks.append(eval_callback)
    
    # Callback de sauvegarde
    checkpoint_callback = CheckpointCallback(
        save_freq=config.training.save_freq,
        save_path=os.path.join(config.training.model_dir, "checkpoints"),
        name_prefix=config.training.model_name
    )
    callbacks.append(checkpoint_callback)
    
    # Démarrer l'entraînement
    print(f"Démarrage de l'entraînement pour {total_timesteps} pas...")
    print(f"Les meilleures parties seront trackées et visualisées dans {elite_games_dir}/")
    
    model.learn(
        total_timesteps=total_timesteps,
        callback=callbacks,
        progress_bar=True
    )
    
    # Sauvegarder le modèle final
    final_model_path = os.path.join(config.training.model_dir, f"{config.training.model_name}_final")
    model.save(final_model_path)
    print(f"Modèle final sauvegardé dans: {final_model_path}")
    
    # Générer la visualisation finale
    elite_games = elite_callback.get_elite_games()
    if elite_games:
        print(f"\n{'='*60}")
        print("MEILLEURES PARTIES FINALES")
        print(f"{'='*60}")
        for i, game in enumerate(elite_games[:5], 1):
            print(f"  #{i}: Recompense {game['reward']:.2f} - {game['move_count']} coups")
        print(f"\nVisualisation HTML: {elite_games_dir}/visualization.html")
        print(f"{'='*60}\n")
    
    return model

