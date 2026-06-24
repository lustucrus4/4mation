"""
Utilitaires de visualisation pour le jeu 4mation
"""

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from typing import List, Optional
from pathlib import Path
import os

from game.game_state import GameState
from game.game_engine import GameEngine


def visualize_game(state: GameState, ax: Optional[plt.Axes] = None, 
                   title: Optional[str] = None) -> plt.Axes:
    """
    Visualise l'état actuel du jeu sur un graphique matplotlib.
    
    Args:
        state: État du jeu à visualiser
        ax: Axes matplotlib (si None, crée une nouvelle figure)
        title: Titre du graphique
    
    Returns:
        Axes matplotlib
    """
    if ax is None:
        fig, ax = plt.subplots(figsize=(10, 8))
    
    board = state.board
    height, width = board.shape
    
    # Couleurs pour les joueurs
    colors = {
        0: 'white',  # Vide
        1: 'red',    # Joueur 1
        2: 'blue'    # Joueur 2
    }
    
    # Dessiner le plateau
    for row in range(height):
        for col in range(width):
            player = board[row, col]
            color = colors.get(player, 'gray')
            
            # Créer un cercle pour représenter une pièce
            circle = patches.Circle(
                (col, row), 0.4,
                color=color,
                edgecolor='black',
                linewidth=2
            )
            ax.add_patch(circle)
    
    # Configuration de l'axe
    ax.set_xlim(-0.5, width - 0.5)
    ax.set_ylim(-0.5, height - 0.5)
    ax.set_aspect('equal')
    ax.invert_yaxis()  # Inverser pour avoir le bas en bas
    
    # Ajouter des lignes de grille
    ax.grid(True, color='gray', linestyle='--', linewidth=0.5)
    ax.set_xticks(range(width))
    ax.set_yticks(range(height))
    ax.set_xlabel('Colonnes')
    ax.set_ylabel('Lignes')
    
    # Titre
    if title:
        ax.set_title(title)
    else:
        ax.set_title(f'État du jeu - Joueur actuel: {state.current_player}')
    
    # Légende
    legend_elements = [
        patches.Patch(facecolor='white', edgecolor='black', label='Case vide'),
        patches.Patch(facecolor='red', edgecolor='black', label='Joueur 1'),
        patches.Patch(facecolor='blue', edgecolor='black', label='Joueur 2')
    ]
    ax.legend(handles=legend_elements, loc='upper right')
    
    # Afficher le statut
    if state.is_terminal:
        if state.winner:
            status_text = f"Partie terminée! Gagnant: Joueur {state.winner}"
        else:
            status_text = "Partie terminée! Égalité"
        ax.text(width/2, -0.8, status_text, 
                ha='center', fontsize=12, weight='bold',
                bbox=dict(boxstyle='round', facecolor='yellow', alpha=0.5))
    
    return ax


def plot_training_progress(log_dir: str, save_path: Optional[str] = None):
    """
    Trace les graphiques de progression de l'entraînement depuis TensorBoard.
    
    Note: Cette fonction nécessite tensorboard et pandas pour lire les logs.
    
    Args:
        log_dir: Répertoire contenant les logs TensorBoard
        save_path: Chemin pour sauvegarder le graphique (si None, affiche seulement)
    """
    try:
        from tensorboard.backend.event_processing.event_accumulator import EventAccumulator
    except ImportError:
        print("TensorBoard n'est pas installé. Installez-le avec: pip install tensorboard")
        return
    
    # Charger les événements TensorBoard
    ea = EventAccumulator(log_dir)
    ea.Reload()
    
    # Obtenir les scalaires disponibles
    scalar_keys = ea.Tags()['scalars']
    
    if not scalar_keys:
        print("Aucun scalaire trouvé dans les logs.")
        return
    
    # Créer une figure avec plusieurs sous-graphiques
    num_plots = len(scalar_keys)
    fig, axes = plt.subplots(num_plots, 1, figsize=(12, 4 * num_plots))
    
    if num_plots == 1:
        axes = [axes]
    
    for idx, key in enumerate(scalar_keys):
        scalar_events = ea.Scalars(key)
        steps = [event.step for event in scalar_events]
        values = [event.value for event in scalar_events]
        
        axes[idx].plot(steps, values)
        axes[idx].set_xlabel('Pas d\'entraînement')
        axes[idx].set_ylabel(key)
        axes[idx].set_title(f'Progression: {key}')
        axes[idx].grid(True)
    
    plt.tight_layout()
    
    if save_path:
        plt.savefig(save_path)
        print(f"Graphique sauvegardé dans {save_path}")
    else:
        plt.show()


def visualize_game_history(engine: GameEngine, save_path: Optional[str] = None):
    """
    Visualise l'historique d'une partie complète.
    
    Args:
        engine: Moteur de jeu avec historique
        save_path: Chemin pour sauvegarder les images (si None, affiche seulement)
    """
    if not engine.history:
        print("Aucun historique disponible.")
        return
    
    num_states = len(engine.history) + 1  # +1 pour l'état initial
    
    # Créer une grille de graphiques
    cols = min(4, num_states)
    rows = (num_states + cols - 1) // cols
    
    fig, axes = plt.subplots(rows, cols, figsize=(4 * cols, 4 * rows))
    
    if rows == 1 and cols == 1:
        axes = [[axes]]
    elif rows == 1:
        axes = [axes]
    elif cols == 1:
        axes = [[ax] for ax in axes]
    
    # Afficher l'état initial
    engine.reset()
    visualize_game(engine.get_state(), ax=axes[0][0], title="État initial")
    
    # Afficher chaque état après chaque action
    for idx, history_entry in enumerate(engine.history):
        row_idx = (idx + 1) // cols
        col_idx = (idx + 1) % cols
        
        state = history_entry['state_after']
        player = history_entry['player']
        action = history_entry['action']
        
        title = f"Coup {idx + 1}: Joueur {player} → Colonne {action}"
        visualize_game(state, ax=axes[row_idx][col_idx], title=title)
    
    # Masquer les axes inutilisés
    for idx in range(num_states, rows * cols):
        row_idx = idx // cols
        col_idx = idx % cols
        axes[row_idx][col_idx].axis('off')
    
    plt.tight_layout()
    
    if save_path:
        plt.savefig(save_path)
        print(f"Historique sauvegardé dans {save_path}")
    else:
        plt.show()


def render_game_html(state: GameState, output_path: str, 
                     highlight_last_move: bool = True,
                     logo_path: Optional[str] = None) -> str:
    """
    Génère un fichier HTML avec le rendu visuel du jeu dans le style 4mation.
    
    Args:
        state: État du jeu à visualiser
        output_path: Chemin où sauvegarder le fichier HTML
        highlight_last_move: Si True, met en évidence le dernier coup
        logo_path: Chemin vers le logo (optionnel)
    
    Returns:
        Chemin du fichier HTML généré
    """
    board = state.board
    height, width = board.shape
    
    # Lire le template HTML
    template_path = Path(__file__).parent.parent / "templates" / "game_template.html"
    
    if not template_path.exists():
        # Créer le template inline si le fichier n'existe pas
        html_template = get_inline_template()
    else:
        with open(template_path, 'r', encoding='utf-8') as f:
            html_template = f.read()
    
    # Générer le HTML du plateau
    board_html = ""
    last_move = None
    last_move_row = None
    if state.action_history:
        last_move = state.action_history[-1]
        # Trouver la ligne de la dernière pièce placée
        last_player, last_col = last_move
        # Chercher la pièce la plus basse dans cette colonne qui appartient au dernier joueur
        for r in range(height - 1, -1, -1):
            if board[r, last_col] == last_player:
                last_move_row = r
                break
    
    for row in range(height):
        for col in range(width):
            player = board[row, col]
            classes = ["casa"]
            
            # Ajouter la classe de couleur selon le joueur
            if player == 1:
                classes.append("vermelho")  # Rouge
            elif player == 2:
                classes.append("azul")  # Bleu
            
            # Mettre en évidence le dernier coup
            if highlight_last_move and last_move_row is not None:
                if row == last_move_row and col == last_move[1]:
                    classes.append("destacada")
                    classes.append("ultima")
            
            class_str = " ".join(classes)
            board_html += f'<div class="{class_str}" data-linha="{row}" data-coluna="{col}" style="pointer-events: none;"></div>\n'
    
    # Générer le message
    message = ""
    if state.is_terminal:
        if state.winner == 1:
            message = "Le joueur rouge a gagné !"
        elif state.winner == 2:
            message = "Le joueur bleu a gagné !"
        elif state.winner == 0:
            message = "Match nul !"
    else:
        if state.current_player == 1:
            message = "Tour du joueur rouge"
        else:
            message = "Tour du joueur bleu"
    
    # Informations supplémentaires
    game_info = f"""
        <p>Coup #{state.move_count}</p>
        <p>Joueur actuel: {state.current_player}</p>
    """
    
    # Remplacer les placeholders dans le template
    # Ajouter les variables CSS personnalisées dans le style
    css_vars = f"""
        :root {{
            --board-width: {width};
            --board-height: {height};
        }}
    """
    html_content = html_template.replace("{{board_html}}", board_html)
    html_content = html_content.replace("{{message}}", message)
    html_content = html_content.replace("{{game_info}}", game_info)
    # Insérer les variables CSS après la balise <style>
    html_content = html_content.replace("<style>", f"<style>{css_vars}")
    
    # Sauvegarder le fichier HTML
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    return str(output_path)


def get_inline_template() -> str:
    """Retourne le template HTML inline si le fichier n'existe pas"""
    return """<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>4mation - Visualisation de partie</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            padding: 20px;
            color: #fff;
        }

        img[alt="Logo 4mation"] {
            max-width: 200px;
            height: auto;
            margin-bottom: 30px;
            filter: drop-shadow(0 0 10px rgba(17, 241, 204, 0.5));
        }

        #tabuleiro {
            display: grid;
            grid-template-columns: repeat(var(--board-width, 7), 1fr);
            grid-template-rows: repeat(var(--board-height, 7), 1fr);
            gap: 8px;
            background: rgba(255, 255, 255, 0.1);
            padding: 15px;
            border-radius: 15px;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255, 255, 255, 0.2);
            max-width: 600px;
            width: 100%;
        }

        .casa {
            aspect-ratio: 1;
            background: rgba(255, 255, 255, 0.2);
            border-radius: 50%;
            border: 3px solid rgba(255, 255, 255, 0.3);
            transition: all 0.3s ease;
            position: relative;
            pointer-events: none;
        }

        .casa.vermelho {
            background: radial-gradient(circle, #ff4757 0%, #c44569 100%);
            border-color: #ff4757;
            box-shadow: 0 0 20px rgba(255, 71, 87, 0.6);
        }

        .casa.azul {
            background: radial-gradient(circle, #3742fa 0%, #2f3542 100%);
            border-color: #3742fa;
            box-shadow: 0 0 20px rgba(55, 66, 250, 0.6);
        }

        .casa.destacada {
            border: 4px solid #11f1cc;
            box-shadow: 0 0 25px rgba(17, 241, 204, 0.8);
            animation: pulse 2s infinite;
        }

        .casa.ultima {
            border: 5px solid #ffd32a;
            box-shadow: 0 0 30px rgba(255, 211, 42, 0.9);
        }

        @keyframes pulse {
            0%, 100% {
                transform: scale(1);
            }
            50% {
                transform: scale(1.05);
            }
        }

        #mensagem {
            margin-top: 30px;
            font-size: 24px;
            font-weight: bold;
            color: #11f1cc;
            text-align: center;
            text-shadow: 0 0 10px rgba(17, 241, 204, 0.5);
            min-height: 40px;
        }

        .game-info {
            margin-top: 20px;
            text-align: center;
            color: rgba(255, 255, 255, 0.7);
            font-size: 14px;
        }

        .game-info p {
            margin: 5px 0;
        }

        @media (max-width: 600px) {
            #tabuleiro {
                gap: 5px;
                padding: 10px;
            }
            
            #mensagem {
                font-size: 18px;
            }
        }
    </style>
</head>
<body>
    <img src="logo.png" alt="Logo 4mation" onerror="this.style.display='none'">
    <div id="tabuleiro">
        {{board_html}}
    </div>
    <p id="mensagem">{{message}}</p>
    <div class="game-info">
        {{game_info}}
    </div>
</body>
</html>"""


def render_game_history_html(engine: GameEngine, output_dir: str = "renders") -> List[str]:
    """
    Génère des fichiers HTML pour chaque étape de l'historique d'une partie.
    
    Args:
        engine: Moteur de jeu avec historique
        output_dir: Répertoire où sauvegarder les fichiers HTML
    
    Returns:
        Liste des chemins des fichiers HTML générés
    """
    if not engine.history:
        print("Aucun historique disponible.")
        return []
    
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    html_files = []
    
    # État initial
    engine.reset()
    initial_state = engine.get_state()
    initial_path = output_path / "etat_initial.html"
    render_game_html(initial_state, str(initial_path), highlight_last_move=False)
    html_files.append(str(initial_path))
    
    # Chaque étape de l'historique
    for idx, history_entry in enumerate(engine.history):
        state = history_entry['state_after']
        step_path = output_path / f"coup_{idx + 1}.html"
        render_game_html(state, str(step_path), highlight_last_move=True)
        html_files.append(str(step_path))
    
    # Créer aussi une page index pour naviguer entre les étapes
    create_history_index(html_files, output_path / "index.html")
    
    print(f"{len(html_files)} fichiers HTML générés dans {output_dir}")
    return html_files


def create_history_index(html_files: List[str], output_path: Path):
    """
    Crée une page index pour naviguer entre les différentes étapes d'une partie.
    
    Args:
        html_files: Liste des fichiers HTML
        output_path: Chemin du fichier index à créer
    """
    index_html = """<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>4mation - Historique de partie</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
            min-height: 100vh;
            padding: 40px 20px;
            color: #fff;
        }

        .container {
            max-width: 1200px;
            margin: 0 auto;
        }

        h1 {
            text-align: center;
            color: #11f1cc;
            margin-bottom: 30px;
            text-shadow: 0 0 10px rgba(17, 241, 204, 0.5);
        }

        .game-list {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
            gap: 20px;
            margin-top: 30px;
        }

        .game-card {
            background: rgba(255, 255, 255, 0.1);
            border-radius: 10px;
            padding: 20px;
            text-align: center;
            transition: all 0.3s ease;
            border: 2px solid rgba(255, 255, 255, 0.2);
            cursor: pointer;
            text-decoration: none;
            color: #fff;
            display: block;
        }

        .game-card:hover {
            transform: translateY(-5px);
            box-shadow: 0 10px 30px rgba(17, 241, 204, 0.3);
            border-color: #11f1cc;
        }

        .game-card h3 {
            color: #11f1cc;
            margin-bottom: 10px;
        }

        .game-card p {
            color: rgba(255, 255, 255, 0.7);
            font-size: 14px;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>Historique de la partie</h1>
        <div class="game-list">
"""
    
    for idx, html_file in enumerate(html_files):
        filename = Path(html_file).name
        if filename == "etat_initial.html":
            title = "État initial"
            description = "Début de la partie"
        else:
            coup_num = idx
            title = f"Coup {coup_num}"
            description = f"Après le coup {coup_num}"
        
        index_html += f"""
            <a href="{filename}" class="game-card">
                <h3>{title}</h3>
                <p>{description}</p>
            </a>
"""
    
    index_html += """
        </div>
    </div>
</body>
</html>"""
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(index_html)

