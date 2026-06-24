"""
Système de suivi et visualisation des meilleures parties
"""

import json
import numpy as np
from pathlib import Path
from typing import List, Dict, Tuple
from datetime import datetime
import os


class EliteGameTracker:
    """
    Suit les meilleures parties et les sauvegarde pour visualisation
    """
    
    def __init__(self, top_n: int = 10, save_dir: str = "elite_games"):
        self.top_n = top_n
        self.save_dir = Path(save_dir)
        self.save_dir.mkdir(parents=True, exist_ok=True)
        
        # Liste des meilleures parties (reward, game_data)
        self.elite_games: List[Tuple[float, Dict]] = []
        
    def add_game(self, reward: float, game_data: Dict):
        """
        Ajoute une partie à la liste des meilleures si elle est dans le top N
        
        Args:
            reward: Récompense totale de la partie
            game_data: Dictionnaire contenant les données de la partie
                - moves: Liste des coups [(row, col), ...]
                - board_history: Historique des plateaux
                - winner: Gagnant (1, 2, ou None pour égalité)
                - final_board: Plateau final
        """
        # Ajouter la récompense aux données
        game_data['reward'] = reward
        game_data['timestamp'] = datetime.now().isoformat()
        
        # Ajouter à la liste
        self.elite_games.append((reward, game_data))
        
        # Trier par récompense décroissante
        self.elite_games.sort(key=lambda x: x[0], reverse=True)
        
        # Garder seulement les top N
        if len(self.elite_games) > self.top_n:
            self.elite_games = self.elite_games[:self.top_n]
    
    def get_elite_games(self) -> List[Dict]:
        """Retourne les meilleures parties"""
        return [game_data for _, game_data in self.elite_games]
    
    def save_elite_games(self, iteration: int = None):
        """Sauvegarde les meilleures parties en JSON"""
        filename = f"elite_games"
        if iteration is not None:
            filename += f"_iter{iteration}"
        filename += ".json"
        
        filepath = self.save_dir / filename
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(self.get_elite_games(), f, indent=2, ensure_ascii=False)
        
        return filepath
    
    def load_elite_games(self, filepath: str = None):
        """Charge les meilleures parties depuis un fichier JSON"""
        if filepath is None:
            filepath = self.save_dir / "elite_games.json"
        else:
            filepath = Path(filepath)
        
        if filepath.exists():
            with open(filepath, 'r', encoding='utf-8') as f:
                games = json.load(f)
                self.elite_games = [(g['reward'], g) for g in games]
                self.elite_games.sort(key=lambda x: x[0], reverse=True)
                # Garder seulement top N
                if len(self.elite_games) > self.top_n:
                    self.elite_games = self.elite_games[:self.top_n]
            return True
        return False


def create_game_data_from_episode(episode_info: Dict) -> Dict:
    """
    Crée un dictionnaire de données de partie depuis les infos d'un épisode
    
    Args:
        episode_info: Dictionnaire avec les infos de l'épisode
            - moves: Liste des coups
            - board_history: Historique des plateaux
            - reward: Récompense totale
            - winner: Gagnant
    
    Returns:
        Dictionnaire formaté pour EliteGameTracker
    """
    return {
        'moves': episode_info.get('moves', []),
        'board_history': episode_info.get('board_history', []),
        'winner': episode_info.get('winner', None),
        'final_board': episode_info.get('final_board', None),
        'move_count': episode_info.get('move_count', 0),
        'reward': episode_info.get('reward', 0.0)
    }

