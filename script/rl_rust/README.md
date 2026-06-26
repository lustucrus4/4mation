# Entraînement RL 4mation (Rust)

Entraînement haute performance par **self-play parallèle** (rayon, 16+ cœurs), policy **linéaire** sur features hand-crafted, **MCTS-lite** pour la sélection de coups, et évaluation périodique vs **Minimax level_5 + tablebase** via subprocess Python.

## Architecture

```
script/rl_rust/
├── src/
│   ├── features.rs      # 12 features par coup (menace, blocage, centre…)
│   ├── policy.rs        # Softmax linéaire + REINFORCE
│   ├── mcts.rs          # Rollouts policy/aléatoire par coup racine
│   ├── self_play.rs     # Batch parallèle rayon
│   ├── eval.rs          # Matchs vs bot level_5 (Python)
│   ├── imitation.rs     # Bootstrap Minimax d6–d8
│   ├── persistence.rs   # checkpoints JSON + metrics JSONL/SQLite
│   └── bin/train.rs     # CLI
├── eval_minimax.py      # Pont Python (move + imitate)
└── data/                # status.json, metrics, checkpoints
```

Réutilise `formation-worker` (`script/solver_rust`) pour les règles plateau, coups frontier et hash Zobrist.

## Prérequis

- Rust stable + `cargo`
- Python 3 avec dépendances 4mation (`game`, `game_tree`, `api`)
- Ryzen / CPU multi-cœur (testé pour 16 workers)

## Compilation

```powershell
cd 4mation\script\rl_rust
cargo build --release
```

## Lancer l'entraînement

```powershell
cargo run --release --bin train -- --cores 16 --self-play-games 1000 --eval-every 5000
```

Options utiles :

| Option | Défaut | Description |
|--------|--------|-------------|
| `--cores` | 16 | Thread pool rayon |
| `--self-play-games` | 1000 | Parties par batch |
| `--eval-every` | 5000 | Éval vs level_5 tous les N coups cumulés |
| `--eval-games` | 20 | Parties par évaluation |
| `--mcts-sims` | 8 | Rollouts MCTS par coup (0 = policy seule) |
| `--resume` | — | Reprend `data/checkpoints/latest.json` |
| `--max-steps` | 0 | 0 = boucle infinie |
| `--data-dir` | `script/rl_rust/data` | Persistance |

### Arrière-plan Windows

```powershell
cd 4mation
.\scripts\run_rl_train.ps1
```

Logs : `script/rl_rust/data/train.log`, PID : `script/rl_rust/data/_train.pid`.

## Dashboard

1. API Flask : `GET /api/rl/status`, `GET /api/rl/metrics`
2. Page React : `/analyze/rl` (rafraîchissement auto 5–10 s)

```powershell
# Terminal 1 — API
cd 4mation
set PYTHONPATH=.
py api/app.py

# Terminal 2 — Dashboard dev
cd 4mation\4mation_dashboard_dev
npm run dev
```

Variable optionnelle : `RL_DATA_DIR` pour pointer vers un autre dossier `data/`.

## Fichiers produits

| Fichier | Rôle |
|---------|------|
| `data/status.json` | État live pour le dashboard |
| `data/metrics.jsonl` | Historique métriques |
| `data/metrics.db` | SQLite (même contenu) |
| `data/checkpoints/latest.json` | Policy courante |
| `data/checkpoints/policy_step_*.json` | Snapshots |

## Algorithme (MVP)

1. **Bootstrap** : imitation Minimax d7 (Python) + heuristique Rust (win/block/centre)
2. **Self-play** : les deux joueurs utilisent policy + MCTS-lite ; mise à jour REINFORCE
3. **Éval** : N parties RL (MCTS) vs `level_5` (subprocess `eval_minimax.py move`)

## Limites MVP

- Policy **linéaire** (pas de réseau profond) — rapide à compiler, plafond de force modéré
- Pas de chargement du PPO Python `best_model.zip` (format SB3 incompatible) ; repartir du bootstrap + `--resume`
- Éval level_5 = 1 appel Python par coup adverse (lent si `--eval-games` élevé)
- Pas de tablebase côté RL (seulement via l'adversaire d'éval)

## Prochaines étapes

- Exporter/importer poids vers petit MLP (candle / burn) AlphaZero-lite
- Batch eval Python (parties complètes en un subprocess)
- Arena vs checkpoint précédent (league training)
- Intégration bot_registry pour jouer en prod après seuil de win rate

## Optimisations Ryzen 9955HX

- `[profile.release] lto = true`, `codegen-units = 1` (déjà activé)
- `--cores 16` (cœurs physiques) ; jusqu'à 24 si hyperthreading utile
- `--release` obligatoire en entraînement
- Pas de GIL Python sur le hot path self-play (100 % Rust)
