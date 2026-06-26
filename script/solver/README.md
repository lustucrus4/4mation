# Solveur 4mation — tablebase et Phase C (résolution exhaustive)

Scripts de construction de la base de positions exactes (W/L/D, meilleur coup, taux de victoire).

## Structure

```
script/solver/
├── build_endgame_tablebase.py   # Phase A — fin de partie (≤12 cases vides)
├── build_opening_book.py        # Phase B — livre d'ouverture (12 premiers coups)
├── build_full_tablebase.py      # Phase C — solveur exhaustif progressif
├── exhaustive_explorer.py       # BFS avant + rétrograde parents
├── retrograde_solver.py         # Moteur rétrograde par position
├── db_schema.py                 # Schéma SQLite partagé
├── solver_status.py             # Fichier JSON live (API + dashboard)
├── position_hasher.py           # Hash Zobrist des positions
└── data/
    ├── tablebase.db             # Base SQLite (positions + progression)
    └── solver_status.json       # État live pour le dashboard
```

## Phase C — résolution exhaustive progressive

Le solveur **ne s'arrête pas** après un lot : il parcourt tout l'espace atteignable.

### Algorithme

1. **BFS avant** depuis l'ouverture (plateau vide) — toutes les positions légales avec ≤ `max_empty` cases vides.
2. **Rétrograde** depuis les positions déjà résolues — génération des parents (coup annulé).
3. **Résolution** de chaque position via `RetrogradeSolver` (W/L/D exact, meilleur coup).
4. **Extension progressive** de `max_empty` : 12 → 20 → 30 → 40 → 49 (fin de partie → ouverture complète).
5. **Checkpoint** après chaque flush — reprise sans perte de progression.

### Estimation de l'espace d'états

| Phase | max_empty | Ordre de grandeur |
|-------|-----------|-------------------|
| Fin de partie | ≤12 | ~800 000 positions |
| Milieu | ≤20 | ~5 millions |
| Ouverture | ≤30 | ~25 millions |
| Large | ≤40 | ~80 millions |
| Complet | 49 | ~150 millions (estimation haute) |

Durée estimée sur VPS : **plusieurs jours à plusieurs semaines** selon la vitesse (~0,5–5 pos/s selon complexité).

Le pourcentage d'avancement n'est affiché que lorsque l'estimation est fiable ; sinon le dashboard indique « X résolues (exploration en cours) ».

### Lancement local

```bash
cd 4mation
set PYTHONPATH=script
python script/solver/build_full_tablebase.py --db script/solver/data/tablebase.db
```

Options :

| Option | Défaut | Description |
|--------|--------|-------------|
| `--db` | `script/solver/data/tablebase.db` | Chemin SQLite |
| `--max-empty` | 12 | Niveau initial de cases vides |
| `--batch` | 25 | Positions entre chaque flush DB |
| `--progress-interval` | 15 | Heartbeat JSON (secondes) |
| `--position-timeout` | 30 | Timeout par position (secondes) |

### Comportement

- **Checkpoint** : `solver_checkpoint.json` (niveau max_empty, exploration BFS/rétrograde)
- **Progression** : table `solver_progress` + `solver_status.json` (heartbeat 15 s)
- **Pas de plafond** : `total_positions_solved` cumule sans limite
- **Phases UI** : `endgame` → `midgame` → `opening` → `complet`

### Variables d'environnement (VPS / Docker)

| Variable | Exemple | Usage |
|----------|---------|--------|
| `TABLEBASE_DB_PATH` | `/app/data/tablebase.db` | Chemin base pour API et solveur |
| `SOLVER_STATUS_PATH` | `/app/data/solver_status.json` | Fichier JSON lu par l'API |

## Phases A et B (amorçage)

```bash
python script/solver/build_endgame_tablebase.py
python script/solver/build_opening_book.py
python script/solver/seed_initial_tablebase.py
```

### Livre d'ouverture longue durée (~2 Go) — **Rust** (recommandé)

Construction parallèle (rayon) adossée à la tablebase en mémoire :

```bat
cd 4mation
scripts\run_opening_book_full.bat
```

Équivalent manuel :

```bat
script\solver_rust\target\release\4mation-local.exe ^
  --opening-book --opening-fresh --opening-target-gb 2 ^
  --opening-max-ply 18 --opening-max-positions 200000 ^
  --threads %NUMBER_OF_PROCESSORS% --dashboard --db script\solver\data\tablebase.db
```

**Algorithme Rust** (remplace Python pour la vitesse) :
- Chargement `ResultTable` (~24M positions) en RAM
- BFS ouverture + tri par ply (enfants avant parents)
- Promotion **exacte** via `resolve_via_children` (lookup O(1))
- Estimations via `RetrogradeSolver` alpha-bêta parallélisé
- Phase dashboard `opening_book`, cible **2 Go**

Version Python legacy (Minimax+MCTS, plus lente) :

```bash
python script/solver/build_opening_book_full.py --target-gb 2 --fresh
```

## API de suivi (dashboard)

| Route | Description |
|-------|-------------|
| `GET /api/solver/status` | Stats live + 20 dernières positions |
| `GET /api/solver/position/{hash}` | Détail d'une position résolue |

Page web : **https://4mation.lab211.fr/solver.html**

## Mode distribué (workers parallèles)

Voir **[README_DISTRIBUTED.md](./README_DISTRIBUTED.md)** pour lancer un worker local (16 processus sur Ryzen 9).

- VPS : `work_queue_filler.py` alimente la file `work_queue`
- Workers : `distributed_worker.py` (PC local, VPS, etc.)
- API : `/api/solver/work/claim|submit|stats|release`

## Déploiement VPS

Le service `solver` dans `deploy/docker-compose.solver.yml` tourne en boucle continue (`restart: unless-stopped`).

```bash
docker compose -f deploy/docker-compose.solver.yml up -d --force-recreate solver
```

L'API et le solveur partagent le volume `4mation-sessions` (`/app/data`).

## Solveur local Rust (100 % hors réseau)

Lancement interactif avec dashboard intégré :

```bat
cd 4mation
lancer_solveur.bat
```

Dashboard : http://127.0.0.1:8765/

### Exploration rétrograde de frontière (base mature)

Au-delà de ~600 000 positions connues, l'explorateur bascule en **rétrograde de frontière** :

- il recharge depuis la DB les positions connues ayant le **plus de cases vides** (la frontière vers l'ouverture) ;
- il génère leurs **parents** (un coup en arrière = +1 case vide) jusqu'à `max_empty=20` (zone solvable) ;
- il alimente la file en continu et se recharge dès qu'elle se vide.

Cela évite le blocage de l'ancien BFS « forward » (qui, partant du plateau vide, ne pouvait jamais atteindre les positions profondes). La progression vers le milieu de partie (cases vides 18→20) est plus lente que l'endgame car les arbres de jeu sont exponentiellement plus grands — c'est attendu, le CPU reste saturé.

Le solveur utilise par défaut **tous les threads logiques** de la machine (`SOLVER_THREADS=%NUMBER_OF_PROCESSORS%`).

### Boucle de test / optimisation automatique

Script PowerShell qui compile, lance le solveur, attend la fin d'un lot, puis valide les métriques (delta DB, taux ok/relâché) :

```powershell
cd 4mation
.\scripts\solver_feedback_loop.ps1 -MaxRounds 5 -RunSeconds 600
```

Paramètres utiles : `-MaxRounds`, `-RunSeconds` (timeout par round), `-MaxIterations`.

La boucle s'arrête dès qu'un round réussit (positions résolues, fail rate < 50 %). Les positions `in_progress` orphelines sont recyclées avant chaque round.
