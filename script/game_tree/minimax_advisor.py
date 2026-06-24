"""
IA Minimax qui calcule les probabilités de gagner pour chaque coup disponible
et génère une visualisation web interactive
"""

import numpy as np
from typing import Dict, List, Tuple, Optional
from pathlib import Path
import json
import sys

# Ajouter le répertoire parent au path pour les imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from game.game_engine import GameEngine


class MinimaxAdvisor:
    """
    IA qui utilise minimax pour évaluer chaque coup possible
    et calculer les probabilités de gagner
    """
    
    def __init__(self, depth: int = 6):
        """
        Args:
            depth: Profondeur de recherche minimax
        """
        self.depth = depth
        self.engine = GameEngine()
    
    def evaluate_move(self, board: np.ndarray, move: Tuple[int, int], 
                     current_player: int, depth: int = None) -> float:
        """
        Évalue un coup avec minimax
        
        Args:
            board: État actuel du plateau
            move: Coup à évaluer (row, col)
            current_player: Joueur qui joue (1 ou 2)
            depth: Profondeur de recherche (None = self.depth)
        
        Returns:
            Score de -1 (perdant) à 1 (gagnant) pour le joueur actuel
        """
        if depth is None:
            depth = self.depth
        
        # Créer une copie de l'engine et appliquer le coup
        engine = GameEngine()
        engine.state.board = board.copy()
        engine.state.current_player = current_player
        
        # Vérifier si le coup est valide
        valid_moves = engine.get_valid_actions()
        if move not in valid_moves:
            return -1.0  # Coup invalide = très mauvais
        
        # Appliquer le coup
        state, success, winner = engine.step(move)
        
        if not success:
            return -1.0
        
        # Si le coup gagne directement, retourner 1.0
        if winner == current_player:
            return 1.0
        elif winner == (3 - current_player):  # L'adversaire gagne
            return -1.0
        elif winner == 0:  # Égalité
            return 0.0
        
        # Sinon, continuer avec minimax
        return self._minimax(engine, depth - 1, current_player, 
                            float('-inf'), float('inf'), False)
    
    def _minimax(self, engine: GameEngine, depth: int, player: int,
                 alpha: float, beta: float, maximizing: bool) -> float:
        """
        Algorithme minimax avec élagage alpha-beta
        
        Args:
            engine: Moteur de jeu avec l'état actuel
            depth: Profondeur restante
            player: Joueur pour lequel on maximise
            alpha: Valeur alpha
            beta: Valeur beta
            maximizing: True si on maximise pour player
        
        Returns:
            Score de la position
        """
        # Condition d'arrêt
        if depth == 0:
            return self._evaluate_position(engine, player)
        
        # Vérifier si la partie est terminée
        winner = engine.get_winner()
        if winner == player:
            return 1.0
        elif winner == (3 - player):
            return -1.0
        elif winner == 0:
            return 0.0
        
        valid_moves = engine.get_valid_actions()
        if not valid_moves:
            return self._evaluate_position(engine, player)
        
        if maximizing:
            max_eval = float('-inf')
            for move in valid_moves:
                # Créer une copie de l'engine
                new_engine = GameEngine()
                new_engine.state.board = engine.state.board.copy()
                new_engine.state.current_player = engine.state.current_player
                
                state, success, winner = new_engine.step(move)
                if not success:
                    continue
                
                # Vérifier victoire immédiate
                if winner == player:
                    return 1.0
                elif winner == (3 - player):
                    eval_score = -1.0
                elif winner == 0:
                    eval_score = 0.0
                else:
                    # Continuer la recherche
                    eval_score = self._minimax(
                        new_engine, depth - 1, player, alpha, beta, False
                    )
                
                max_eval = max(max_eval, eval_score)
                alpha = max(alpha, eval_score)
                if beta <= alpha:
                    break  # Élagage alpha-beta
            return max_eval
        else:
            min_eval = float('inf')
            for move in valid_moves:
                # Créer une copie de l'engine
                new_engine = GameEngine()
                new_engine.state.board = engine.state.board.copy()
                new_engine.state.current_player = engine.state.current_player
                
                state, success, winner = new_engine.step(move)
                if not success:
                    continue
                
                # Vérifier victoire immédiate
                if winner == player:
                    eval_score = 1.0
                elif winner == (3 - player):
                    return -1.0
                elif winner == 0:
                    eval_score = 0.0
                else:
                    # Continuer la recherche
                    eval_score = self._minimax(
                        new_engine, depth - 1, player, alpha, beta, True
                    )
                
                min_eval = min(min_eval, eval_score)
                beta = min(beta, eval_score)
                if beta <= alpha:
                    break  # Élagage alpha-beta
            return min_eval
    
    def _evaluate_position(self, engine: GameEngine, player: int) -> float:
        """
        Évalue une position avec une heuristique simple
        
        Args:
            engine: Moteur de jeu
            player: Joueur pour lequel on évalue
        
        Returns:
            Score heuristique entre -1 et 1
        """
        board = engine.state.board
        opponent = 3 - player
        
        # Compter les alignements
        my_score = self._count_alignments(board, player)
        opp_score = self._count_alignments(board, opponent)
        
        # Normaliser
        total = my_score + opp_score
        if total == 0:
            return 0.0
        
        return (my_score - opp_score) / max(total, 1)
    
    def _count_alignments(self, board: np.ndarray, player: int) -> float:
        """Compte les alignements pour un joueur"""
        height, width = board.shape
        score = 0.0
        directions = [(0, 1), (1, 0), (1, 1), (1, -1)]
        
        for row in range(height):
            for col in range(width):
                if board[row, col] != player:
                    continue
                
                for dr, dc in directions:
                    count = 1
                    for step in [1, -1]:
                        r, c = row, col
                        for _ in range(3):
                            r += dr * step
                            c += dc * step
                            if (0 <= r < height and 0 <= c < width and 
                                board[r, c] == player):
                                count += 1
                            else:
                                break
                    
                    # Bonus selon la longueur de l'alignement
                    if count >= 4:
                        score += 10.0
                    elif count >= 3:
                        score += 3.0
                    elif count >= 2:
                        score += 1.0
        
        return score
    
    def analyze_position(self, board: np.ndarray, current_player: int = 1, last_move: Tuple[int, int] = None) -> Dict:
        """
        Analyse une position et retourne les probabilités pour chaque coup
        
        Args:
            board: État actuel du plateau (7x7 numpy array)
            current_player: Joueur qui doit jouer (1 ou 2)
            last_move: Position du dernier coup joué (row, col) ou None si premier coup
        
        Returns:
            Dictionnaire avec:
            - 'moves': Liste de dicts avec 'move', 'score', 'win_probability'
            - 'best_move': Meilleur coup
            - 'board': État du plateau
        """
        engine = GameEngine()
        engine.state.board = board.copy()
        engine.state.current_player = current_player
        
        # Déterminer la dernière position jouée si non fournie
        if last_move is None:
            # Chercher la dernière pièce posée dans l'historique du plateau
            num_pieces = np.count_nonzero(board)
            if num_pieces == 0:
                # Premier coup : aucune pièce sur le plateau
                engine.state.last_move_position = None
            else:
                # Trouver la position de la dernière pièce jouée
                # On cherche la pièce la plus récente (dernière dans l'ordre de parcours)
                # En pratique, on devrait avoir l'historique, mais on peut l'inférer
                # On prend la dernière pièce non-vide trouvée (approximation)
                last_pos = None
                for row in range(board.shape[0]):
                    for col in range(board.shape[1]):
                        if board[row, col] != 0:
                            last_pos = (row, col)
                engine.state.last_move_position = last_pos
        else:
            engine.state.last_move_position = last_move
        
        # Mettre à jour le compteur de coups
        engine.state.move_count = np.count_nonzero(board)
        
        valid_moves = engine.get_valid_actions()
        
        if not valid_moves:
            return {
                'moves': [],
                'best_move': None,
                'board': board.tolist(),
                'current_player': current_player
            }
        
        # Évaluer chaque coup
        move_scores = []
        for move in valid_moves:
            score = self.evaluate_move(board, move, current_player)
            # Convertir le score (-1 à 1) en probabilité (0 à 1)
            win_probability = (score + 1) / 2
            
            move_scores.append({
                'move': move,
                'row': move[0],
                'col': move[1],
                'score': score,
                'win_probability': win_probability
            })
        
        # Trier par score décroissant
        move_scores.sort(key=lambda x: x['score'], reverse=True)
        
        # Meilleur coup
        best_move = move_scores[0]['move'] if move_scores else None
        
        return {
            'moves': move_scores,
            'best_move': best_move,
            'board': board.tolist(),
            'current_player': current_player,
            'valid_moves_count': len(valid_moves)
        }
    
    def generate_visualization(self, analysis: Dict, output_path: str = "minimax_advisor.html"):
        """
        Génère une visualisation HTML interactive
        
        Args:
            analysis: Résultat de analyze_position
            output_path: Chemin de sortie
        """
        # Utiliser des doubles accolades pour échapper dans le format
        html_template = """<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>IA Minimax - Probabilités de Gain</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 20px;
            min-height: 100vh;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            border-radius: 15px;
            padding: 30px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.2);
        }}
        h1 {{
            color: #333;
            margin-bottom: 20px;
            text-align: center;
        }}
        .board-container {{
            display: flex;
            justify-content: center;
            margin: 30px 0;
        }}
        .board {{
            display: grid;
            grid-template-columns: repeat(7, 70px);
            gap: 5px;
            background: #2c3e50;
            padding: 10px;
            border-radius: 10px;
        }}
        .cell {{
            width: 70px;
            height: 70px;
            border-radius: 8px;
            border: 3px solid rgba(255, 255, 255, 0.3);
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            font-weight: bold;
            transition: all 0.3s ease;
            cursor: pointer;
            position: relative;
        }}
        .cell.empty {{
            background: rgba(255, 255, 255, 0.1);
        }}
        .cell.empty:hover {{
            background: rgba(255, 255, 255, 0.2);
            transform: scale(1.05);
        }}
        .cell.player1 {{
            background: linear-gradient(135deg, #ff4757 0%, #c44569 100%);
            color: white;
            box-shadow: 0 0 15px rgba(255, 71, 87, 0.5);
        }}
        .cell.player2 {{
            background: linear-gradient(135deg, #3742fa 0%, #2f3542 100%);
            color: white;
            box-shadow: 0 0 15px rgba(55, 66, 250, 0.5);
        }}
        .cell.valid-move {{
            border-color: #11f1cc;
            border-width: 4px;
        }}
        .cell.valid-move::after {{
            content: attr(data-prob);
            position: absolute;
            bottom: 2px;
            font-size: 10px;
            background: rgba(0, 0, 0, 0.7);
            color: #11f1cc;
            padding: 2px 4px;
            border-radius: 3px;
        }}
        .cell.best-move {{
            border-color: #feca57;
            border-width: 5px;
            box-shadow: 0 0 20px rgba(254, 202, 87, 0.8);
            animation: pulse 2s infinite;
        }}
        @keyframes pulse {{
            0%, 100% {{
                box-shadow: 0 0 20px rgba(254, 202, 87, 0.8);
            }}
            50% {{
                box-shadow: 0 0 30px rgba(254, 202, 87, 1);
            }}
        }}
        .cell-value {{
            font-size: 24px;
        }}
        .info-panel {{
            margin-top: 30px;
            padding: 20px;
            background: #f8f9fa;
            border-radius: 10px;
        }}
        .move-list {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
            gap: 10px;
            margin-top: 15px;
        }}
        .move-item {{
            padding: 10px;
            background: white;
            border-radius: 5px;
            border-left: 4px solid #667eea;
        }}
        .move-item.best {{
            border-left-color: #feca57;
            background: #fff9e6;
        }}
        .move-coords {{
            font-weight: bold;
            color: #333;
        }}
        .move-prob {{
            font-size: 18px;
            color: #28a745;
            font-weight: bold;
            margin-top: 5px;
        }}
        .move-score {{
            font-size: 12px;
            color: #666;
            margin-top: 3px;
        }}
        .legend {{
            display: flex;
            gap: 20px;
            justify-content: center;
            margin: 20px 0;
            flex-wrap: wrap;
        }}
        .legend-item {{
            display: flex;
            align-items: center;
            gap: 8px;
        }}
        .legend-color {{
            width: 20px;
            height: 20px;
            border-radius: 4px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🎮 IA Minimax - Probabilités de Gain</h1>
        
        <div class="legend">
            <div class="legend-item">
                <div class="legend-color" style="background: #ff4757;"></div>
                <span>Joueur 1</span>
            </div>
            <div class="legend-item">
                <div class="legend-color" style="background: #3742fa;"></div>
                <span>Joueur 2</span>
            </div>
            <div class="legend-item">
                <div class="legend-color" style="background: rgba(255,255,255,0.1); border: 3px solid #11f1cc;"></div>
                <span>Coup possible</span>
            </div>
            <div class="legend-item">
                <div class="legend-color" style="background: rgba(255,255,255,0.1); border: 5px solid #feca57; box-shadow: 0 0 20px rgba(254,202,87,0.8);"></div>
                <span>Meilleur coup</span>
            </div>
        </div>
        
        <div class="board-container">
            <div class="board" id="board"></div>
        </div>
        
        <div class="info-panel">
            <h2>Analyse des Coups Disponibles</h2>
            <p>Joueur actuel: <strong>Joueur {current_player}</strong></p>
            <p>Nombre de coups valides: <strong>{valid_moves_count}</strong></p>
            
            <div class="move-list" id="moveList"></div>
        </div>
    </div>
    
    <script>
        // Attendre que le DOM soit chargé
        document.addEventListener('DOMContentLoaded', function() {{
            const analysis = {analysis_json};
            const board = analysis.board;
            const moves = analysis.moves;
            const bestMove = analysis.best_move;
            const currentPlayer = analysis.current_player;
            
            // Créer le plateau
            const boardDiv = document.getElementById('board');
        for (let row = 0; row < 7; row++) {{
            for (let col = 0; col < 7; col++) {{
                const cell = document.createElement('div');
                cell.className = 'cell';
                
                const value = board[row][col];
                if (value === 0) {{
                    cell.className += ' empty';
                    // Vérifier si c'est un coup valide
                    const move = moves.find(m => m.row === row && m.col === col);
                    if (move) {{
                        cell.className += ' valid-move';
                        const prob = (move.win_probability * 100).toFixed(1);
                        cell.setAttribute('data-prob', prob + '%');
                        
                        if (bestMove && bestMove[0] === row && bestMove[1] === col) {{
                            cell.className += ' best-move';
                        }}
                    }}
                }} else if (value === 1) {{
                    cell.className += ' player1';
                    const valueDiv = document.createElement('div');
                    valueDiv.className = 'cell-value';
                    valueDiv.textContent = '1';
                    cell.appendChild(valueDiv);
                }} else if (value === 2) {{
                    cell.className += ' player2';
                    const valueDiv = document.createElement('div');
                    valueDiv.className = 'cell-value';
                    valueDiv.textContent = '2';
                    cell.appendChild(valueDiv);
                }}
                
                boardDiv.appendChild(cell);
            }}
        }}
        
        // Créer la liste des coups
        const moveList = document.getElementById('moveList');
        moves.forEach((move, index) => {{
            const moveItem = document.createElement('div');
            moveItem.className = 'move-item';
            if (bestMove && move.row === bestMove[0] && move.col === bestMove[1]) {{
                moveItem.className += ' best';
            }}
            
            moveItem.innerHTML = 
                '<div class="move-coords">Position: (' + move.row + ', ' + move.col + ')</div>' +
                '<div class="move-prob">' + (move.win_probability * 100).toFixed(1) + '% de gagner</div>' +
                '<div class="move-score">Score: ' + move.score.toFixed(3) + '</div>';
            
            moveList.appendChild(moveItem);
        }});
        }});
    </script>
</body>
</html>"""
        
        # Générer le HTML
        html_content = html_template.format(
            current_player=analysis['current_player'],
            valid_moves_count=analysis['valid_moves_count'],
            analysis_json=json.dumps(analysis, indent=2)
        )
        
        # Sauvegarder
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        print(f"Visualisation HTML generee: {output_path}")
        return output_path


def main():
    """Fonction principale pour tester l'IA"""
    import argparse
    
    parser = argparse.ArgumentParser(description="IA Minimax pour analyser les positions")
    parser.add_argument("--depth", type=int, default=6,
                       help="Profondeur de recherche minimax (défaut: 6)")
    parser.add_argument("--board", type=str, default=None,
                       help="Fichier JSON avec l'état du plateau (optionnel)")
    parser.add_argument("--output", type=str, default="minimax_advisor.html",
                       help="Fichier HTML de sortie (défaut: minimax_advisor.html)")
    args = parser.parse_args()
    
    # Créer l'IA
    advisor = MinimaxAdvisor(depth=args.depth)
    
    # Charger ou créer un plateau
    if args.board:
        with open(args.board, 'r') as f:
            data = json.load(f)
            board = np.array(data['board'], dtype=np.int8)
            current_player = data.get('current_player', 1)
    else:
        # Créer un plateau vide pour test
        board = np.zeros((7, 7), dtype=np.int8)
        current_player = 1
        print("Utilisation d'un plateau vide pour test")
        print("Utilisez --board pour charger un plateau spécifique")
    
    print(f"Analyse de la position avec minimax (profondeur {args.depth})...")
    print("Cela peut prendre quelques secondes...")
    
    # Analyser la position
    analysis = advisor.analyze_position(board, current_player)
    
    # Afficher les résultats
    print(f"\nNombre de coups valides: {analysis['valid_moves_count']}")
    if analysis['best_move']:
        best = next(m for m in analysis['moves'] if m['move'] == analysis['best_move'])
        print(f"Meilleur coup: {analysis['best_move']} (probabilité de gagner: {best['win_probability']*100:.1f}%)")
    
    # Générer la visualisation
    advisor.generate_visualization(analysis, args.output)
    
    print(f"\nVisualisation HTML generee: {args.output}")
    print(f"Ouvrez {args.output} dans votre navigateur pour voir les probabilités!")


if __name__ == "__main__":
    main()

