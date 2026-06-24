"""
Générateur de page web interactive pour jouer avec l'IA Minimax
"""

from pathlib import Path
import json
import numpy as np
from game_tree.minimax_advisor import MinimaxAdvisor


def generate_interactive_page(output_path: str = "interactive_minimax.html"):
    """
    Génère une page HTML interactive où on peut jouer et voir les probabilités
    """
    
    html_content = """<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>4mation - IA Minimax Interactive</title>
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
            max-width: 1400px;
            margin: 0 auto;
            background: white;
            border-radius: 15px;
            padding: 30px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.2);
        }}
        h1 {{
            color: #333;
            margin-bottom: 10px;
            text-align: center;
        }}
        .game-info {{
            text-align: center;
            margin-bottom: 20px;
            padding: 15px;
            background: #f8f9fa;
            border-radius: 10px;
        }}
        .current-player {{
            font-size: 20px;
            font-weight: bold;
            color: #667eea;
            margin-bottom: 10px;
        }}
        .board-container {{
            display: flex;
            justify-content: center;
            margin: 30px 0;
        }}
        .board {{
            display: grid;
            grid-template-columns: repeat(7, 80px);
            gap: 5px;
            background: #2c3e50;
            padding: 15px;
            border-radius: 10px;
        }}
        .cell {{
            width: 80px;
            height: 80px;
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
            cursor: default;
        }}
        .cell.player2 {{
            background: linear-gradient(135deg, #3742fa 0%, #2f3542 100%);
            color: white;
            box-shadow: 0 0 15px rgba(55, 66, 250, 0.5);
            cursor: default;
        }}
        .cell.valid-move {{
            border-color: #11f1cc;
            border-width: 4px;
            cursor: pointer;
        }}
        .cell.valid-move:hover {{
            background: rgba(17, 241, 204, 0.2);
            transform: scale(1.1);
        }}
        .cell.valid-move::after {{
            content: attr(data-prob);
            position: absolute;
            bottom: 2px;
            font-size: 11px;
            background: rgba(0, 0, 0, 0.8);
            color: #11f1cc;
            padding: 3px 6px;
            border-radius: 4px;
            font-weight: bold;
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
            font-size: 28px;
        }}
        .controls {{
            text-align: center;
            margin: 20px 0;
        }}
        .btn {{
            background: #667eea;
            color: white;
            border: none;
            padding: 12px 24px;
            border-radius: 8px;
            cursor: pointer;
            font-size: 16px;
            font-weight: bold;
            margin: 0 10px;
            transition: all 0.3s;
        }}
        .btn:hover {{
            background: #5568d3;
            transform: translateY(-2px);
        }}
        .btn:disabled {{
            background: #ccc;
            cursor: not-allowed;
            transform: none;
        }}
        .loading {{
            text-align: center;
            padding: 20px;
            color: #667eea;
            font-size: 18px;
        }}
        .game-over {{
            text-align: center;
            padding: 20px;
            background: #28a745;
            color: white;
            border-radius: 10px;
            font-size: 24px;
            font-weight: bold;
            margin: 20px 0;
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
        <h1>🎮 4mation - IA Minimax Interactive</h1>
        
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
                <div class="legend-color" style="background: rgba(255,255,255,0.1); border: 4px solid #11f1cc;"></div>
                <span>Coup possible (probabilité affichée)</span>
            </div>
            <div class="legend-item">
                <div class="legend-color" style="background: rgba(255,255,255,0.1); border: 5px solid #feca57; box-shadow: 0 0 20px rgba(254,202,87,0.8);"></div>
                <span>Meilleur coup</span>
            </div>
        </div>
        
        <div class="game-info">
            <div class="current-player" id="currentPlayer">Joueur 1 - Cliquez sur une case pour jouer</div>
            <div id="gameStatus"></div>
        </div>
        
        <div class="controls">
            <button class="btn" onclick="resetGame()">🔄 Nouvelle Partie</button>
            <button class="btn" onclick="toggleAutoPlay()" id="autoPlayBtn">🤖 Mode Auto: OFF</button>
        </div>
        
        <div class="board-container">
            <div class="board" id="board"></div>
        </div>
        
        <div class="loading" id="loading" style="display: none;">
            ⏳ Calcul des probabilités en cours...
        </div>
    </div>
    
    <script>
        // État du jeu
        let gameState = {{
            board: Array(7).fill(null).map(() => Array(7).fill(0)),
            currentPlayer: 1,
            lastMove: null,
            gameOver: false,
            winner: null,
            moveCount: 0
        }};
        
        let autoPlay = false;
        let isCalculating = false;
        
        // Initialiser le plateau
        function initBoard() {{
            const boardDiv = document.getElementById('board');
            boardDiv.innerHTML = '';
            
            for (let row = 0; row < 7; row++) {{
                for (let col = 0; col < 7; col++) {{
                    const cell = document.createElement('div');
                    cell.className = 'cell empty';
                    cell.dataset.row = row;
                    cell.dataset.col = col;
                    cell.onclick = () => handleCellClick(row, col);
                    boardDiv.appendChild(cell);
                }}
            }}
        }}
        
        // Gérer le clic sur une case
        async function handleCellClick(row, col) {{
            if (isCalculating || gameState.gameOver) return;
            
            // Vérifier si c'est un coup valide
            if (!isValidMove(row, col)) {{
                alert('Coup invalide! Vous devez jouer sur une case adjacente à la dernière position.');
                return;
            }}
            
            // Jouer le coup
            playMove(row, col);
            
            // Vérifier si la partie est terminée
            if (checkGameOver(row, col)) {{
                return;
            }}
            
            // Calculer les probabilités pour le joueur suivant
            await calculateProbabilities();
        }}
        
        // Vérifier si un coup est valide
        function isValidMove(row, col) {{
            // Vérifier que la case est vide
            if (gameState.board[row][col] !== 0) return false;
            
            // Premier coup : toutes les cases sont valides
            if (gameState.lastMove === null) return true;
            
            // Coups suivants : doit être adjacent au dernier coup
            const [lastRow, lastCol] = gameState.lastMove;
            const dr = Math.abs(row - lastRow);
            const dc = Math.abs(col - lastCol);
            
            return dr <= 1 && dc <= 1 && (dr > 0 || dc > 0);
        }}
        
        // Jouer un coup
        function playMove(row, col) {{
            gameState.board[row][col] = gameState.currentPlayer;
            gameState.lastMove = [row, col];
            gameState.moveCount++;
            
            // Passer au joueur suivant
            gameState.currentPlayer = gameState.currentPlayer === 1 ? 2 : 1;
            
            updateBoard();
            updateGameInfo();
        }}
        
        // Mettre à jour l'affichage du plateau
        function updateBoard() {{
            const boardDiv = document.getElementById('board');
            const cells = boardDiv.children;
            
            for (let row = 0; row < 7; row++) {{
                for (let col = 0; col < 7; col++) {{
                    const cell = cells[row * 7 + col];
                    const value = gameState.board[row][col];
                    
                    // Réinitialiser la cellule
                    cell.className = 'cell';
                    cell.innerHTML = '';
                    cell.removeAttribute('data-prob');
                    cell.onclick = () => handleCellClick(row, col);
                    
                    if (value === 0) {{
                        cell.className += ' empty';
                    }} else if (value === 1) {{
                        cell.className += ' player1';
                        const valueDiv = document.createElement('div');
                        valueDiv.className = 'cell-value';
                        valueDiv.textContent = '1';
                        cell.appendChild(valueDiv);
                        cell.onclick = null;
                    }} else if (value === 2) {{
                        cell.className += ' player2';
                        const valueDiv = document.createElement('div');
                        valueDiv.className = 'cell-value';
                        valueDiv.textContent = '2';
                        cell.appendChild(valueDiv);
                        cell.onclick = null;
                    }}
                }}
            }}
        }}
        
        // Calculer les probabilités avec l'IA
        async function calculateProbabilities() {{
            if (gameState.gameOver) return;
            
            isCalculating = true;
            document.getElementById('loading').style.display = 'block';
            
            try {{
                // Appeler l'API backend pour calculer les probabilités
                const response = await fetch('/api/analyze', {{
                    method: 'POST',
                    headers: {{
                        'Content-Type': 'application/json'
                    }},
                    body: JSON.stringify({{
                        board: gameState.board,
                        current_player: gameState.currentPlayer,
                        last_move: gameState.lastMove
                    }})
                }});
                
                if (!response.ok) {{
                    throw new Error('Erreur lors du calcul');
                }}
                
                const analysis = await response.json();
                
                // Afficher les probabilités sur le plateau
                displayProbabilities(analysis);
                
                // Si mode auto, jouer le meilleur coup après un délai
                if (autoPlay && analysis.best_move) {{
                    setTimeout(() => {{
                        const [row, col] = analysis.best_move;
                        playMove(row, col);
                        if (!checkGameOver(row, col)) {{
                            calculateProbabilities();
                        }}
                    }}, 1000);
                }}
            }} catch (error) {{
                console.error('Erreur:', error);
                // Fallback: utiliser une version simplifiée en JavaScript
                calculateProbabilitiesSimple();
            }} finally {{
                isCalculating = false;
                document.getElementById('loading').style.display = 'none';
            }}
        }}
        
        // Version simplifiée du calcul (fallback si pas d'API)
        function calculateProbabilitiesSimple() {{
            // Nettoyer les probabilités précédentes
            document.querySelectorAll('.cell').forEach(cell => {{
                cell.classList.remove('valid-move', 'best-move');
                cell.removeAttribute('data-prob');
            }});
            
            // Calcul simple basé sur la distance au dernier coup
            const validMoves = getValidMoves();
            if (validMoves.length === 0) return;
            
            const bestMove = validMoves[0]; // Premier coup valide (approximation)
            
            validMoves.forEach(([row, col], index) => {{
                const cell = document.querySelector(`[data-row="${{row}}"][data-col="${{col}}"]`);
                if (cell && gameState.board[row][col] === 0) {{
                    cell.className += ' valid-move';
                    // Probabilité approximative basée sur la position
                    // Les coups au centre sont généralement meilleurs
                    const centerRow = 3;
                    const centerCol = 3;
                    const distToCenter = Math.abs(row - centerRow) + Math.abs(col - centerCol);
                    const prob = Math.max(40, 70 - distToCenter * 5);
                    cell.setAttribute('data-prob', Math.min(prob, 95).toFixed(1) + '%');
                    
                    if (index === 0) {{
                        cell.className += ' best-move';
                    }}
                }}
            }});
        }}
        
        // Obtenir les coups valides
        function getValidMoves() {{
            const moves = [];
            
            for (let row = 0; row < 7; row++) {{
                for (let col = 0; col < 7; col++) {{
                    if (isValidMove(row, col)) {{
                        moves.push([row, col]);
                    }}
                }}
            }}
            
            return moves;
        }}
        
        // Afficher les probabilités
        function displayProbabilities(analysis) {{
            const moves = analysis.moves || [];
            const bestMove = analysis.best_move;
            
            moves.forEach(move => {{
                const [row, col] = move.move || [move.row, move.col];
                const cell = document.querySelector(`[data-row="${{row}}"][data-col="${{col}}"]`);
                
                if (cell && gameState.board[row][col] === 0) {{
                    cell.className += ' valid-move';
                    const prob = (move.win_probability * 100).toFixed(1);
                    cell.setAttribute('data-prob', prob + '%');
                    
                    if (bestMove && bestMove[0] === row && bestMove[1] === col) {{
                        cell.className += ' best-move';
                    }}
                }}
            }});
        }}
        
        // Vérifier si la partie est terminée
        function checkGameOver(row, col) {{
            // Vérifier les alignements (simplifié)
            const player = gameState.board[row][col];
            const directions = [[0,1], [1,0], [1,1], [1,-1]];
            
            for (const [dr, dc] of directions) {{
                let count = 1;
                
                // Compter dans une direction
                for (let step of [1, -1]) {{
                    for (let i = 1; i < 4; i++) {{
                        const r = row + dr * step * i;
                        const c = col + dc * step * i;
                        if (r >= 0 && r < 7 && c >= 0 && c < 7 && 
                            gameState.board[r][c] === player) {{
                            count++;
                        }} else {{
                            break;
                        }}
                    }}
                }}
                
                if (count >= 4) {{
                    gameState.gameOver = true;
                    gameState.winner = player;
                    showGameOver();
                    return true;
                }}
            }}
            
            // Vérifier égalité
            if (gameState.moveCount >= 49) {{
                gameState.gameOver = true;
                gameState.winner = 0;
                showGameOver();
                return true;
            }}
            
            return false;
        }}
        
        // Afficher le message de fin de partie
        function showGameOver() {{
            const statusDiv = document.getElementById('gameStatus');
            if (gameState.winner === 0) {{
                statusDiv.innerHTML = '<div class="game-over">Égalité!</div>';
            }} else {{
                statusDiv.innerHTML = `<div class="game-over">Joueur ${{gameState.winner}} a gagné!</div>`;
            }}
        }}
        
        // Mettre à jour les informations du jeu
        function updateGameInfo() {{
            const playerDiv = document.getElementById('currentPlayer');
            if (gameState.gameOver) {{
                playerDiv.textContent = 'Partie terminée';
            }} else {{
                playerDiv.textContent = `Joueur ${{gameState.currentPlayer}} - Cliquez sur une case pour jouer`;
            }}
        }}
        
        // Réinitialiser le jeu
        function resetGame() {{
            gameState = {{
                board: Array(7).fill(null).map(() => Array(7).fill(0)),
                currentPlayer: 1,
                lastMove: null,
                gameOver: false,
                winner: null,
                moveCount: 0
            }};
            
            document.getElementById('gameStatus').innerHTML = '';
            updateBoard();
            updateGameInfo();
            calculateProbabilities();
        }}
        
        // Basculer le mode auto
        function toggleAutoPlay() {{
            autoPlay = !autoPlay;
            const btn = document.getElementById('autoPlayBtn');
            btn.textContent = `🤖 Mode Auto: ${{autoPlay ? 'ON' : 'OFF'}}`;
            
            if (autoPlay && !gameState.gameOver && !isCalculating) {{
                calculateProbabilities();
            }}
        }}
        
        // Initialiser au chargement
        function initialize() {{
            initBoard();
            updateGameInfo();
            // Calculer les probabilités initiales (premier coup)
            setTimeout(() => {{
                calculateProbabilitiesSimple();
            }}, 100);
        }}
        
        // Initialiser quand le DOM est prêt
        if (document.readyState === 'loading') {{
            document.addEventListener('DOMContentLoaded', initialize);
        }} else {{
            initialize();
        }}
    </script>
</body>
</html>"""
    
    # Sauvegarder
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    print(f"Page interactive generee: {output_path}")
    return output_path


def create_api_server(port: int = 5000):
    """
    Crée un serveur API Flask pour calculer les probabilités
    """
    try:
        from flask import Flask, request, jsonify
        from flask_cors import CORS
    except ImportError:
        print("Flask n'est pas installe. Installation...")
        import subprocess
        subprocess.check_call(['pip', 'install', 'flask', 'flask-cors'])
        from flask import Flask, request, jsonify
        from flask_cors import CORS
    
    app = Flask(__name__)
    CORS(app)
    
    # Créer l'IA minimax
    advisor = MinimaxAdvisor(depth=5)
    
    @app.route('/api/analyze', methods=['POST'])
    def analyze():
        try:
            data = request.json
            board = np.array(data['board'], dtype=np.int8)
            current_player = data.get('current_player', 1)
            last_move = data.get('last_move')
            
            if last_move:
                last_move = tuple(last_move)
            
            # Analyser la position
            analysis = advisor.analyze_position(board, current_player, last_move)
            
            return jsonify(analysis)
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    
    @app.route('/')
    def index():
        # Servir la page HTML
        html_path = Path(__file__).parent.parent / "interactive_minimax.html"
        if html_path.exists():
            return open(html_path, 'r', encoding='utf-8').read()
        return "Page interactive non trouvee. Generez-la d'abord avec generate_interactive_page()"
    
    print(f"\n🚀 Serveur API demarre sur http://localhost:{port}")
    print(f"   Ouvrez http://localhost:{port} dans votre navigateur")
    print(f"   Appuyez sur Ctrl+C pour arreter\n")
    
    app.run(host='127.0.0.1', port=port, debug=False)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Page interactive avec IA Minimax")
    parser.add_argument("--generate", action="store_true",
                       help="Generer la page HTML interactive")
    parser.add_argument("--server", action="store_true",
                       help="Lancer le serveur API")
    parser.add_argument("--port", type=int, default=5000,
                       help="Port du serveur (defaut: 5000)")
    
    args = parser.parse_args()
    
    if args.generate:
        generate_interactive_page()
        print("Page HTML generee! Lancez le serveur avec --server")
    elif args.server:
        create_api_server(args.port)
    else:
        # Par défaut, générer et lancer le serveur
        generate_interactive_page()
        create_api_server(args.port)

