# Théorie d'ouverture

Extraite du livre d'ouverture évalué par `4mation-engine` (2026-09-25T08:34:46, demi-coups 0 à 6).

Deux natures de valeurs, jamais confondues : **prouvé** (`exact=1`, mat forcé ou verdict de la tablebase) et **estimé** (évaluation du moteur convertie en taux de victoire par une sigmoïde calibrée, échelle 281).

## Position de départ

| Mesure | Valeur |
|--------|--------|
| Meilleur coup | (3, 3) |
| Score espéré du 1ᵉʳ joueur (V=1, N=0,5) | 100.0 % |
| Lecture | prouvé |
| Nature | prouvé |

Une position **prouvée gagnante** affiche 100 % par convention : ce n'est pas une estimation, c'est un verdict (gain forcé, quoi que joue l'adversaire).

## Les 10 ouvertures uniques

Le plateau est symétrique (rotations et miroir) : ces dix coups couvrent les 49 cases de départ. Un seul est **démontré** ; les neuf autres sont **estimés** et doivent se lire avec la section « Fiabilité des chiffres ».

### Coups démontrés

| Case | Taille d'orbite | Verdict | Meilleure réponse |
|------|-----------------|---------|-------------------|
| (3, 3) | 1 | prouvé | (3, 2) |

### Coups estimés (aucun n'est départagé par nos mesures)

| Case | Taille d'orbite | Score espéré (1ᵉʳ joueur) | Écart au meilleur estimé | Meilleure réponse |
|------|-----------------|----------------------------|--------------------------|-------------------|
| (2, 3) | 4 | 55.0 % | 0.0 % | (3, 3) |
| (1, 3) | 4 | 54.5 % | 0.4 % | (2, 3) |
| (1, 2) | 8 | 52.8 % | 2.1 % | (2, 3) |
| (1, 1) | 4 | 52.5 % | 2.5 % | (1, 2) |
| (2, 2) | 4 | 52.3 % | 2.6 % | (3, 3) |
| (0, 0) | 4 | 51.9 % | 3.1 % | (1, 1) |
| (0, 2) | 8 | 51.8 % | 3.2 % | (1, 3) |
| (0, 3) | 4 | 51.5 % | 3.4 % | (1, 3) |
| (0, 1) | 8 | 47.5 % | 7.4 % | (1, 2) |

Les écarts de ce second tableau portent sur des estimations non reproductibles : ils ne doivent pas servir à classer les coups.

## Ligne principale

Meilleur jeu supposé des deux camps, demi-coup par demi-coup.

| Demi-coup | Camp | Coup | Score espéré (1ᵉʳ joueur) | Lecture |
|-----------|------|------|----------------------------|---------|
| 0 | 1 | (3, 3) | 100.0 % | prouvé |
| 1 | 2 | (3, 2) | 100.0 % | prouvé |
| 2 | 1 | (2, 3) | 100.0 % | prouvé |
| 3 | 2 | (1, 3) | 100.0 % | prouvé |
| 4 | 1 | (2, 2) | 100.0 % | prouvé |
| 5 | 2 | (1, 1) | 100.0 % | prouvé |
| 6 | 1 | (1, 2) | 100.0 % | prouvé |

## Alternatives après le premier coup

- **(2, 3)** (55.0 %) : (3, 3) (2, 4) (1, 3) (0, 4) (1, 4) (1, 5)
- **(1, 3)** (54.5 %) : (3, 2) (2, 1) (1, 1) (2, 2) (1, 3) (2, 3)
- **(1, 2)** (52.8 %) : (4, 3) (5, 3) (5, 2) (4, 2) (3, 1) (2, 2)

## Vérification en parties réelles

Le livre est une évaluation ; voici ce que donnent de **vraies parties** entre deux bots forts, premier coup imposé. La colonne « partie » est le score du **second joueur** : c'est lui qui subit l'ouverture.

| Ouverture | Parties | Score du 2ᵉ joueur | Défaites | Nulles | Durée moyenne (demi-coups) | Score espéré du livre (1ᵉʳ joueur) |
|-----------|---------|--------------------|----------|--------|------------------------|----------------------------------------|
| (0, 0) | 1 | 100 % | 0 | 0 | — | 51.9 % |
| (0, 2) | 1 | 100 % | 0 | 0 | — | 51.8 % |
| (0, 1) | 1 | 50 % | 0 | 1 | — | 47.5 % |
| (0, 3) | 1 | 0 % | 1 | 0 | — | 51.5 % |
| (1, 1) | 1 | 0 % | 1 | 0 | — | 52.5 % |
| (1, 2) | 1 | 0 % | 1 | 0 | — | 52.8 % |
| (1, 3) | 1 | 0 % | 1 | 0 | — | 54.5 % |
| (2, 2) | 1 | 0 % | 1 | 0 | — | 52.3 % |
| (2, 3) | 1 | 0 % | 1 | 0 | — | 55.0 % |
| (3, 3) | 1 | 0 % | 1 | 0 | — | 100.0 % |

Un écart entre les deux colonnes n'est pas une contradiction : le livre note une **espérance** (une position perdue peut encore rapporter un demi-point si l'adversaire se trompe), la partie note un **résultat**. L'écart mesure donc la capacité de la défense à convertir son espérance en points — c'est exactement ce qu'un cours doit enseigner.

## Fiabilité des chiffres

Les valeurs de ce document ne sont pas des preuves : elles viennent d'une recherche arrêtée par un budget de temps. Les mêmes ouvertures ont été chiffrées plusieurs fois pour vérifier si elles tiennent.

| Ouverture | courte | longue | Écart | Lecture |
|-----------|---------|---------|---------|---------|
| (0, 0) | -5 | 42 | 47 | **instable** |
| (0, 1) | -13 | 30 | 43 | **instable** |
| (0, 2) | 22 | 30 | 8 | stable |
| (0, 3) | -39 | 16 | 55 | **instable** |
| (1, 1) | 5 | -2 | 7 | signe instable (amplitude faible) |
| (1, 2) | -42 | 5 | 47 | **instable** |

**Conclusion :** les scores ne sont pas reproductibles : 4 ouverture(s) sur 6 varient de plus de 20 points entre deux passes (5 changent même de signe) et l'ordre du classement change. Aucun classement ne doit être publié ; seule la valeur prouvée du centre est enseignable.

Reproduire cette mesure : `python script/solver/compare_probe_passes.py --passe libellé=fichier …`

## Seuils de lecture

| Bande | Score moteur | Score espéré | Ce que ça veut dire |
|-------|--------------|--------------|---------------------|
| Favorable | ≥ +40 | ≥ 0,54 | le camp au trait a mieux que la moyenne |
| Équilibré | entre −40 et +40 | 0,46 – 0,54 | position sans avantage net |
| Défavorable | ≤ −40 | ≤ 0,46 | le camp au trait subit |

Le seuil de ±40 points vient de la table de fiabilité du calibrage : c'est l'écart à partir duquel la prédiction s'écarte vraiment de 0,50.

| Score | n | Prédit | Observé sur les finales exactes |
|-------|---|--------|--------------------------------|
| -200 → -100 | 9 | 0.388 | 0.389 |
| -100 → -40 | 10 | 0.442 | 0.450 |
| -40 → 40 | 62 | 0.501 | 0.516 |
| 40 → 100 | 8 | 0.564 | 0.500 |
| 100 → 200 | 2 | 0.634 | 0.750 |

## Couverture du livre

| Demi-coup | Entrées | dont prouvées |
|-----------|---------|---------------|
| 0 | 1 | 1 |
| 1 | 10 | 1 |
| 2 | 45 | 1 |
| 3 | 233 | 1 |
| 4 | 1077 | 38 |
| 5 | 5612 | 198 |
| 6 | 26175 | 2754 |

## Avertissements

- alt [2, 3] : ligne principale : 4 demi-coup(s) lu(s) après transport par symétrie

## Conseils prêts pour un cours

- **Commencer au centre** : (3, 3) est **démontré gagnant**. C'est la seule valeur de ce document qu'un cours peut affirmer sans réserve.
- **Ne pas publier de classement** : 4 ouverture(s) changent de plus de 20 points de score entre deux passes de la sonde, et l'ordre du classement se réorganise. Ces scores servent à explorer, pas à classer.
- **Le premier coup ne décide pas la partie** : aucune des neuf ouvertures non centrales n'est démontrée perdante — un cours peut les présenter comme jouables.
- **Réponses au premier coup** (indicatif, non prouvé hors du centre) : (3, 3) → (3, 2) ; (2, 3) → (3, 3) ; (1, 3) → (2, 3) ; (1, 2) → (2, 3) ; (1, 1) → (1, 2).
- **Notion à enseigner** : la différence entre une valeur *prouvée* (mat forcé ou verdict de la tablebase) et une *estimation* — le centre et les neuf autres ouvertures illustrent les deux cas dans la même table.

## Limites

- La valeur chiffrée est un **score espéré** (victoire = 1, nulle = 0,5, défaite = 0) : c'est la cible sur laquelle la sigmoïde a été calibrée. Ce n'est pas une probabilité de victoire ; dans un jeu où la nulle est fréquente, les deux chiffres diffèrent nettement.
- Au-delà des positions prouvées, les scores sont des estimations du moteur, pas des résultats exacts. Ils servent à **explorer** une position, pas à classer les coups (la section « Fiabilité des chiffres » montre qu'ils changent d'une passe à l'autre) ni à trancher une partie.
- La tablebase exacte couvre les finales (≤ 12 cases vides) ; l'ouverture reste hors de sa portée, c'est le livre qui l'évalue.
- Les coups sont donnés dans l'orientation du plateau de départ du livre ; pour lire une ligne, le script transporte chaque coup par la symétrie qui fait correspondre la position (voir `reorient`).
