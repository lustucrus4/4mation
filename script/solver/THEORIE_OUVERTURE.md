# Théorie d'ouverture

Extraite du livre d'ouverture évalué par `4mation-engine` (2026-09-24T23:01:20, demi-coups 0 à 6).

Deux natures de valeurs, jamais confondues : **prouvé** (`exact=1`, mat forcé ou verdict de la tablebase) et **estimé** (évaluation du moteur convertie en taux de victoire par une sigmoïde calibrée, échelle 281).

## Position de départ

| Mesure | Valeur |
|--------|--------|
| Meilleur coup | (3, 3) |
| Score espéré du 1ᵉʳ joueur (V=1, N=0,5) | 58.1 % |
| Lecture | équilibré |
| Nature | estimé |

## Les 10 ouvertures uniques

Le plateau est symétrique (rotations et miroir) : ces dix coups couvrent les 49 cases de départ.

| Case | Taille d'orbite | Score espéré (1ᵉʳ joueur) | Écart au meilleur | Meilleure réponse | Lecture | Nature |
|------|-----------------|----------------------------|-------------------|-------------------|---------|--------|
| (3, 3) | 1 | 58.1 % | 0.0 % | (2, 2) | équilibré | estimé |
| (2, 3) | 4 | 55.0 % | 3.1 % | (3, 3) | équilibré | estimé |
| (1, 3) | 4 | 54.5 % | 3.6 % | (2, 3) | équilibré | estimé |
| (1, 2) | 8 | 52.8 % | 5.3 % | (2, 3) | équilibré | estimé |
| (1, 1) | 4 | 52.5 % | 5.6 % | (1, 2) | équilibré | estimé |
| (2, 2) | 4 | 52.3 % | 5.8 % | (3, 3) | équilibré | estimé |
| (0, 0) | 4 | 51.9 % | 6.2 % | (1, 1) | équilibré | estimé |
| (0, 2) | 8 | 51.8 % | 6.3 % | (1, 3) | équilibré | estimé |
| (0, 3) | 4 | 51.5 % | 6.6 % | (1, 3) | équilibré | estimé |
| (0, 1) | 8 | 47.5 % | 10.6 % | (1, 2) | équilibré | estimé |

## Ligne principale

Meilleur jeu supposé des deux camps, demi-coup par demi-coup.

| Demi-coup | Camp | Coup | Score espéré (1ᵉʳ joueur) | Lecture |
|-----------|------|------|----------------------------|---------|
| 0 | 1 | (3, 3) | 58.1 % | équilibré |
| 1 | 2 | (2, 2) | 58.1 % | équilibré |
| 2 | 1 | (3, 2) | 54.0 % | équilibré |
| 3 | 2 | (4, 3) | 56.5 % | équilibré |
| 4 | 1 | (3, 4) | 54.2 % | équilibré |
| 5 | 2 | (3, 5) | 61.6 % | équilibré |
| 6 | 1 | (2, 4) | 56.2 % | équilibré |

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
| (3, 3) | 1 | 0 % | 1 | 0 | — | 58.1 % |

Un écart entre les deux colonnes n'est pas une contradiction : le livre note une **espérance** (une position perdue peut encore rapporter un demi-point si l'adversaire se trompe), la partie note un **résultat**. L'écart mesure donc la capacité de la défense à convertir son espérance en points — c'est exactement ce qu'un cours doit enseigner.

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
| 0 | 1 | 0 |
| 1 | 10 | 0 |
| 2 | 45 | 0 |
| 3 | 233 | 0 |
| 4 | 1077 | 37 |
| 5 | 5612 | 197 |
| 6 | 26175 | 2753 |

## Avertissements

- ligne principale : 5 demi-coup(s) lu(s) après transport par symétrie
- alt [2, 3] : ligne principale : 4 demi-coup(s) lu(s) après transport par symétrie

## Conseils prêts pour un cours

- **Commencer au centre** : (3, 3) donne le meilleur score espéré du premier joueur (58.1 %).
- **Le premier coup ne décide pas la partie** : les dix ouvertures uniques tiennent dans 10.6 points de score espéré, et aucune n'est classée perdante par le moteur.
- **Le coup le plus faible** est (0, 1) (47.5 %), soit 10.6 % de moins que le meilleur : de quoi l'écarter, pas de quoi perdre sur-le-champ.
- **Réponses au premier coup** : (3, 3) → (2, 2) ; (2, 3) → (3, 3) ; (1, 3) → (2, 3) ; (1, 2) → (2, 3) ; (1, 1) → (1, 2).
- **Aucune ouverture n'est prouvée à ce jour** : tout ce tableau est une estimation du moteur, à présenter comme telle.
- **Notion à enseigner** : la différence entre une valeur *prouvée* (mat forcé ou verdict de la tablebase) et une *estimation* — le premier coup de la ligne principale illustre les deux cas.

## Limites

- La valeur chiffrée est un **score espéré** (victoire = 1, nulle = 0,5, défaite = 0) : c'est la cible sur laquelle la sigmoïde a été calibrée. Ce n'est pas une probabilité de victoire ; dans un jeu où la nulle est fréquente, les deux chiffres diffèrent nettement.
- Au-delà des positions prouvées, les scores sont des estimations du moteur, pas des résultats exacts : ils servent à classer les coups, pas à trancher une partie.
- La tablebase exacte couvre les finales (≤ 12 cases vides) ; l'ouverture reste hors de sa portée, c'est le livre qui l'évalue.
- Les coups sont donnés dans l'orientation du plateau de départ du livre ; pour lire une ligne, le script transporte chaque coup par la symétrie qui fait correspondre la position (voir `reorient`).
