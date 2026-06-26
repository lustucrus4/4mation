"""
Script pour tester un modèle entraîné (obs 149 dims).

Usage (depuis script/) :
    python test_model.py
    python test_model.py --model models/best/best_model.zip
    python test_model.py --games 10 --render
"""

import argparse
from pathlib import Path
import sys

import numpy as np

# Permettre l'exécution depuis la racine 4mation/ ou script/
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "script") not in sys.path:
    sys.path.insert(0, str(ROOT / "script"))

from agent.env_utils import OBSERVATION_DIM, LEGACY_OBSERVATION_DIM
from agent.model import create_model
from simulator.env import FourMationEnv
from utils.config import config
from utils.visualization import render_game_html


def test_model(model_path: str = None, num_games: int = 5, render: bool = False):
    if model_path is None:
        best_model = Path(config.training.model_dir) / "best" / "best_model.zip"
        if best_model.exists():
            model_path = str(best_model)
            print(f"Utilisation du meilleur modele: {model_path}")
        else:
            final_model = Path(config.training.model_dir) / f"{config.training.model_name}_final.zip"
            if final_model.exists():
                model_path = str(final_model)
                print(f"Utilisation du modele final: {model_path}")
            else:
                print("Aucun modele trouve!")
                print(f"   Cherche dans: {config.training.model_dir}")
                return
    elif not Path(model_path).exists():
        print(f"Modele non trouve: {model_path}")
        return

    env = FourMationEnv(opponent_type="random")
    obs_size = env.observation_space.shape[0]
    print(f"Observation: {obs_size} dims (Phase 2 attend {OBSERVATION_DIM})")
    if obs_size != OBSERVATION_DIM:
        print(
            f"ATTENTION: ce modele pourrait etre Phase 1 ({LEGACY_OBSERVATION_DIM} dims) "
            f"et etre incompatible."
        )

    print(f"Chargement du modele: {model_path}")
    model = create_model(env=env, load_path=model_path)

    wins = losses = draws = 0
    total_rewards = []

    print(f"\nDebut des tests ({num_games} parties vs adversaire aleatoire)...")
    print("=" * 60)

    for game_num in range(num_games):
        obs, info = env.reset()
        done = False
        total_reward = 0.0
        moves = 0

        while not done and moves < 100:
            action, _ = model.predict(obs, deterministic=True)
            obs, reward, terminated, truncated, info = env.step(action)
            done = terminated or truncated
            total_reward += reward
            moves += 1

        state = env.engine.get_state()
        if state.is_terminal:
            if state.winner == 1:
                wins += 1
                result = "VICTOIRE"
            elif state.winner == 2:
                losses += 1
                result = "DEFAITE"
            else:
                draws += 1
                result = "EGALITE"
        else:
            result = "INCOMPLET"

        total_rewards.append(total_reward)
        print(f"Partie {game_num + 1}/{num_games}: {result} (reward: {total_reward:.2f}, coups: {moves})")

        if render:
            render_dir = Path("renders") / "test_games"
            render_dir.mkdir(parents=True, exist_ok=True)
            render_path = render_dir / f"partie_{game_num + 1}.html"
            render_game_html(state, str(render_path), highlight_last_move=True)

    print("=" * 60)
    print("STATISTIQUES")
    print("=" * 60)
    print(f"Victoires: {wins} ({wins / num_games * 100:.1f}%)")
    print(f"Defaites: {losses} ({losses / num_games * 100:.1f}%)")
    print(f"Egalites: {draws} ({draws / num_games * 100:.1f}%)")
    print(f"Recompense moyenne: {np.mean(total_rewards):.2f}")

    if render:
        print(f"\nRendu HTML: renders/test_games/")


def main():
    parser = argparse.ArgumentParser(description="Teste un modele PPO entraîne")
    parser.add_argument("--model", type=str, default=None, help="Chemin vers le checkpoint")
    parser.add_argument("--games", type=int, default=5, help="Nombre de parties")
    parser.add_argument("--render", action="store_true", help="Genere des rendus HTML")
    args = parser.parse_args()
    test_model(model_path=args.model, num_games=args.games, render=args.render)


if __name__ == "__main__":
    main()
