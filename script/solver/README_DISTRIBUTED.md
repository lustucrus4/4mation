# Solveur distribué 4mation — workers parallèles

Architecture **coordinateur VPS + workers** (PC local, VPS, autres machines) pour résoudre la tablebase sans doublons.

## Vue d'ensemble

```
[VPS] work_queue_filler.py  →  work_queue (SQLite)
         ↓
[VPS API] /api/solver/work/claim|submit|stats
         ↓
[Workers] distributed_worker.py (multiprocessing)
         → positions dans tablebase.db
```

- Le **filler** génère des positions `pending` via BFS / rétrograde (même logique que le solveur exhaustif).
- Chaque **worker** demande des positions (`claim`), les résout (`retrograde_solver`), puis soumet le résultat (`submit`).
- Un hash ne peut être `in_progress` que pour un seul worker ; reclaim automatique après **5 min** sans submit.

## Prérequis locaux

- Python 3.10+
- `numpy` : `pip install numpy`
- Accès réseau vers `https://api-4mation.lab211.fr`

Optionnel : environnement virtuel à la racine du projet :

```powershell
cd 4mation
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install numpy
```

## Lancement rapide (Windows)

**Recommandé — double-clic** (contourne `ExecutionPolicy` PowerShell, pas de configuration système) :

```bat
scripts\run_local_worker.bat
```

Ou depuis l'explorateur : double-clic sur `scripts\run_local_worker.bat` (ou `.cmd`, identique).

Alternative PowerShell (si `ExecutionPolicy` autorise les scripts) :

```powershell
cd c:\Users\Lucien\Documents\Projet code\4mation
.\scripts\run_local_worker.ps1
```

Par défaut : **16 processus** (adapté Ryzen 9 9955HX — 16 cœurs / 32 threads).

Variables d'environnement optionnelles :

| Variable | Défaut | Description |
|----------|--------|-------------|
| `SOLVER_API_URL` | `https://api-4mation.lab211.fr` | URL de l'API |
| `SOLVER_WORKERS` | `16` | Nombre de processus parallèles |
| `SOLVER_WORKER_TOKEN` | (vide) | Token si activé côté serveur |
| `TABLEBASE_MAX_EMPTY` | `49` | Profondeur max cases vides |

## Lancement manuel

```powershell
$env:PYTHONPATH = "c:\Users\Lucien\Documents\Projet code\4mation;c:\Users\Lucien\Documents\Projet code\4mation\script"
python script\solver\distributed_worker.py --api-url https://api-4mation.lab211.fr --workers 16
```

Test court (2 workers, quelques itérations) :

```powershell
python script\solver\distributed_worker.py --api-url https://api-4mation.lab211.fr --workers 2 --max-iterations 3
```

## API workers

| Route | Méthode | Description |
|-------|---------|-------------|
| `/api/solver/work/claim` | POST | Body : `{ "worker_id": "...", "count": N }` |
| `/api/solver/work/submit` | POST | Body : `{ "hash", "result", "win_rate", "best_move", ... }` |
| `/api/solver/work/stats` | GET | Stats file + workers actifs |

Sécurité : si `SOLVER_WORKER_TOKEN` est défini sur le VPS, envoyer le header `X-Solver-Worker-Token`.

## Suivi

- Dashboard : [https://4mation.lab211.fr/solver.html](https://4mation.lab211.fr/solver.html) — section **Workers distribués**
- Logs console : chaque position résolue affiche `hash → W/L/D`

## VPS (filler + worker)

Sur le VPS, le conteneur `4mation-solver` exécute :

1. `work_queue_filler.py` — alimente la queue
2. `distributed_worker.py` — consomme via `http://api:8097`

Le solveur exhaustif monolithique (`build_full_tablebase.py`) peut coexister ou être remplacé par ce mode distribué.

## Dépannage

| Symptôme | Cause probable | Action |
|----------|----------------|--------|
| `L'exécution de scripts est désactivée` (`.ps1`) | `ExecutionPolicy` Windows | Utiliser `scripts\run_local_worker.bat` à la place |
| `Claim` vide en boucle | Queue vide | Vérifier que le filler tourne sur le VPS |
| HTTP 401 | Token requis | Exporter `SOLVER_WORKER_TOKEN` localement |
| HTTP 429 | Rate limit | Réduire `--workers` ou attendre |
| Résolution impossible | Position trop profonde | Augmenter `TABLEBASE_MAX_EMPTY` |

## Fichiers

- `script/solver/distributed_worker.py` — worker multiprocessing
- `script/solver/work_queue_filler.py` — générateur de travail (VPS)
- `api/routes/solver_workers.py` — routes API
- `api/services/work_queue_service.py` — logique file partagée
- `scripts/run_local_worker.bat` — lanceur Windows (recommandé, double-clic)
- `scripts/run_local_worker.cmd` — alias identique au `.bat`
- `scripts/run_local_worker.ps1` — lanceur PowerShell (nécessite ExecutionPolicy)
