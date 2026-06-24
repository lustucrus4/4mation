"""
Callback pour l'apprentissage par imitation (Imitation Learning)
Entraîne le PPO à imiter les coups de Minimax
"""

import numpy as np
from typing import List, Dict, Optional
from stable_baselines3.common.callbacks import BaseCallback
import torch
import torch.nn.functional as F


class ImitationCallback(BaseCallback):
    """
    Callback qui entraîne le modèle PPO à imiter Minimax via les données expert.
    """
    
    def __init__(self, 
                 expert_data: List[Dict],
                 imitation_ratio: float = 0.5,
                 batch_size: int = 64,
                 learning_rate: float = 1e-4,
                 verbose: int = 0):
        """
        Args:
            expert_data: Liste de transitions expert (observation, action, ...)
            imitation_ratio: Probabilité d'utiliser l'imitation learning à chaque step
            batch_size: Taille du batch pour l'entraînement par imitation
            learning_rate: Taux d'apprentissage pour l'imitation
            verbose: Niveau de verbosité
        """
        super().__init__(verbose)
        self.expert_data = expert_data
        self.imitation_ratio = imitation_ratio
        self.batch_size = batch_size
        self.learning_rate = learning_rate
        
        # Statistiques
        self.imitation_steps = 0
        self.total_steps = 0
        
        # Convertir les données expert en format tensor
        if len(expert_data) > 0:
            self.expert_observations = np.array([d['observation'] for d in expert_data])
            self.expert_actions = np.array([d['action'] for d in expert_data])
        else:
            self.expert_observations = np.array([])
            self.expert_actions = np.array([])
    
    def _on_step(self) -> bool:
        """
        Appelé à chaque step. Avec probabilité imitation_ratio,
        on fait un pas d'apprentissage par imitation.
        """
        self.total_steps += 1
        
        # Décider si on fait de l'imitation learning
        if len(self.expert_data) == 0:
            return True
        
        if np.random.random() < self.imitation_ratio:
            self._imitation_step()
            self.imitation_steps += 1
        
        return True
    
    def _imitation_step(self):
        """
        Effectue un pas d'apprentissage par imitation.
        Entraîne le modèle à prédire les actions de Minimax.
        """
        if len(self.expert_observations) == 0:
            return
        
        try:
            # Échantillonner un batch de données expert
            indices = np.random.choice(
                len(self.expert_observations),
                size=min(self.batch_size, len(self.expert_observations)),
                replace=False
            )
            
            batch_obs = self.expert_observations[indices]
            batch_actions = self.expert_actions[indices]
            
            # Convertir en tensors
            device = self.model.policy.device
            obs_tensor = torch.FloatTensor(batch_obs).to(device)
            actions_tensor = torch.LongTensor(batch_actions).to(device)
            
            # Obtenir les prédictions du modèle
            # Utiliser la méthode standard de stable_baselines3
            with torch.enable_grad():
                # Extraire les features
                features = self.model.policy.extract_features(obs_tensor)
                latent_pi = self.model.policy.mlp_extractor.forward_actor(features)
                action_logits = self.model.policy.action_net(latent_pi)
                
                # Calculer la perte (cross-entropy entre prédictions et actions expert)
                loss = F.cross_entropy(action_logits, actions_tensor)
                
                # Backpropagation
                self.model.policy.optimizer.zero_grad()
                loss.backward()
                torch.nn.utils.clip_grad_norm_(self.model.policy.parameters(), 0.5)
                self.model.policy.optimizer.step()
        except Exception as e:
            # En cas d'erreur, ignorer silencieusement pour ne pas interrompre l'entraînement
            if self.verbose > 1:
                print(f"⚠️  Erreur dans imitation_step: {e}")
    
    def _on_training_end(self) -> None:
        """Appelé à la fin de l'entraînement"""
        if self.verbose > 0:
            ratio = (self.imitation_steps / self.total_steps * 100) if self.total_steps > 0 else 0
            print(f"\n📊 Statistiques Imitation Learning:")
            print(f"   Steps d'imitation: {self.imitation_steps}/{self.total_steps} ({ratio:.1f}%)")
            print(f"   Données expert utilisées: {len(self.expert_data)} transitions")

