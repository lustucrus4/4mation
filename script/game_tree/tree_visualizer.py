"""
Visualisation de l'arbre de jeu avec D3.js et PDF
"""

import json
import numpy as np
from typing import Dict, Optional
from pathlib import Path

try:
    import matplotlib
    matplotlib.use('Agg')  # Backend non-interactif pour serveurs
    from matplotlib.backends.backend_pdf import PdfPages
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    from matplotlib.patches import FancyBboxPatch, Circle, FancyArrowPatch
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False


class TreeVisualizer:
    """
    Génère une visualisation HTML interactive de l'arbre de jeu.
    """
    
    def __init__(self):
        self.html_template = """<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Arbre de jeu 4mation - 8 premiers coups</title>
    <script src="https://d3js.org/d3.v7.min.js"></script>
    <style>
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            margin: 0;
            padding: 20px;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
            color: #fff;
            overflow: hidden;
        }}
        
        .container {{
            width: 100%;
            height: 100vh;
            display: flex;
            flex-direction: column;
        }}
        
        h1 {{
            text-align: center;
            color: #11f1cc;
            margin: 10px 0;
            font-size: 24px;
        }}
        
        .controls {{
            display: flex;
            gap: 10px;
            justify-content: center;
            margin-bottom: 10px;
            flex-wrap: wrap;
        }}
        
        button {{
            background: #11f1cc;
            color: #0f3460;
            border: none;
            padding: 8px 16px;
            border-radius: 5px;
            cursor: pointer;
            font-weight: bold;
            transition: all 0.3s;
        }}
        
        button:hover {{
            background: #0dd4b8;
            transform: translateY(-2px);
        }}
        
        button.active {{
            background: #0f3460;
            color: #11f1cc;
        }}
        
        .legend {{
            display: flex;
            gap: 20px;
            justify-content: center;
            margin-bottom: 10px;
            flex-wrap: wrap;
        }}
        
        .legend-item {{
            display: flex;
            align-items: center;
            gap: 5px;
        }}
        
        .legend-color {{
            width: 20px;
            height: 20px;
            border-radius: 50%;
            border: 2px solid rgba(255, 255, 255, 0.3);
        }}
        
        #tree-container {{
            flex: 1;
            overflow: hidden;
            background: rgba(255, 255, 255, 0.05);
            border-radius: 10px;
            border: 1px solid rgba(255, 255, 255, 0.1);
        }}
        
        .node {{
            cursor: pointer;
        }}
        
        .node circle {{
            stroke: rgba(255, 255, 255, 0.5);
            stroke-width: 2px;
        }}
        
        .node.winning circle {{
            fill: #2ecc71;
        }}
        
        .node.losing circle {{
            fill: #e74c3c;
        }}
        
        .node.draw circle {{
            fill: #f39c12;
        }}
        
        .node.ongoing circle {{
            fill: #3498db;
        }}
        
        .node.terminal circle {{
            stroke-width: 3px;
        }}
        
        .link {{
            fill: none;
            stroke: rgba(255, 255, 255, 0.2);
            stroke-width: 1.5px;
        }}
        
        .node-label {{
            font-size: 10px;
            fill: #fff;
            text-anchor: middle;
            pointer-events: none;
        }}
        
        .tooltip {{
            position: absolute;
            background: rgba(0, 0, 0, 0.9);
            color: #fff;
            padding: 10px;
            border-radius: 5px;
            pointer-events: none;
            font-size: 12px;
            max-width: 300px;
            z-index: 1000;
        }}
        
        .tooltip h3 {{
            margin: 0 0 5px 0;
            color: #11f1cc;
        }}
        
        .mini-board {{
            display: grid;
            grid-template-columns: repeat(7, 1fr);
            gap: 2px;
            margin-top: 5px;
        }}
        
        .mini-cell {{
            width: 15px;
            height: 15px;
            border-radius: 2px;
            border: 1px solid rgba(255, 255, 255, 0.3);
        }}
        
        .mini-cell.empty {{
            background: rgba(255, 255, 255, 0.1);
        }}
        
        .mini-cell.player1 {{
            background: #ff4757;
        }}
        
        .mini-cell.player2 {{
            background: #3742fa;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🌳 Arbre de jeu 4mation - 8 premiers coups</h1>
        
        <div class="controls">
            <button id="btn-all" class="active" data-filter="all">Toutes les branches</button>
            <button id="btn-winning" data-filter="winning">Branches gagnantes</button>
            <button id="btn-losing" data-filter="losing">Branches perdantes</button>
            <button id="btn-draw" data-filter="draw">Égalités</button>
            <button id="btn-ongoing" data-filter="ongoing">En cours</button>
        </div>
        
        <div class="legend">
            <div class="legend-item">
                <div class="legend-color" style="background: #2ecc71;"></div>
                <span>Gagnant (Joueur 1)</span>
            </div>
            <div class="legend-item">
                <div class="legend-color" style="background: #e74c3c;"></div>
                <span>Perdant (Joueur 1)</span>
            </div>
            <div class="legend-item">
                <div class="legend-color" style="background: #f39c12;"></div>
                <span>Égalité</span>
            </div>
            <div class="legend-item">
                <div class="legend-color" style="background: #3498db;"></div>
                <span>En cours</span>
            </div>
        </div>
        
        <div id="tree-container"></div>
    </div>
    
    <div class="tooltip" id="tooltip" style="display: none;"></div>
    
    <script>
        const treeData = {tree_data_json};
        
        let currentFilter = 'all';
        let svg, g, zoom, tooltip;
        let root, tree, diagonal;
        
        function initVisualization() {{
            const container = d3.select("#tree-container");
            const width = container.node().offsetWidth;
            const height = container.node().offsetHeight;
            
            svg = d3.select("#tree-container")
                .append("svg")
                .attr("width", width)
                .attr("height", height);
            
            g = svg.append("g");
            
            zoom = d3.zoom()
                .scaleExtent([0.1, 3])
                .on("zoom", (event) => {{
                    g.attr("transform", event.transform);
                }});
            
            svg.call(zoom);
            
            tooltip = d3.select("#tooltip");
            
            diagonal = d3.linkHorizontal()
                .x(d => d.y)
                .y(d => d.x);
            
            updateTree();
        }}
        
        function convertToD3Tree(data, rootId) {{
            function convertNode(nodeId, parent = null, depth = 0) {{
                const node = data[nodeId];
                if (!node) return null;
                
                const d3Node = {{
                    name: `Coup ${{node.move_count}}`,
                    nodeId: nodeId,
                    node: node,
                    depth: depth,
                    parent: parent,
                    children: []
                }};
                
                if (node.children && node.children.length > 0) {{
                    d3Node.children = node.children
                        .map(child => convertNode(child.node_id, d3Node, depth + 1))
                        .filter(n => n !== null);
                }}
                
                return d3Node;
            }}
            
            return convertNode(rootId);
        }}
        
        function updateTree() {{
            // Trouver la racine (move_count = 0)
            const rootId = Object.keys(treeData).find(id => treeData[id].move_count === 0);
            if (!rootId) {{
                console.error("Racine non trouvée");
                return;
            }}
            
            root = convertToD3Tree(treeData, rootId);
            if (!root) {{
                console.error("Impossible de convertir l'arbre");
                return;
            }}
            
            tree = d3.tree()
                .size([document.getElementById("tree-container").offsetHeight - 40, 
                       document.getElementById("tree-container").offsetWidth - 200]);
            
            const treeRoot = d3.hierarchy(root);
            tree(treeRoot);
            
            // Filtrer selon le filtre actuel
            if (currentFilter !== 'all') {{
                filterNodes(treeRoot, currentFilter);
            }}
            
            renderTree(treeRoot);
        }}
        
        function filterNodes(node, filter) {{
            if (node.children) {{
                node.children = node.children.filter(child => {{
                    const classification = child.data.node.classification;
                    if (filter === 'winning' && classification === 'winning') return true;
                    if (filter === 'losing' && classification === 'losing') return true;
                    if (filter === 'draw' && classification === 'draw') return true;
                    if (filter === 'ongoing' && classification === 'ongoing') return true;
                    return false;
                }});
                
                node.children.forEach(child => filterNodes(child, filter));
            }}
        }}
        
        function renderTree(root) {{
            g.selectAll("*").remove();
            
            const links = g.selectAll(".link")
                .data(root.links())
                .enter()
                .append("path")
                .attr("class", "link")
                .attr("d", diagonal);
            
            const nodes = g.selectAll(".node")
                .data(root.descendants())
                .enter()
                .append("g")
                .attr("class", d => {{
                    const classification = d.data.node.classification || 'ongoing';
                    const terminal = d.data.node.is_terminal ? ' terminal' : '';
                    return `node ${{classification}}${{terminal}}`;
                }})
                .attr("transform", d => `translate(${{d.y}},${{d.x}})`)
                .on("mouseover", showTooltip)
                .on("mouseout", hideTooltip)
                .on("click", zoomToNode);
            
            nodes.append("circle")
                .attr("r", d => d.data.node.is_terminal ? 8 : 6);
            
            nodes.append("text")
                .attr("class", "node-label")
                .attr("dy", 20)
                .text(d => `${{d.data.node.move_count}}`);
            
            // Centrer la vue
            const bounds = g.node().getBBox();
            const fullWidth = bounds.width;
            const fullHeight = bounds.height;
            const width = document.getElementById("tree-container").offsetWidth;
            const height = document.getElementById("tree-container").offsetHeight;
            
            const scale = 0.8 / Math.max(fullWidth / width, fullHeight / height);
            const translate = [
                width / 2 - scale * (bounds.x + bounds.width / 2),
                height / 2 - scale * (bounds.y + bounds.height / 2)
            ];
            
            g.transition()
                .duration(750)
                .attr("transform", `translate(${{translate[0]}},${{translate[1]}}) scale(${{scale}})`);
        }}
        
        function showTooltip(event, d) {{
            const node = d.data.node;
            const board = node.board;
            
            let boardHtml = '<div class="mini-board">';
            for (let row = 0; row < board.length; row++) {{
                for (let col = 0; col < board[row].length; col++) {{
                    const cell = board[row][col];
                    let cellClass = 'empty';
                    if (cell === 1) cellClass = 'player1';
                    if (cell === 2) cellClass = 'player2';
                    boardHtml += `<div class="mini-cell ${{cellClass}}"></div>`;
                }}
            }}
            boardHtml += '</div>';
            
            const moveInfo = node.last_move 
                ? `Coup: (${{node.last_move[0]}}, ${{node.last_move[1]}})<br>`
                : 'Position initiale<br>';
            
            const winnerInfo = node.is_terminal
                ? (node.winner === 1 ? '🎉 Joueur 1 gagne' : 
                   node.winner === 2 ? '❌ Joueur 2 gagne' : 
                   '🤝 Égalité')
                : `En cours - Joueur ${{node.current_player}}`;
            
            tooltip
                .style("display", "block")
                .html(`
                    <h3>Coup #${{node.move_count}}</h3>
                    ${{moveInfo}}
                    ${{winnerInfo}}<br>
                    Classification: <strong>${{node.classification || 'N/A'}}</strong><br>
                    Évaluation: ${{node.evaluation !== undefined ? node.evaluation.toFixed(2) : 'N/A'}}
                    ${{boardHtml}}
                `)
                .style("left", (event.pageX + 10) + "px")
                .style("top", (event.pageY + 10) + "px");
        }}
        
        function hideTooltip() {{
            tooltip.style("display", "none");
        }}
        
        function zoomToNode(event, d) {{
            const scale = 2;
            const x = -d.y * scale + document.getElementById("tree-container").offsetWidth / 2;
            const y = -d.x * scale + document.getElementById("tree-container").offsetHeight / 2;
            
            g.transition()
                .duration(750)
                .attr("transform", `translate(${{x}},${{y}}) scale(${{scale}})`);
        }}
        
        // Définir filterTree dans la portée globale
        window.filterTree = function(filter) {{
            currentFilter = filter;
            
            // Mettre à jour les boutons
            d3.selectAll("button").classed("active", false);
            d3.select(`#btn-${{filter}}`).classed("active", true);
            
            updateTree();
        }};
        
        // Attacher les event listeners aux boutons
        document.addEventListener("DOMContentLoaded", function() {{
            document.querySelectorAll("button[data-filter]").forEach(button => {{
                button.addEventListener("click", function() {{
                    const filter = this.getAttribute("data-filter");
                    window.filterTree(filter);
                }});
            }});
        }});
        
        // Initialiser quand la page est chargée
        window.addEventListener("resize", () => {{
            if (svg) {{
                const container = document.getElementById("tree-container");
                svg.attr("width", container.offsetWidth)
                   .attr("height", container.offsetHeight);
                updateTree();
            }}
        }});
        
        // Initialiser la visualisation
        if (document.readyState === 'loading') {{
            document.addEventListener('DOMContentLoaded', initVisualization);
        }} else {{
            initVisualization();
        }}
    </script>
</body>
</html>"""
    
    def generate_html(self, tree: Dict[str, dict], output_path: str):
        """
        Génère le fichier HTML de visualisation.
        
        Args:
            tree: Arbre de jeu classifié
            output_path: Chemin du fichier HTML à générer
        """
        print(f"🎨 Génération de la visualisation HTML...")
        
        # Convertir les tableaux numpy en listes pour JSON
        tree_json = {}
        for node_id, node_data in tree.items():
            node_json = node_data.copy()
            # Convertir le board numpy en liste
            if 'board' in node_json:
                node_json['board'] = node_json['board'].tolist()
            tree_json[node_id] = node_json
        
        # Générer le JSON
        tree_data_json = json.dumps(tree_json, indent=2)
        
        # Remplacer dans le template
        html_content = self.html_template.format(tree_data_json=tree_data_json)
        
        # Sauvegarder
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(html_content, encoding='utf-8')
        
        print(f"✅ Visualisation sauvegardée dans: {output_path}")
    
    def generate_pdf(self, tree: Dict[str, dict], output_path: str, max_depth: int = 5):
        """
        Génère un fichier PDF de visualisation de l'arbre.
        
        Args:
            tree: Arbre de jeu classifié
            output_path: Chemin du fichier PDF à générer
            max_depth: Profondeur maximale à afficher (pour éviter les PDF trop grands)
        """
        if not HAS_MATPLOTLIB:
            print("❌ Erreur: matplotlib n'est pas installé. Installez-le avec: pip install matplotlib")
            return
        
        print(f"📄 Génération du PDF...")
        
        # Trouver la racine
        root_id = None
        for node_id, node_data in tree.items():
            if node_data.get('move_count', 0) == 0:
                root_id = node_id
                break
        
        if root_id is None:
            print("❌ Erreur: Racine de l'arbre non trouvée")
            return
        
        # Construire la structure hiérarchique
        def build_hierarchy(node_id: str, depth: int = 0) -> Optional[dict]:
            if depth > max_depth:
                return None
            
            node = tree.get(node_id)
            if not node:
                return None
            
            hierarchy_node = {
                'id': node_id,
                'data': node,
                'children': []
            }
            
            if 'children' in node:
                for child_link in node['children']:
                    child_id = child_link.get('node_id')
                    if child_id and child_id in tree:
                        child_hierarchy = build_hierarchy(child_id, depth + 1)
                        if child_hierarchy:
                            hierarchy_node['children'].append(child_hierarchy)
            
            return hierarchy_node
        
        root_hierarchy = build_hierarchy(root_id)
        if not root_hierarchy:
            print("❌ Erreur: Impossible de construire la hiérarchie")
            return
        
        # Calculer les positions des nœuds
        positions = {}
        y_positions_by_depth = {}
        
        def calculate_positions(node: dict, x: float, depth: int = 0):
            if depth not in y_positions_by_depth:
                y_positions_by_depth[depth] = []
            
            # Calculer la position Y (verticale)
            num_siblings = len(y_positions_by_depth[depth])
            y = num_siblings * 2.0  # Espacement vertical
            y_positions_by_depth[depth].append(y)
            
            positions[node['id']] = (x, y)
            
            # Positionner les enfants
            if node['children']:
                child_x = x + 3.0  # Espacement horizontal
                for child in node['children']:
                    calculate_positions(child, child_x, depth + 1)
        
        calculate_positions(root_hierarchy, 0.0)
        
        # Créer le PDF
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        with PdfPages(str(output_file)) as pdf:
            # Page 1: Vue d'ensemble de l'arbre
            fig, ax = plt.subplots(figsize=(16, 12))
            ax.set_xlim(-1, max([p[0] for p in positions.values()]) + 2)
            ax.set_ylim(-1, max([p[1] for p in positions.values()]) + 2)
            ax.axis('off')
            ax.set_title('Arbre de jeu 4mation - 8 premiers coups', 
                        fontsize=16, fontweight='bold', pad=20)
            
            # Couleurs pour les classifications
            color_map = {
                'winning': '#2ecc71',  # Vert
                'losing': '#e74c3c',   # Rouge
                'draw': '#f39c12',     # Orange
                'ongoing': '#3498db'   # Bleu
            }
            
            # Dessiner les liens
            def draw_links(node: dict):
                node_pos = positions[node['id']]
                for child in node['children']:
                    child_pos = positions[child['id']]
                    arrow = FancyArrowPatch(
                        node_pos, child_pos,
                        arrowstyle='->', 
                        mutation_scale=15,
                        color='gray',
                        alpha=0.5,
                        linewidth=1
                    )
                    ax.add_patch(arrow)
                    draw_links(child)
            
            draw_links(root_hierarchy)
            
            # Dessiner les nœuds
            for node_id, (x, y) in positions.items():
                node = tree[node_id]
                classification = node.get('classification', 'ongoing')
                color = color_map.get(classification, '#95a5a6')
                
                # Taille du nœud selon s'il est terminal
                radius = 0.3 if node.get('is_terminal') else 0.25
                
                circle = Circle((x, y), radius, color=color, 
                              ec='black', linewidth=1.5, zorder=3)
                ax.add_patch(circle)
                
                # Texte avec le numéro de coup
                move_count = node.get('move_count', 0)
                ax.text(x, y, str(move_count), ha='center', va='center',
                       fontsize=8, fontweight='bold', color='white', zorder=4)
            
            # Légende
            legend_elements = [
                mpatches.Patch(color=color_map['winning'], label='Gagnant (J1)'),
                mpatches.Patch(color=color_map['losing'], label='Perdant (J1)'),
                mpatches.Patch(color=color_map['draw'], label='Égalité'),
                mpatches.Patch(color=color_map['ongoing'], label='En cours')
            ]
            ax.legend(handles=legend_elements, loc='upper right', fontsize=10)
            
            # Statistiques
            stats_text = f"Total nœuds: {len(tree)}\n"
            stats_text += f"Profondeur max affichée: {max_depth}\n"
            winning = sum(1 for n in tree.values() if n.get('classification') == 'winning')
            losing = sum(1 for n in tree.values() if n.get('classification') == 'losing')
            draw = sum(1 for n in tree.values() if n.get('classification') == 'draw')
            stats_text += f"Gagnants: {winning}, Perdants: {losing}, Égalités: {draw}"
            
            ax.text(0.02, 0.98, stats_text, transform=ax.transAxes,
                   fontsize=9, verticalalignment='top',
                   bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))
            
            plt.tight_layout()
            pdf.savefig(fig, bbox_inches='tight')
            plt.close()
            
            # Pages supplémentaires: Détails des positions importantes
            # Page 2: Positions gagnantes
            winning_nodes = [(nid, n) for nid, n in tree.items() 
                          if n.get('classification') == 'winning' and n.get('is_terminal')]
            
            if winning_nodes:
                fig, axes = plt.subplots(2, 3, figsize=(16, 12))
                axes = axes.flatten()
                fig.suptitle('Positions gagnantes (Joueur 1)', fontsize=14, fontweight='bold')
                
                for idx, (node_id, node) in enumerate(winning_nodes[:6]):  # Max 6 exemples
                    ax = axes[idx]
                    board = node.get('board', np.zeros((7, 7), dtype=np.int8))
                    if isinstance(board, list):
                        board = np.array(board)
                    
                    # Dessiner le plateau
                    ax.imshow(board, cmap='RdYlBu', vmin=0, vmax=2, aspect='equal')
                    ax.set_xticks(range(7))
                    ax.set_yticks(range(7))
                    ax.grid(True, color='black', linewidth=0.5)
                    ax.set_title(f"Coup #{node.get('move_count', 0)} - Gagnant", fontsize=10)
                    
                    # Marquer les pièces
                    for r in range(7):
                        for c in range(7):
                            if board[r, c] == 1:
                                ax.text(c, r, '●', ha='center', va='center',
                                       color='red', fontsize=12, fontweight='bold')
                            elif board[r, c] == 2:
                                ax.text(c, r, '●', ha='center', va='center',
                                       color='blue', fontsize=12, fontweight='bold')
                
                # Cacher les axes non utilisés
                for idx in range(len(winning_nodes), 6):
                    axes[idx].axis('off')
                
                plt.tight_layout()
                pdf.savefig(fig, bbox_inches='tight')
                plt.close()
        
        print(f"✅ PDF généré: {output_path}")

