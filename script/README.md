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
