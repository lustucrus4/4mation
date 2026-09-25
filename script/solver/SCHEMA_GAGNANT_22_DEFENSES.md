# Vérification d'un schéma gagnant contre plusieurs défenses

Ouverture (2,2), 8 partie(s), analyse à la profondeur 20 pendant 1500 ms. L'attaque joue toujours son meilleur coup ; la défense tire à chaque tour dans ses 3 meilleurs coups.

## Résultat par partie

| Partie | Vainqueur | Demi-coups | Rangs défensifs tirés | Taux final du trait |
|--------|-----------|------------|----------------------|---------------------|
| 1 | X | 17 | 1 2 1 1 2 0 0 2 | 100 % |
| 2 | X | 7 | 1 2 2 | 100 % |
| 3 | X | 21 | 0 0 1 1 0 0 2 2 2 0 | 100 % |
| 4 | X | 9 | 2 1 1 2 | 100 % |
| 5 | X | 7 | 2 2 2 | 100 % |
| 6 | X | 19 | 0 2 0 0 0 0 0 0 2 | 100 % |
| 7 | X | 11 | 0 1 1 1 2 | 100 % |
| 8 | X | 13 | 0 2 0 1 1 0 | 100 % |

## Lignes jouées

Chaque ligne part de l'ouverture imposée. `Xn,m` = coup du premier joueur, `On,m` = coup du second joueur, au format `ligne,colonne` (0 à 6).

- **1** (X, 17 demi-coups) : X2,2 O2,3 X3,3 O3,4 X4,4 O3,5 X2,4 O1,5 X2,5 O1,6 X0,6 O0,5 X1,4 O0,3 X1,3 O0,2 X1,1
- **2** (X, 7 demi-coups) : X2,2 O2,3 X3,2 O3,1 X4,2 O4,1 X5,2
- **3** (X, 21 demi-coups) : X2,2 O3,3 X2,4 O2,3 X1,3 O1,4 X0,4 O1,5 X0,5 O0,6 X1,6 O2,5 X3,5 O4,4 X5,3 O6,2 X5,2 O5,1 X4,2 O4,3 X3,2
- **4** (X, 9 demi-coups) : X2,2 O3,2 X4,3 O3,4 X3,3 O2,4 X2,3 O1,2 X1,3
- **5** (X, 7 demi-coups) : X2,2 O3,2 X2,3 O1,3 X2,4 O1,4 X2,5
- **6** (X, 19 demi-coups) : X2,2 O3,3 X2,4 O3,5 X2,5 O1,6 X0,6 O0,5 X0,4 O1,5 X1,4 O0,3 X1,3 O0,2 X0,1 O0,0 X1,0 O2,0 X3,1
- **7** (X, 11 demi-coups) : X2,2 O3,3 X2,4 O2,5 X3,4 O4,3 X4,4 O3,5 X2,6 O1,5 X1,4
- **8** (X, 13 demi-coups) : X2,2 O3,3 X2,4 O3,5 X2,5 O1,6 X0,6 O1,5 X0,4 O0,3 X1,4 O2,3 X3,4

## Ligne la plus courte

Partie 2, gagnée par X en 7 demi-coups — la ligne la plus directe, celle qu'un cours peut montrer telle quelle.

**0. X joue `2,2`**

```
      c0   c1   c2   c3   c4   c5   c6
  r0  .   .   .   .   .   .   .   
  r1  .   .   .   .   .   .   .   
  r2  .   .   X#  .   .   .   .   
  r3  .   .   .   .   .   .   .   
  r4  .   .   .   .   .   .   .   
  r5  .   .   .   .   .   .   .   
  r6  .   .   .   .   .   .   .   
```

**1. O joue `2,3`** — rang 1, évaluation avant le coup 48 %

```
      c0   c1   c2   c3   c4   c5   c6
  r0  .   .   .   .   .   .   .   
  r1  .   .   .   .   .   .   .   
  r2  .   .   X   O#  .   .   .   
  r3  .   .   .   .   .   .   .   
  r4  .   .   .   .   .   .   .   
  r5  .   .   .   .   .   .   .   
  r6  .   .   .   .   .   .   .   
```

**2. X joue `3,2`** — rang 0, évaluation avant le coup 56 %

```
      c0   c1   c2   c3   c4   c5   c6
  r0  .   .   .   .   .   .   .   
  r1  .   .   .   .   .   .   .   
  r2  .   .   X   O   .   .   .   
  r3  .   .   X#  .   .   .   .   
  r4  .   .   .   .   .   .   .   
  r5  .   .   .   .   .   .   .   
  r6  .   .   .   .   .   .   .   
```

**3. O joue `3,1`** — rang 2, évaluation avant le coup 47 %

```
      c0   c1   c2   c3   c4   c5   c6
  r0  .   .   .   .   .   .   .   
  r1  .   .   .   .   .   .   .   
  r2  .   .   X   O   .   .   .   
  r3  .   O#  X   .   .   .   .   
  r4  .   .   .   .   .   .   .   
  r5  .   .   .   .   .   .   .   
  r6  .   .   .   .   .   .   .   
```

**4. X joue `4,2`** — rang 0, évaluation avant le coup 59 %

```
      c0   c1   c2   c3   c4   c5   c6
  r0  .   .   .   .   .   .   .   
  r1  .   .   .   .   .   .   .   
  r2  .   .   X   O   .   .   .   
  r3  .   O   X   .   .   .   .   
  r4  .   .   X#  .   .   .   .   
  r5  .   .   .   .   .   .   .   
  r6  .   .   .   .   .   .   .   
```

**5. O joue `4,1`** — rang 2, évaluation avant le coup 0 %

```
      c0   c1   c2   c3   c4   c5   c6
  r0  .   .   .   .   .   .   .   
  r1  .   .   .   .   .   .   .   
  r2  .   .   X   O   .   .   .   
  r3  .   O   X   .   .   .   .   
  r4  .   O#  X   .   .   .   .   
  r5  .   .   .   .   .   .   .   
  r6  .   .   .   .   .   .   .   
```

**6. X joue `5,2`** — rang 0, évaluation avant le coup 100 %

```
      c0   c1   c2   c3   c4   c5   c6
  r0  .   .   .   .   .   .   .   
  r1  .   .   .   .   .   .   .   
  r2  .   .   X   O   .   .   .   
  r3  .   O   X   .   .   .   .   
  r4  .   O   X   .   .   .   .   
  r5  .   .   X#  .   .   .   .   
  r6  .   .   .   .   .   .   .   
```

## Verdict

Répartition : 8 victoire(s) du premier joueur, 0 du second, 0 nulle(s), sur 8 partie(s) dont 8 défense(s) distincte(s).

**Schéma robuste** : aucune des défenses essayées n'a tenu, et plusieurs d'entre elles sont distinctes. Le gain ne dépend pas d'une imprécision particulière de la défense.

## Limites

- Le tirage porte sur les meilleurs coups du moteur, pas sur tous les coups légaux : une défense *exotique* qui tiendrait n'est pas testée. Le verdict porte donc sur les défenses fortes, ce qui est l'usage d'un cours.
- Les taux de victoire sont des estimations du moteur (sigmoïde calibrée) : ils servent à classer les coups, pas à mesurer une fréquence.
