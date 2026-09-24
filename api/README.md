# API 4mation

API Flask pour les parties, bots, analyse MCTS et comptes joueurs (phase 2).

## Lancement local

```bash
cd 4mation
set PYTHONPATH=.
pip install -r api/requirements.txt
python api/app.py
```

Variables utiles : voir `api/.env.example` (`DATABASE_URL`, `LAB211_*`, chemins DB).

## Production

```bash
export PYTHONPATH=.:script
export DATABASE_URL=postgresql://...
gunicorn -c api/gunicorn_config.py api.app:app
```

Sur le VPS : `deploy/docker-compose.vps.yml` inclut PostgreSQL 16 + l'API.

## Authentification (Lab211)

Les routes `/api/me/*` exigent une session SSO Lab211 (cookie `.lab211.fr`).
L'API relaie le cookie du navigateur vers `GET /api/auth/session?site_key=4mation`.

Le jeu vs bots reste jouable **sans connexion** ; la sauvegarde et l'Elo ne s'appliquent
qu'aux utilisateurs connectés en **mode classique**.

## Endpoints compte (phase 2)

| Méthode | Route | Description |
|---------|-------|-------------|
| GET | `/api/me` | Profil + Elo + 10 dernières parties |
| GET | `/api/me/games?limit=&offset=` | Historique paginé |
| GET | `/api/me/games/<uuid>/review` | Game Review (précision, coups classifiés, graphe) |

## Endpoints jeu (rappel)

- `POST /api/session` — body `{ mode, bot_id? }`
- `POST /api/reset` — body `{ mode, bot_id? }`
- `POST /api/move` / `POST /api/ai_move` — renvoie `saved_game` si partie finie + connecté
- `GET /api/health` — inclut l'état PostgreSQL

## Elo (vs bots)

6 niveaux (`level_1` … `level_6`). Elo de référence bot : 800 → 2000.
K-factor 32. Mise à jour automatique à la fin de chaque partie classique enregistrée.

## Moteur Rust (`4mation-engine`)

Le moteur Rust du dépôt (recherche alpha-bêta, table de transposition, finales exactes
lues dans la tablebase) sert à deux choses : le bot de **niveau 6** et **toute
l'analyse du site**. Il parle un protocole « une requête JSON par ligne » sur
stdin/stdout et conserve sa table de transposition entre les requêtes :
`api/services/engine_client.py` le garde donc dans un **processus persistant**, partagé
par les requêtes d'un même worker.

Le service est tolérant à l'absence du binaire : si `4mation-engine` n'est pas compilé
(cas d'un serveur qui ne l'a pas), `is_available()` renvoie `False`, le niveau 6
retombe sur le chemin Minimax/tablebase du niveau 5 et l'analyse sur l'ancien chemin
(livre d'ouverture puis MCTS). Le moteur ne peut pas rendre le site indisponible.

Compilation :

```bash
cd script/solver_rust && cargo build --release
```

### Analyse : où le moteur intervient

`TablebaseLookup.analyze_position` est le point d'entrée unique du coach, de la revue de
partie, des puzzles et de l'explorateur d'ouvertures. L'ordre de confiance est :

1. **valeur prouvée** — lecture de la tablebase pour les finales (≤ 12 cases vides) ou
   entrée `exact=1` du livre d'ouverture ;
2. **moteur** — tout le reste : ouvertures estimées et milieu de partie. C'est le cas
   courant de très loin ;
3. **replis historiques** (remontée des enfants du livre, MCTS) uniquement si le moteur
   est absent.

Chaque résultat porte son degré de confiance, que l'interface doit montrer :

| Champ | Sens |
|-------|------|
| `source` | `engine`, `opening_book` ou `tablebase` |
| `exact` | `true` = valeur **prouvée** (mat forcé ou tablebase) ; `false` = estimation |
| `label` | texte prêt à afficher (« Mat forcé en 3 coup(s) », « Estimation (moteur, profondeur 12) ») |
| `coverage_percent` | part des coups légaux effectivement notés |
| `truncated` | `true` = recherche arrêtée au temps imparti (les scores viennent de la dernière profondeur terminée) |

### Jouer : la preuve passe avant la recherche

Même ordre de confiance pour le choix des coups des bots (`DifficultyBot.choose_move`) :
une position **prouvée** (tablebase exacte, ou entrée de livre `exact=1`) se joue
directement, sans lancer le moteur (`choose_move(..., require_exact=True)`). Le moteur
n'intervient qu'ensuite, puis les estimations du livre en dernier recours.

Conséquence mesurable : le `level_6` joue `(3,3)` en 11 ms au lieu de 2,5 s de recherche, et
rejoue la ligne prouvée du centre (29 demi-coups) sans un seul écart, à ~4 ms le coup. Une
preuve ne se discute pas : aucune recherche ne fera mieux, et cela garantit que le bot ne
joue jamais un coup gagnant plus lent qu'un autre.

### Score → taux de victoire

Le score du moteur n'est pas un taux de victoire : son unité est la *menace immédiate*
(une menace vaut 60 points, une ligne potentielle 1, le centre 3). La conversion est une
sigmoïde `1 / (1 + exp(-score / échelle))`, dont l'échelle est **mesurée**, pas devinée :

```bash
python script/solver/calibrate_engine_scale.py --samples 150 --depth 8
```

Le script tire des finales dont la tablebase connaît le résultat exact, demande au
moteur son score **sans tablebase**, et ajuste l'échelle minimisant l'erreur de Brier.
Il écrit `script/solver/data/engine_scale.json`, lu par l'API et par le constructeur du
livre d'ouverture (une même échelle partout, sinon les taux de victoire ne veulent plus
rien dire d'une couche à l'autre). Mesure du 24/09/2026 : échelle 281 (Brier 0,0139),
contre 0,0177 pour la constante 120 utilisée jusque-là.

Les valeurs **prouvées** ne passent jamais par la sigmoïde : elles valent exactement
1,0 / 0,5 / 0,0. C'est ce qui permet à la revue de partie de distinguer un coup qui
manque un mat (faute certaine) d'un écart entre deux estimations (indice).

### Protocole

```json
{"board": [[0,...], ...], "current_player": 1, "last_move": [3,3], "depth": 16, "time_ms": 1000}
```

`last_move` vaut `null` au premier coup. Deux drapeaux **par requête** (pas au lancement
du processus) :

- `"exact": true` — chaque coup de la racine est recherché en fenêtre pleine. Sans lui,
  seuls le meilleur coup et les coups qui l'améliorent ont un score exact ; les autres
  ne sont que des bornes (un coup perdant peut s'afficher à −147 au lieu de « perte
  forcée »). Indispensable pour analyser, superflu pour jouer.
- `"all_moves": true` — énumère tous les coups légaux à la racine. Sans lui, la racine
  est réduite aux orbites de symétrie : le premier coup ne rend que **10 coups sur 49**.
  Vaut `exact` par défaut.

Les deux modes cohabitent dans le même processus : le bot joue en mode rapide, l'analyse
en mode complet, et les deux partagent la table de transposition.

Parité vérifiée : sur 320 positions issues de parties aléatoires, le moteur Rust et le
moteur de jeu Python listent exactement les mêmes coups légaux (`scripts/check_movegen_parity.py`).

| Variable | Défaut | Rôle |
|----------|--------|------|
| `ENGINE_BIN` | `script/solver_rust/target/release/4mation-engine[.exe]` | Binaire du moteur |
| `ENGINE_TABLEBASE` | `script/solver/data/tablebase.db` | Tablebase SQLite |
| `ENGINE_TT_MB` | `192` | Table de transposition, **par worker Gunicorn** |
| `ENGINE_DEPTH` | `18` | Profondeur par défaut (bot) |
| `ENGINE_TIME_MS` | `1200` | Budget temps par défaut (bot) |
| `ENGINE_ANALYZE_DEPTH` | `14` | Profondeur de l'analyse du site |
| `ENGINE_ANALYZE_TIME_MS` | `700` | Budget temps de l'analyse du site |
| `ENGINE_TIMEOUT_S` | `30` | Attente maximale d'une réponse (au-delà : processus relancé) |
| `ENGINE_DISABLED` | — | `1` pour ne jamais démarrer le moteur |

⚠️ Chaque worker Gunicorn garde son propre processus moteur : avec 8 workers et
`ENGINE_TT_MB=192`, prévoir ~2 Go de RAM. Baisser la valeur ou désactiver `level_6`
(`ENGINE_DISABLED=1`) si la RAM du VPS manque.

⚠️ Le moteur est **mono-requête** (un verrou sérialise stdin/stdout) : une revue de
partie de 40 coups occupe le processus quelques secondes et retarde les coups de bot du
même worker. C'est le prix d'une table de transposition partagée ; l'analyse reste
toujours mieux lotie que l'ancien MCTS de 350 ms par coup.
