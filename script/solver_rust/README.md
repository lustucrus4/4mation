# Solveur Rust — 4mation-local & 4mation-worker

Binaires haute performance pour construire la tablebase Connect4/4mation (7×7, frontier, WDL exact).

## Prérequis

- [Rust](https://rustup.rs) (toolchain stable)
- Windows : **Visual Studio Build Tools** avec « Développement Desktop en C++ »

```powershell
rustup default stable
```

## Compilation

```powershell
cd script/solver_rust
cargo build --release
```

Binaires produits :

| Binaire | Rôle |
|---------|------|
| `target/release/4mation-local.exe` | **Recommandé Legion** — exploration + résolution + SQLite + dashboard (`--dashboard`) |
| `target/release/4mation-dashboard.exe` | Dashboard seul (lecture SQLite, sans solveur) |
| `target/release/4mation-worker.exe` | Worker HTTP (API distribuée, conservé pour compatibilité) |

## Lancement local (Legion, 16 cœurs)

Depuis la racine du projet :

```bat
scripts\run_local_solver_rust.bat
```

Ou directement :

```powershell
.\script\solver_rust\target\release\4mation-local.exe `
  --db script\solver\data\tablebase.db `
  --threads 16 `
  --max-empty 12 `
  --solve-batch 500 `
  --min-pending 5000 `
  --dashboard
```

### Options CLI (`4mation-local`)

| Option | Défaut | Description |
|--------|--------|-------------|
| `--db` | `script/solver/data/tablebase.db` | Chemin SQLite |
| `--threads` | `16` | Threads rayon (résolution parallèle) |
| `--max-empty` | `12` | Niveau initial cases vides (12→20→30→40→49) |
| `--solve-batch` | `500` | Positions par lot de résolution |
| `--min-pending` | `5000` | Tampon file avant pause exploration |
| `--max-iterations` | — | Arrêt après N résolutions (tests) |
| `--once` | — | Un cycle puis sortie |
| `--dashboard` | — | Serveur web intégré (port 8765) |
| `--dashboard-port` | `8765` | Port HTTP (`SOLVER_DASHBOARD_PORT`) |
| `--dashboard-host` | `127.0.0.1` | Interface d'écoute (`SOLVER_DASHBOARD_HOST`) |

Variables d'environnement : `SOLVER_THREADS`, `TABLEBASE_MAX_EMPTY`, `SOLVER_DASHBOARD_PORT`.

## Architecture locale

```
4mation-local [--dashboard]
├── explorer.rs     — BFS avant + rétrograde parents (remplace work_queue_filler.py)
├── hasher.rs       — Hash Zobrist identique à position_hasher.py
├── solver.rs       — Résolution rétrograde W/L/D (port retrograde_solver.py)
├── game.rs         — Règles 7×7, frontier, victoire
├── local_db.rs     — Schéma SQLite, inserts groupés, claim/submit bulk
├── local_engine.rs — Boucle : explorer → claim → résoudre (rayon) → écrire
└── dashboard/      — Serveur Axum (thread séparé si --dashboard)
```

Une seule machine, 16 threads. Le dashboard HTTP est hors chemin critique de résolution.

## Tests

```powershell
cargo test
cargo build --release
.\target\release\4mation-local.exe --max-iterations 5 --threads 4 --once
```

## Performance attendue vs mode API distribué

| Goulot | API + filler VPS | 4mation-local (Legion) |
|--------|------------------|------------------------|
| Réseau | Latence claim/submit | Aucun |
| Exploration | Process Python séparé | Rust intégré, même processus |
| Résolution | 16 workers HTTP | 16 threads rayon, cache local |
| SQLite | VPS distant | Disque NVMe local, WAL + bulk |

Ordre de grandeur : **10–30×** plus de positions/minute qu'une chaîne API+VPS+workers Python, selon profondeur des positions. CPU cible : **70–95 %** sur 16 cœurs en fin de partie.

## Worker HTTP (legacy)

```powershell
.\target\release\4mation-worker.exe --api-url https://api-4mation.lab211.fr --threads 16
.\target\release\4mation-worker.exe --local-db ..\solver\data\tablebase.db --threads 16
```

## Reste à faire (évolutions)

- Symétries / canonicalisation des positions (réduction espace d'états)
- Checkpoint JSON persistant (`filler_checkpoint.json`) comme le filler Python
- Parallélisation de l'exploration BFS (actuellement séquentielle, résolution déjà parallèle)
- Livre d'ouverture (`opening_book`) et phases A/B Python
- Timeout par position (budget nœuds déjà limité à 500k)

## Dashboard local (suivi avancement)

Page web locale calquée sur `4mation_dashboard_dev/solver.html` : progression, débit, ETA, file de travail, mini-plateaux des 20 dernières positions.

**Stack 100 % Rust** — plus de Python/Flask requis pour le dashboard local.

### URL

**http://127.0.0.1:8765/** (port via `SOLVER_DASHBOARD_PORT`)

### Lancement (recommandé — 1 commande)

```bat
REM Solveur + dashboard intégrés (1 fenêtre, 1 processus)
scripts\run_local_solver_stack.bat
```

Équivalent :

```bat
scripts\run_local_solver_rust.bat
```

Le script lance `4mation-local --dashboard` par défaut.

### Dashboard seul (lecture SQLite)

```bat
scripts\run_local_dashboard.bat
```

Binaire :

```powershell
.\script\solver_rust\target\release\4mation-dashboard.exe --db script\solver\data\tablebase.db
```

### Fichiers

| Fichier | Rôle |
|---------|------|
| `web/index.html`, `web/style.css`, `web/solver.js` | UI (auto-refresh 2,5 s) |
| `src/dashboard/` | Serveur Axum + stats SQLite |
| `local_dashboard.py` | **Déprécié** — ancien serveur Flask (conservé pour référence) |

Le dashboard lit la même base SQLite que `4mation-local`. **Aucun impact** sur le dashboard prod Hostinger.

### Contrôle depuis le navigateur (localhost uniquement)

Depuis **http://127.0.0.1:8765/**, la section **Contrôle solveur** permet de :

- **Démarrer le solveur** — lance `scripts\run_local_solver_rust.bat` dans une nouvelle fenêtre `cmd`
- **Arrêter le solveur** — termine `4mation-local.exe` (`taskkill`) ou signale l'arrêt si mode `--dashboard` intégré
- Afficher l'état **actif** / **arrêté** (polling toutes les 3 s)

Endpoints réservés à `127.0.0.1` / `::1` (403 sinon) :

| Méthode | Route | Rôle |
|---------|-------|------|
| `GET` | `/api/solver/status` | Progression, débit, ETA, positions récentes |
| `GET` | `/api/solver/work/stats` | File de travail et workers actifs |
| `GET` | `/api/local/process-status` | `4mation-local.exe` en cours ? |
| `GET` | `/health` | Santé du serveur |
| `POST` | `/api/local/start-solver` | Lance le solveur (whitelist `.bat`) |
| `POST` | `/api/local/stop-solver` | Arrête le solveur |
| `POST` | `/api/local/start-stack` | Lance stack complète (optionnel) |
