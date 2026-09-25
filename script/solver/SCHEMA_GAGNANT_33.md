# Schéma gagnant — ouverture et ligne de référence

Partie de référence jouée le 2026-09-24T23:04:30 par `level_6` (X) contre `level_6` (O), premier coup imposé (3,3).

## Verdict

Chaque demi-coup a été analysé par le moteur en mode exact. Un coup est dit **optimal** quand le meilleur coup connu ne lui rend pas plus de 0.05 de taux de victoire.

| Camp | Coups | dont optimaux | Pire écart | Écart moyen | Issue |
|------|-------|---------------|------------|-------------|-------|
| X (premier) | 15 | 14 | 0.444 | 0.030 | gagne |
| O (second) | 14 | 14 | 0.046 | 0.003 | perd |

**Le camp qui perd n'a commis aucune faute** : 14 coups sur 14 sont les meilleurs connus du moteur, et il perd quand même en 29 demi-coups. La défaite vient de l'ouverture, pas du jeu : c'est ce qui fait de cette ligne un schéma et non un fait divers.
Le camp qui gagne a joué 14 coups optimaux sur 15.

## Ligne complète

Le taux de victoire est celui de **X** (premier joueur) : il monte si l'ouverture tient, il s'effondre si la défense renverse la partie.

| Demi-coup | Camp | Coup | Taux de victoire du trait | Écart au meilleur | Lecture |
|-----------|------|------|---------------------------|-------------------|---------|
| 0 | X | (3,3) | 57.5 % | 0.000 | optimal |
| 1 | O | (2,3) | 62.7 % | 0.046 | optimal |
| 2 | X | (3,2) | 55.2 % | 0.000 | optimal |
| 3 | O | (3,1) | 62.9 % | 0.000 | optimal |
| 4 | X | (2,2) | 56.8 % | 0.010 | optimal |
| 5 | O | (1,1) | 63.5 % | 0.000 | optimal |
| 6 | X | (2,1) | 58.6 % | 0.000 | optimal |
| 7 | O | (1,2) | 67.0 % | 0.000 | optimal |
| 8 | X | (1,3) | 59.8 % | 0.000 | optimal |
| 9 | O | (2,4) | 100.0 % | 0.000 | optimal (exact) |
| 10 | X | (3,4) | 100.0 % | 0.000 | optimal (exact) |
| 11 | O | (3,5) | 100.0 % | 0.000 | optimal (exact) |
| 12 | X | (4,5) | 100.0 % | 0.000 | optimal (exact) |
| 13 | O | (5,4) | 100.0 % | 0.000 | optimal (exact) |
| 14 | X | (4,3) | 100.0 % | 0.000 | optimal (exact) |
| 15 | O | (4,2) | 100.0 % | 0.000 | optimal (exact) |
| 16 | X | (5,2) | 100.0 % | 0.000 | optimal (exact) |
| 17 | O | (6,1) | 100.0 % | 0.000 | optimal (exact) |
| 18 | X | (5,0) | 100.0 % | 0.000 | optimal (exact) |
| 19 | O | (5,1) | 100.0 % | 0.000 | optimal (exact) |
| 20 | X | (6,2) | 100.0 % | 0.000 | optimal (exact) |
| 21 | O | (6,3) | 100.0 % | 0.000 | optimal (exact) |
| 22 | X | (6,4) | 100.0 % | 0.000 | optimal (exact) |
| 23 | O | (6,5) | 100.0 % | 0.000 | optimal (exact) |
| 24 | X | (6,6) | 100.0 % | 0.000 | optimal (exact) |
| 25 | O | (5,5) | 100.0 % | 0.000 | optimal (exact) |
| 26 | X | (4,4) | 55.6 % | 0.444 | +0.444 possible (exact) |
| 27 | O | (5,3) | 100.0 % | 0.000 | optimal (exact) |
| 28 | X | (1,0) | 100.0 % | 0.000 | optimal (exact) |

## Plateaux

Un plateau tous les 4 demi-coups (`#` = dernier coup joué).

### Demi-coup 0 — X joue (3,3)

```
      c0   c1   c2   c3   c4   c5   c6
  r0  .   .   .   .   .   .   .   
  r1  .   .   .   .   .   .   .   
  r2  .   .   .   .   .   .   .   
  r3  .   .   .   X#  .   .   .   
  r4  .   .   .   .   .   .   .   
  r5  .   .   .   .   .   .   .   
  r6  .   .   .   .   .   .   .   
```

### Demi-coup 4 — X joue (2,2)

```
      c0   c1   c2   c3   c4   c5   c6
  r0  .   .   .   .   .   .   .   
  r1  .   .   .   .   .   .   .   
  r2  .   .   X#  O   .   .   .   
  r3  .   O   X   X   .   .   .   
  r4  .   .   .   .   .   .   .   
  r5  .   .   .   .   .   .   .   
  r6  .   .   .   .   .   .   .   
```

### Demi-coup 8 — X joue (1,3)

```
      c0   c1   c2   c3   c4   c5   c6
  r0  .   .   .   .   .   .   .   
  r1  .   O   O   X#  .   .   .   
  r2  .   X   X   O   .   .   .   
  r3  .   O   X   X   .   .   .   
  r4  .   .   .   .   .   .   .   
  r5  .   .   .   .   .   .   .   
  r6  .   .   .   .   .   .   .   
```

### Demi-coup 12 — X joue (4,5)

```
      c0   c1   c2   c3   c4   c5   c6
  r0  .   .   .   .   .   .   .   
  r1  .   O   O   X   .   .   .   
  r2  .   X   X   O   O   .   .   
  r3  .   O   X   X   X   O   .   
  r4  .   .   .   .   .   X#  .   
  r5  .   .   .   .   .   .   .   
  r6  .   .   .   .   .   .   .   
```

### Demi-coup 16 — X joue (5,2)

```
      c0   c1   c2   c3   c4   c5   c6
  r0  .   .   .   .   .   .   .   
  r1  .   O   O   X   .   .   .   
  r2  .   X   X   O   O   .   .   
  r3  .   O   X   X   X   O   .   
  r4  .   .   O   X   .   X   .   
  r5  .   .   X#  .   O   .   .   
  r6  .   .   .   .   .   .   .   
```

### Demi-coup 20 — X joue (6,2)

```
      c0   c1   c2   c3   c4   c5   c6
  r0  .   .   .   .   .   .   .   
  r1  .   O   O   X   .   .   .   
  r2  .   X   X   O   O   .   .   
  r3  .   O   X   X   X   O   .   
  r4  .   .   O   X   .   X   .   
  r5  X   O   X   .   O   .   .   
  r6  .   O   X#  .   .   .   .   
```

### Demi-coup 24 — X joue (6,6)

```
      c0   c1   c2   c3   c4   c5   c6
  r0  .   .   .   .   .   .   .   
  r1  .   O   O   X   .   .   .   
  r2  .   X   X   O   O   .   .   
  r3  .   O   X   X   X   O   .   
  r4  .   .   O   X   .   X   .   
  r5  X   O   X   .   O   .   .   
  r6  .   O   X   O   X   O   X#  
```

### Demi-coup 28 — X joue (1,0)

```
      c0   c1   c2   c3   c4   c5   c6
  r0  .   .   .   .   .   .   .   
  r1  X#  O   O   X   .   .   .   
  r2  .   X   X   O   O   .   .   
  r3  .   O   X   X   X   O   .   
  r4  .   .   O   X   X   X   .   
  r5  X   O   X   O   O   O   .   
  r6  .   O   X   O   X   O   X   
```

## Comment lire ce schéma pour un cours

- La **position de départ** est un coup unique imposé : c'est l'ouverture à enseigner, sans variantes parasites.
- La colonne « écart au meilleur » dit ce qu'un joueur peut se permettre : les demi-coups marqués `optimal` sont ceux où il n'y avait rien de mieux à faire.
- Les taux de victoire sont des **estimations du moteur** converties en probabilité par la sigmoïde calibrée, sauf mention « exact » (verdict de la tablebase ou mat forcé) : à lire comme des tendances, pas comme des fréquences mesurées.

## Limites

- Une ligne unique ne prouve pas que l'ouverture gagne : elle prouve que la *meilleure défense connue* du moteur n'a pas suffi. Un schéma gagne en valeur quand plusieurs défenses différentes échouent de la même façon.
- Les analyses de milieu de partie sont des estimations profondes, pas des verdicts exacts ; seules les positions à 12 cases vides ou moins sont tranchées par la tablebase.
