"""
Visualisation HTML des meilleures parties
"""

from pathlib import Path
from typing import List, Dict
import json


def generate_elite_games_html(elite_games: List[Dict], output_path: str = "elite_games/visualization.html"):
    """
    Génère une visualisation HTML interactive des meilleures parties
    
    Args:
        elite_games: Liste des meilleures parties (format EliteGameTracker)
        output_path: Chemin de sortie pour le fichier HTML
    """
    html_template = """<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Meilleures Parties - 4mation IA</title>
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
        .subtitle {{
            text-align: center;
            color: #666;
            margin-bottom: 30px;
        }}
        .game-list {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }}
        .game-card {{
            background: #f8f9fa;
            border: 2px solid #e9ecef;
            border-radius: 10px;
            padding: 15px;
            cursor: pointer;
            transition: all 0.3s ease;
        }}
        .game-card:hover {{
            transform: translateY(-5px);
            box-shadow: 0 5px 15px rgba(0,0,0,0.2);
            border-color: #667eea;
        }}
        .game-card.selected {{
            border-color: #667eea;
            background: #e7f3ff;
        }}
        .game-rank {{
            font-size: 24px;
            font-weight: bold;
            color: #667eea;
            margin-bottom: 5px;
        }}
        .game-reward {{
            font-size: 18px;
            color: #28a745;
            font-weight: bold;
            margin-bottom: 10px;
        }}
        .game-info {{
            font-size: 14px;
            color: #666;
        }}
        .game-viewer {{
            margin-top: 30px;
            padding: 20px;
            background: #f8f9fa;
            border-radius: 10px;
            display: none;
        }}
        .game-viewer.active {{
            display: block;
        }}
        .board-container {{
            display: inline-block;
            background: rgba(255, 255, 255, 0.2);
            padding: 20px;
            border-radius: 12px;
            margin: 10px;
        }}
        .board {{
            display: grid;
            grid-template-columns: repeat(7, 50px);
            gap: 5px;
            background: rgba(0, 0, 0, 0.1);
            padding: 10px;
            border-radius: 10px;
        }}
        .cell {{
            width: 50px;
            height: 50px;
            border-radius: 8px;
            border: 2px solid rgba(255, 255, 255, 0.3);
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: bold;
            transition: all 0.3s ease;
        }}
        .cell.empty {{
            background: rgba(255, 255, 255, 0.3);
        }}
        .cell.player1 {{
            background: linear-gradient(135deg, #ff4757 0%, #c44569 100%);
            color: white;
            box-shadow: 0 0 10px rgba(255, 71, 87, 0.5);
        }}
        .cell.player2 {{
            background: linear-gradient(135deg, #3742fa 0%, #2f3542 100%);
            color: white;
            box-shadow: 0 0 10px rgba(55, 66, 250, 0.5);
        }}
        .controls {{
            text-align: center;
            margin: 20px 0;
        }}
        .btn {{
            background: #667eea;
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 5px;
            cursor: pointer;
            font-size: 16px;
            margin: 0 5px;
            transition: background 0.3s;
        }}
        .btn:hover {{
            background: #5568d3;
        }}
        .btn:disabled {{
            background: #ccc;
            cursor: not-allowed;
        }}
        .move-info {{
            text-align: center;
            margin: 10px 0;
            font-size: 18px;
            color: #333;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🎮 Meilleures Parties - 4mation IA</h1>
        <p class="subtitle">Top {num_games} parties les plus récompensées</p>
        
        <div class="game-list">
            {game_cards}
        </div>
        
        <div class="game-viewer" id="gameViewer">
            <h2 id="viewerTitle">Sélectionnez une partie</h2>
            <div class="controls">
                <button class="btn" id="prevBtn" onclick="previousMove()">◀ Précédent</button>
                <span class="move-info" id="moveInfo">Coup 0 / 0</span>
                <button class="btn" id="nextBtn" onclick="nextMove()">Suivant ▶</button>
            </div>
            <div id="boardContainer" class="board-container"></div>
        </div>
    </div>
    
    <script>
        const games = {games_json};
        let currentGameIndex = -1;
        let currentMoveIndex = 0;
        
        function selectGame(index) {{
            // Mettre à jour la sélection visuelle
            document.querySelectorAll('.game-card').forEach((card, i) => {{
                card.classList.toggle('selected', i === index);
            }});
            
            currentGameIndex = index;
            currentMoveIndex = 0;
            displayGame();
        }}
        
        function displayGame() {{
            if (currentGameIndex < 0 || currentGameIndex >= games.length) {{
                document.getElementById('gameViewer').classList.remove('active');
                return;
            }}
            
            const game = games[currentGameIndex];
            document.getElementById('gameViewer').classList.add('active');
            document.getElementById('viewerTitle').textContent = 
                `Partie #{currentGameIndex + 1} - Récompense: {game.reward.toFixed(2)}`;
            
            updateBoard();
            updateControls();
        }}
        
        function updateBoard() {{
            if (currentGameIndex < 0) return;
            
            const game = games[currentGameIndex];
            const boardHistory = game.board_history || [];
            
            if (boardHistory.length === 0) {{
                // Reconstruire depuis les coups si pas d'historique
                const board = Array(7).fill(null).map(() => Array(7).fill(0));
                for (let i = 0; i <= currentMoveIndex && i < game.moves.length; i++) {{
                    const [row, col] = game.moves[i];
                    // Joueur 1 joue aux coups pairs (0, 2, 4...), joueur 2 aux impairs (1, 3, 5...)
                    board[row][col] = (i % 2 === 0) ? 1 : 2;
                }}
                renderBoard(board);
            }} else {{
                const boardIndex = Math.min(currentMoveIndex, boardHistory.length - 1);
                renderBoard(boardHistory[boardIndex]);
            }}
        }}
        
        function renderBoard(board) {{
            const container = document.getElementById('boardContainer');
            const boardDiv = document.createElement('div');
            boardDiv.className = 'board';
            
            for (let row = 0; row < 7; row++) {{
                for (let col = 0; col < 7; col++) {{
                    const cell = document.createElement('div');
                    cell.className = 'cell';
                    const value = board[row][col];
                    if (value === 0) {{
                        cell.className += ' empty';
                    }} else if (value === 1) {{
                        cell.className += ' player1';
                        cell.textContent = '1';
                    }} else if (value === 2) {{
                        cell.className += ' player2';
                        cell.textContent = '2';
                    }}
                    boardDiv.appendChild(cell);
                }}
            }}
            
            container.innerHTML = '';
            container.appendChild(boardDiv);
        }}
        
        function previousMove() {{
            if (currentMoveIndex > 0) {{
                currentMoveIndex--;
                updateBoard();
                updateControls();
            }}
        }}
        
        function nextMove() {{
            const game = games[currentGameIndex];
            const maxMoves = Math.max(game.moves.length, (game.board_history || []).length);
            if (currentMoveIndex < maxMoves - 1) {{
                currentMoveIndex++;
                updateBoard();
                updateControls();
            }}
        }}
        
        function updateControls() {{
            const game = games[currentGameIndex];
            const maxMoves = Math.max(game.moves.length, (game.board_history || []).length);
            
            document.getElementById('moveInfo').textContent = 
                `Coup ${{currentMoveIndex + 1}} / ${{maxMoves}}`;
            
            document.getElementById('prevBtn').disabled = currentMoveIndex === 0;
            document.getElementById('nextBtn').disabled = currentMoveIndex >= maxMoves - 1;
        }}
    </script>
</body>
</html>"""
    
    # Générer les cartes de jeu
    game_cards_html = ""
    for i, game in enumerate(elite_games):
        reward = game.get('reward', 0)
        move_count = game.get('move_count', len(game.get('moves', [])))
        winner = game.get('winner', 'N/A')
        
        game_cards_html += f"""
            <div class="game-card" onclick="selectGame({i})">
                <div class="game-rank">#{i+1}</div>
                <div class="game-reward">Récompense: {reward:.2f}</div>
                <div class="game-info">
                    Coups: {move_count}<br>
                    Gagnant: {winner if winner else 'Égalité'}
                </div>
            </div>
        """
    
    # Générer le HTML
    html_content = html_template.format(
        num_games=len(elite_games),
        game_cards=game_cards_html,
        games_json=json.dumps(elite_games, indent=2)
    )
    
    # Sauvegarder
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    print(f"Visualisation HTML generee: {output_path}")
    return output_path


def generate_elite_games_html_by_generation(generations_history: List[Dict], output_path: str = "elite_generations/visualization.html"):
    """
    Génère une visualisation HTML organisée par génération
    
    Args:
        generations_history: Liste des statistiques de générations
        output_path: Chemin de sortie pour le fichier HTML
    """
    html_template = """<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Meilleures Parties par Génération - 4mation IA</title>
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
        .subtitle {{
            text-align: center;
            color: #666;
            margin-bottom: 30px;
        }}
        .generation-section {{
            margin-bottom: 40px;
            padding: 20px;
            background: #f8f9fa;
            border-radius: 10px;
            border-left: 5px solid #667eea;
        }}
        .generation-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
            padding-bottom: 10px;
            border-bottom: 2px solid #e9ecef;
        }}
        .generation-title {{
            font-size: 24px;
            font-weight: bold;
            color: #667eea;
        }}
        .generation-stats {{
            color: #666;
            font-size: 14px;
        }}
        .game-list {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
            margin-bottom: 20px;
        }}
        .game-card {{
            background: white;
            border: 2px solid #e9ecef;
            border-radius: 10px;
            padding: 15px;
            cursor: pointer;
            transition: all 0.3s ease;
        }}
        .game-card:hover {{
            transform: translateY(-5px);
            box-shadow: 0 5px 15px rgba(0,0,0,0.2);
            border-color: #667eea;
        }}
        .game-card.selected {{
            border-color: #667eea;
            background: #e7f3ff;
        }}
        .game-rank {{
            font-size: 20px;
            font-weight: bold;
            color: #667eea;
            margin-bottom: 5px;
        }}
        .game-reward {{
            font-size: 18px;
            color: #28a745;
            font-weight: bold;
            margin-bottom: 10px;
        }}
        .game-info {{
            font-size: 14px;
            color: #666;
        }}
        .game-viewer {{
            margin-top: 30px;
            padding: 20px;
            background: #f8f9fa;
            border-radius: 10px;
            display: none;
        }}
        .game-viewer.active {{
            display: block;
        }}
        .board-container {{
            display: inline-block;
            background: rgba(255, 255, 255, 0.2);
            padding: 20px;
            border-radius: 12px;
            margin: 10px;
        }}
        .board {{
            display: grid;
            grid-template-columns: repeat(7, 50px);
            gap: 5px;
            background: rgba(0, 0, 0, 0.1);
            padding: 10px;
            border-radius: 10px;
        }}
        .cell {{
            width: 50px;
            height: 50px;
            border-radius: 8px;
            border: 2px solid rgba(255, 255, 255, 0.3);
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: bold;
            transition: all 0.3s ease;
        }}
        .cell.empty {{
            background: rgba(255, 255, 255, 0.3);
        }}
        .cell.player1 {{
            background: linear-gradient(135deg, #ff4757 0%, #c44569 100%);
            color: white;
            box-shadow: 0 0 10px rgba(255, 71, 87, 0.5);
        }}
        .cell.player2 {{
            background: linear-gradient(135deg, #3742fa 0%, #2f3542 100%);
            color: white;
            box-shadow: 0 0 10px rgba(55, 66, 250, 0.5);
        }}
        .controls {{
            text-align: center;
            margin: 20px 0;
        }}
        .btn {{
            background: #667eea;
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 5px;
            cursor: pointer;
            font-size: 16px;
            margin: 0 5px;
            transition: background 0.3s;
        }}
        .btn:hover {{
            background: #5568d3;
        }}
        .btn:disabled {{
            background: #ccc;
            cursor: not-allowed;
        }}
        .move-info {{
            text-align: center;
            margin: 10px 0;
            font-size: 18px;
            color: #333;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🎮 Meilleures Parties par Génération - 4mation IA</h1>
        <p class="subtitle">Les 2 meilleures parties de chaque génération</p>
        
        {generations_html}
        
        <div class="game-viewer" id="gameViewer">
            <h2 id="viewerTitle">Sélectionnez une partie</h2>
            <div class="controls">
                <button class="btn" id="prevBtn" onclick="previousMove()">◀ Précédent</button>
                <span class="move-info" id="moveInfo">Coup 0 / 0</span>
                <button class="btn" id="nextBtn" onclick="nextMove()">Suivant ▶</button>
            </div>
            <div id="boardContainer" class="board-container"></div>
        </div>
    </div>
    
    <script>
        const allGames = {all_games_json};
        let currentGameIndex = -1;
        let currentMoveIndex = 0;
        
        function selectGame(gameIndex) {{
            // Mettre à jour la sélection visuelle
            document.querySelectorAll('.game-card').forEach((card, i) => {{
                if (card.dataset.gameIndex == gameIndex) {{
                    card.classList.add('selected');
                }} else {{
                    card.classList.remove('selected');
                }}
            }});
            
            currentGameIndex = gameIndex;
            currentMoveIndex = 0;
            displayGame();
        }}
        
        function displayGame() {{
            if (currentGameIndex < 0 || currentGameIndex >= allGames.length) {{
                document.getElementById('gameViewer').classList.remove('active');
                return;
            }}
            
            const game = allGames[currentGameIndex];
            document.getElementById('gameViewer').classList.add('active');
            document.getElementById('viewerTitle').textContent = 
                `Partie #${{currentGameIndex + 1}} - Récompense: ${{game.reward.toFixed(2)}}`;
            
            updateBoard();
            updateControls();
        }}
        
        function updateBoard() {{
            if (currentGameIndex < 0) return;
            
            const game = allGames[currentGameIndex];
            const boardHistory = game.board_history || [];
            
            if (boardHistory.length === 0) {{
                // Reconstruire depuis les coups si pas d'historique
                const board = Array(7).fill(null).map(() => Array(7).fill(0));
                for (let i = 0; i <= currentMoveIndex && i < game.moves.length; i++) {{
                    const [row, col] = game.moves[i];
                    // Joueur 1 joue aux coups pairs (0, 2, 4...), joueur 2 aux impairs (1, 3, 5...)
                    board[row][col] = (i % 2 === 0) ? 1 : 2;
                }}
                renderBoard(board);
            }} else {{
                const boardIndex = Math.min(currentMoveIndex, boardHistory.length - 1);
                renderBoard(boardHistory[boardIndex]);
            }}
        }}
        
        function renderBoard(board) {{
            const container = document.getElementById('boardContainer');
            const boardDiv = document.createElement('div');
            boardDiv.className = 'board';
            
            for (let row = 0; row < 7; row++) {{
                for (let col = 0; col < 7; col++) {{
                    const cell = document.createElement('div');
                    cell.className = 'cell';
                    const value = board[row][col];
                    if (value === 0) {{
                        cell.className += ' empty';
                    }} else if (value === 1) {{
                        cell.className += ' player1';
                        cell.textContent = '1';
                    }} else if (value === 2) {{
                        cell.className += ' player2';
                        cell.textContent = '2';
                    }}
                    boardDiv.appendChild(cell);
                }}
            }}
            
            container.innerHTML = '';
            container.appendChild(boardDiv);
        }}
        
        function previousMove() {{
            if (currentMoveIndex > 0) {{
                currentMoveIndex--;
                updateBoard();
                updateControls();
            }}
        }}
        
        function nextMove() {{
            const game = allGames[currentGameIndex];
            const maxMoves = Math.max(game.moves.length, (game.board_history || []).length);
            if (currentMoveIndex < maxMoves - 1) {{
                currentMoveIndex++;
                updateBoard();
                updateControls();
            }}
        }}
        
        function updateControls() {{
            const game = allGames[currentGameIndex];
            const maxMoves = Math.max(game.moves.length, (game.board_history || []).length);
            
            document.getElementById('moveInfo').textContent = 
                `Coup ${{currentMoveIndex + 1}} / ${{maxMoves}}`;
            
            document.getElementById('prevBtn').disabled = currentMoveIndex === 0;
            document.getElementById('nextBtn').disabled = currentMoveIndex >= maxMoves - 1;
        }}
    </script>
</body>
</html>"""
    
    # Organiser les parties par génération
    generations_html = ""
    all_games_flat = []
    game_index = 0
    
    for gen in generations_history:
        gen_num = gen.get('generation', 0)
        elite_games = gen.get('elite_games', [])
        best_reward = gen.get('best_reward', 0)
        avg_reward = gen.get('avg_reward', 0)
        total_games = gen.get('total_games', 0)
        
        # Générer les cartes pour cette génération
        game_cards_html = ""
        for i, game in enumerate(elite_games):
            reward = game.get('reward', 0)
            move_count = game.get('move_count', len(game.get('moves', [])))
            winner = game.get('winner', 'N/A')
            
            game_cards_html += f"""
                <div class="game-card" onclick="selectGame({game_index})" data-game-index="{game_index}">
                    <div class="game-rank">#{i+1} de la Génération {gen_num}</div>
                    <div class="game-reward">Récompense: {reward:.2f}</div>
                    <div class="game-info">
                        Coups: {move_count}<br>
                        Gagnant: {winner if winner else 'Égalité'}
                    </div>
                </div>
            """
            
            # Ajouter à la liste plate pour le JavaScript
            all_games_flat.append(game)
            game_index += 1
        
        # Section de génération
        generations_html += f"""
        <div class="generation-section">
            <div class="generation-header">
                <div class="generation-title">Génération {gen_num}</div>
                <div class="generation-stats">
                    {total_games} parties jouées | Meilleure: {best_reward:.2f} | Moyenne: {avg_reward:.2f}
                </div>
            </div>
            <div class="game-list">
                {game_cards_html}
            </div>
        </div>
        """
    
    # Générer le HTML
    html_content = html_template.format(
        generations_html=generations_html,
        all_games_json=json.dumps(all_games_flat, indent=2)
    )
    
    # Sauvegarder
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    print(f"Visualisation HTML par generation generee: {output_path}")
    return output_path

