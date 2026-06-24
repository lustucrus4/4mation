"""
Configuration centralisée pour le simulateur 4mation
"""

from dataclasses import dataclass
from pathlib import Path


@dataclass
class GameConfig:
    """Configuration du jeu"""
    # Dimensions du plateau (à adapter selon les règles de 4mation)
    board_width: int = 7
    board_height: int = 7  # Modifié pour correspondre à game_logic.py
    # Nombre de joueurs
    num_players: int = 2
    # Nombre de pièces à aligner pour gagner (style Connect 4)
    win_length: int = 4


@dataclass
class TrainingConfig:
    """Configuration de l'entraînement"""
    # Nombre total de pas d'entraînement
    total_timesteps: int = 100000
    # Fréquence de sauvegarde (en pas)
    save_freq: int = 10000
    # Fréquence d'évaluation (en pas)
    eval_freq: int = 5000
    # Nombre d'épisodes pour l'évaluation
    eval_episodes: int = 10
    # Répertoire pour sauvegarder les modèles
    model_dir: str = "models"
    # Répertoire pour les logs TensorBoard
    log_dir: str = "logs"
    # Nom du modèle
    model_name: str = "fourmation_ppo"


@dataclass
class Config:
    """Configuration principale"""
    game: GameConfig = None
    training: TrainingConfig = None
    
    def __post_init__(self):
        if self.game is None:
            self.game = GameConfig()
        if self.training is None:
            self.training = TrainingConfig()
        
        # Créer les répertoires si nécessaire
        Path(self.training.model_dir).mkdir(parents=True, exist_ok=True)
        Path(self.training.log_dir).mkdir(parents=True, exist_ok=True)


# Instance globale de configuration
config = Config()

