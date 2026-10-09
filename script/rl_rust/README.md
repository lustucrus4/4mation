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
│   ├── bin/train.rs               # CLI entraînement (`--eval-only` pour mesurer sans entraîner)
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
| `level_6` | 10 | 10 | 0 | 0,70 | 0,30 |

Lecture : contre le bot le plus fort du site (`level_6`), le réseau marque **70 % quand il
commence** et **30 % quand il répond** — exactement la signature de l'avantage du premier
joueur, désormais **prouvé** (voir `script/solver/GAIN_FORCE_33.md` : le centre gagne de
force en 28 demi-coups). Le total reste 50 %, donc le réseau n'apporte rien : il joue
« correctement » sans dominer.

Deux réserves à garder en tête :

- échantillon **petit** (10 parties par siège) : ±2 parties ne veulent rien dire ;
- le résultat contre `level_3` (10 % en premier) est **contre-intuitif** et n'a pas
  d'explication satisfaisante : soit bruit statistique, soit le style très aléatoire de
  `level_3` (12 % de coups au hasard) déstabilise une politique linéaire entraînée contre
  `level_5`. À re-mesurer avec 100+ parties avant toute conclusion.

### Bug corrigé (important)

Le pont Python envoyait la position au bot, mais le bot **rejouait depuis un plateau
vide** : toutes les évaluations antérieures (et donc la phase 1) étaient fausses, et les
échecs de communication étaient comptés comme des nulles. Correction :

- `eval_minimax.py` reconstruit correctement l'état (`engine.state`) ;
- le pont utilise un **process persistant** (`daemon`) au lieu d'un interpréteur Python
  par coup ;
- côté Rust, toute réponse vide, illégale ou en erreur **fait échouer l'évaluation**
  (`anyhow::bail!`) au lieu d'être comptée comme nulle ;
- `scripts/check_rl_eval_bridge.py` contrôle le pont sur 9 positions de référence, dont une
  à **gain immédiat** : la conclusion doit être trouvée, ce qui est impossible depuis un
  plateau vide — le bug historique ne peut donc plus passer inaperçu.

### Le daemon n'est pas reproductible (et ce n'est pas un bug)

Le daemon garde le même bot d'une requête à l'autre, donc la même table de transposition
réchauffée, et la recherche est bornée par un budget de temps. Deux interrogations de la
même position peuvent donc conclure à deux coups **également bons** (mesuré : 4 cas sur
27 pour `level_3`, `level_5`, `level_6`). Le contrôle exige donc ce qui compte — coups
légaux, gain immédiat trouvé — et **signale** ces variations sans échouer. Conséquence
pratique : ne jamais supposer deux exécutions identiques au coup près.

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
- `--cores 16` (cœurs physiques) ; jusqu'à 24 si l'hyperthreading aide
- `--release` obligatoire en entraînement
- Pas de GIL Python sur le hot path self-play (100 % Rust)
