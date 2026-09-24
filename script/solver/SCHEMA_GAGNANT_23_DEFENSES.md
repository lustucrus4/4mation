# Vérification d'un schéma gagnant contre plusieurs défenses

Ouverture (2,3), 8 partie(s), analyse à la profondeur 20 pendant 1500 ms. L'attaque joue toujours son meilleur coup ; la défense tire à chaque tour dans ses 3 meilleurs coups.

## Résultat par partie

| Partie | Vainqueur | Demi-coups | Rangs défensifs tirés | Taux final du trait |
|--------|-----------|------------|----------------------|---------------------|
| 1 | X | 7 | 1 2 1 | 100 % |
| 2 | X | 13 | 1 2 2 0 0 2 | 100 % |
| 3 | X | 13 | 1 2 2 0 0 1 | 100 % |
| 4 | X | 11 | 1 0 0 2 2 | 100 % |
| 5 | X | 9 | 2 0 2 1 | 100 % |
| 6 | X | 9 | 1 2 2 2 | 100 % |
| 7 | X | 23 | 2 0 2 0 2 0 0 0 0 0 2 | 100 % |
| 8 | X | 17 | 0 1 1 1 2 0 2 0 | 100 % |

## Lignes jouées

Chaque ligne part de l'ouverture imposée. `Xn,m` = coup du premier joueur, `On,m` = coup du second joueur, au format `ligne,colonne` (0 à 6).

- **1** (X, 7 demi-coups) : X2,3 O3,2 X3,3 O3,4 X4,3 O4,2 X5,3
- **2** (X, 13 demi-coups) : X2,3 O1,3 X2,2 O2,1 X3,2 O4,3 X3,4 O3,5 X2,4 O3,3 X4,2 O5,3 X5,2
- **3** (X, 13 demi-coups) : X2,3 O1,3 X2,4 O1,5 X1,4 O2,5 X3,4 O4,4 X3,3 O3,2 X4,3 O4,2 X5,3
- **4** (X, 11 demi-coups) : X2,3 O3,3 X3,2 O4,3 X3,4 O4,5 X4,4 O3,5 X2,4 O1,3 X1,4
- **5** (X, 9 demi-coups) : X2,3 O2,4 X3,3 O4,4 X3,4 O4,5 X3,5 O4,6 X3,6
- **6** (X, 9 demi-coups) : X2,3 O2,2 X3,2 O2,1 X3,1 O4,2 X3,3 O2,4 X3,4
- **7** (X, 23 demi-coups) : X2,3 O2,4 X3,4 O3,3 X4,2 O3,2 X4,3 O4,4 X4,5 O5,6 X5,5 O6,6 X6,5 O6,4 X5,3 O5,4 X6,3 O5,2 X4,1 O4,0 X3,1 O2,1 X1,2
- **8** (X, 17 demi-coups) : X2,3 O3,3 X3,2 O2,1 X2,2 O3,1 X4,1 O5,0 X5,1 O4,2 X5,3 O5,2 X4,3 O3,4 X2,4 O3,5 X2,5

## Ligne la plus courte

Partie 1, gagnée par X en 7 demi-coups — la ligne la plus directe, celle qu'un cours peut montrer telle quelle.

**0. X joue `2,3`**

```
      c0   c1   c2   c3   c4   c5   c6
  r0  .   .   .   .   .   .   .   
  r1  .   .   .   .   .   .   .   
  r2  .   .   .   X#  .   .   .   
  r3  .   .   .   .   .   .   .   
  r4  .   .   .   .   .   .   .   
  r5  .   .   .   .   .   .   .   
  r6  .   .   .   .   .   .   .   
```

**1. O joue `3,2`** — rang 1, évaluation avant le coup 42 %

```
      c0   c1   c2   c3   c4   c5   c6
  r0  .   .   .   .   .   .   .   
  r1  .   .   .   .   .   .   .   
  r2  .   .   .   X   .   .   .   
  r3  .   .   O#  .   .   .   .   
  r4  .   .   .   .   .   .   .   
  r5  .   .   .   .   .   .   .   
  r6  .   .   .   .   .   .   .   
```

**2. X joue `3,3`** — rang 0, évaluation avant le coup 55 %

```
      c0   c1   c2   c3   c4   c5   c6
  r0  .   .   .   .   .   .   .   
  r1  .   .   .   .   .   .   .   
  r2  .   .   .   X   .   .   .   
  r3  .   .   O   X#  .   .   .   
  r4  .   .   .   .   .   .   .   
  r5  .   .   .   .   .   .   .   
  r6  .   .   .   .   .   .   .   
```

**3. O joue `3,4`** — rang 2, évaluation avant le coup 0 %

```
      c0   c1   c2   c3   c4   c5   c6
  r0  .   .   .   .   .   .   .   
  r1  .   .   .   .   .   .   .   
  r2  .   .   .   X   .   .   .   
  r3  .   .   O   X   O#  .   .   
  r4  .   .   .   .   .   .   .   
  r5  .   .   .   .   .   .   .   
  r6  .   .   .   .   .   .   .   
```

**4. X joue `4,3`** — rang 0, évaluation avant le coup 100 %

```
      c0   c1   c2   c3   c4   c5   c6
  r0  .   .   .   .   .   .   .   
  r1  .   .   .   .   .   .   .   
  r2  .   .   .   X   .   .   .   
  r3  .   .   O   X   O   .   .   
  r4  .   .   .   X#  .   .   .   
  r5  .   .   .   .   .   .   .   
  r6  .   .   .   .   .   .   .   
```

**5. O joue `4,2`** — rang 1, évaluation avant le coup 0 %

```
      c0   c1   c2   c3   c4   c5   c6
  r0  .   .   .   .   .   .   .   
  r1  .   .   .   .   .   .   .   
  r2  .   .   .   X   .   .   .   
  r3  .   .   O   X   O   .   .   
  r4  .   .   O#  X   .   .   .   
  r5  .   .   .   .   .   .   .   
  r6  .   .   .   .   .   .   .   
```

**6. X joue `5,3`** — rang 0, évaluation avant le coup 100 %

```
      c0   c1   c2   c3   c4   c5   c6
  r0  .   .   .   .   .   .   .   
  r1  .   .   .   .   .   .   .   
  r2  .   .   .   X   .   .   .   
  r3  .   .   O   X   O   .   .   
  r4  .   .   O   X   .   .   .   
  r5  .   .   .   X#  .   .   .   
  r6  .   .   .   .   .   .   .   
```

## Verdict

Répartition : 8 victoire(s) du premier joueur, 0 du second, 0 nulle(s), sur 8 partie(s) dont 8 défense(s) distincte(s).

**Schéma robuste** : aucune des défenses essayées n'a tenu, et plusieurs d'entre elles sont distinctes. Le gain ne dépend pas d'une imprécision particulière de la défense.

## Limites

- Le tirage porte sur les meilleurs coups du moteur, pas sur tous les coups légaux : une défense *exotique* qui tiendrait n'est pas testée. Le verdict porte donc sur les défenses fortes, ce qui est l'usage d'un cours.
- Les taux de victoire sont des estimations du moteur (sigmoïde calibrée) : ils servent à classer les coups, pas à mesurer une fréquence.
