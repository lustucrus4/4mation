# Vérification d'un schéma gagnant contre plusieurs défenses

Ouverture (3,3), 6 partie(s), analyse à la profondeur 20 pendant 1500 ms. L'attaque joue toujours son meilleur coup ; la défense tire à chaque tour dans ses 6 meilleurs coups.

## Résultat par partie

| Partie | Vainqueur | Demi-coups | Rangs défensifs tirés | Taux final du trait |
|--------|-----------|------------|----------------------|---------------------|
| 1 | X | 9 | 2 0 0 4 | 100 % |
| 2 | X | 7 | 2 3 3 | 100 % |
| 3 | X | 9 | 4 2 1 5 | 100 % |
| 4 | X | 7 | 1 2 3 | 100 % |
| 5 | X | 7 | 0 1 4 | 100 % |
| 6 | X | 17 | 3 0 0 0 3 1 0 4 | 100 % |

## Lignes jouées

Chaque ligne part de l'ouverture imposée. `Xn,m` = coup du premier joueur, `On,m` = coup du second joueur, au format `ligne,colonne` (0 à 6).

- **1** (X, 9 demi-coups) : X3,3 O4,2 X3,2 O3,1 X2,2 O2,3 X3,4 O2,5 X3,5
- **2** (X, 7 demi-coups) : X3,3 O4,2 X3,2 O2,2 X3,1 O2,0 X3,0
- **3** (X, 9 demi-coups) : X3,3 O3,2 X2,3 O1,4 X1,3 O2,2 X3,1 O4,2 X4,3
- **4** (X, 7 demi-coups) : X3,3 O2,4 X2,3 O1,2 X1,3 O0,2 X0,3
- **5** (X, 7 demi-coups) : X3,3 O2,2 X2,3 O3,4 X4,3 O5,2 X5,3
- **6** (X, 17 demi-coups) : X3,3 O4,4 X3,4 O3,5 X2,4 O1,5 X0,4 O1,4 X2,3 O1,2 X1,3 O2,2 X3,1 O3,0 X4,1 O4,2 X3,2

## Ligne la plus courte

Partie 2, gagnée par X en 7 demi-coups — la ligne la plus directe, celle qu'un cours peut montrer telle quelle.

**0. X joue `3,3`**

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

**1. O joue `4,2`** — rang 2, évaluation avant le coup 42 %

```
      c0   c1   c2   c3   c4   c5   c6
  r0  .   .   .   .   .   .   .   
  r1  .   .   .   .   .   .   .   
  r2  .   .   .   .   .   .   .   
  r3  .   .   .   X   .   .   .   
  r4  .   .   O#  .   .   .   .   
  r5  .   .   .   .   .   .   .   
  r6  .   .   .   .   .   .   .   
```

**2. X joue `3,2`** — rang 0, évaluation avant le coup 63 %

```
      c0   c1   c2   c3   c4   c5   c6
  r0  .   .   .   .   .   .   .   
  r1  .   .   .   .   .   .   .   
  r2  .   .   .   .   .   .   .   
  r3  .   .   X#  X   .   .   .   
  r4  .   .   O   .   .   .   .   
  r5  .   .   .   .   .   .   .   
  r6  .   .   .   .   .   .   .   
```

**3. O joue `2,2`** — rang 3, évaluation avant le coup 0 %

```
      c0   c1   c2   c3   c4   c5   c6
  r0  .   .   .   .   .   .   .   
  r1  .   .   .   .   .   .   .   
  r2  .   .   O#  .   .   .   .   
  r3  .   .   X   X   .   .   .   
  r4  .   .   O   .   .   .   .   
  r5  .   .   .   .   .   .   .   
  r6  .   .   .   .   .   .   .   
```

**4. X joue `3,1`** — rang 0, évaluation avant le coup 100 %

```
      c0   c1   c2   c3   c4   c5   c6
  r0  .   .   .   .   .   .   .   
  r1  .   .   .   .   .   .   .   
  r2  .   .   O   .   .   .   .   
  r3  .   X#  X   X   .   .   .   
  r4  .   .   O   .   .   .   .   
  r5  .   .   .   .   .   .   .   
  r6  .   .   .   .   .   .   .   
```

**5. O joue `2,0`** — rang 3, évaluation avant le coup 0 %

```
      c0   c1   c2   c3   c4   c5   c6
  r0  .   .   .   .   .   .   .   
  r1  .   .   .   .   .   .   .   
  r2  O#  .   O   .   .   .   .   
  r3  .   X   X   X   .   .   .   
  r4  .   .   O   .   .   .   .   
  r5  .   .   .   .   .   .   .   
  r6  .   .   .   .   .   .   .   
```

**6. X joue `3,0`** — rang 0, évaluation avant le coup 100 %

```
      c0   c1   c2   c3   c4   c5   c6
  r0  .   .   .   .   .   .   .   
  r1  .   .   .   .   .   .   .   
  r2  O   .   O   .   .   .   .   
  r3  X#  X   X   X   .   .   .   
  r4  .   .   O   .   .   .   .   
  r5  .   .   .   .   .   .   .   
  r6  .   .   .   .   .   .   .   
```

## Verdict

Répartition : 6 victoire(s) du premier joueur, 0 du second, 0 nulle(s), sur 6 partie(s) dont 6 défense(s) distincte(s).

**Schéma robuste** : aucune des défenses essayées n'a tenu, et plusieurs d'entre elles sont distinctes. Le gain ne dépend pas d'une imprécision particulière de la défense.

## Limites

- Le tirage porte sur les meilleurs coups du moteur, pas sur tous les coups légaux : une défense *exotique* qui tiendrait n'est pas testée. Le verdict porte donc sur les défenses fortes, ce qui est l'usage d'un cours.
- Les taux de victoire sont des estimations du moteur (sigmoïde calibrée) : ils servent à classer les coups, pas à mesurer une fréquence.
