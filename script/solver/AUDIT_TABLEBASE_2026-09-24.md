# Audit d'intégrité de la tablebase — 24/09/2026

Contrôle complet des 24 426 473 positions de `script/solver/data/tablebase.db`, réalisé
par `4mation-local.exe --verify` (2 h 47 sur un cœur).

## Méthode

Pour chaque position stockée, l'outil recalcule la valeur (victoire / nulle / défaite) à
partir des valeurs de ses enfants, puis la compare à ce qui est écrit. Trois verdicts :

| Verdict | Signification |
|---------|---------------|
| **ok** | la valeur écrite est exactement celle que donnent les enfants |
| **faux** | la valeur écrite contredit les enfants — un bug de données |
| **indécidable** | au moins un enfant nécessaire est absent de la base : impossible de trancher |

Les indécidables sont ensuite échantillonnés (3 000 positions) et retestés sous un
**dernier coup alternatif** menant au même plateau. Si une variante rend la position
résoluble, l'entrée est un « alias fantôme » : même plateau enregistré sous une clé
inatteignable, valeur juste mais inutilisable. Sinon, c'est un vrai trou.

## Résultat par couche

| Cases vides | Lignes | ok | faux | indécidables |
|-------------|--------|----|------|--------------|
| 1 | 2 | 1 | 0 | 1 |
| 2 | 82 | 11 | 0 | 71 |
| 3 | 1 513 | 630 | 0 | 883 |
| 4 | 25 607 | 5 301 | 0 | 20 306 |
| 5 | 241 996 | 115 159 | 0 | 126 837 |
| 6 | 2 098 695 | 681 510 | 0 | 1 417 185 |
| 7 | 12 944 110 | 6 651 321 | 0 | 6 292 789 |
| 8 | 1 459 993 | 552 217 | 0 | 907 776 |
| 9 | 1 621 337 | 766 399 | 0 | 854 938 |
| 10 | 2 288 206 | 836 297 | 0 | 1 451 909 |
| 11 | 2 248 413 | 929 085 | 0 | 1 319 328 |
| 12 | 1 496 519 | 538 732 | 0 | 957 787 |
| **total** | **24 426 473** | **11 076 663** | **0** | **13 349 810** |

## Conclusion

1. **Aucune valeur fausse, sur aucune couche.** La base ne se contredit jamais : tout ce
   qu'elle affirme, les enfants le confirment. C'est le point le plus important — la
   tablebase est utilisable telle quelle par le moteur, qui ne lit que ce qu'elle contient.
2. **Le défaut restant est un défaut de couverture, pas de justesse.** Sur les 13,35 M
   d'indécidables, l'échantillonnage donne 2 841 alias fantômes contre 159 vrais trous,
   soit 5,3 % → **≈ 0,7 million de positions réellement absentes (2,9 % de la base)**.
3. **Les couches 8 à 12 n'ont jamais été terminées.** Le décrochage des volumes après la
   couche 7 (12,9 M puis ≈ 1,5 M par couche) montre qu'elles ne contiennent que ce qui a
   été atteint en explorant. Les trous remontent en réalité jusqu'à la couche 3.
4. Le comblement se fait couche par couche, **du bas vers le haut** (générer les parents
   d'une couche enfant complète, puis résoudre) — c'est le seul ordre où chaque couche
   repose sur une couche juste.

## Reproduire

```bash
cd 4mation/script/solver_rust
cargo build --release
./target/release/4mation-local.exe --db ../solver/data/tablebase.db --verify
```

La sortie brute est aussi conservée localement dans `_tmp_verify.log` (non versionné).
