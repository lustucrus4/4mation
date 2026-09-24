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
│   ├── eval.rs          # Évaluation vs bot Python (process persistant « daemon »)
│   ├── imitation.rs     # Bootstrap Minimax d6–d8
│   ├── persistence.rs   # checkpoints JSON + metrics JSONL/SQLite
│   ├── trainer.rs       # Boucle d'entraînement
│   └── bin/train.rs     # CLI (`--eval-only` pour mesurer sans entraîner)
├── eval_minimax.py      # Pont Python (modes `move`, `daemon`, `imitate`)
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

## Où en est le chantier (état réel, honnête)

**Statut : en pause.** Le RL est un chantier exploratoire ; la priorité est donnée au
solveur exact (tablebase + livre d'ouvertures), qui alimente déjà le site et les cours.
Le RL est conservé tel quel, corrigé et documenté, mais **il n'est pas prêt à produire
un bot de production**.

### Ce qui fonctionne

- Self-play parallèle (rayon) avec policy linéaire + MCTS-lite, checkpoints et metrics.
- Reproduction d'un checkpoint via `--resume`.
- Évaluation contre les bots du site (`level_1` … `level_6`) : `level_3`, `level_5`,
  `level_6` sont mesurés, le reste est disponible via `--bot-id`.
- Mesure **par siège** : le score quand le réseau commence (`score_p1`) et quand il
  répond (`score_p2`) sont désormais séparés, car le premier joueur a un avantage
  structurel dans 4mation.

### Mesures réelles (20 parties par bot, réseau = policy + MCTS 8 simulations)

| Adversaire | Victoires | Défaites | Nulles | score_p1 (10 part.) | score_p2 (10 part.) |
|-----------|-----------|----------|--------|---------------------|---------------------|
| `level_3` | 6 | 14 | 0 | 0,10 | 0,50 |
| `level_5` | 10 | 10 | 0 | 0,50 | 0,50 |

Lecture : échantillon **petit** (10 parties par siège) — les écarts de ±2 parties ne
sont pas significatifs. Le point remarquable est que le réseau ne domine personne : il
n'a pas dépassé le stade « fait des coups légaux et bloque les menaces immédiates ».

### Bug corrigé (important)

Le pont Python envoyait la position au bot, mais le bot **rejouait depuis un plateau
vide** : toutes les évaluations antérieures (et donc la phase 1) étaient fausses, et les
échecs de communication étaient comptés comme des nulles. Correction :

- `eval_minimax.py` reconstruit correctement l'état (`engine.state`) ;
- le pont utilise un **process persistant** (`daemon`) au lieu d'un interpréteur Python
  par coup ;
- côté Rust, toute réponse vide, illégale ou en erreur **fait échouer l'évaluation**
  (`anyhow::bail!`) au lieu d'être comptée comme nulle ;
- `scripts/check_rl_eval_bridge.py` vérifie le pont (modes `move` et `daemon`).

Conséquence : **les mesures ci-dessus sont les premières fiables**. Elles remplacent les
anciens « taux » (et le 50/50 historique vs `level_5`, qui était un artefact).

### Limites connues

- Policy **linéaire** (12 features), pas de réseau profond → plafond de force modéré.
- Aucun accès à la tablebase pendant l'entraînement (les finales exactes ne sont pas
  exploitées ; c'est justement là que le solveur est imbattable).
- Pas de league/arène entre checkpoints, pas de curriculum.
- L'évaluation reste lente : 20 parties ≈ 1 à 3 minutes selon le bot.

### Prochaine étape si le chantier reprend

1. Bootstrap d'imitation depuis le moteur exact (`4mation-engine`) plutôt que Minimax.
2. Ajouter les features de finale (distance au gain tablebase) au jeu de features.
3. Curriculum : commencer par des positions ouvertes à 8–10 cases vides (tablebase) et
   remonter, ce qui rend le signal bien plus dense qu'un self-play depuis le vide.
4. Arena contre checkpoint précédent pour suivre la progression réelle.

## Optimisations Ryzen 9955HX

- `[profile.release] lto = true`, `codegen-units = 1` (déjà activé)
- `--cores 16` (cœurs physiques) ; jusqu'à 24 si hyperthreading utile
- `--release` obligatoire en entraînement
- Pas de GIL Python sur le hot path self-play (100 % Rust)
