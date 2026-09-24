"""Routes section Apprendre : ouvertures, puzzles, leçons."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

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
        "title": "Ouvertures : ce que dit le moteur",
        "level": "intermédiaire",
        "duration_min": 8,
        "sections": [
            {
                "heading": "Le premier coup est le seul coup libre",
                "body": "Plateau vide : vous posez où vous voulez, sur les 49 cases. C'est la seule fois de la "
                "partie. À partir du deuxième coup, tout est contraint par la **frontière** du dernier coup "
                "joué. Le premier coup fixe donc l'endroit du plateau où va se dérouler la partie — d'où son "
                "importance.",
            },
            {
                "heading": "Le classement des 10 premiers coups",
                "body": "Sur les 49 cases, il n'y a que **10 premiers coups réellement différents** : les 39 "
                "autres sont des rotations ou des symétries. Voici le classement du moteur, score du joueur 1 "
                "(profondeur 14) : **(3,3) centre +29**, (2,3) +8, (1,3) +2, (2,2) 0, (1,2) −5, (1,1) −7, "
                "(0,3) −9, (0,0) −12, (0,1) −16, (0,2) −17. Tout est dit : le centre domine, les bords coûtent.",
            },
            {
                "heading": "Ce que valent ces chiffres",
                "body": "Le moteur estime le premier coup central à environ **68 % de victoire pour le premier "
                "joueur**, et une ouverture sur le bord à moins de 40 %. Ce sont des **estimations** issues de "
                "la recherche et d'une échelle calibrée sur les finales exactes — pas des preuves. Ce qui est "
                "prouvé, en revanche, c'est qu'aucune victoire forcée de blanc n'existe dans les 19 premiers "
                "demi-coups depuis le centre : le gain, s'il existe, est long.",
            },
            {
                "heading": "Une case décalée n'est pas la même ouverture",
                "body": "Attention à ne pas confondre **symétrie** et **translation**. (3,3) et (2,2) sont deux "
                "ouvertures distinctes : le bord change toute la suite de la partie. Une ouverture décalée d'une "
                "case vers le bord n'a ni les mêmes continuations ni la même évaluation — d'où les écarts de "
                "score ci-dessus.",
            },
            {
                "heading": "Comment utiliser l'explorateur",
                "body": "L'**explorateur d'ouvertures** du site rejoue une séquence et affiche, pour chaque "
                "continuation, le taux de victoire estimé par le moteur. Servez-vous-en pour comparer deux "
                "coups qui vous semblent équivalents : l'écart de pourcentage est la réponse, et l'étiquette "
                "vous dit s'il s'agit d'une estimation ou d'une valeur prouvée.",
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
                "heading": "Menace réelle, menace fantôme",
                "body": "Une **menace** est une ligne de **3 pions alignés** dont la case de complétion est "
                "**jouable maintenant**, c'est-à-dire sur la frontière du dernier coup. C'est la définition "
                "exacte utilisée par le moteur : il compte les cases de la frontière actuelle qui termineraient "
                "la partie. Trois pions alignés dont la quatrième case n'est pas jouable ne sont **pas** une "
                "menace — au coup suivant elle peut avoir disparu.",
            },
            {
                "heading": "Blocage obligatoire",
                "body": "Si l'adversaire a une menace réelle, vous **devez** jouer sur la case qui complète son "
                "alignement, et elle doit être jouable pour vous. Le moteur ne s'y trompe pas : une menace "
                "immédiate vaut 60 points d'évaluation, tandis que trois pions alignés sans case de complétion "
                "jouable n'en valent que 14. C'est le rapport qui commande tout le jeu tactique.",
            },
            {
                "heading": "Exemple sur 7×7",
                "body": "Rouge a trois pions en (3,2)-(3,3)-(3,4) et la case (3,5) est libre. La menace n'est "
                "réelle que si (3,5) figure dans vos coups légaux : elle doit toucher le dernier coup joué. "
                "Si (3,5) est hors frontière, vous jouez ailleurs en toute sécurité — et si vous jouez un coup "
                "qui éloigne la frontière de (3,5), la menace est définitivement éteinte.",
            },
            {
                "heading": "Deux menaces ne se bloquent pas",
                "body": "Le cas décisif est la **menace double** : deux cases de complétion jouables d'un seul "
                "coup. L'adversaire ne peut en bloquer qu'une, et le moteur le voit immédiatement car il compte "
                "les deux (2 × 60 points). La plupart des parties gagnées le sont par deux menaces simultanées, "
                "pas par une seule.",
            },
            {
                "heading": "Ordre des priorités",
                "body": "Scanner le plateau dans cet ordre, à chaque coup : 1) puis-je gagner tout de suite ? "
                "2) l'adversaire peut-il gagner au prochain coup (menace réelle à bloquer) ? 3) puis-je créer "
                "une menace réelle, si possible double ? 4) sinon, améliorer mes lignes et ma centralité. "
                "Cet ordre est exactement celui que suit le moteur.",
            },
        ],
    },
    {
        "id": "menaces-fantomes",
        "title": "La leçon n°1 : les menaces fantômes",
        "level": "intermédiaire",
        "duration_min": 6,
        "sections": [
            {
                "heading": "Le point que tout le monde rate",
                "body": "C'est la découverte la plus importante faite en construisant le moteur : **un alignement "
                "de trois pions ne sert à rien si la case qui le complète n'est pas adjacente au dernier coup "
                "joué**. Le plateau est vivant, la frontière se déplace à chaque coup, et une menace qui n'est "
                "pas jouable maintenant s'éteint presque toujours d'elle-même.",
            },
            {
                "heading": "Pourquoi",
                "body": "Après chaque coup, on ne peut jouer que sur les 8 voisins du dernier pion posé. "
                "Donc pour compléter votre ligne au coup suivant, la case de complétion doit être voisine du "
                "pion que **l'adversaire** va poser — et vous ne choisissez pas son coup. S'il joue à l'opposé, "
                "votre case de complétion sort de la frontière et vos trois pions deviennent inertes.",
            },
            {
                "heading": "Conséquence pratique",
                "body": "Avant de compter sur une menace, vérifiez trois choses : la case de complétion est-elle "
                "**jouable maintenant** ? Si oui, l'adversaire est obligé de la bloquer. Sinon, elle ne force rien "
                "et vous venez probablement de perdre un temps. L'adversaire, lui, peut « s'éloigner » : jouer "
                "un coup calme à distance pour éteindre la menace sans dépenser un blocage.",
            },
            {
                "heading": "Le retournement",
                "body": "Cette règle explique aussi pourquoi les parties durent : aucune victoire forcée "
                "n'apparaît dans les premières vingtaines de demi-coups, car chaque tentative de menaces "
                "peut être neutralisée par un coup à distance. Elle donne le plan de jeu défensif de référence : "
                "face à un alignement de trois, demandez-vous si la case de complétion est jouable **pour "
                "l'adversaire au prochain tour** — si non, jouez ailleurs.",
            },
            {
                "heading": "Comment s'entraîner",
                "body": "Ouvrez l'entraîneur et regardez les pourcentages affichés par le moteur : les cases "
                "qui font chuter le taux adverse sont presque toujours celles qui **créent** une menace réelle "
                "ou qui **éteignent** celle de l'adversaire. Comparez avec votre coup : l'écart est la leçon.",
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
                "heading": "Poids heuristiques du moteur",
                "body": "Le moteur note une position avec trois termes : les **menaces réelles** (une case "
                "jouable qui complète un 4) valent **60 points** chacune, les **lignes** valent 14 points par "
                "trois alignés et 2 points par paire, et la **centralité** compte 3 fois la valeur de la case "
                "(6 au centre contre 0 dans un coin). Un simple trois alignés sans case jouable pèse donc "
                "quatre fois moins qu'une menace réelle.",
            },
            {
                "heading": "Fenêtres polluées",
                "body": "Si une fenêtre contient des pions des **deux** joueurs, elle est ignorée : les lignes "
                "se bloquent mutuellement. Évitez de poser au milieu d'une ligne adverse ; préférez prolonger "
                "vos propres fenêtres ou couper celles de l'adversaire tôt.",
            },
            {
                "heading": "Exemple concret",
                "body": "Rouge occupe (2,2) et (2,3) : la paire vaut 2 points par fenêtre. Si Bleu joue en (2,4), "
                "la fenêtre est polluée et ne compte plus pour personne — un bon blocage préventif, mais qui "
                "coûte un tempo : le moteur ne le joue que si le gain de la pollution dépasse le coup perdu.",
            },
            {
                "heading": "Centre et bords",
                "body": "La valeur d'une case suit sa distance au centre : (3,3) vaut 6, une case du bord "
                "milieu vaut 3, un coin vaut 0. Puisque la centralité est multipliée par 3, un pion central "
                "rapporte 18 points — autant qu'un trois alignés complet. C'est mesurable, et cela explique "
                "pourquoi le premier coup au centre est le meilleur du jeu.",
            },
            {
                "heading": "Lien avec les menaces",
                "body": "Une fenêtre à 3 pions propres ne vaut 14 points que si la quatrième case n'est pas "
                "jouable ; dès qu'elle l'est, la même ligne vaut 60. Tout l'enjeu du milieu de partie est "
                "de faire coïncider vos trois pions avec la frontière du dernier coup — pour vous comme pour "
                "l'adversaire.",
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
                "body": "Une **menace double** survient quand vous avez **deux cases de complétion jouables** "
                "(ou plus) au même tour : deux lignes de 3 dont les quatrièmes cases sont toutes deux sur la "
                "frontière. L'adversaire ne peut en bloquer qu'une seule — la partie est gagnée. C'est le seul "
                "motif qui produit des victoires forcées à court terme.",
            },
            {
                "heading": "Exemple classique",
                "body": "Rouge avec deux lignes de 3 qui se croisent : horizontale (3,1)-(3,2)-(3,3) et "
                "verticale (1,3)-(2,3)-(3,3), extrémités libres en (3,0), (3,4), (0,3) et (4,3). Encore "
                "faut-il que **deux** de ces extrémités soient jouables au même moment : c'est la frontière, "
                "pas le dessin des pions, qui décide.",
            },
            {
                "heading": "Frontière et timing",
                "body": "Construire une double menace demande plusieurs coups. Anticipez où sera la frontière "
                "après chaque réponse adverse : une menace « fantôme » sur une case non jouable ne force rien. "
                "Guidez la partie pour que **vos deux lignes** deviennent jouables au même coup, et non l'une "
                "après l'autre.",
            },
            {
                "heading": "Créer la fourchette",
                "body": "Cherchez les coups qui **augmentent deux fenêtres à la fois** (pion au carrefour de "
                "lignes). Le centre (3,3) et ses voisins sont des cases pivot : un pion en (3,3) peut "
                "participer à quatre directions différentes.",
            },
            {
                "heading": "Comment le moteur la voit",
                "body": "L'évaluation compte simplement les cases de la frontière qui terminent un 4 : deux "
                "menaces valent 120 points, soit plus du double de tout ce qu'une position peut rapporter par "
                "ailleurs. C'est aussi pour cela que le moteur ordonne ses coups en essayant d'abord les "
                "victoires immédiates, puis les blocages, puis la création de menaces.",
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
                "heading": "Répondre au premier coup",
                "body": "Le deuxième coup est déjà contraint : il doit toucher le premier pion. Votre réponse "
                "choisit donc la direction de la partie. Répondez en restant proche du centre quand c'est "
                "possible, et évitez de pousser la partie vers un coin : la frontière s'y referme et vous "
                "perdez des options avant même la première menace.",
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
        "title": "Mobilité et frontière",
        "level": "avancé",
        "duration_min": 7,
        "sections": [
            {
                "heading": "Mobilité = coups légaux",
                "body": "La **mobilité** est le nombre de cases où l'on peut jouer légalement. Au 4mation, "
                "elle dépend entièrement de la **frontière** (voisins du dernier coup, ou règle de secours). "
                "Plus la frontière est large, plus il y a de cases de complétion possibles — pour vous comme "
                "pour l'adversaire.",
            },
            {
                "heading": "Ce que le moteur évalue vraiment",
                "body": "Le moteur ne note pas la mobilité en tant que telle : il note les **menaces réelles** "
                "(60 points), les lignes (14 et 2 points) et la centralité (×3). Mais la mobilité agit sur les "
                "menaces : une case de complétion n'est une menace que si elle est sur la frontière. Réduire "
                "la mobilité adverse est donc un moyen, pas une fin — la fin, c'est de rendre vos lignes "
                "jouables et les siennes inertes.",
            },
            {
                "heading": "Enfermer la frontière",
                "body": "Si les 8 voisins du dernier coup sont occupés, la règle de secours active : seules "
                "les cases vides **adjacentes à un pion adverse** sont jouables. Vous pouvez guider la "
                "partie vers cette configuration pour limiter drastiquement les réponses adverses — et donc "
                "le nombre de menaces qu'il peut créer.",
            },
            {
                "heading": "Exemple sur 7×7",
                "body": "Bleu vient de jouer en (3,4). Si les cases (2,3) à (4,5) autour sont déjà pleines, "
                "le rouge ne pourra jouer que sur les cases vides touchant un pion bleu — souvent 1 ou 2 "
                "choix au lieu de 8. Attention : cette configuration peut aussi **armer** l'adversaire, "
                "puisque ses cases restantes touchent vos pions.",
            },
            {
                "heading": "Mobilité vs menaces",
                "body": "Ne sacrifiez jamais une menace réelle pour la mobilité : une menace vaut 60 points, "
                "la mobilité n'est pas comptée. À score égal, préférez le coup qui laisse le moins de "
                "**completions jouables** à l'adversaire au tour suivant — c'est cela que regarde le moteur "
                "à la profondeur suivante, et c'est ce que les pourcentages du coach traduisent.",
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
                "body": "Quand peu de cases restent libres, la position peut être **résolue** : le résultat est "
                "connu (victoire, défaite ou nulle) avec la séquence optimale, sans aucune estimation. La base "
                "de finales du site couvre exactement toutes les positions jusqu'à **7 cases vides** ; au-delà, "
                "la couverture est partielle. Quand la position est résolue, le coach affiche des pourcentages "
                "**exacts** — 100 %, 50 % ou 0 % — et le meilleur coup n'est pas une opinion.",
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
                "heading": "Estimation ou preuve : lire l'étiquette",
                "body": "En finale, deux étiquettes coexistent. « **Exact (tablebase)** » signifie que le "
                "résultat est mathématiquement connu : faites-y confiance, les 100 % et 0 % sont définitifs. "
                "« **Estimation (moteur, profondeur N)** » signifie que le moteur a calculé N demi-coups et "
                "propose un pourcentage : c'est solide, mais ce n'est pas une preuve. Un « **Mat forcé en N "
                "coup(s)** » est une preuve trouvée par le moteur : c'est le cas le plus net.",
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
                "de vue des rouges). Vert = favorable, rouge = défavorable. Ces chiffres viennent du moteur "
                "d'analyse : c'est la lecture de son évaluation sur une échelle **calibrée sur les finales "
                "exactes**, pas des simulations approximatives.",
            },
            {
                "heading": "Meilleur coup suggéré",
                "body": "Le coup recommandé apparaît en **pointillés dorés** sur le plateau. Il correspond au "
                "`best_move` de l'analyse — victoire immédiate, blocage, ou meilleure continuation. "
                "Comparez votre choix au sien après avoir réfléchi.",
            },
            {
                "heading": "Barre de probabilité",
                "body": "La barre en bas indique la probabilité de victoire globale des rouges dans la position "
                "actuelle. Elle se met à jour après chaque coup. Un 50 % signifie position équilibrée ; "
                "au-delà de 70 %, vous avez un avantage net. En dessous de 30 %, cherchez d'abord la défense.",
            },
            {
                "heading": "Exact vs estimé",
                "body": "Trois étiquettes à distinguer. « **Exact (tablebase)** » ou « **Mat forcé en N coup(s)** » : "
                "le résultat est prouvé, les pourcentages sont définitifs. « **Estimation (moteur, profondeur N)** » : "
                "le moteur a cherché N demi-coups, le pourcentage est une estimation calibrée — fiable, mais "
                "révisable. « **recherche interrompue** » : le budget temps a été atteint, la profondeur "
                "atteinte est plus faible. En début de partie sur 7×7, l'estimation est la norme ; en finale, "
                "l'exact prend le relais.",
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


def _load_generated_lessons() -> Dict[str, Dict[str, Any]]:
    """Leçons regénérées depuis le solveur, indexées par identifiant.

    `script/solver/build_lessons.py` écrit ce fichier en relisant les artefacts de
    résolution (sonde profonde, preuve du centre, vérifications de schémas, finales
    exactes). Il est **versionné** (`api/content/`) : sinon le site déployé servirait
    les anciennes leçons. Le fichier reste optionnel : sans lui, le site sert les
    leçons écrites à la main.
    """
    path = Path(__file__).resolve().parent.parent / "content" / "lessons_engine.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    lessons = payload.get("lessons")
    if not isinstance(lessons, list):
        return {}
    return {
        lesson["id"]: lesson
        for lesson in lessons
        if isinstance(lesson, dict) and isinstance(lesson.get("id"), str)
    }


def all_lessons() -> List[Dict[str, Any]]:
    """Leçons servies par l'API : les regénérées remplacent celles écrites à la main."""
    generated = _load_generated_lessons()
    merged: List[Dict[str, Any]] = []
    replaced: set = set()
    for lesson in LESSONS:
        replacement = generated.get(lesson["id"])
        if replacement:
            merged.append(replacement)
            replaced.add(lesson["id"])
        else:
            merged.append(lesson)
    for lesson_id, lesson in generated.items():
        if lesson_id not in replaced:
            merged.append(lesson)
    return merged


@learn_bp.route("/api/learn/lessons", methods=["GET"])
def api_lessons():
    """Liste des leçons disponibles."""
    return jsonify({"success": True, "lessons": all_lessons()})


@learn_bp.route("/api/learn/lessons/<lesson_id>", methods=["GET"])
def api_lesson_detail(lesson_id: str):
    """Contenu d'une leçon."""
    for lesson in all_lessons():
        if lesson["id"] == lesson_id:
            return jsonify({"success": True, "lesson": lesson})
    return jsonify({"success": False, "error": "Leçon introuvable"}), 404
