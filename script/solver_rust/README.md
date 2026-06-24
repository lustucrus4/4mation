# Worker solveur Rust — 4mation-worker

Binaire haute performance pour résoudre des positions 4mation en local ou via l'API distribuée.

## Prérequis

- [Rust](https://rustup.rs) (toolchain stable)
- Windows : **Visual Studio Build Tools** avec charge de travail « Développement Desktop en C++ » (`link.exe` MSVC requis)

```powershell
rustup default stable
# Si cargo build échoue avec "link.exe not found" :
winget install Microsoft.VisualStudio.2022.BuildTools
# Puis cocher « MSVC v143 » et « Windows SDK » dans l'installateur
```

## Compilation

```powershell
cd script/solver_rust
cargo build --release
```

Le binaire se trouve dans `target/release/4mation-worker.exe` (Windows).

## Lancement rapide (Windows)

Depuis la racine du projet :

```bat
scripts\run_local_worker_rust.bat
```

Variables d'environnement utiles :

| Variable | Défaut | Description |
|----------|--------|-------------|
| `SOLVER_API_URL` | `https://api-4mation.lab211.fr` | URL API |
| `SOLVER_THREADS` | `16` | Threads rayon (cœurs physiques) |
| `SOLVER_CLAIM_BATCH` | `25` | Positions par claim (max 50) |
| `TABLEBASE_MAX_EMPTY` | `49` | Cases vides max pour résolution |
| `SOLVER_WORKER_TOKEN` | — | Token si requis par l'API |

## Modes

### API distante (défaut)

Connexion HTTP persistante (reqwest), claim par lot, résolution parallèle (rayon), submit-batch.

```powershell
.\target\release\4mation-worker.exe `
  --api-url https://api-4mation.lab211.fr `
  --threads 16 `
  --claim-batch 25
```

### Base locale (`--local-db`)

Zéro latence réseau : lecture/écriture directe sur `tablebase.db` (copie synchronisée ou API locale).

```powershell
.\target\release\4mation-worker.exe `
  --local-db ..\solver\data\tablebase.db `
  --threads 16
```

## Tests

```powershell
cargo test
cargo build --release
.\target\release\4mation-worker.exe --max-iterations 3 --threads 4 --claim-batch 5
```

## Architecture

- `game.rs` — règles 7×7, coups frontier, détection victoire
- `solver.rs` — solveur rétrograde (port de `retrograde_solver.py`)
- `api_client.rs` — client HTTP avec pool et submit-batch
- `local_db.rs` — mode SQLite direct
- `main.rs` — boucle claim → résolution parallèle → submit

## Gain attendu vs worker Python (16 processus)

| Goulot | Python (avant) | Rust worker |
|--------|----------------|-------------|
| HTTP | Nouvelle connexion par requête (urllib) | Pool keep-alive, batch submit |
| Parallélisme | 16 processus × overhead IPC | 1 processus, 16 threads rayon |
| Résolution | Python + numpy récursif | Rust natif, cache HashMap |
| CPU typique | ~20 % (réseau) | 60–90 % selon profondeur |

Ordre de grandeur : **3–10×** plus de positions/minute selon la latence API et la complexité des positions, jusqu'à **15×** en mode `--local-db`.

## Compatibilité API

Endpoints inchangés : `claim`, `submit`, `release`. Nouveau endpoint optionnel : `submit-batch` (repli automatique sur submit unitaire si absent).
