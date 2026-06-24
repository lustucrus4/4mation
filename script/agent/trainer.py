"""
Script d'entraînement pour l'agent IA
"""

import os
from stable_baselines3 import PPO
from stable_baselines3.common.callbacks import EvalCallback, CheckpointCallback
from stable_baselines3.common.monitor import Monitor

from agent.model import create_model, create_vec_env
from agent.callbacks import TrainingProgressCallback
from simulator.env import FourMationEnv
from simulator.game_tracker_wrapper import GameTrackerWrapper
from utils.config import config


def train_agent(total_timesteps: int = None, 
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
                imitation_ratio: float = 0.5):
    """
    Entraîne un agent IA à jouer à 4mation.
    
    Args:
        total_timesteps: Nombre total de pas d'entraînement
        save_freq: Fréquence de sauvegarde (en pas)
        eval_freq: Fréquence d'évaluation (en pas)
        eval_episodes: Nombre d'épisodes pour l'évaluation
        model_name: Nom du modèle
        load_model: Chemin vers un modèle à charger
        num_envs: Nombre d'environnements parallèles
        opponent_type: Type d'adversaire ("random", "self", "none")
    """
    # Utiliser les valeurs de config par défaut si non spécifiées
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
    
    # Créer l'environnement avec tracking des parties
    print("Création de l'environnement...")
    
    # Si on utilise Minimax comme enseignant, on l'intègre
    if use_minimax_teacher:
        from simulator.minimax_opponent_wrapper import MinimaxOpponentWrapper
        
        def make_minimax_env():
            """Factory pour créer un environnement avec Minimax"""
            env_base = FourMationEnv(opponent_type="none")
            env_base = MinimaxOpponentWrapper(env_base, minimax_depth=minimax_depth)
            return GameTrackerWrapper(env_base)
        
        if num_envs > 1:
            # Créer l'environnement vectorisé avec Minimax
            from stable_baselines3.common.vec_env import DummyVecEnv
            env = DummyVecEnv([make_minimax_env for _ in range(num_envs)])
        else:
            env = make_minimax_env()
        
        # Environnement d'évaluation avec Minimax
        eval_env = make_minimax_env()
        
        print(f"🤖 Minimax activé comme adversaire (profondeur: {minimax_depth})")
    else:
        if num_envs > 1:
            env = create_vec_env(num_envs=num_envs, opponent_type=opponent_type, track_games=True)
            # Pour l'évaluation, on utilise un environnement simple (pas vectorisé)
            eval_env = FourMationEnv(opponent_type=opponent_type)
            eval_env = GameTrackerWrapper(eval_env)
        else:
            env_base = FourMationEnv(opponent_type=opponent_type)
            env = GameTrackerWrapper(env_base)
            eval_env = FourMationEnv(opponent_type=opponent_type)
            eval_env = GameTrackerWrapper(eval_env)
    
    # Envelopper l'environnement d'évaluation avec Monitor pour les statistiques
    # Note: GameTrackerWrapper doit être avant Monitor pour capturer les données
    eval_env = Monitor(eval_env)
    
    # Créer ou charger le modèle
    print("Création du modèle...")
    if load_model:
        model = PPO.load(load_model, env=env)
        print(f"Modèle chargé depuis {load_model}")
        # S'assurer que le modèle utilise le GPU si disponible
        try:
            import torch
            if torch.cuda.is_available() and hasattr(model.policy, 'device'):
                model.policy.to(torch.device("cuda"))
                print(f"Modèle déplacé sur GPU: {torch.cuda.get_device_name(0)}")
        except:
            pass
    else:
        model = create_model(env=env, num_envs=num_envs)
    
    # Créer les callbacks
    callbacks = []
    
    # Callback pour afficher la progression (améliore le feedback)
    progress_callback = TrainingProgressCallback(verbose=1)
    callbacks.append(progress_callback)
    
    # Callbacks pour Minimax (imitation learning + curriculum)
    if use_minimax_teacher:
        from agent.expert_data_generator import ExpertDataGenerator
        from agent.imitation_callback import ImitationCallback
        from agent.curriculum_callback import CurriculumCallback
        
        # Générer les données expert pour l'imitation learning
        print("Génération des données expert avec Minimax...")
        expert_gen = ExpertDataGenerator(minimax_depth=8)  # Profondeur max pour les données expert
        expert_data = expert_gen.generate(num_games=1000, player1_minimax=True)
        
        # Callback d'imitation learning
        imitation_callback = ImitationCallback(
            expert_data=expert_data,
            imitation_ratio=imitation_ratio,
            verbose=1
        )
        callbacks.append(imitation_callback)
        print(f"📚 Imitation Learning activé (ratio: {imitation_ratio * 100:.0f}%)")
        
        # Callback de curriculum learning
        curriculum_callback = CurriculumCallback(
            initial_depth=2,
            max_depth=8,
            verbose=1
        )
        callbacks.append(curriculum_callback)
        print(f"📈 Curriculum Learning activé (profondeur: 2→4→6→8)")
    
    # Callback pour tracker les meilleures parties
    if enable_elite_tracking:
        # Utiliser le système de générations élitistes
        from agent.elite_generations import EliteGenerationCallback
        elite_callback = EliteGenerationCallback(
            games_per_generation=games_per_generation,
            elite_size=elite_games,
            save_dir="elite_generations",
            verbose=1
        )
        callbacks.append(elite_callback)
        print(f"Systeme elitiste par generations active:")
        print(f"   - {games_per_generation} parties par generation")
        print(f"   - {elite_games} meilleures parties conservees par generation")
        print(f"   - Les meilleures influencent la generation suivante")
        print(f"   - Visualisation HTML: elite_generations/visualization.html")
    
    # Callback d'évaluation
    eval_callback = EvalCallback(
        eval_env,
        best_model_save_path=os.path.join(config.training.model_dir, "best"),
        log_path=os.path.join(config.training.log_dir, "evaluations"),
        eval_freq=eval_freq,
        n_eval_episodes=eval_episodes,
        deterministic=True,
        render=False,
        verbose=0  # Réduire le verbose pour éviter la duplication
    )
    callbacks.append(eval_callback)
    
    # Callback de sauvegarde périodique
    checkpoint_callback = CheckpointCallback(
        save_freq=save_freq,
        save_path=os.path.join(config.training.model_dir, "checkpoints"),
        name_prefix=model_name
    )
    callbacks.append(checkpoint_callback)
    
    # Démarrer l'entraînement
    print(f"Démarrage de l'entraînement pour {total_timesteps} pas...")
    print(f"Logs TensorBoard: {config.training.log_dir}")
    print(f"Modèles sauvegardés dans: {config.training.model_dir}")
    
    # Vérifier si tqdm et rich sont disponibles pour la barre de progression
    try:
        import tqdm
        import rich
        use_progress_bar = True
    except ImportError:
        use_progress_bar = False
        print("⚠️  tqdm et rich non installés - barre de progression désactivée")
        print("   Installez-les avec: pip install tqdm rich")
    
    model.learn(
        total_timesteps=total_timesteps,
        callback=callbacks,
        progress_bar=use_progress_bar
    )
    
    # Sauvegarder le modèle final
    final_model_path = os.path.join(config.training.model_dir, f"{model_name}_final")
    model.save(final_model_path)
    print(f"Modèle final sauvegardé dans: {final_model_path}")
    
    return model


if __name__ == "__main__":
    # Exemple d'utilisation
    print("=== Entraînement de l'agent IA pour 4mation ===")
    
    # Entraîner avec un adversaire aléatoire
    model = train_agent(
        total_timesteps=100000,
        opponent_type="random"
    )
    
    print("Entraînement terminé!")

