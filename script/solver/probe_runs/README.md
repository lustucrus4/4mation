# Mesures de la sonde d'ouverture

Ce dossier conserve les **preuves brutes** des mesures d'ouverture, pour qu'on puisse
les revérifier sans relancer de calcul.

## Fichiers

| Fichier | Contenu |
|---------|---------|
| `passe_longue.log` | Journal brut d'une passe de la sonde avec 600 s de budget par ouverture. Six ouvertures ont été mesurées avant l'arrêt de la passe. Encodage d'origine : UTF-16 (redirection PowerShell), accents normalisés. |
| `stability.json` | Résultat de `compare_probe_passes.py` : comparaison des passes, écart par ouverture, et conclusion sur la reproductibilité. |

## Pourquoi ces fichiers existent

La sonde `probe_opening_proof.py` chiffre chaque premier coup avec un **budget de temps**.
Un budget, ce n'est pas une preuve : deux passes peuvent donner des scores différents sur
la même position. Comparer les passes est donc obligatoire avant de publier un chiffre
dans un cours.

Mesure du 2026-09-25 : sur six ouvertures mesurées deux fois (90 s puis 600 s), **quatre
varient de plus de 20 points** et cinq changent carrément de signe. Exemple : `(1,2)` vaut
−42 puis +5. L'ordre du classement est entièrement rebattu. Conclusion : **aucun
classement d'ouvertures ne doit être publié** ; seul le gain forcé du centre est démontré.

## Reproduire la comparaison

```bash
python script/solver/compare_probe_passes.py \
  --passe "courte=script/solver/preuve_profonde.json" \
  --passe "longue=script/solver/probe_runs/passe_longue.log"
```

L'outil ne lance aucun calcul : il ne fait que relire des fichiers déjà présents.

## Passe courte

`preuve_profonde.json` (à la racine de `script/solver/`) est la passe courte : les 10
ouvertures, 90 s de budget par coup. C'est elle qui alimente la leçon « Ouvertures » du
site, uniquement pour la **profondeur atteinte** et la **meilleure réponse connue** — pas
pour un classement.
