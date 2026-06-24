"""
Système d'élitisme par générations : génère N parties, garde les K meilleures,
puis utilise leurs stratégies pour la génération suivante
"""

import json
import numpy as np
from pathlib import Path
from typing import List, Dict, Tuple
from datetime import datetime
from stable_baselines3.common.callbacks import BaseCallback


class EliteGenerationTracker:
    """
    Gère les générations de parties avec élitisme
    """
    
    def __init__(self, games_per_generation: int = 100, elite_size: int = 2, save_dir: str = "elite_generations"):
        self.games_per_generation = games_per_generation
        self.elite_size = elite_size
        self.save_dir = Path(save_dir)
        self.save_dir.mkdir(parents=True, exist_ok=True)
        
        # Génération actuelle
        self.current_generation = 0
        self.current_generation_games: List[Tuple[float, Dict]] = []
        self.games_collected_this_gen = 0
        
        # Historique des générations
        self.generations_history: List[Dict] = []
    
    def add_game(self, reward: float, game_data: Dict):
        """Ajoute une partie à la génération actuelle"""
        game_data['reward'] = reward
        game_data['timestamp'] = datetime.now().isoformat()
        self.current_generation_games.append((reward, game_data))
        self.games_collected_this_gen += 1
    
    def is_generation_complete(self) -> bool:
        """Vérifie si on a collecté assez de parties pour cette génération"""
        return self.games_collected_this_gen >= self.games_per_generation
    
    def finish_generation(self) -> List[Dict]:
        """
        Termine la génération actuelle, sélectionne les élites, et passe à la suivante
        
        Returns:
            Liste des parties élites de cette génération
        """
        if not self.current_generation_games:
            return []
        
        # Trier par récompense décroissante
        self.current_generation_games.sort(key=lambda x: x[0], reverse=True)
        
        # Sélectionner les élites
        elite_games = [game_data for _, game_data in self.current_generation_games[:self.elite_size]]
        
        # Sauvegarder les statistiques de la génération
        gen_stats = {
            'generation': self.current_generation,
            'total_games': len(self.current_generation_games),
            'elite_size': self.elite_size,
            'best_reward': self.current_generation_games[0][0] if self.current_generation_games else 0,
            'avg_reward': sum(r for r, _ in self.current_generation_games) / len(self.current_generation_games) if self.current_generation_games else 0,
            'elite_rewards': [r for r, _ in self.current_generation_games[:self.elite_size]],
            'elite_games': elite_games
        }
        
        self.generations_history.append(gen_stats)
        
        # Sauvegarder
        self._save_generation(gen_stats)
        
        # Passer à la génération suivante
        self.current_generation += 1
        self.current_generation_games = []
        self.games_collected_this_gen = 0
        
        return elite_games
    
    def _save_generation(self, gen_stats: Dict):
        """Sauvegarde les statistiques d'une génération"""
        # Sauvegarder les stats de la génération
        stats_file = self.save_dir / f"generation_{gen_stats['generation']}_stats.json"
        with open(stats_file, 'w', encoding='utf-8') as f:
            json.dump(gen_stats, f, indent=2, ensure_ascii=False)
        
        # Sauvegarder l'historique complet
        history_file = self.save_dir / "generations_history.json"
        with open(history_file, 'w', encoding='utf-8') as f:
            json.dump(self.generations_history, f, indent=2, ensure_ascii=False)
    
    def get_current_elite(self) -> List[Dict]:
        """Retourne les parties élites de la génération actuelle (si terminée)"""
        if self.generations_history:
            return self.generations_history[-1].get('elite_games', [])
        return []
    
    def get_all_elite(self) -> List[Dict]:
        """Retourne toutes les parties élites de toutes les générations"""
        all_elite = []
        for gen in self.generations_history:
            all_elite.extend(gen.get('elite_games', []))
        # Trier par récompense et garder les meilleures
        all_elite.sort(key=lambda x: x.get('reward', 0), reverse=True)
        return all_elite


class EliteGenerationCallback(BaseCallback):
    """
    Callback qui gère les générations avec élitisme
    """
    
    def __init__(self, games_per_generation: int = 100, elite_size: int = 2, 
                 save_dir: str = "elite_generations", verbose=0):
        super().__init__(verbose)
        self.tracker = EliteGenerationTracker(
            games_per_generation=games_per_generation,
            elite_size=elite_size,
            save_dir=save_dir
        )
        self.save_dir = Path(save_dir)
        self.save_dir.mkdir(parents=True, exist_ok=True)
        self.iteration = 0
        self.last_episode_count = 0  # Pour tracker les épisodes via VecMonitor
        print(f"\n[EliteGen] Initialisation:")
        print(f"   - Parties par generation: {games_per_generation}")
        print(f"   - Elites par generation: {elite_size}")
        print(f"   - Dossier de sauvegarde: {save_dir}")
    
    def _find_game_tracker(self, env, max_depth=10, depth=0):
        """Trouve récursivement le GameTrackerWrapper dans la hiérarchie d'environnements"""
        if depth >= max_depth:
            return None
        
        # Vérifier si c'est le GameTrackerWrapper
        if hasattr(env, 'get_episode_data'):
            return env
        
        # Essayer d'accéder à l'environnement sous-jacent
        if hasattr(env, 'env'):
            return self._find_game_tracker(env.env, max_depth, depth + 1)
        
        return None
    
    def _on_step(self) -> bool:
        """Appelé à chaque step - on vérifie si des épisodes sont terminés"""
        try:
            # Vérifier les épisodes terminés via VecMonitor
            if hasattr(self.training_env, 'get_episode_rewards'):
                # VecMonitor track les épisodes terminés
                episode_rewards = self.training_env.get_episode_rewards()
                episode_lengths = self.training_env.get_episode_lengths()
                
                # Si de nouveaux épisodes sont terminés
                if len(episode_rewards) > self.last_episode_count:
                    new_episodes = len(episode_rewards) - self.last_episode_count
                    self.last_episode_count = len(episode_rewards)
                    
                    # Récupérer les données des nouveaux épisodes terminés
                    self._collect_finished_episodes(new_episodes)
        except Exception as e:
            pass  # Ignorer les erreurs silencieusement
        
        return True
    
    def _on_rollout_end(self) -> None:
        """Appelé à la fin de chaque rollout"""
        self.iteration += 1
        
        # Essayer aussi de collecter à la fin du rollout
        self._collect_finished_episodes()
        
        # Debug périodique
        if self.iteration % 10 == 0:
            print(f"[EliteGen] Iteration {self.iteration}: "
                  f"{self.tracker.games_collected_this_gen}/{self.tracker.games_per_generation} parties collectees")
        
        # Vérifier si la génération est complète
        if self.tracker.is_generation_complete():
            elite_games = self.tracker.finish_generation()
            gen_num = self.tracker.current_generation - 1
            
            print(f"\n{'='*60}")
            print(f"GENERATION {gen_num} TERMINEE")
            print(f"{'='*60}")
            print(f"Parties jouees: {self.tracker.games_per_generation}")
            print(f"Elites selectionnees: {len(elite_games)}")
            
            if elite_games:
                best_reward = elite_games[0].get('reward', 0)
                print(f"Meilleure recompense: {best_reward:.2f}")
                print(f"Recompenses des elites: {[g.get('reward', 0) for g in elite_games]}")
                print(f"\nLes {len(elite_games)} meilleures parties seront utilisees")
                print(f"pour influencer la generation suivante.")
                print(f"{'='*60}\n")
            
            # Générer la visualisation
            self._generate_visualization()
        
        # Générer aussi une visualisation périodique même si la génération n'est pas complète
        elif self.iteration % 20 == 0 and self.tracker.games_collected_this_gen > 0:
            # Sauvegarder l'état actuel
            self._save_current_state()
            # Générer une visualisation avec les générations complètes + la génération en cours
            self._generate_visualization(include_current=True)
    
    def _collect_finished_episodes(self, num_episodes=None):
        """Collecte les épisodes terminés depuis les environnements"""
        episodes_collected = 0
        try:
            # Accéder aux environnements vectorisés
            envs_to_check = []
            
            # Essayer différentes structures d'environnements vectorisés
            if hasattr(self.training_env, 'envs'):
                envs_to_check = self.training_env.envs
            elif hasattr(self.training_env, 'venv'):
                if hasattr(self.training_env.venv, 'envs'):
                    envs_to_check = self.training_env.venv.envs
                elif hasattr(self.training_env.venv, 'venv') and hasattr(self.training_env.venv.venv, 'envs'):
                    envs_to_check = self.training_env.venv.venv.envs
            elif hasattr(self.training_env, 'env') and hasattr(self.training_env.env, 'envs'):
                envs_to_check = self.training_env.env.envs
            
            # Parcourir tous les environnements
            for env_wrapper in envs_to_check:
                # Trouver le GameTrackerWrapper dans la hiérarchie
                tracker = self._find_game_tracker(env_wrapper)
                if tracker:
                    episode_data = tracker.get_episode_data()
                    if episode_data and episode_data.get('reward') is not None:
                        reward = episode_data.get('reward', 0)
                        self.tracker.add_game(reward, episode_data)
                        episodes_collected += 1
                        # Réinitialiser pour éviter de relire
                        if hasattr(tracker, 'reset_episode_tracking'):
                            tracker.reset_episode_tracking()
                        
                        # Limiter si num_episodes est spécifié
                        if num_episodes and episodes_collected >= num_episodes:
                            break
            
            # Si aucun épisode collecté, essayer l'environnement simple
            if episodes_collected == 0:
                tracker = self._find_game_tracker(self.training_env)
                if tracker:
                    episode_data = tracker.get_episode_data()
                    if episode_data and episode_data.get('reward') is not None:
                        reward = episode_data.get('reward', 0)
                        self.tracker.add_game(reward, episode_data)
                        episodes_collected += 1
                        if hasattr(tracker, 'reset_episode_tracking'):
                            tracker.reset_episode_tracking()
            
            # Debug : afficher le nombre d'épisodes collectés
            if episodes_collected > 0:
                print(f"[EliteGen] {episodes_collected} episodes collectes, "
                      f"total gen {self.tracker.current_generation}: {self.tracker.games_collected_this_gen}/{self.tracker.games_per_generation}")
                
        except Exception as e:
            if self.verbose > 0:
                print(f"[EliteGen] Erreur lors de la collecte: {e}")
            import traceback
            if self.verbose > 1:
                traceback.print_exc()
            # Générer une visualisation avec les générations complètes + la génération en cours
            self._generate_visualization(include_current=True)
    
    def _generate_visualization(self, include_current=False):
        """Génère la visualisation HTML des générations"""
        try:
            from agent.elite_visualizer import generate_elite_games_html_by_generation
            
            # Préparer l'historique des générations
            generations_to_visualize = self.tracker.generations_history.copy()
            
            # Si demandé, inclure la génération en cours (avec les meilleures parties actuelles)
            if include_current and self.tracker.current_generation_games:
                sorted_games = sorted(self.tracker.current_generation_games, key=lambda x: x[0], reverse=True)
                elite_size = min(self.tracker.elite_size, len(sorted_games))
                elite_games = [game_data for _, game_data in sorted_games[:elite_size]]
                
                current_gen_stats = {
                    'generation': self.tracker.current_generation,
                    'total_games': len(self.tracker.current_generation_games),
                    'elite_size': elite_size,
                    'best_reward': sorted_games[0][0] if sorted_games else 0,
                    'avg_reward': sum(r for r, _ in self.tracker.current_generation_games) / len(self.tracker.current_generation_games) if self.tracker.current_generation_games else 0,
                    'elite_rewards': [r for r, _ in sorted_games[:elite_size]],
                    'elite_games': elite_games
                }
                generations_to_visualize.append(current_gen_stats)
            
            # Visualiser toutes les élites organisées par génération
            if generations_to_visualize:
                html_path = self.save_dir / "visualization.html"
                generate_elite_games_html_by_generation(
                    generations_to_visualize, 
                    str(html_path)
                )
                abs_path = html_path.resolve()
                print(f"\n✅ Visualisation HTML generee: {abs_path}")
                print(f"   🌐 Ouvrez ce fichier dans votre navigateur pour voir les parties!")
                print(f"   💡 Commandes pour ouvrir:")
                print(f"      - PowerShell: .\\ouvrir_visualisation.ps1")
                print(f"      - CMD: ouvrir_visualisation.bat")
                print(f"      - Ou double-cliquez sur: {abs_path}")
                
                # Essayer d'ouvrir automatiquement (optionnel)
                try:
                    import os
                    import platform
                    if platform.system() == 'Windows':
                        os.startfile(str(abs_path))
                        print(f"   🚀 Ouverture automatique dans le navigateur...")
                except:
                    pass  # Ignorer si l'ouverture automatique échoue
        except Exception as e:
            print(f"Erreur lors de la generation de la visualisation: {e}")
            import traceback
            traceback.print_exc()
    
    def get_current_elite(self) -> List[Dict]:
        """Retourne les parties élites de la génération actuelle"""
        return self.tracker.get_current_elite()
    
    def get_generation_stats(self) -> Dict:
        """Retourne les statistiques de la génération actuelle"""
        if self.tracker.generations_history:
            return self.tracker.generations_history[-1]
        return {}
    
    def _save_current_state(self):
        """Sauvegarde l'état actuel de la génération en cours"""
        if not self.tracker.current_generation_games:
            return
        
        # Trier par récompense
        sorted_games = sorted(self.tracker.current_generation_games, key=lambda x: x[0], reverse=True)
        
        # Sauvegarder un snapshot
        snapshot = {
            'generation': self.tracker.current_generation,
            'games_collected': self.tracker.games_collected_this_gen,
            'games_per_generation': self.tracker.games_per_generation,
            'current_best_reward': sorted_games[0][0] if sorted_games else 0,
            'current_top_5_rewards': [r for r, _ in sorted_games[:5]],
            'iteration': self.iteration
        }
        
        snapshot_file = self.save_dir / f"generation_{self.tracker.current_generation}_snapshot.json"
        try:
            import json
            with open(snapshot_file, 'w', encoding='utf-8') as f:
                json.dump(snapshot, f, indent=2, ensure_ascii=False)
        except Exception as e:
            if self.verbose > 0:
                print(f"[EliteGen] Erreur lors de la sauvegarde du snapshot: {e}")

