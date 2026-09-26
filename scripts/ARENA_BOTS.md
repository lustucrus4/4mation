# Arène des bots 4mation — classement mesuré

Généré le 2026-09-26T16:09:12+00:00 par `scripts/bot_arena.py`.

## Configuration mesurée

- Bots : level_1, level_2, level_3, level_4, level_5, level_6
- Parties par paire : 60 (sièges alternés)
- Parties jouées : 900
- Limite de coups : 90
- Graine de base : 20260926
- Mode rapide (`--fast`) : oui
- Moteur Rust `4mation-engine` disponible : oui
- Durée de calcul : 504 s

## Caveats (à lire avant tout chiffre)

- **Petit échantillon** : 60 parties par paire (900 au total). Les IC à 95 % sont larges et des écarts de quelques dizaines d'Elo ne sont pas significatifs.
- **Non-reproductibilité due aux budgets temps** : la graine fixe la séquence des blunders, mais le Minimax itératif et le moteur Rust coupent selon le temps CPU réel. Les résultats peuvent donc varier légèrement d'une exécution à l'autre.
- **Mode `--fast`** : les budgets temps sont réduits (÷4), pour les bots comme pour les sondes. L'effet n'est **pas symétrique** : un bot dont la recherche est limitée par le temps (niveaux 4 à 6, profondeurs 8 à 26) perd beaucoup plus qu'un bot limité par la profondeur (niveaux 1 à 3). Les scores de cette page sont donc **pessimistes pour le haut de l'échelle** : en production (3 s), le niveau 6 est plus dur que ce qui est mesuré ici.
- **Avantage structurel du premier joueur** : quand chaque bot gagne dans son siège, la paire finit 0.50/0.50 et l'Elo ne peut pas les séparer. L'absence d'écart ne veut pas dire égalité de force.

## Classement Elo (Bradley-Terry logistique)

| Rang | Bot | Niveau | Elo | Parties | Score | V/N/D | Siège 1 | Siège 2 |
|-----:|-----|-------:|----:|--------:|------:|------:|--------:|--------:|
| 1 | `level_6` | 6 | **1855** | 300 | 258.5/300 | 257/3/40 | 1.00 (150/150) | 0.72 (108.5/150) |
| 2 | `level_5` | 5 | **1750** | 300 | 228.5/300 | 226/5/69 | 0.90 (135/150) | 0.62 (93.5/150) |
| 3 | `level_4` | 4 | **1640** | 300 | 193.5/300 | 191/5/104 | 0.79 (118/150) | 0.50 (75.5/150) |
| 4 | `level_3` | 3 | **1413** | 300 | 120/300 | 119/2/179 | 0.48 (72.5/150) | 0.32 (47.5/150) |
| 5 | `level_2` | 2 | **1234** | 300 | 66/300 | 65/2/233 | 0.29 (43/150) | 0.15 (23/150) |
| 6 | `level_1` | 1 | **1109** | 300 | 33.5/300 | 33/1/266 | 0.11 (17/150) | 0.11 (16.5/150) |

## Matrice des confrontations (score du bot en ligne, IC 95 % Wilson)

| A \ B | `level_1` | `level_2` | `level_3` | `level_4` | `level_5` | `level_6` |
|---|---:|---:|---:|---:|---:|---:|
| `level_1` | — | 0.34 [0.23,0.47] (20-1-39) | 0.18 [0.11,0.30] (11-0-49) | 0.02 [0.00,0.09] (1-0-59) | 0.02 [0.00,0.09] (1-0-59) | 0.00 [0.00,0.06] (0-0-60) |
| `level_2` | 0.66 [0.53,0.77] (39-1-20) | — | 0.33 [0.23,0.46] (20-0-40) | 0.09 [0.04,0.19] (5-1-54) | 0.02 [0.00,0.09] (1-0-59) | 0.00 [0.00,0.06] (0-0-60) |
| `level_3` | 0.82 [0.70,0.89] (49-0-11) | 0.67 [0.54,0.77] (40-0-20) | — | 0.27 [0.17,0.39] (15-2-43) | 0.20 [0.12,0.32] (12-0-48) | 0.05 [0.02,0.14] (3-0-57) |
| `level_4` | 0.98 [0.91,1.00] (59-0-1) | 0.91 [0.81,0.96] (54-1-5) | 0.73 [0.61,0.83] (43-2-15) | — | 0.35 [0.24,0.48] (20-2-38) | 0.25 [0.16,0.37] (15-0-45) |
| `level_5` | 0.98 [0.91,1.00] (59-0-1) | 0.98 [0.91,1.00] (59-0-1) | 0.80 [0.68,0.88] (48-0-12) | 0.65 [0.52,0.76] (38-2-20) | — | 0.39 [0.28,0.52] (22-3-35) |
| `level_6` | 1.00 [0.94,1.00] (60-0-0) | 1.00 [0.94,1.00] (60-0-0) | 0.95 [0.86,0.98] (57-0-3) | 0.75 [0.63,0.84] (45-0-15) | 0.61 [0.48,0.72] (35-3-22) | — |

Cellule = score de A contre B, IC 95 % de Wilson, puis (V-N-D). 0.50 = parfaite égalité.

## Monotonie attendue

Ordre attendu : `level_6 >= level_5 >= level_4 >= level_3 >= level_2 >= level_1`.

| Paire adjacente | Elo bas | Elo haut | Δ (haut − bas) | Respecté |
|---|---:|---:|---:|:---:|
| `level_1` → `level_2` | 1109 | 1234 | +125 | oui |
| `level_2` → `level_3` | 1234 | 1413 | +179 | oui |
| `level_3` → `level_4` | 1413 | 1640 | +227 | oui |
| `level_4` → `level_5` | 1640 | 1750 | +110 | oui |
| `level_5` → `level_6` | 1750 | 1855 | +105 | oui |

Aucune inversion sur les paires adjacentes mesurées.

## Détail par bot (sièges)

Tous les bots forts terminent à 1.00 dans le siège du premier joueur : l'avantage structurel du centre écrase la différence de force tant qu'un bot ne gagne pas aussi depuis le siège 2.

| Bot | Parties siège 1 | Score siège 1 | Parties siège 2 | Score siège 2 |
|---|---:|---:|---:|---:|
| `level_6` | 150 | 150 (1.00) | 150 | 108.5 (0.72) |
| `level_5` | 150 | 135 (0.90) | 150 | 93.5 (0.62) |
| `level_4` | 150 | 118 (0.79) | 150 | 75.5 (0.50) |
| `level_3` | 150 | 72.5 (0.48) | 150 | 47.5 (0.32) |
| `level_2` | 150 | 43 (0.29) | 150 | 23 (0.15) |
| `level_1` | 150 | 17 (0.11) | 150 | 16.5 (0.11) |

## Courbe de difficulté (proxy humain en siège 1)

Score d'un adversaire de référence (profondeur et taux d'erreur fixés, voir colonnes) qui joue **toujours le premier** contre chaque bot. Plus ce score est bas, plus le bot est difficile à battre pour un joueur non-parfait. C'est la difficulté *ressentie*, là où l'Elo head-to-head est écrasé par l'avantage du premier joueur.

### Profil `novice` (profondeur 4, 30% d'erreurs)

| Bot | Niveau | Score du proxy | IC 95 % | V/N/D du proxy |
|---|---:|---:|:---:|:---:|
| `level_1` | 1 | 95/96 (0.99) | [0.94, 1.00] | 95/0/1 |
| `level_2` | 2 | 87/96 (0.91) | [0.83, 0.95] | 87/0/9 |
| `level_3` | 3 | 74/96 (0.77) | [0.68, 0.84] | 74/0/22 |
| `level_4` | 4 | 59/96 (0.61) | [0.52, 0.71] | 59/0/37 |
| `level_5` | 5 | 25/96 (0.26) | [0.18, 0.36] | 23/4/69 |
| `level_6` | 6 | 1/96 (0.01) | [0.00, 0.06] | 1/0/95 |

### Profil `debutant` (profondeur 2, 45% d'erreurs)

| Bot | Niveau | Score du proxy | IC 95 % | V/N/D du proxy |
|---|---:|---:|:---:|:---:|
| `level_1` | 1 | 90.5/96 (0.94) | [0.88, 0.97] | 90/1/5 |
| `level_2` | 2 | 77/96 (0.80) | [0.71, 0.87] | 77/0/19 |
| `level_3` | 3 | 58/96 (0.60) | [0.50, 0.70] | 58/0/38 |
| `level_4` | 4 | 28/96 (0.29) | [0.21, 0.39] | 27/2/67 |
| `level_5` | 5 | 13.5/96 (0.14) | [0.09, 0.22] | 13/1/82 |
| `level_6` | 6 | 3/96 (0.03) | [0.01, 0.09] | 3/0/93 |

### Profil `moyen` (profondeur 6, 15% d'erreurs)

| Bot | Niveau | Score du proxy | IC 95 % | V/N/D du proxy |
|---|---:|---:|:---:|:---:|
| `level_1` | 1 | 96/96 (1.00) | [0.96, 1.00] | 96/0/0 |
| `level_2` | 2 | 92/96 (0.96) | [0.90, 0.98] | 92/0/4 |
| `level_3` | 3 | 87/96 (0.91) | [0.83, 0.95] | 87/0/9 |
| `level_4` | 4 | 69.5/96 (0.72) | [0.63, 0.80] | 69/1/26 |
| `level_5` | 5 | 49/96 (0.51) | [0.41, 0.61] | 49/0/47 |
| `level_6` | 6 | 16/96 (0.17) | [0.10, 0.25] | 16/0/80 |

### Profil `avance` (profondeur 8, 6% d'erreurs)

| Bot | Niveau | Score du proxy | IC 95 % | V/N/D du proxy |
|---|---:|---:|:---:|:---:|
| `level_1` | 1 | 96/96 (1.00) | [0.96, 1.00] | 96/0/0 |
| `level_2` | 2 | 94/96 (0.98) | [0.93, 0.99] | 94/0/2 |
| `level_3` | 3 | 94/96 (0.98) | [0.93, 0.99] | 94/0/2 |
| `level_4` | 4 | 83.5/96 (0.87) | [0.79, 0.92] | 83/1/12 |
| `level_5` | 5 | 54/96 (0.56) | [0.46, 0.66] | 53/2/41 |
| `level_6` | 6 | 27/96 (0.28) | [0.20, 0.38] | 26/2/68 |

### Verdict de force (tous profils confondus)

Une paire de niveaux adjacents est validée en **force** si la confrontation directe ne démontre jamais l'inverse **et** qu'**au moins un instrument** démontre la séparation. Les deux instruments sont indépendants : la courbe de difficulté (sonde en siège 1) et la confrontation directe (sièges alternés, colonne « direct »). La démonstration porte sur la **différence** des scores (intervalle hybride de Newcombe) : comparer deux intervalles de Wilson isolés serait trop conservateur.

La tolérance d'inversion apparente (0.05) ne sert qu'à classer les écarts non significatifs en « indiscernables » : un écart net mais non significatif ne réfute pas l'ordre, il dit que les deux niveaux se jouent pareil pour ce profil.

| Paire (facile → dur) | Δ `novice` | Δ `debutant` | Δ `moyen` | Δ `avance` | Direct | Démonstration | Statut |
|---|---:|---:|---:|---:|:---:|:---:|:---:|
| `level_1` → `level_2` | +0.08 [+0.02, +0.16] | +0.14 [+0.05, +0.24] | +0.04 [-0.00, +0.10] | +0.02 [-0.02, +0.07] | 0.34 [0.23, 0.47] | `novice`, `debutant`, directe | validée |
| `level_2` → `level_3` | +0.14 [+0.03, +0.24] | +0.20 [+0.07, +0.32] | +0.05 [-0.02, +0.13] | +0.00 [-0.05, +0.05] | 0.33 [0.23, 0.46] | `novice`, `debutant`, directe | validée |
| `level_3` → `level_4` | +0.16 [+0.03, +0.28] | +0.31 [+0.17, +0.43] | +0.18 [+0.07, +0.29] | +0.11 [+0.04, +0.19] | 0.27 [0.17, 0.39] | `novice`, `debutant`, `moyen`, `avance`, directe | validée |
| `level_4` → `level_5` | +0.35 [+0.22, +0.47] | +0.15 [+0.03, +0.26] | +0.21 [+0.08, +0.34] | +0.31 [+0.18, +0.42] | 0.35 [0.24, 0.48] | `novice`, `debutant`, `moyen`, `avance`, directe | validée |
| `level_5` → `level_6` | +0.25 [+0.16, +0.35] | +0.11 [+0.03, +0.20] | +0.34 [+0.21, +0.46] | +0.28 [+0.14, +0.41] | 0.39 [0.28, 0.52] | `novice`, `debutant`, `moyen`, `avance` | validée |

Chaque niveau est strictement plus fort que le précédent : séparation démontrée par au moins un instrument, et aucune inversion de la confrontation directe sur aucune paire.

## Reproduction

```powershell
$env:PYTHONPATH=".;script"
.venv\Scripts\python.exe scripts/bot_arena.py --games 60 --seed 20260926 --fast --probe-games 96 --probe-profiles novice debutant moyen avance
```
