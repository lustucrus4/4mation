# Solveur 4mation — tablebase et Phase C

Scripts de construction de la base de positions exactes (W/L/D, meilleur coup, taux de victoire).

## Structure

```
script/solver/
├── build_endgame_tablebase.py   # Phase A — fin de partie (≤12 cases vides)
├── build_opening_book.py      # Phase B — livre d'ouverture (12 premiers coups)
├── build_full_tablebase.py    # Phase C — solveur complet progressif
├── retrograde_solver.py       # Moteur rétrograde
├── db_schema.py               # Schéma SQLite partagé
├── solver_status.py           # Fichier JSON live (API + dashboard)
├── position_hasher.py         # Hash Zobrist des positions
└── data/
    ├── tablebase.db           # Base SQLite (positions + progression)
    └── solver_status.json     # État live pour le dashboard
```

## Schéma SQLite

- **positions** — résultats exacts + snapshot plateau (`board_json`) pour visualisation
- **opening_book** — coups d'ouverture pré-calculés
- **solver_progress** — compteurs globaux, phase, checkpoint

## Phase C — solveur complet

```bash
cd 4mation
set PYTHONPATH=script
python script/solver/build_full_tablebase.py --db script/solver/data/tablebase.db --batch 500
```

Options :

| Option | Défaut | Description |
|--------|--------|-------------|
| `--db` | `script/solver/data/tablebase.db` | Chemin SQLite |
| `--max-empty` | 20 | Cases vides max par position |
| `--batch` | 500 | Positions entre chaque flush / log |

### Comportement

- **Checkpoint** : `solver_checkpoint.json` (reprise après interruption)
- **Progression** : table `solver_progress` + `solver_status.json` (rafraîchi chaque batch)
- **Métriques** : % avancement, positions/s, ETA, 20 dernières positions avec plateau

### Variables d'environnement (VPS / Docker)

| Variable | Exemple | Usage |
|----------|---------|--------|
| `TABLEBASE_DB_PATH` | `/app/data/tablebase.db` | Chemin base pour API et solveur |
| `SOLVER_STATUS_PATH` | `/app/data/solver_status.json` | Fichier JSON lu par l'API |

## Phases A et B (amorçage)

```bash
python script/solver/build_endgame_tablebase.py
python script/solver/build_opening_book.py
# ou en une fois :
python script/solver/seed_initial_tablebase.py
```

## API de suivi (dashboard)

| Route | Description |
|-------|-------------|
| `GET /api/solver/status` | Stats live + 20 dernières positions |
| `GET /api/solver/position/{hash}` | Détail d'une position résolue |

Page web : **https://4mation.lab211.fr/solver.html**

## Déploiement VPS

Le service `solver` du `deploy/docker-compose.vps.yml` lance Phase C en arrière-plan.
L'API et le solveur partagent le volume `4mation-data` (`/app/data`).

Redémarrage après push GitHub :

```bash
docker compose -f deploy/docker-compose.vps.yml up -d --force-recreate api solver
```
