# Gain forcé après le premier coup central

Premier coup : **X en 3,3** (centre).
Verdict du moteur : **perte forcée du second joueur** (perte, mat en 28 demi-coups), prouvé en 27.6 s à la profondeur 28.

## La ligne principale

```
X3,3 O3,2 X2,3 O1,3 X2,2 O1,1 X1,2 O2,1 X3,1 O4,2 X4,3 O5,3 X5,4 O4,5 X3,4 O2,4 X2,5 O1,6 X0,5 O1,5 X2,6 O3,6 X4,6 O5,6 X6,6 O5,5 X6,4 O6,5 X0,1
```

`Xn,m` = coup du premier joueur, `On,m` = coup du second, format `ligne,colonne`.

## Déroulé, demi-coup par demi-coup

| # | Camp | Coup | Score | Verdict | Mat | Prof. | Coups légaux | Résistent | s |
| ---: | --- | --- | ---: | --- | ---: | ---: | ---: | ---: | ---: |
| 2 | O | 3,2 | -99972 | perte | 28 | 28 | 8 | 4/8 | 27.6 |
| 3 | X | 2,3 | 99973 | gain | 27 | 2 | 7 | 2/7 | 0.0 |
| 4 | O | 1,3 | -99974 | perte | 26 | 22 | 6 | 1/6 | 4.7 |
| 5 | X | 2,2 | 99975 | gain | 25 | 2 | 7 | 1/7 | 0.0 |
| 6 | O | 1,1 | -99976 | perte | 24 | 20 | 4 | 1/4 | 0.2 |
| 7 | X | 1,2 | 99977 | gain | 23 | 2 | 7 | 1/7 | 0.0 |
| 8 | O | 2,1 | -99978 | perte | 22 | 20 | 4 | 1/4 | 0.4 |
| 9 | X | 3,1 | 99979 | gain | 21 | 2 | 4 | 1/4 | 0.0 |
| 10 | O | 4,2 | -99980 | perte | 20 | 18 | 5 | 1/5 | 0.2 |
| 11 | X | 4,3 | 99981 | gain | 19 | 2 | 5 | 1/5 | 0.0 |
| 12 | O | 5,3 | -99982 | perte | 18 | 10 | 5 | 1/5 | 0.0 |
| 13 | X | 5,4 | 99983 | gain | 17 | 2 | 6 | 1/6 | 0.0 |
| 14 | O | 4,5 | -99984 | perte | 16 | 12 | 6 | 1/6 | 0.0 |
| 15 | X | 3,4 | 99985 | gain | 15 | 2 | 7 | 1/7 | 0.0 |
| 16 | O | 2,4 | -99986 | perte | 14 | 12 | 4 | 1/4 | 0.0 |
| 17 | X | 2,5 | 99987 | gain | 13 | 2 | 4 | 1/4 | 0.0 |
| 18 | O | 1,6 | -99988 | perte | 12 | 8 | 6 | 1/6 | 0.0 |
| 19 | X | 0,5 | 99989 | gain | 11 | 2 | 4 | 1/4 | 0.0 |
| 20 | O | 1,5 | -99990 | perte | 10 | 6 | 4 | 1/4 | 0.0 |
| 21 | X | 2,6 | 99991 | gain | 9 | 5 | 4 | 1/4 | 0.0 |
| 22 | O | 3,6 | -99992 | perte | 8 | 4 | 2 | 1/2 | 0.0 |
| 23 | X | 4,6 | 99993 | gain | 7 | 2 | 2 | 1/2 | 0.0 |
| 24 | O | 5,6 | -99994 | perte | 6 | 4 | 3 | 1/3 | 0.0 |
| 25 | X | 6,6 | 99995 | gain | 5 | 2 | 3 | 1/3 | 0.0 |
| 26 | O | 5,5 | -99996 | perte | 4 | 4 | 2 | 2/2 | 0.0 |
| 27 | X | 6,4 | 99997 | gain | 3 | 2 | 3 | 1/3 | 0.0 |
| 28 | O | 6,5 | -99998 | perte | 2 | 2 | 2 | 2/2 | 0.0 |
| 29 | X | 0,1 | 99999 | gain | 1 | 1 | 17 | 3/17 | 0.0 |

Total : 62 111 446 nœuds sur 28 demi-coups analysés.

## Lecture

La colonne « Résistent » donne le nombre de coups de défense qui retardent le mat autant que le meilleur coup (sur le nombre de coups légaux). Plus ce nombre est petit, plus la défense est contrainte ; le verdict final ne dépend d'aucune faute de l'adversaire puisque **tous** ses coups perdent.

## Positions clés

Après X 3,3 (demi-coup 1) :

    0 1 2 3 4 5 6
0   .  .  .  .  .  .  . 
1   .  .  .  .  .  .  . 
2   .  .  .  .  .  .  . 
3   .  .  . (X) .  .  . 
4   .  .  .  .  .  .  . 
5   .  .  .  .  .  .  . 
6   .  .  .  .  .  .  . 

Après O 4,2 (demi-coup 10) :

    0 1 2 3 4 5 6
0   .  .  .  .  .  .  . 
1   .  O  X  O  .  .  . 
2   .  O  X  X  .  .  . 
3   .  X  O  X  .  .  . 
4   .  . (O) .  .  .  . 
5   .  .  .  .  .  .  . 
6   .  .  .  .  .  .  . 

Après X 0,5 (demi-coup 19) :

    0 1 2 3 4 5 6
0   .  .  .  .  . (X) . 
1   .  O  X  O  .  .  O 
2   .  O  X  X  O  X  . 
3   .  X  O  X  X  .  . 
4   .  .  O  X  .  O  . 
5   .  .  .  O  X  .  . 
6   .  .  .  .  .  .  . 

Après O 6,5 (demi-coup 28) :

    0 1 2 3 4 5 6
0   .  .  .  .  .  X  . 
1   .  O  X  O  .  O  O 
2   .  O  X  X  O  X  X 
3   .  X  O  X  X  .  O 
4   .  .  O  X  .  O  X 
5   .  .  .  O  X  O  O 
6   .  .  .  .  X (O) X 

Alignement final pour le joueur 1. Le premier joueur gagne.
