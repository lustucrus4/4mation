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

## API de suivi (dashboard)

| Route | Description |
|-------|-------------|
| `GET /api/solver/status` | Stats live + 20 dernières positions |
| `GET /api/solver/position/{hash}` | Détail d'une position résolue |

Page web : **https://4mation.lab211.fr/solver.html**

## Déploiement VPS

Le service `solver` dans `deploy/docker-compose.solver.yml` tourne en boucle continue (`restart: unless-stopped`).

```bash
docker compose -f deploy/docker-compose.solver.yml up -d --force-recreate solver
```

L'API et le solveur partagent le volume `4mation-sessions` (`/app/data`).
