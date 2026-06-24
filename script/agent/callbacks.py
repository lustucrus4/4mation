"""
Callbacks personnalisés pour améliorer le feedback pendant l'entraînement
"""

from stable_baselines3.common.callbacks import BaseCallback
import time


class TrainingProgressCallback(BaseCallback):
    """
    Callback pour afficher la progression pendant l'entraînement.
    Montre les phases de collecte de données et d'entraînement.
    """
    
    def __init__(self, verbose=0):
        super().__init__(verbose)
        self.iteration = 0
        self.last_iteration = -1
        self.rollout_start_time = None
        self.training_start_time = None
        self.last_print_time = time.time()
        self.last_print_steps = 0
        
    def _on_training_start(self) -> None:
        """Appelé au début de l'entraînement"""
        print("\n" + "="*60)
        print("DEBUT DE L'ENTRAINEMENT")
        print("="*60)
        print("Note: La barre de progression montre la collecte de donnees.")
        print("      L'entrainement du modele sur GPU se fait entre les iterations")
        print("      et peut prendre 10-30 secondes (c'est normal!).")
        print("="*60 + "\n")
        
    def _on_step(self) -> bool:
        """Appelé à chaque step pendant la collecte de données"""
        current_time = time.time()
        
        # Afficher un message toutes les 2 secondes pendant la collecte
        if current_time - self.last_print_time >= 2.0:
            elapsed = current_time - self.last_print_time
            steps_collected = self.num_timesteps - self.last_print_steps
            steps_per_sec = steps_collected / elapsed if elapsed > 0 else 0
            
            # Obtenir l'itération actuelle si disponible
            iteration = self.locals.get('iteration', 0) if hasattr(self, 'locals') else 0
            
            if iteration != self.last_iteration:
                self.last_iteration = iteration
                self.iteration = iteration
                if iteration > 0:
                    print(f"\n--- Iteration {iteration} ---")
                    print(f"[Rollout] Collecte de donnees en cours...")
            
            print(f"  {self.num_timesteps:,} steps collectes ({steps_per_sec:.0f} steps/s)")
            
            self.last_print_time = current_time
            self.last_print_steps = self.num_timesteps
        
        return True
    
    def _on_rollout_end(self) -> None:
        """Appelé à la fin de chaque rollout (après collecte, avant entraînement)"""
        if self.rollout_start_time:
            elapsed = time.time() - self.rollout_start_time
            print(f"[Rollout] Termine en {elapsed:.1f}s - {self.num_timesteps:,} steps collectes")
        
        print(f"[Entrainement] Debut de l'entrainement du modele sur GPU...")
        print("   (Cette phase peut prendre 10-30 secondes - c'est normal!)")
        print("   Le GPU traite les donnees collectees...")
        self.training_start_time = time.time()
        
    def _on_rollout_start(self) -> None:
        """Appelé au début de chaque rollout (collecte de données)"""
        self.rollout_start_time = time.time()
        self.last_print_time = time.time()
        self.last_print_steps = self.num_timesteps
        
    def _on_training_end(self) -> None:
        """Appelé à la fin de l'entraînement"""
        if self.training_start_time:
            elapsed = time.time() - self.training_start_time
            print(f"[Entrainement] Derniere iteration terminee en {elapsed:.1f}s")
        print("\n" + "="*60)
        print("ENTRAINEMENT TERMINE")
        print("="*60 + "\n")


class VerboseTrainingCallback(BaseCallback):
    """
    Callback simple qui affiche des messages périodiques pendant l'entraînement
    """
    
    def __init__(self, verbose=0, print_freq=10):
        super().__init__(verbose)
        self.print_freq = print_freq
        self.last_print = 0
        
    def _on_step(self) -> bool:
        """Affiche un message toutes les N itérations"""
        if self.num_timesteps - self.last_print >= self.print_freq * 1000:
            print(f"Progression: {self.num_timesteps:,} / {self.locals.get('total_timesteps', '?')} steps")
            self.last_print = self.num_timesteps
        return True

