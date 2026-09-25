# Vérifications en parties réelles

Ce dossier conserve les résultats de **vraies parties** jouées entre deux bots forts,
premier coup imposé, utilisés pour confronter le livre d'ouverture au terrain.

## Fichiers

| Fichier | Contenu |
|---------|---------|
| `verification_l6.json` | 10 ouvertures, 1 partie chacune, niveau 6. Donne le score du **second joueur** (celui qui subit l'ouverture), le nombre de défaites et de nulles. |

## Provenance

Ce fichier a été reconstruit depuis le bloc `verification_parties` de
`script/solver/opening_theory.json`, dont la source d'origine (`_tmp_sweep_l6.json`) était
un fichier temporaire supprimé. Les données sont celles du balayage réel ; seul le
conteneur a été remis au format attendu par `extract_opening_theory.py --sweep`.

## Utilité

Le livre donne une **espérance** ; ces parties donnent un **résultat**. L'écart entre les
deux mesure la capacité de la défense à convertir son espérance en points — c'est un
enseignement en soi, et c'est la raison pour laquelle cette table est conservée.

Attention : avec **une seule partie par ouverture**, ces chiffres sont anecdotiques. Ils
illustrent, ils ne démontrent pas. Pour conclure quoi que ce soit, il faudrait plusieurs
parties par ouverture.
