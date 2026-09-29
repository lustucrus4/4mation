# Scripts et moteur de jeu

Modules copiés depuis `4 mation/` :

- `game/` — règles et moteur
- `game_tree/` — Minimax optimisé
- `agent/`, `simulator/` — entraînement (Phase 2)
- `utils/` — configuration
- `train.py` — script d'entraînement PPO / MaskablePPO
- `evaluate.py` — benchmark vs bots Minimax
- `test_model.py` — test rapide vs adversaire aléatoire

Les imports Python se font avec `PYTHONPATH` pointant sur ce dossier ou la racine `4mation/`.

## Phase 2 — réentraînement (observation 149 dims)

L'environnement RL expose désormais **149 dimensions** :

| Composante | Dims |
|---|---|
| Plateau (2 canaux joueur) | 98 |
| Dernier coup (row, col normalisés) | 2 |
| Masque d'actions légales | 49 |

Les checkpoints PPO Phase 1 (**98 dims**, sans `last_move` ni `action_mask`) sont **incompatibles**. Repartir avec `--new-model`.

### Prérequis

```bash
cd 4mation
pip install -r requirements.txt
# Recommandé pour le masquage d'actions natif :
pip install sb3-contrib
```

### Entraînement test (10k steps)

```bash
cd script
set PYTHONPATH=..;.
python train.py --new-model --quick --parallel 4 --eval-bots
```

### Entraînement recommandé (objectif battre Minimax level_5)

```bash
cd script
set PYTHONPATH=..;.
python train.py --new-model --minimax-teacher --minimax-depth 4 ^
  --steps 500000 --parallel 16 --eval-bots --eval-bots-games 20
```

Options utiles :

| Option | Description |
|---|---|
| `--new-model` | Ignore les anciens checkpoints (obligatoire Phase 2) |
| `--minimax-teacher` | Adversaire + imitation Minimax |
| `--eval-bots` | Benchmark inline vs level_1/3/5 pendant l'entraînement |
| `--eval-bots-games N` | Parties par bot (défaut : 10) |
| `--eval-bots-freq N` | Fréquence en steps (défaut : `eval_freq`) |
| `--quick` | 10 000 steps (smoke test) |

### Benchmark post-entraînement

```bash
cd 4mation
set PYTHONPATH=.;script
python script/evaluate.py --games 50 --opponent ppo
python script/evaluate.py --games 20 --opponent ppo --bot level_5
```

### Test rapide vs aléatoire

```bash
cd script
set PYTHONPATH=..;.
python test_model.py --games 10
```

### Masquage d'actions

- **sb3-contrib installé** → `MaskablePPO` + `ActionMasker` (masquage au niveau politique)
- **Sinon** → `PPO` standard + `ActionMaskWrapper` (remap des actions invalides)

Les modèles sont sauvegardés dans `script/models/` (best, checkpoints, final).

## Pack de puzzles (victoires forcées)

`build_puzzle_pack.py` génère `api/data/puzzles.json`, puis `build_puzzle_solutions.py`
précalcule pour chaque puzzle l'**arbre de solution** (`nodes`) : à chaque position, la
liste des coups humains qui forcent encore la victoire et, pour chacun, la défense
adverse la plus tenace. C'est cet arbre que `api/services/puzzle_service.py` consulte :
un déroulé linéaire (`line`) refusait à tort les autres coups gagnants.

- `build_puzzle_pack.py` appelle désormais `add_solutions` en fin de génération : un pack
  régénéré ne peut plus perdre ses arbres.
- `line` est dérivé de l'arbre (premier coup gagnant, puis la meilleure défense) et sert
  uniquement de repli.
- `min_moves` (exposé par l'API) est le nombre minimal de coups humains réellement
  nécessaires ; il peut être inférieur à `human_moves`.

```bash
cd 4mation
set PYTHONPATH=.;script
python script/build_puzzle_pack.py            # régénère le pack (arbres inclus)
python script/build_puzzle_solutions.py       # recalcule seulement les arbres
python scripts/check_puzzle_pack.py           # intégrité arbre <-> moteur
python scripts/_puzzle_diag.py                # cohérence `line` <-> arbre
```
