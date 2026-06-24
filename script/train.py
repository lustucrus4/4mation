"""
Script simple pour entraîner l'IA à jouer à 4mation

Usage:
    python train.py                    # Entraînement avec paramètres par défaut
    python train.py --steps 200000     # Spécifier le nombre de pas
    python train.py --continue         # Continuer depuis le dernier modèle
    python train.py --quick            # Entraînement rapide (pour test)
"""

import argparse
import os
import sys
from pathlib import Path

# Configurer l'encodage UTF-8 pour Windows
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

from agent.trainer import train_agent
from utils.config import config


def main():
    parser = argparse.ArgumentParser(
        description="Entraîne une IA à jouer à 4mation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples:
  # Entraînement de base (100 000 pas)
  python train.py

  # Entraînement rapide pour tester (10 000 pas)
  python train.py --quick

  # Entraînement long (500 000 pas)
  python train.py --steps 500000

  # Continuer depuis le meilleur modèle
  python train.py --continue

  # Créer un nouveau modèle (ignorer les modèles existants)
  python train.py --new-model

  # Entraînement avec plusieurs environnements parallèles (plus rapide)
  python train.py --parallel 4

  # Voir les logs TensorBoard
  tensorboard --logdir logs
        """
    )
    
    parser.add_argument("--steps", type=int, default=None,
                       help=f"Nombre de pas d'entraînement (défaut: {config.training.total_timesteps})")
    parser.add_argument("--quick", action="store_true",
                       help="Mode rapide pour test (10 000 pas)")
    parser.add_argument("--continue", dest="continue_training", action="store_true",
                       help="Continuer l'entraînement depuis le meilleur modèle")
    parser.add_argument("--new-model", dest="new_model", action="store_true",
                       help="Créer un nouveau modèle (ignorer les modèles existants)")
    parser.add_argument("--parallel", type=int, default=16,
                       help="Nombre d'environnements parallèles (défaut: 16, recommandé: 16-128 selon votre CPU/GPU)")
    parser.add_argument("--cpu", action="store_true",
                       help="Forcer l'utilisation du CPU (désactive le GPU)")
    parser.add_argument("--opponent", type=str, default="random",
                       choices=["random"],
                       help="Type d'adversaire (défaut: random)")
    parser.add_argument("--model-name", type=str, default=None,
                       help="Nom du modèle (défaut: fourmation_ppo)")
    parser.add_argument("--elite-games", type=int, default=2,
                       help="Nombre de meilleures parties à conserver par génération (défaut: 2)")
    parser.add_argument("--games-per-gen", type=int, default=100,
                       help="Nombre de parties par génération (défaut: 100)")
    parser.add_argument("--no-elite", action="store_true",
                       help="Désactiver le système élitiste par générations")
    parser.add_argument("--minimax-teacher", action="store_true",
                       help="Utiliser Minimax comme enseignant (imitation learning + adversaire)")
    parser.add_argument("--minimax-depth", type=int, default=4,
                       help="Profondeur initiale de Minimax (défaut: 4)")
    parser.add_argument("--imitation-ratio", type=float, default=0.5,
                       help="Ratio d'imitation learning (0.0-1.0, défaut: 0.5)")
    
    args = parser.parse_args()
    
    # Déterminer le nombre de pas
    if args.quick:
        total_timesteps = 10000
        print("⚠️  Mode rapide activé (10 000 pas) - pour test uniquement")
    elif args.steps:
        total_timesteps = args.steps
    else:
        total_timesteps = config.training.total_timesteps
    
    # Déterminer si on charge un modèle existant
    load_model = None
    best_model_path = Path(config.training.model_dir) / "best" / "best_model.zip"
    
    # Si Minimax est activé et qu'un modèle best existe, le charger automatiquement
    if args.minimax_teacher and best_model_path.exists() and not args.new_model:
        load_model = str(best_model_path)
        print(f"🤖 Minimax activé - Chargement automatique du modèle best pour amélioration")
    
    # Afficher les règles du jeu
    print("📋 Règles du jeu 4mation:")
    print("   - Premier coup: n'importe où sur le plateau")
    print("   - Coups suivants: 8 cases adjacentes au dernier coup joué")
    print("   - Si toutes les cases adjacentes au dernier coup sont pleines:")
    print("     → on peut jouer sur n'importe quelle case vide adjacente à l'adversaire")
    print()
    
    if args.new_model:
        # Mode --new-model : créer un nouveau modèle (ignorer les existants)
        print("🆕 Création d'un nouveau modèle (les modèles existants seront ignorés)")
        load_model = None
    elif args.continue_training:
        # Mode --continue explicite
        if best_model_path.exists():
            load_model = str(best_model_path)
            print(f"📂 Continuation depuis: {load_model}")
            print("⚠️  ATTENTION: Si ce modèle a été entraîné avec d'anciennes règles,")
            print("   il devra réapprendre les nouvelles règles.")
        else:
            print("🆕 Aucun modèle trouvé, démarrage d'un nouvel entraînement")
    else:
        # Comportement par défaut : charger le meilleur modèle s'il existe
        if best_model_path.exists():
            load_model = str(best_model_path)
            print(f"📂 Chargement automatique du meilleur modèle: {load_model}")
            print(f"   L'entraînement continuera pour améliorer ce modèle")
            print("⚠️  Si ce modèle a été entraîné avec d'anciennes règles,")
            print("   il devra réapprendre les nouvelles règles.")
            print("   Utilisez --new-model pour créer un nouveau modèle avec les nouvelles règles.")
        else:
            print("🆕 Aucun modèle existant, création d'un nouveau modèle")
    
    # Afficher les informations
    print("=" * 60)
    print("🚀 ENTRAÎNEMENT DE L'IA POUR 4MATION")
    print("=" * 60)
    print(f"📊 Nombre de pas: {total_timesteps:,}")
    print(f"🔄 Environnements parallèles: {args.parallel}")
    if args.minimax_teacher:
        print(f"🤖 Minimax activé (profondeur: {args.minimax_depth}, imitation: {args.imitation_ratio * 100:.0f}%)")
    else:
        print(f"🎮 Adversaire: {args.opponent}")
    print(f"💾 Modèles sauvegardés dans: {config.training.model_dir}")
    print(f"📈 Logs TensorBoard: {config.training.log_dir}")
    
    # Vérifier la disponibilité du GPU et afficher les recommandations
    try:
        import torch
        import os
        cpu_cores = os.cpu_count()
        
        if args.cpu:
            print("🖥️  Mode CPU forcé (GPU désactivé)")
            print(f"💻 CPU: {cpu_cores} cœurs disponibles")
            print(f"   Recommandé: --parallel {min(16, cpu_cores)} pour CPU")
        elif torch.cuda.is_available():
            gpu_name = torch.cuda.get_device_name(0)
            gpu_memory = torch.cuda.get_device_properties(0).total_memory / 1024**3
            print(f"🎮 GPU détecté: {gpu_name}")
            print(f"   Mémoire GPU: {gpu_memory:.1f} GB")
            print(f"💻 CPU: {cpu_cores} cœurs disponibles")
            
            # Recommandations basées sur les ressources
            if args.parallel >= 64:
                print(f"⚡ Configuration ultra-optimisée: batch_size=4096, n_steps=16384, réseau [512,512,256]")
                print(f"   ⚠️  Surveillez l'utilisation GPU/CPU avec nvidia-smi")
            elif args.parallel >= 32:
                print(f"⚡ Configuration optimisée: batch_size=3072, n_steps=12288, réseau [384,384,192]")
                print(f"   Recommandé pour maximiser l'utilisation GPU avec {cpu_cores} cœurs")
            elif args.parallel >= 8:
                print(f"⚡ Optimisations GPU: batch_size=2048, n_steps=8192, réseau [256,256,128]")
                print(f"   Optimisé pour RTX 5070 et GPU similaires")
            
            # Avertissements
            if args.parallel > cpu_cores * 2:
                print(f"⚠️  Attention: {args.parallel} environnements > {cpu_cores * 2} (2x cœurs)")
                print(f"   Le CPU pourrait être saturé. Recommandé: {cpu_cores}-{cpu_cores * 2}")
            if args.parallel > 128:
                print(f"⚠️  Attention: {args.parallel} environnements est très élevé")
                print(f"   Surveillez la mémoire GPU et système")
        else:
            print("⚠️  GPU non détecté - entraînement sur CPU (plus lent)")
            print(f"💻 CPU: {cpu_cores} cœurs disponibles")
            print(f"   Recommandé: --parallel {min(16, cpu_cores)} pour CPU")
            print("   Pour utiliser le GPU, installez PyTorch avec CUDA:")
            print("   pip install --pre torch torchvision --index-url https://download.pytorch.org/whl/nightly/cu128")
    except ImportError:
        print("⚠️  PyTorch non installé - impossible de détecter le GPU")
    print("=" * 60)
    print()
    
    # Vérifier que TensorBoard peut être lancé
    print("💡 Astuce: Ouvrez un autre terminal et lancez:")
    print(f"   tensorboard --logdir {config.training.log_dir}")
    print("   Puis ouvrez http://localhost:6006 dans votre navigateur")
    print()
    
    try:
        # Démarrer l'entraînement
        model = train_agent(
            total_timesteps=total_timesteps,
            num_envs=args.parallel,
            opponent_type=args.opponent,
            model_name=args.model_name,
            load_model=load_model,
            force_cpu=args.cpu,
            elite_games=args.elite_games,
            games_per_generation=args.games_per_gen,
            enable_elite_tracking=not args.no_elite,
            use_minimax_teacher=args.minimax_teacher,
            minimax_depth=args.minimax_depth,
            imitation_ratio=args.imitation_ratio
        )
        
        print()
        print("=" * 60)
        print("✅ ENTRAÎNEMENT TERMINÉ!")
        print("=" * 60)
        print(f"📁 Meilleur modèle: {config.training.model_dir}/best/best_model.zip")
        print(f"📁 Modèle final: {config.training.model_dir}/{args.model_name or config.training.model_name}_final.zip")
        print()
        print("🧪 Pour tester le modèle:")
        print("   python test_model.py")
        print()
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Entraînement interrompu par l'utilisateur")
        print(f"💾 Les checkpoints sont sauvegardés dans: {config.training.model_dir}/checkpoints")
        print(f"💾 Le meilleur modèle est dans: {config.training.model_dir}/best/best_model.zip")
        print("   Vous pouvez continuer avec: python train.py")
        print("   (Le meilleur modèle sera chargé automatiquement)")
    except Exception as e:
        print(f"\n❌ Erreur pendant l'entraînement: {e}")
        raise


if __name__ == "__main__":
    main()

