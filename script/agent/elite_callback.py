"""
Callback pour tracker les meilleures parties et les visualiser
"""

from stable_baselines3.common.callbacks import BaseCallback
from agent.elite_tracker import EliteGameTracker
from agent.elite_visualizer import generate_elite_games_html
from pathlib import Path
import numpy as np


class EliteGameCallback(BaseCallback):
    """
    Callback qui track les meilleures parties et les sauvegarde
    """
    
    def __init__(self, top_n: int = 10, save_dir: str = "elite_games", verbose=0):
        super().__init__(verbose)
        self.tracker = EliteGameTracker(top_n=top_n, save_dir=save_dir)
        self.save_dir = Path(save_dir)
        self.save_dir.mkdir(parents=True, exist_ok=True)
        self.episode_count = 0
        self.iteration = 0
    
    def _on_step(self) -> bool:
        """Appelé à chaque step - requis par BaseCallback"""
        return True
        
    def _on_rollout_end(self) -> None:
        """Appelé à la fin de chaque rollout"""
        # Incrémenter l'itération
        self.iteration += 1
        
        # Récupérer les données des épisodes depuis les environnements
        # Les environnements avec GameTrackerWrapper ont les données
        episodes_collected = 0
        try:
            if hasattr(self.training_env, 'envs'):
                # Environnement vectorisé - accéder aux environnements wrappés
                for env_wrapper in self.training_env.envs:
                    # Le wrapper peut être dans env ou directement accessible
                    env = getattr(env_wrapper, 'env', env_wrapper)
                    if hasattr(env, 'get_episode_data'):
                        episode_data = env.get_episode_data()
                        if episode_data:
                            reward = episode_data.get('reward', 0)
                            # Ajouter toutes les parties (pas seulement positives)
                            # pour avoir une meilleure sélection
                            self.tracker.add_game(reward, episode_data)
                            episodes_collected += 1
                            # Réinitialiser le tracking pour le prochain épisode
                            if hasattr(env, 'reset_episode_tracking'):
                                env.reset_episode_tracking()
            elif hasattr(self.training_env, 'get_episode_data'):
                # Environnement simple
                episode_data = self.training_env.get_episode_data()
                if episode_data:
                    reward = episode_data.get('reward', 0)
                    self.tracker.add_game(reward, episode_data)
                    episodes_collected += 1
                    if hasattr(self.training_env, 'reset_episode_tracking'):
                        self.training_env.reset_episode_tracking()
        except Exception as e:
            # Ignorer les erreurs de récupération
            pass
        
        # Sauvegarder les meilleures parties toutes les 5 itérations
        if self.iteration % 5 == 0:
            self.tracker.save_elite_games(iteration=self.iteration)
            
            # Générer la visualisation HTML
            elite_games = self.tracker.get_elite_games()
            if elite_games:
                html_path = self.save_dir / "visualization.html"
                try:
                    generate_elite_games_html(elite_games, str(html_path))
                    
                    # Afficher les statistiques
                    best_reward = elite_games[0]['reward']
                    avg_reward = sum(g['reward'] for g in elite_games) / len(elite_games)
                    print(f"\n[Elite Games] Iteration {self.iteration} - Top {len(elite_games)} parties:")
                    print(f"   Meilleure recompense: {best_reward:.2f}")
                    print(f"   Recompense moyenne (top {len(elite_games)}): {avg_reward:.2f}")
                    print(f"   Visualisation HTML: {html_path}")
                    print(f"   (Ouvrez le fichier dans votre navigateur pour voir les parties)")
                except Exception as e:
                    print(f"   Erreur lors de la generation de la visualisation: {e}")
    
    def get_elite_games(self):
        """Retourne les meilleures parties"""
        return self.tracker.get_elite_games()

