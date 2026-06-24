"""
Script principal pour calculer et visualiser l'arbre de jeu
"""

import json
import sys
from pathlib import Path

# Ajouter le répertoire parent au path pour les imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from game_tree.tree_builder import GameTreeBuilder
from game_tree.tree_evaluator import TreeEvaluator
from game_tree.tree_visualizer import TreeVisualizer


def save_tree_data(tree: dict, filepath: str):
    """
    Sauvegarde l'arbre en JSON.
    
    Args:
        tree: Arbre de jeu
        filepath: Chemin du fichier JSON
    """
    print(f"Sauvegarde de l'arbre dans {filepath}...")
    
    import numpy as np
    
    def convert_to_json(obj):
        """Fonction récursive pour convertir tous les types numpy en types Python"""
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        elif isinstance(obj, (np.integer, np.int8, np.int16, np.int32, np.int64)):
            return int(obj)
        elif isinstance(obj, (np.floating, np.float32, np.float64)):
            return float(obj)
        elif isinstance(obj, np.bool_):
            return bool(obj)
        elif isinstance(obj, (list, tuple)):
            return [convert_to_json(item) for item in obj]
        elif isinstance(obj, dict):
            return {k: convert_to_json(v) for k, v in obj.items()}
        else:
            return obj
    
    # Convertir les tableaux numpy en listes et les types numpy en types Python
    tree_json = convert_to_json(tree)
    
    output_file = Path(filepath)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(tree_json, f, indent=2, ensure_ascii=False)
    
    print(f"Arbre sauvegardé")


def load_tree_data(filepath: str) -> dict:
    """
    Charge l'arbre depuis un fichier JSON.
    
    Args:
        filepath: Chemin du fichier JSON
    
    Returns:
        Arbre de jeu ou None si fichier inexistant
    """
    filepath_obj = Path(filepath)
    if not filepath_obj.exists():
        return None
    
    print(f"Chargement de l'arbre depuis {filepath}...")
    
    import numpy as np
    
    with open(filepath_obj, 'r', encoding='utf-8') as f:
        tree_json = json.load(f)
    
    # Convertir les listes en tableaux numpy
    tree = {}
    for node_id, node_data in tree_json.items():
        node = node_data.copy()
        if 'board' in node:
            node['board'] = np.array(node['board'], dtype=np.int8)
        tree[node_id] = node
    
    print(f"Arbre chargé: {len(tree)} nœuds")
    return tree


def main():
    """Fonction principale"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Calcule et visualise l'arbre de jeu")
    parser.add_argument("--recalculate", action="store_true", 
                       help="Recalculer l'arbre même s'il existe déjà")
    parser.add_argument("--recalculate-eval", action="store_true",
                       help="Recalculer l'évaluation même si elle existe déjà")
    parser.add_argument("--visualize-only", action="store_true",
                       help="Générer uniquement les visualisations (HTML/PDF) sans recalculer")
    parser.add_argument("--max-moves", type=int, default=8,
                       help="Nombre maximum de coups à explorer (défaut: 8)")
    args = parser.parse_args()
    
    print("=" * 60)
    print("CALCUL DE L'ARBRE DE JEU - 8 PREMIERS COUPS")
    print("=" * 60)
    print()
    
    max_moves = args.max_moves
    data_dir = Path(__file__).parent / "data"
    tree_file = data_dir / f"tree_{max_moves}moves.json"
    html_file = Path(__file__).parent / f"tree_visualization_{max_moves}moves.html"
    
    # Vérifier si l'arbre existe déjà
    tree = None
    if tree_file.exists() and not args.recalculate:
        print(f"Un arbre existe déjà dans {tree_file}.")
        print("Chargement de l'arbre existant...")
        print("(Utilisez --recalculate pour forcer le recalcul)")
        tree = load_tree_data(str(tree_file))
        if tree is None:
            print("Erreur lors du chargement")
            return
    
    # Construire l'arbre si nécessaire
    if tree is None:
        print(f"ATTENTION: Le calcul peut prendre plusieurs minutes/heures")
        print(f"   Nombre de coups: {max_moves}")
        print()
        print("Démarrage du calcul...")
        
        print()
        builder = GameTreeBuilder(max_moves=max_moves)
        tree = builder.build_tree()
        
        # Afficher les statistiques
        stats = builder.get_tree_stats()
        print()
        print("Statistiques de l'arbre:")
        print(f"   Total de nœuds: {stats['total_nodes']}")
        print(f"   Nœuds terminaux: {stats['terminal_nodes']}")
        print(f"   Nœuds en cours: {stats['ongoing_nodes']}")
        print(f"   Victoires J1: {stats['winning_nodes_p1']}")
        print(f"   Victoires J2: {stats['winning_nodes_p2']}")
        print(f"   Égalités: {stats['draw_nodes']}")
        print(f"   Enfants max: {stats['max_children']}")
        print(f"   Enfants moyen: {stats['avg_children']:.2f}")
        print()
        
        # Sauvegarder l'arbre brut
        save_tree_data(tree, str(tree_file))
    
    # Vérifier si l'arbre classifié existe déjà
    classified_file = data_dir / f"tree_{max_moves}moves_classified.json"
    classified_tree = None
    
    if args.visualize_only:
        # Mode visualisation uniquement : charger l'arbre classifié
        if classified_file.exists():
            print()
            print("Mode visualisation uniquement - Chargement de l'arbre classifie...")
            classified_tree = load_tree_data(str(classified_file))
            if classified_tree is None:
                print("Erreur: Impossible de charger l'arbre classifie")
                print("Utilisez sans --visualize-only pour le generer d'abord")
                return
        else:
            print("Erreur: Aucun arbre classifie trouve")
            print("Utilisez sans --visualize-only pour le generer d'abord")
            return
    elif classified_file.exists() and not args.recalculate_eval:
        # Charger l'arbre classifié s'il existe
        print()
        print(f"Un arbre classifie existe deja dans {classified_file}")
        print("Chargement de l'arbre classifie...")
        print("(Utilisez --recalculate-eval pour forcer la re-evaluation)")
        classified_tree = load_tree_data(str(classified_file))
        if classified_tree is None:
            print("Erreur lors du chargement, re-evaluation necessaire...")
            classified_tree = None
    
    # Évaluer l'arbre si nécessaire
    if classified_tree is None:
        print()
        # Détecter automatiquement le GPU
        try:
            import torch
            use_gpu = torch.cuda.is_available()
        except ImportError:
            use_gpu = False
        
        evaluator = TreeEvaluator(use_gpu=use_gpu)
        evaluated_tree = evaluator.evaluate_tree(tree)
        
        # Classifier les branches
        print()
        classified_tree = evaluator.classify_branches(evaluated_tree)
        
        # Sauvegarder l'arbre classifié
        save_tree_data(classified_tree, str(classified_file))
    
    # Générer les visualisations
    print()
    visualizer = TreeVisualizer()
    
    # Générer HTML
    visualizer.generate_html(classified_tree, str(html_file))
    
    # Générer PDF
    pdf_file = Path(__file__).parent / f"tree_visualization_{max_moves}moves.pdf"
    visualizer.generate_pdf(classified_tree, str(pdf_file), max_depth=5)
    
    print()
    print("=" * 60)
    print("TERMINE !")
    print("=" * 60)
    print(f"Arbre brut: {tree_file}")
    print(f"Arbre classifie: {classified_file}")
    print(f"Visualisation HTML: {html_file}")
    print(f"Visualisation PDF: {pdf_file}")
    print()
    print(f"Ouvrez {html_file} dans votre navigateur pour voir l'arbre interactif !")
    print(f"Ou ouvrez {pdf_file} pour voir la version PDF !")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nInterrompu par l'utilisateur")
        sys.exit(1)
    except Exception as e:
        print(f"\nErreur: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

