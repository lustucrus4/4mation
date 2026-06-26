"""Routes section Apprendre : ouvertures, puzzles, leçons."""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from api.services.opening_explorer import explore_opening
from api.services.puzzle_service import (
    check_pack_puzzle_move,
    check_puzzle_solution,
    get_pack_puzzle,
    list_pack_puzzles,
    random_puzzle,
)

learn_bp = Blueprint("learn", __name__)

LESSONS = [
    {
        "id": "intro",
        "title": "Les règles du 4mation",
        "level": "débutant",
        "duration_min": 3,
        "sections": [
            {
                "heading": "Objectif",
                "body": "Aligner 4 pions adjacents (horizontal, vertical ou diagonal) sur un plateau 7×7.",
            },
            {
                "heading": "Frontière",
                "body": "Après le premier coup, vous devez jouer sur une case adjacente au **dernier coup joué** "
                "(8 directions). Si ces voisins sont tous occupés, les cases vides adjacentes à un pion "
                "adverse deviennent jouables. Au premier coup, toute case est libre.",
            },
            {
                "heading": "Stratégie",
                "body": "Contrôler le centre, créer des menaces doubles et bloquer les alignements adverses.",
            },
        ],
    },
    {
        "id": "ouvertures",
        "title": "Principes d'ouverture",
        "level": "intermédiaire",
        "duration_min": 5,
        "sections": [
            {
                "heading": "Centre d'abord",
                "body": "Les cases centrales (3,3) et voisines offrent le plus de continuations — "
                "consultez l'explorateur pour comparer les taux de victoire.",
            },
            {
                "heading": "Suivez la frontière",
                "body": "Vos coups légaux dépendent du dernier coup joué : anticipez où l'adversaire pourra "
                "répondre et verrouillez les cases autour de sa dernière pose.",
            },
        ],
    },
    {
        "id": "frontier",
        "title": "La règle du dernier coup",
        "level": "débutant",
        "duration_min": 4,
        "sections": [
            {
                "heading": "Principe",
                "body": "Contrairement à un jeu où l'on doit toucher n'importe quel pion existant, au 4mation "
                "seule compte la **dernière case jouée**. Vous devez poser sur l'un de ses 8 voisins immédiats.",
            },
            {
                "heading": "Premier coup",
                "body": "Plateau vide : le premier joueur choisit librement n'importe quelle case. "
                "C'est le seul moment sans contrainte de voisinage.",
            },
            {
                "heading": "Exemple",
                "body": "Si le bleu vient de jouer en (3,4), le rouge ne peut jouer que sur les cases qui "
                "touchent (3,4). Une case qui touche seulement un pion rouge plus ancien reste interdite.",
            },
            {
                "heading": "Règle de secours",
                "body": "Lorsque les 8 voisins du dernier coup sont tous occupés, les coups légaux sont "
                "toutes les cases vides adjacentes à au moins un pion adverse. Ce cas est rare en milieu "
                "de partie mais important en finale.",
            },
            {
                "heading": "Conséquence tactique",
                "body": "La frontière se déplace à chaque coup : contrôler le centre au début, puis guider "
                "l'adversaire vers des zones où ses réponses restent limitées.",
            },
        ],
    },
    {
        "id": "menaces",
        "title": "Menaces et blocages",
        "level": "intermédiaire",
        "duration_min": 6,
        "sections": [
            {
                "heading": "Menace ouverte",
                "body": "Une **menace** est une ligne de **3 pions alignés** avec au moins une extrémité libre "
                "sur laquelle un 4ᵉ pion terminerait la partie. Le moteur Minimax compte ces menaces dans "
                "chaque direction (horizontal, vertical, diagonale) — c'est la base de la recherche tactique.",
            },
            {
                "heading": "Blocage obligatoire",
                "body": "Si l'adversaire peut gagner au prochain coup, vous **devez** jouer sur la case qui "
                "bloque son alignement. Le moteur classe ce coup en priorité juste après une victoire immédiate "
                "(win > block > menace). Ignorer un blocage coûte la partie.",
            },
            {
                "heading": "Exemple sur 7×7",
                "body": "Rouge a trois pions en (3,2)-(3,3)-(3,4) et la case (3,5) est libre : c'est une menace "
                "horizontale. Bleu doit jouer en (3,5) s'il peut légalement (case sur la frontière du dernier coup). "
                "Si (3,5) n'est pas jouable, cherchez une autre menace adverse à bloquer ou créez la vôtre.",
            },
            {
                "heading": "Menace et frontière",
                "body": "La règle du **dernier coup** peut empêcher un blocage évident : une case critique peut "
                "être hors frontière. Avant de construire une menace, vérifiez que l'adversaire pourra répondre "
                "sur la case de blocage au tour suivant — sinon votre menace est plus forte qu'il n'y paraît.",
            },
            {
                "heading": "Ordre des priorités",
                "body": "Comme dans le Minimax du projet : 1) gagner tout de suite, 2) bloquer une victoire adverse, "
                "3) créer une menace (3 alignés ouverts), 4) améliorer vos fenêtres de 4. Entraînez-vous à scanner "
                "le plateau dans cet ordre à chaque coup.",
            },
        ],
    },
    {
        "id": "fenetres",
        "title": "Fenêtres de 4",
        "level": "intermédiaire",
        "duration_min": 7,
        "sections": [
            {
                "heading": "Définition",
                "body": "Sur un plateau 7×7, une **fenêtre de 4** est tout segment de **4 cases consécutives** "
                "en ligne droite (horizontal, vertical ou diagonal). Il y en a 68 au total — le moteur les "
                "pré-calcule pour évaluer chaque position.",
            },
            {
                "heading": "Poids heuristiques",
                "body": "Le Minimax attribue un score selon le nombre de vos pions dans une fenêtre propre : "
                "1 pion → 1, 2 pions → 10, 3 pions → 100, 4 pions → victoire (10 000). Plus vous remplissez "
                "une fenêtre sans l'adversaire, plus la position est favorable.",
            },
            {
                "heading": "Fenêtres polluées",
                "body": "Si une fenêtre contient des pions des **deux** joueurs, elle est ignorée : les lignes "
                "se bloquent mutuellement. Évitez de poser au milieu d'une ligne adverse ; préférez prolonger "
                "vos propres fenêtres ou couper celles de l'adversaire tôt.",
            },
            {
                "heading": "Exemple concret",
                "body": "Rouge occupe (2,2) et (2,3) sur la ligne horizontale de la rangée 2, cases (2,1) à (2,4) "
                "libres : cette fenêtre vaut 10 points. Si Bleu joue en (2,4), la fenêtre est polluée et ne "
                "compte plus pour personne — un bon blocage préventif.",
            },
            {
                "heading": "Lien avec les menaces",
                "body": "Une fenêtre à 3 pions propres correspond à une menace ouverte (score 100). L'évaluation "
                "des fenêtres guide le moteur en milieu de partie quand aucune victoire ou blocage immédiat "
                "n'est disponible.",
            },
        ],
    },
    {
        "id": "double-menace",
        "title": "Menaces doubles",
        "level": "avancé",
        "duration_min": 8,
        "sections": [
            {
                "heading": "Principe",
                "body": "Une **menace double** survient quand vous créez **deux lignes de 3** (ou plus) que "
                "l'adversaire ne peut pas bloquer en un seul coup. Au 4mation, un seul pion par tour suffit "
                "rarement à parer deux alignements simultanés — la partie est souvent gagnée.",
            },
            {
                "heading": "Exemple classique",
                "body": "Imaginez Rouge avec deux lignes de 3 qui se croisent : horizontale (3,1)-(3,2)-(3,3) "
                "et verticale (1,3)-(2,3)-(3,3), extrémités libres en (3,0), (3,4), (0,3) et (4,3). "
                "Bleu ne peut bloquer qu'une extrémité ; Rouge complète l'autre et gagne.",
            },
            {
                "heading": "Frontière et timing",
                "body": "Construire une double menace demande plusieurs coups. Anticipez où sera la frontière "
                "après chaque réponse adverse : une menace « fantôme » sur une case non jouable ne force rien. "
                "Guidez la partie pour que vos deux lignes deviennent bloquables au même moment.",
            },
            {
                "heading": "Créer la fourchette",
                "body": "Cherchez les coups qui **augmentent deux fenêtres à la fois** (pion au carrefour de "
                "lignes). Le centre (3,3) et ses voisins sont des cases pivot : un pion en (3,3) peut "
                "participer à quatre directions différentes.",
            },
            {
                "heading": "Recherche de quiescence",
                "body": "Le Minimax prolonge la recherche tant qu'il détecte des menaces (quiescence search) "
                "pour ne pas sous-estimer une double menace en cours de maturation. Si vous voyez une position "
                "« instable », calculez un coup de plus — la tactique peut exploser.",
            },
        ],
    },
    {
        "id": "ouvertures-principes",
        "title": "Principes d'ouverture",
        "level": "intermédiaire",
        "duration_min": 6,
        "sections": [
            {
                "heading": "Occuper le centre",
                "body": "Le premier coup en **(3,3)** (ou voisin immédiat) maximise les fenêtres de 4 accessibles "
                "et la mobilité future. L'explorateur d'ouvertures du dashboard compare les taux de victoire "
                "selon les premières séquences — le centre domine statistiquement.",
            },
            {
                "heading": "Suivre la frontière dès le coup 2",
                "body": "Dès la réponse adverse, vos coups sont contraints par le **dernier coup joué**. "
                "Choisissez des cases qui gardent plusieurs voisins libres pour ne pas vous enfermer "
                "dans un coin du plateau.",
            },
            {
                "heading": "Développement harmonieux",
                "body": "Évitez les coups isolés sur le bord (rangée 0 ou 6) en début de partie : moins de "
                "fenêtres, moins de menaces potentielles. Reliez vos pions pour former des structures "
                "qui peuvent évoluer vers 2 puis 3 alignés.",
            },
            {
                "heading": "Ne pas offrir de tempo",
                "body": "Un coup passif laisse l'adversaire imposer la frontière. Si vous devez répondre près "
                "de son dernier pion, cherchez un coup qui **bloque** sa fenêtre en cours tout en "
                "développant la vôtre — deux effets en un.",
            },
            {
                "heading": "Préparer le milieu de partie",
                "body": "L'ouverture se termine quand les menaces directes apparaissent. D'ici là, visez "
                "3 objectifs : centre contrôlé, fenêtres propres non polluées, et mobilité supérieure "
                "à l'adversaire sur la frontière actuelle.",
            },
        ],
    },
    {
        "id": "mobilite",
        "title": "Mobilité et frontier",
        "level": "avancé",
        "duration_min": 7,
        "sections": [
            {
                "heading": "Mobilité = coups légaux",
                "body": "La **mobilité** est le nombre de cases où vous pouvez jouer légalement. Au 4mation, "
                "elle dépend entièrement de la **frontière** (voisins du dernier coup, ou règle de secours). "
                "Plus vous avez d'options, plus vous gardez l'initiative.",
            },
            {
                "heading": "Évaluation du moteur",
                "body": "Le Minimax pénalise les positions où l'adversaire a beaucoup de coups légaux "
                "(malus −0,1 par coup adverse) et récompense légèrement vos propres options (+0,05). "
                "Réduire la mobilité adverse est un plan de jeu valide, surtout en finale.",
            },
            {
                "heading": "Enfermer la frontière",
                "body": "Si les 8 voisins du dernier coup sont occupés, la règle de secours active : seules "
                "les cases vides **adjacentes à un pion adverse** sont jouables. Vous pouvez guider la "
                "partie vers cette configuration pour limiter drastiquement les réponses adverses.",
            },
            {
                "heading": "Exemple sur 7×7",
                "body": "Bleu vient de jouer en (3,4). Si les cases (2,3) à (4,5) autour sont déjà pleines, "
                "le rouge ne pourra jouer que sur les cases vides touchant un pion bleu — souvent 1 ou 2 "
                "choix au lieu de 8. C'est un gain stratégique même sans menace immédiate.",
            },
            {
                "heading": "Mobilité vs menaces",
                "body": "Ne sacrifiez pas une menace gagnante pour la mobilité. Mais à score égal tactique, "
                "préférez le coup qui laisse l'adversaire le moins de cases valides au tour suivant — "
                "le coach MCTS valorise souvent ces coups dans ses pourcentages.",
            },
        ],
    },
    {
        "id": "finales",
        "title": "Finales parfaites",
        "level": "expert",
        "duration_min": 9,
        "sections": [
            {
                "heading": "Positions résolues",
                "body": "En finale, quand peu de cases restent libres, le moteur peut consulter une **table de "
                "finales** (tablebase) qui connaît le résultat exact de la position : victoire, défaite ou nul "
                "avec la séquence optimale. Le coach affiche alors des pourcentages **exacts**.",
            },
            {
                "heading": "Frontière en finale",
                "body": "La contrainte du dernier coup est maximale en finale : chaque coup réduit le plateau "
                "et resserre la frontière. La règle de secours (jouer près d'un pion adverse) devient "
                "fréquente — maîtrisez-la pour ne pas perdre sur une case illégale.",
            },
            {
                "heading": "Technique du zugzwang",
                "body": "Forcer l'adversaire à jouer sur la frontière où **tous** ses coups aggravent sa position "
                "est l'équivalent du zugzwang. Réduisez sa mobilité tout en maintenant une menace latente "
                "sur une fenêtre de 4 encore jouable.",
            },
            {
                "heading": "Alignement forcé",
                "body": "Si vous avez une menace double ou une menace que l'adversaire ne peut bloquer qu'en "
                "s'éloignant de sa meilleure défense, la tablebase confirme le gain forcé. Entraînez-vous "
                "sur les puzzles du pack (3 à 8 coups) pour reconnaître ces motifs.",
            },
            {
                "heading": "Passer du MCTS à l'exact",
                "body": "Tant que la position n'est pas en tablebase, le coach utilise le MCTS (estimations). "
                "Quand la base couvre la position, le label passe à « exact ». En finale, faites confiance "
                "aux 100 % / 0 % — ils reflètent une résolution complète, pas une intuition.",
            },
        ],
    },
    {
        "id": "lire-coach",
        "title": "Lire le coach",
        "level": "tous",
        "duration_min": 5,
        "sections": [
            {
                "heading": "Mode apprentissage",
                "body": "Dans l'**entraîneur** (mode apprentissage), vous jouez les rouges contre le **coach** "
                "bleu. Après chaque coup, le moteur analyse la position et affiche des indices sur le plateau "
                "— pas de surprise : c'est un outil pédagogique, pas une partie classée.",
            },
            {
                "heading": "Pourcentages par case",
                "body": "Chaque case **jouable** affiche un taux de victoire estimé si vous y jouez (du point "
                "de vue des rouges). Vert = favorable, rouge = défavorable. Ces chiffres viennent du MCTS "
                "(simulations) ou de la tablebase si la position est résolue.",
            },
            {
                "heading": "Meilleur coup suggéré",
                "body": "Le coup recommandé apparaît en **pointillés dorés** sur le plateau. Il correspond au "
                "`best_move` de l'analyse — victoire immédiate, blocage, ou meilleure continuation heuristique. "
                "Comparez votre choix au sien après avoir réfléchi.",
            },
            {
                "heading": "Barre de probabilité",
                "body": "La barre en bas indique la probabilité de victoire globale des rouges dans la position "
                "actuelle. Elle se met à jour après chaque coup. Un 50 % signifie position équilibrée ; "
                "au-delà de 70 %, vous avez un avantage net.",
            },
            {
                "heading": "Exact vs estimé",
                "body": "Le label « Estimé (MCTS) » signifie que le calcul est approché (simulations limitées). "
                "« Exact » (tablebase) signifie que le résultat est mathématiquement connu. En début de partie "
                "sur 7×7, l'estimation est la norme ; en finale, l'exact prend le relais.",
            },
        ],
    },
]


@learn_bp.route("/api/learn/openings/explore", methods=["POST"])
def api_openings_explore():
    """Explore une ligne d'ouverture à partir d'une séquence de coups."""
    data = request.get_json(silent=True) or {}
    raw_moves = data.get("moves") or []
    moves = []
    for m in raw_moves:
        if isinstance(m, dict):
            moves.append((int(m["row"]), int(m["col"])))
        elif isinstance(m, (list, tuple)) and len(m) == 2:
            moves.append((int(m[0]), int(m[1])))
    return jsonify({"success": True, **explore_opening(moves)})


@learn_bp.route("/api/learn/puzzles", methods=["GET"])
def api_puzzles_list():
    """Liste des puzzles du pack (30 victoires forcées)."""
    puzzles = list_pack_puzzles()
    if not puzzles:
        return jsonify({"success": False, "error": "Pack de puzzles indisponible"}), 503
    return jsonify({"success": True, "puzzles": puzzles})


@learn_bp.route("/api/learn/puzzles/<puzzle_id>", methods=["GET"])
def api_puzzle_detail(puzzle_id: str):
    """Détail d'un puzzle (sans la ligne solution)."""
    puzzle = get_pack_puzzle(puzzle_id)
    if puzzle is None:
        return jsonify({"success": False, "error": "Puzzle introuvable"}), 404
    return jsonify({"success": True, "puzzle": puzzle})


@learn_bp.route("/api/learn/puzzles/random", methods=["GET"])
def api_puzzle_random():
    """Puzzle tactique aléatoire."""
    puzzle = random_puzzle()
    if puzzle is None:
        return jsonify({"success": False, "error": "Aucun puzzle trouvé"}), 503
    return jsonify({"success": True, "puzzle": puzzle})


@learn_bp.route("/api/learn/puzzles/check", methods=["POST"])
def api_puzzle_check():
    """Vérifie un coup de puzzle (pack multi-coups ou tactique 1 coup)."""
    data = request.get_json(silent=True) or {}
    history = data.get("history") or []
    move = data.get("move") or {}
    if "row" not in move or "col" not in move:
        return jsonify({"success": False, "error": "Coup manquant"}), 400

    puzzle_id = data.get("puzzle_id")
    if puzzle_id:
        result = check_pack_puzzle_move(
            str(puzzle_id),
            history,
            int(move["row"]),
            int(move["col"]),
        )
        return jsonify({"success": True, **result})

    player = int(data.get("player_to_move", 1))
    result = check_puzzle_solution(history, player, int(move["row"]), int(move["col"]))
    return jsonify({"success": True, **result})


@learn_bp.route("/api/learn/lessons", methods=["GET"])
def api_lessons():
    """Liste des leçons disponibles."""
    return jsonify({"success": True, "lessons": LESSONS})


@learn_bp.route("/api/learn/lessons/<lesson_id>", methods=["GET"])
def api_lesson_detail(lesson_id: str):
    """Contenu d'une leçon."""
    for lesson in LESSONS:
        if lesson["id"] == lesson_id:
            return jsonify({"success": True, "lesson": lesson})
    return jsonify({"success": False, "error": "Leçon introuvable"}), 404
