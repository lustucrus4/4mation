# Entraînement RL 4mation (Rust)

Entraînement par **self-play parallèle** (rayon, 16+ cœurs) et par **matchs contre les bots
Python du site**, avec un réseau **MLP** (policy + valeur), un **MCTS type AlphaZero-lite**,
un **adversaire de réserve** et un **curriculum**.

## Architecture

```
script/rl_rust/
├── src/
│   ├── features.rs                # features par coup (12) et par position
│   ├── mlp.rs                     # réseau MLP (policy + tête valeur), softmax
│   ├── policy.rs                  # PolicyNet (MLP ou linéaire historique) + REINFORCE
│   ├── az_mcts.rs                 # MCTS AlphaZero-lite (policy + valeur)
│   ├── mcts.rs                    # MCTS-lite (rollouts)
│   ├── self_play.rs               # Batch parallèle rayon
│   ├── opponent.rs                # Adversaire de réserve (league)
│   ├── vs_minimax_training.rs     # Phase 1 : parties contre level_3 / level_5 (Python)
│   ├── eval.rs                    # Matchs vs bots Python (pont daemon)
│   ├── imitation.rs               # Bootstrap par imitation Minimax
│   ├── trainer.rs                 # Boucle d'entraînement, phases, checkpoints
│   ├── persistence.rs             # checkpoints JSON + metrics JSONL/SQLite
│   ├── bin/train.rs               # CLI entraînement
│   └── bin/eval.rs                # CLI évaluation seule
├── eval_minimax.py                # Pont Python (`move`, `daemon`, `imitate`)
└── data/                          # status.json, metrics, checkpoints
```

Réutilise `formation-worker` (`script/solver_rust`) pour les règles plateau, les coups
frontière et le hash Zobrist.

## État réel au 24/09/2026

| Élément | Valeur |
|---------|--------|
| Parties cumulées | 215 980 400 (dernier `status.json`) |
| Dernier entraînement | **02/07/2026** — processus arrêté, `status.json` resté sur `running: true` |
| Checkpoint | `data/checkpoints/latest.json` (02/07/2026, MLP) |
| Éval vs level_5 | 0 % (0 victoire / 12 défaites / 0 nulle) |
| Éval vs level_3 | 0 % (0 / 12 / 0) |
| Vitesse self-play | ≈ 2 500 parties/s sur 16 cœurs |

**Important — historique faussé.** Jusqu'au 24/09/2026 inclus, l'évaluation annonçait
`0 victoire / 0 défaite / 12 nulles` contre **tous** les adversaires, y compris avec un
réseau aléatoire. Ce n'était pas une nulle parfaite : le pont Python répondait sur le
**plateau vide** à chaque coup (voir « Pont Python » ci-dessous). Toutes les métriques
`eval_*` antérieures à la correction sont donc **sans valeur**, et la phase 1
(`vs_level5`) s'entraînait contre un adversaire qui jouait toujours la même case.

La voie RL reste **en pause** : la force de jeu du site vient du moteur exact
(`4mation-engine` : tablebase + recherche alpha-bêta), pas de ce chantier.

## Pont Python (`eval_minimax.py`)

Le Rust envoie une ligne JSON par coup :

```json
{"board": [[0,…],[…]], "current_player": 2, "last_move": [3, 3], "bot_id": "level_5"}
```

**Contrat :** l'état du jeu doit être reconstruit dans `engine.state`
(`state.board`, `state.current_player`, `state.last_move_position`, `state.action_history`).
Écrire `engine.board` / `engine.current_player` crée des attributs que les bots ne lisent
jamais : ils consultent `engine.get_state()`, donc le daemon répondait sur la position
initiale sans lever d'erreur.

Côté Rust, un coup refusé par `GameSession::apply` fait maintenant **échouer l'évaluation**
(`anyhow::bail!`) au lieu de terminer la partie en « nulle » : un désaccord de protocole
doit se voir, pas se déguiser en statistique.

## Prérequis

- Rust stable + `cargo`
- Python 3 avec les dépendances 4mation (`game`, `game_tree`, `api`)
- CPU multi-cœur (16 workers par défaut)

## Compilation

```powershell
cd 4mation\script\rl_rust
cargo build --release
```

## Lancer l'entraînement

```powershell
# Depuis 4mation/ — phase auto : level_5 puis self-play
.\scripts\rl.ps1 train -Fresh

# Reprendre le dernier checkpoint
.\scripts\rl.ps1 train -Resume

# Self-play direct (pas de phase 1)
.\scripts\rl.ps1 train -TrainingPhase self_play
```

Options principales de `train` :

| Option | Défaut | Description |
|--------|--------|-------------|
| `--cores` | 16 | Thread pool rayon |
| `--self-play-games` | 1000 | Parties par batch |
| `--training-phase` | `self_play` | `auto` \| `vs_level5` \| `self_play` |
| `--phase2-win-threshold` | 0.50 | Win rate vs level_5 déclenchant la bascule en self-play |
| `--phase-transition-games` | 20 | Parties d'éval pour décider la bascule |
| `--eval-every-l5` | 10000 | Éval vs level_5 tous les N coups cumulés |
| `--eval-every-l3` | 25000 | Éval vs level_3 |
| `--eval-games` | 12 | Parties par évaluation |
| `--mcts-sims` | 36 | Simulations MCTS en self-play |
| `--eval-mcts-sims` | 16 | Simulations MCTS en évaluation |
| `--curriculum` | 0.45 | Part de parties contre l'adversaire de réserve |
| `--resume` / `--fresh` | — | Reprendre / repartir de zéro |
| `--max-steps` | 0 | 0 = boucle infinie |
| `--data-dir` | `data` | Persistance (relatif à la crate) |

### Arrière-plan Windows

```powershell
cd 4mation
.\scripts\rl.ps1 train          # lance, log dans script/rl_rust/data/train.log
.\scripts\rl.ps1 status         # état + dernières lignes de log
.\scripts\rl.ps1 stop
```

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
| `data/metrics.jsonl` | Historique métriques (64 Mo au 02/07/2026) |
| `data/checkpoints/latest.json` | Réseau courant |
| `data/checkpoints/policy_step_*.json` | Snapshots numérotés |

## Limites connues

- Le harnais d'éval est **lent** (un appel Python par coup adverse : ≈ 8 s par partie
  contre level_5) — il faut un lot de parties par subprocess pour aller plus vite.
- `GameSession` compte « plus aucun coup jouable » comme une **nulle**, alors que le
  solveur exact le compte comme une **défaite** : à aligner si le RL reprend.
- Pas de tablebase côté RL (uniquement via l'adversaire d'évaluation).
- Aucun résultat probant à ce jour : la force de jeu vient du moteur exact.

## Prochaines étapes (si le chantier reprend)

- Corriger/accélérer le pont : parties complètes par appel, ou adversaires Rust.
- Aligner la règle « aucun coup jouable » sur celle du solveur.
- Arena contre checkpoint précédent (league training) pour mesurer la progression réelle.
- Brancher le vainqueur dans `bot_registry` seulement après un seuil de win rate mesuré.

## Optimisations Ryzen 9955HX

- `[profile.release] lto = true`, `codegen-units = 1` (déjà activé)
- `--cores 16` (cœurs physiques) ; jusqu'à 24 si l'hyperthreading aide
- `--release` obligatoire en entraînement
- Pas de GIL Python sur le hot path self-play (100 % Rust)
