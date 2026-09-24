# Motifs des finales exactes

Généré le 2026-09-24T22:55:57 depuis `C:\Users\Lucien\Documents\Projet code\4mation\script\solver\data\tablebase.db`.

## Ce qui a été mesuré, et sur quoi

Une position n'est retenue que si son dernier coup porte bien une pierre adverse, que **tous** ses enfants sont présents en base et que la valeur déduite des enfants est celle qui est stockée. Ces trois conditions définissent une position « exploitable » : le sous-ensemble de la base où l'on peut raisonner de bout en bout. Les lignes écartées sont comptées, parce que leur part dit la qualité réelle de la couche.

| Cases vides | Lignes lues | Alias fantômes | Enfants manquants | Incohérentes | Exploitables |
|-------------|-------------|----------------|-------------------|--------------|--------------|
| 7 | 3,119 | 1,361 | 1,158 | 0 | 600 |
| 8 | 4,090 | 1,997 | 1,493 | 0 | 600 |
| 9 | 4,035 | 1,820 | 1,615 | 0 | 600 |
| 10 | 4,357 | 2,126 | 1,631 | 0 | 600 |
| 11 | 4,211 | 1,905 | 1,706 | 0 | 600 |

Sur l'ensemble de l'échantillon, **0 position(s) incohérente(s)** : aucune valeur déduite ne contredit la valeur stockée. C'est une vérification indépendante de l'audit Rust — deux chemins de calcul, même verdict.

## Volumétrie des couches touchées

| Cases vides | Positions en base | Victoires du trait | Nulles | Défaites |
|-------------|-------------------|--------------------|--------|----------|
| 7 | 12,944,110 | 8,624,281 | 2,281,726 | 2,038,103 |
| 8 | 1,459,993 | 924,484 | 240,995 | 294,514 |
| 9 | 1,621,337 | 1,192,138 | 90,070 | 339,129 |
| 10 | 2,288,206 | 1,634,155 | 64,234 | 589,817 |
| 11 | 2,248,413 | 1,656,810 | 25,918 | 565,685 |

## Qui conclut, et qui joue la vraie finale

`trait conclut` : le trait a une case d'alignement **jouable** — il gagne sur le champ. `adversaire conclut` : quoi que joue le trait, l'adversaire a ensuite une case d'alignement jouable. `bataille` : ni l'un ni l'autre — la position se joue.

| Case | Positions | Victoires du trait | Nulles | Défaites |
|------|-----------|--------------------|--------|----------|
| trait conclut | 480 | 480 | 0 | 0 |
| adversaire conclut | 1559 | 0 | 0 | 1559 |
| **bataille** | 961 | 479 | 271 | 211 |

## Règles enseignables, mesurées

- **Contrôle — quand le trait peut conclure, il conclut** : 480 victoire(s) sur 480 positions où une case d'alignement était jouable (100 % : la base ne se contredit pas).
- **Contrôle — quand l'adversaire conclut quoi qu'il arrive, on perd** : 1559 défaite(s) sur 1559 positions (100 %).
- **La vraie finale est la bataille** : quand ni le trait ni l'adversaire ne peut conclure, le trait gagne 50 % du temps, fait nulle 28 % et perd 22 % (961 positions). C'est le terrain des exercices.
- **La fourchette est le moteur des gains construits** : sur 479 gains sans conclusion immédiate, 367 (77 %) passent par un coup qui crée au moins deux cases d'alignement d'un seul coup.
- **Le gain construit passe presque toujours par une menace** : sur 479 gains sans conclusion immédiate, 3 % en créent 0, 21 % en créent 1, 48 % en créent 2, 20 % en créent 3, 6 % en créent 4, 3 % en créent 5 case(s) d'alignement — une fourchette (deux menaces d'un seul coup) est le cas majoritaire.
- **Le gain a rarement une seule voie** : 224 positions à plusieurs coups gagnants contre 735 à coup gagnant unique — les exercices à solution unique se choisissent, ils ne sont pas la règle.
- **La menace fantôme n'est pas une exception** : dans 68 % des positions de bataille, l'adversaire a une case d'alignement **sur le plateau** alors que la position n'est pas perdue — cette case n'est pas jouable pour lui. C'est exactement ce que la leçon du site appelle une menace fantôme.

## Exercices tirés des finales

Positions exactes à **coup gagnant unique**, sans conclusion immédiate : il faut trouver l'idée, pas l'alignement. La ligne forcée est rejouée depuis la base, gain le plus rapide contre défense la plus tenace, et **chaque camp y tient son rôle** : le camp qui gagne ne joue que des coups gagnants, le camp qui perd résiste au maximum. Un exercice n'est retenu que si la ligne se termine bien sur un alignement du camp gagnant ; sinon la position est écartée, ce qui arrive dès qu'un trou de la base empêche de vérifier la suite.

Sur les **474** positions candidates, 12 ont été écartées parce qu'un trou de la base coupait la ligne, 0 parce que la base se contredisait, 6 comme quasi-doublons et 449 parce que leur motif était déjà représenté. Le premier chiffre mesure directement ce que les trous coûtent au matériel pédagogique.

### Exercice 1 — 7 cases vides, trait à X

Motif : **fourchette**. Ligne forcée vérifiée de **3** demi-coup(s) ; hauteur de preuve en base : 3. Coup gagnant unique : (3,1).

```
      c0   c1   c2   c3   c4   c5   c6
  r0  .  O  .  .  X  O  X 
  r1  O  O  X  O  X  O  O 
  r2  X  X  O# O  X  X  X 
  r3  .  .* X  X  O  .  O 
  r4  X  O  O  O  X  X  X 
  r5  O  X  O  X  O  O  O 
  r6  O  X  O  X  .  X  X 
```

*`*` = case où jouer (le coup à trouver), `#` = dernier coup joué.*

Ligne forcée (`#` = le coup qui fait quatre) : X(3,1) O(3,0) X(6,4)#

Le coup gagnant crée 3 case(s) d'alignement : l'adversaire ne peut pas parer les deux, le gain est forcé. Au départ, le trait n'a aucune case d'alignement jouable, et l'adversaire non plus : aucun des deux ne conclut sur-le-champ.

### Exercice 2 — 7 cases vides, trait à X

Motif : **fourchette**. Ligne forcée vérifiée de **3** demi-coup(s) ; hauteur de preuve en base : 3. Coup gagnant unique : (1,1).

```
      c0   c1   c2   c3   c4   c5   c6
  r0  O  O  X  O  X  O  X 
  r1  X  .* O  X  X  O  O 
  r2  O# O  .  X  O  .  X 
  r3  X  X  O  X  O  O  . 
  r4  .  O  .  O  X  X  X 
  r5  X  O  X  O  X  O  O 
  r6  X  O  X  .  X  O  X 
```

*`*` = case où jouer (le coup à trouver), `#` = dernier coup joué.*

Ligne forcée (`#` = le coup qui fait quatre) : X(1,1) O(2,2) X(4,0)#

Le coup gagnant crée 2 case(s) d'alignement : l'adversaire ne peut pas parer les deux, le gain est forcé. Au départ, le trait n'a aucune case d'alignement jouable, et l'adversaire non plus : aucun des deux ne conclut sur-le-champ.

### Exercice 3 — 7 cases vides, trait à X

Motif : **fourchette**. Ligne forcée vérifiée de **3** demi-coup(s) ; hauteur de preuve en base : 3. Coup gagnant unique : (1,3).

```
      c0   c1   c2   c3   c4   c5   c6
  r0  O  O  X  O# X  .  . 
  r1  X  X  O  .* X  O  O 
  r2  O  O  .  X  O  X  X 
  r3  X  X  O  X  O  O  . 
  r4  .  O  X  O  X  X  X 
  r5  X  O  X  O  X  O  O 
  r6  X  O  X  O  .  O  X 
```

*`*` = case où jouer (le coup à trouver), `#` = dernier coup joué.*

Ligne forcée (`#` = le coup qui fait quatre) : X(1,3) O(2,2) X(4,0)#

Le coup gagnant crée 2 case(s) d'alignement : l'adversaire ne peut pas parer les deux, le gain est forcé. Au départ, le trait n'a aucune case d'alignement jouable, et l'adversaire non plus : aucun des deux ne conclut sur-le-champ.

### Exercice 4 — 7 cases vides, trait à X

Motif : **menace unique**. Ligne forcée vérifiée de **3** demi-coup(s) ; hauteur de preuve en base : 3. Coup gagnant unique : (3,1).

```
      c0   c1   c2   c3   c4   c5   c6
  r0  O  O  O  X  X  O  X 
  r1  X  X  X  O  O  .  O 
  r2  .  O  O  .  X  X  O 
  r3  X  .* X  O  O  .  X 
  r4  .  X  O# X  X  O  O 
  r5  O  X  O  X  O  X  X 
  r6  X  .  O  X  O  X  O 
```

*`*` = case où jouer (le coup à trouver), `#` = dernier coup joué.*

Ligne forcée (`#` = le coup qui fait quatre) : X(3,1) O(4,0) X(6,1)#

Le coup gagnant crée 1 case(s) d'alignement : il doit parer, ce qui laisse le trait conclure. Au départ, le trait n'a aucune case d'alignement jouable, et l'adversaire non plus : aucun des deux ne conclut sur-le-champ.

### Exercice 5 — 7 cases vides, trait à X

Motif : **menace unique**. Ligne forcée vérifiée de **3** demi-coup(s) ; hauteur de preuve en base : 3. Coup gagnant unique : (5,0).

```
      c0   c1   c2   c3   c4   c5   c6
  r0  X  O  X  O  X  X  X 
  r1  O  O  .  X  O  O  . 
  r2  X  X  O  X  O  X  X 
  r3  O  O  X  X  O  X  O 
  r4  X  O# O  O  .  O  . 
  r5  .* X  O  X  O  X  O 
  r6  .  X  O  X  O  X  . 
```

*`*` = case où jouer (le coup à trouver), `#` = dernier coup joué.*

Ligne forcée (`#` = le coup qui fait quatre) : X(5,0) O(6,0) X(4,4)#

Le coup gagnant crée 1 case(s) d'alignement : il doit parer, ce qui laisse le trait conclure. Au départ, le trait n'a aucune case d'alignement jouable, et l'adversaire non plus : aucun des deux ne conclut sur-le-champ.

### Exercice 6 — 8 cases vides, trait à O

Motif : **menace unique**. Ligne forcée vérifiée de **3** demi-coup(s) ; hauteur de preuve en base : 3. Coup gagnant unique : (3,3).

```
      c0   c1   c2   c3   c4   c5   c6
  r0  X  O  .  X  .  X  O 
  r1  O  X  X  X  O  X  O 
  r2  O  O  O  X  O  X  O 
  r3  X  X  X# .* .  O  X 
  r4  O  O  X  O  X  O  X 
  r5  X  X  O  .  X  .  O 
  r6  O  .  .  X  O  O  X 
```

*`*` = case où jouer (le coup à trouver), `#` = dernier coup joué.*

Ligne forcée (`#` = le coup qui fait quatre) : O(3,3) X(3,4) O(5,5)#

Le coup gagnant crée 1 case(s) d'alignement : il doit parer, ce qui laisse le trait conclure. Au départ, le trait n'a aucune case d'alignement jouable, et l'adversaire non plus : aucun des deux ne conclut sur-le-champ.

### Exercice 7 — 10 cases vides, trait à O

Motif : **prise de tempo**. Ligne forcée vérifiée de **5** demi-coup(s) ; hauteur de preuve en base : 10. Coup gagnant unique : (5,6).

```
      c0   c1   c2   c3   c4   c5   c6
  r0  O  O  .  .  .  X  O 
  r1  X  X  X  O  X  O  X 
  r2  O  O  X  .  X  O  O 
  r3  X  O  X  O  .  O  X 
  r4  O  X  O  X  O  X  . 
  r5  X  .  O  X  O  X  .*
  r6  .  O  X  .  X  O  X#
```

*`*` = case où jouer (le coup à trouver), `#` = dernier coup joué.*

Ligne forcée (`#` = le coup qui fait quatre) : O(5,6) X(4,6) O(2,3) X(3,4) O(0,3)#

Le coup gagnant crée 0 case(s) d'alignement : le gain ne passe pas par une menace directe mais par le tempo. Au départ, le trait n'a aucune case d'alignement jouable, et l'adversaire non plus : aucun des deux ne conclut sur-le-champ.

## Limites

- Le census porte sur un **échantillon** de chaque couche, et seulement sur les positions exploitables : les pourcentages sont des mesures sur ce sous-ensemble.
- Une case d'alignement peut être géométriquement libre et pourtant injouable : c'est justement ce que le découpage « trait conclut / adversaire conclut / bataille » sépare, en testant la jouabilité à chaque coup.
- Les positions dont un enfant manque à la base (trou) sont écartées du census, sinon les trous se liraient comme des défaites.
- La distance annoncée est la longueur de la ligne forcée rejouée depuis la base ; la hauteur de preuve stockée est un majorant plus pessimiste.
