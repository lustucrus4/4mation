# Solveur 4mation — tablebase et Phase C (résolution exhaustive)

Scripts de construction de la base de positions exactes (W/L/D, meilleur coup, taux de victoire).

## Résultat principal : le centre gagne de force (prouvé)

Le premier coup **`3,3` (centre) gagne de force** : après ce coup, le second joueur est
perdant **quoi qu'il fasse**, mat en 28 demi-coups. Ce n'est pas une estimation du moteur,
c'est une **preuve** (recherche alpha-bêta complète, profondeur 28, ~23 s, table de
transposition 2 Go), et elle est **contre-vérifiée** :

- ligne rejouée avec le moteur de jeu Python (autorité sur les règles) : **0 anomalie** ;
- à chaque position, le nombre de coups légaux du moteur coïncide avec celui des règles
  (8/8, 7/7, 6/6, 4/4, … 17/17) — aucun coup de défense n'est oublié ;
- distance de mat décroissante d'exactement 1 par demi-coup, alternance stricte des camps ;
- à chaque tour de défense, **tous** les coups perdent : le gain ne dépend d'aucune faute.

La ligne principale (défense la plus tenace, attaque au plus court) :

```
X3,3 O3,2 X2,3 O1,3 X2,2 O1,1 X1,2 O2,1 X3,1 O4,2 X4,3 O5,3 X5,4 O4,5 X3,4 O2,4
X2,5 O1,6 X0,5 O1,5 X2,6 O3,6 X4,6 O5,6 X6,6 O5,5 X6,4 O6,5 X0,1
```

`Xn,m` = coup du premier joueur, `On,m` = coup du second, format `ligne,colonne`.

Outils :

| Script | Rôle |
|--------|------|
| `scripts/probe_opening_proof.py` | Sonde profonde des 10 ouvertures (preuve ou pas, meilleure réponse) |
| `scripts/extract_forced_win.py` | Extrait la ligne de gain forcée, demi-coup par demi-coup |
| `scripts/check_forced_win.py` | Contre-vérifie la ligne avec les règles du site (0 anomalie attendue) |
| `script/solver/mark_proven_lines.py` | Inscrit la ligne prouvée dans le livre du site (`opening_book`, `exact=1`) |

```powershell
python scripts\probe_opening_proof.py --depth 30 --time-ms 90000 --tt-mb 2048
python scripts\extract_forced_win.py --opening 3,3 --depth 40 --time-ms 120000 --tt-mb 2048
python scripts\check_forced_win.py script\solver\forced_win_33.json
python script\solver\mark_proven_lines.py --line script\solver\forced_win_33.json
```

Sorties : `script/solver/PREUVE_PROFONDE.md`, `GAIN_FORCE_33.md`, `forced_win_33.json`.

**Ordre important** : `build_opening_book_engine.py` réécrit les entrées du livre par des
estimations. Marquer la ligne prouvée doit donc être la **dernière** étape, après tout
rebuild du livre (sinon les valeurs `exact=1` sont écrasées). La racine du livre passe alors
de « nulle, 58 % » à « gain prouvé, meilleur coup `3,3` », et le site sert ce verdict
(`position_win_rate` de la position prouvée fait foi, même si certains enfants ne sont
qu'estimés).

Conséquence pratique : les ouvertures non centrales restent des **estimations** (le moteur
n'y prouve rien à profondeur 24-26, leurs scores restent proches de l'équilibre), tandis que
le centre est **démontré gagnant**. C'est aussi l'explication de ce que les parties réelles
montraient déjà : contre une défense exacte, le second joueur perd systématiquement après
une ouverture centrale — ce n'est pas un défaut du bot `level_6`, c'est le jeu.

## État de la tablebase (audit complet)

`4mation-local.exe --verify` (couches 1 à 12) :

```
BILAN : 11 076 663 ok | 0 faux | 13 349 810 indécidables
Échantillon de 3000 indécidables : 2841 alias fantômes, 159 vrais trous
```

- **0 valeur fausse** sur les 11,1 M de positions vérifiables : la base est saine.
- Les 13,3 M « indécidables » sont à ~95 % des **alias fantômes** (même plateau, `last_move`
  différent : redondance, pas une erreur) et à ~5 % de **vrais trous** (~0,7 M estimés).
- Conséquence : les couches 1-7 sont solides, les couches 8-12 sont **partielles**. Le
  comblement se fait par `4mation-local --sweep-from / --sweep-to`.

## Structure

```
script/solver/
├── build_endgame_tablebase.py       # Phase A — fin de partie (≤12 cases vides)
├── build_opening_book.py            # Phase B — livre d'ouverture (12 premiers coups)
├── build_opening_book_engine.py     # Livre d'ouverture évalué par le moteur Rust
├── calibrate_engine_scale.py        # Calibrage score moteur → taux de victoire
├── check_opening_book.py            # Contrôle d'intégrité et de cohérence du livre
├── build_full_tablebase.py          # Phase C — solveur exhaustif progressif
├── exhaustive_explorer.py           # BFS avant + rétrograde parents
├── retrograde_solver.py             # Moteur rétrograde par position
├── db_schema.py                     # Schéma SQLite partagé
├── solver_status.py                 # Fichier JSON live (API + dashboard)
├── position_hasher.py               # Hash Zobrist des positions
└── data/
    ├── tablebase.db                 # Base SQLite (positions + progression)
    └── solver_status.json           # État live pour le dashboard
```

## Phase C — résolution exhaustive progressive

Le solveur **ne s'arrête pas** après un lot : il parcourt tout l'espace atteignable.

### Algorithme

1. **BFS avant** depuis l'ouverture (plateau vide) — toutes les positions légales avec ≤ `max_empty` cases vides.
2. **Rétrograde** depuis les positions déjà résolues — génération des parents (coup annulé).
3. **Résolution** de chaque position via `RetrogradeSolver` (W/L/D exact, meilleur coup).
4. **Extension progressive** de `max_empty` : 12 → 20 → 30 → 40 → 49 (fin de partie → ouverture complète).
5. **Checkpoint** après chaque flush — reprise sans perte de progression.

### Estimation de l'espace d'états

| Phase | max_empty | Ordre de grandeur |
|-------|-----------|-------------------|
| Fin de partie | ≤12 | ~800 000 positions |
| Milieu | ≤20 | ~5 millions |
| Ouverture | ≤30 | ~25 millions |
| Large | ≤40 | ~80 millions |
| Complet | 49 | ~150 millions (estimation haute) |

Durée estimée sur VPS : **plusieurs jours à plusieurs semaines** selon la vitesse (~0,5–5 pos/s selon complexité).

Le pourcentage d'avancement n'est affiché que lorsque l'estimation est fiable ; sinon le dashboard indique « X résolues (exploration en cours) ».

### Lancement local

```bash
cd 4mation
set PYTHONPATH=script
python script/solver/build_full_tablebase.py --db script/solver/data/tablebase.db
```

Options :

| Option | Défaut | Description |
|--------|--------|-------------|
| `--db` | `script/solver/data/tablebase.db` | Chemin SQLite |
| `--max-empty` | 12 | Niveau initial de cases vides |
| `--batch` | 25 | Positions entre chaque flush DB |
| `--progress-interval` | 15 | Heartbeat JSON (secondes) |
| `--position-timeout` | 30 | Timeout par position (secondes) |

### Comportement

- **Checkpoint** : `solver_checkpoint.json` (niveau max_empty, exploration BFS/rétrograde)
- **Progression** : table `solver_progress` + `solver_status.json` (heartbeat 15 s)
- **Pas de plafond** : `total_positions_solved` cumule sans limite
- **Phases UI** : `endgame` → `midgame` → `opening` → `complet`

### Variables d'environnement (VPS / Docker)

| Variable | Exemple | Usage |
|----------|---------|--------|
| `TABLEBASE_DB_PATH` | `/app/data/tablebase.db` | Chemin base pour API et solveur |
| `SOLVER_STATUS_PATH` | `/app/data/solver_status.json` | Fichier JSON lu par l'API |

## Phases A et B (amorçage)

```bash
python script/solver/build_endgame_tablebase.py
python script/solver/build_opening_book.py
python script/solver/seed_initial_tablebase.py
```

### Livre d'ouverture longue durée (~2 Go) — **Rust** (recommandé)

Construction parallèle (rayon) adossée à la tablebase en mémoire :

```bat
cd 4mation
scripts\run_opening_book_full.bat
```

Équivalent manuel :

```bat
script\solver_rust\target\release\4mation-local.exe ^
  --opening-book --opening-fresh --opening-target-gb 2 ^
  --opening-max-ply 18 --opening-max-positions 200000 ^
  --threads %NUMBER_OF_PROCESSORS% --dashboard --db script\solver\data\tablebase.db
```

**Algorithme Rust** (remplace Python pour la vitesse) :
- Chargement `ResultTable` (~24M positions) en RAM
- BFS ouverture + tri par ply (enfants avant parents)
- Promotion **exacte** via `resolve_via_children` (lookup O(1))
- Estimations via `RetrogradeSolver` alpha-bêta parallélisé
- Phase dashboard `opening_book`, cible **2 Go**

Version Python legacy (Minimax+MCTS, plus lente) :

```bash
python script/solver/build_opening_book_full.py --target-gb 2 --fresh
```

## Livre d'ouverture évalué par le moteur Rust

Le livre (`opening_book`) est la matière première des cours d'ouverture et de
l'explorateur du site. Depuis septembre 2026, ses estimations ne viennent plus du
Minimax Python ni du MCTS mais du moteur `4mation-engine` (voir
`script/solver_rust/README.md`), qui apporte deux choses que l'ancien pipeline n'avait
pas : la **détection de mat forcé** (valeurs `exact=1`) et une **échelle de score
calibrée** sur les positions exactes de la tablebase.

```bash
# 1. Calibrer l'échelle score -> taux de victoire (à refaire si le moteur change)
python script/solver/calibrate_engine_scale.py --samples 150 --depth 8
#    -> engine_scale.json, lu automatiquement par le constructeur et par l'API

# 2. Rejouer les positions du livre par le moteur (les écritures sont idempotentes)
python script/solver/build_opening_book_engine.py --max-ply 6 --max-positions 40000
#    --budget-factor 0.5 pour une passe d'exploration rapide

# 3. Contrôler le résultat
python script/solver/check_opening_book.py --ply 0 1 2 3 4 --all --by-ply
```

Budget de recherche par demi-coup (`_budget` dans le constructeur) : 20 demi-coups au
premier coup, 18 au deuxième, 14 aux coups 3 à 6, 12 au-delà. Les premiers coups sont
peu nombreux mais très consultés : c'est là que le budget compte.

### Contrôle d'intégrité (`check_opening_book.py`)

| Contrôle | Nature | Ce qu'il détecte |
|----------|--------|------------------|
| `plateau` | erreur | plateau non vide sans dernier coup (vestige d'anciens bugs) |
| `pions` | erreur | nombre de pions incohérent avec le demi-coup |
| `dernier_coup` | erreur | la case du dernier coup ne porte pas un pion adverse |
| `coup_legal` | erreur | meilleur coup enregistré illégal (décalage d'orientation) |
| `coherence` | avertissement | valeur du parent ≠ opposé de celle de l'enfant atteint |

`--by-ply` ventile l'écart de cohérence par demi-coup : c'est ce qui permet de
distinguer un estimateur intrinsèquement bruité d'un **mélange de deux générations de
calcul**. Mesure du 24/09/2026 : 2,8 % d'écart moyen dans les couches écrites par le
moteur (0 à 3) contre 6 à 9 % aux frontières avec les couches restées au Minimax
(4 à 6), et 1,1 % entre deux couches Minimax (7 et 8) — les estimations du moteur sont
cohérentes entre elles, les incohérences viennent du mélange.

### Théorie d'ouverture extraite du livre (`extract_opening_theory.py`)

Le livre brut n'est pas lisible par un humain : ce script en tire la théorie prête pour
les cours (ligne principale, ouvertures uniques, seuils, conseils chiffrés).

```bash
python script/solver/extract_opening_theory.py --max-ply 6
#    -> script/solver/opening_theory.json   (données brutes, versionné)
#    -> script/solver/THEORIE_OUVERTURE.md  (rapport lisible)
```

Ce que produit le rapport, et sur quoi il faut être précis :

- **Ouvertures uniques** : le plateau est symétrique par rotation et miroir, les 49 cases
  de départ se réduisent à **10 orbites**. Chaque orbite est présentée avec son
  représentant et le score espéré du premier joueur, plus l'écart au meilleur coup.
- **Transport par symétrie** : le livre range chaque position dans la première orientation
  rencontrée. Pour suivre une ligne, le script retrouve, parmi les 8 images du plateau
  stocké, celle qui correspond à la position courante, puis transporte le coup par la même
  symétrie (`reorient`). Sans cela, les coups lus paraissent illégaux.
- **Nature des valeurs** : chaque ligne dit si elle vient d'un verdict de la tablebase
  (`exact=1`) ou d'une estimation du moteur — les deux ne se mélangent jamais.
- **Score espéré, pas probabilité** : la valeur chiffrée est une espérance
  (victoire = 1, nulle = 0,5, défaite = 0), cible du calibrage. Dans un jeu où la nulle est
  fréquente, « 58 % de score espéré » n'est pas « 58 % de victoires ». Le vocabulaire du
  rapport suit cette distinction.
- **Seuils** : ±40 points d'évaluation, lus dans la table de fiabilité du calibrage, sont
  la frontière où la prédiction s'écarte vraiment de 0,50 ; le rapport les affiche en clair
  pour que les cours ne surinterprètent pas le bruit.

Mesure du 24/09/2026 (`--max-ply 6`, livre aux couches 1-6 réévaluées par le moteur) :

| Enseignement | Chiffre |
|--------------|---------|
| Meilleur premier coup | `(3,3)`, score espéré du 1ᵉʳ joueur 58,1 % |
| Coup le plus faible | `(0,1)`, 47,5 % — soit 10,6 points de moins |
| Amplitude totale des 10 ouvertures | 10,6 points : le premier coup ne décide pas la partie |
| Couverture | 26 175 positions au 6ᵉ demi-coup, dont 2 753 prouvées |

### Vérification en parties réelles (`opening_sweep.py`)

Le livre est une évaluation ; pour savoir ce qui se passe quand on joue vraiment la
position, `scripts/opening_sweep.py` fait s'affronter deux bots forts avec le premier coup
imposé, et mesure le rendement du **second joueur** — celui qui subit l'ouverture.

```bash
python scripts/opening_sweep.py --bot level_6 --opponent level_6 --per-orbit 1
#    -> _tmp_opening_sweep.json (table par ouverture + parties complètes)
python script/solver/extract_opening_theory.py --max-ply 6 --sweep _tmp_opening_sweep.json
#    -> section « Vérification en parties réelles » dans THEORIE_OUVERTURE.md
```

`--only-opening "3,3 2,3 2,2"` restreint le balayage à quelques ouvertures, et
`--defender-depth` / `--defender-time-ms` donnent à la défense un budget hors norme : c'est
ainsi qu'on mesure si une défaite du second joueur est une faiblesse du bot ou une
propriété de l'ouverture.

Mesure du 24/09/2026 (10 orbites, `level_6` contre lui-même, 1 partie par orbite) :

| Ouverture | Score du 2ᵉ joueur | Verdict |
|-----------|--------------------|---------|
| `(0,0)`, `(0,2)` | 100 % | le second joueur gagne |
| `(0,1)` | 50 % | nulle |
| `(0,3)` → `(3,3)` | 0 % | le premier joueur gagne, d'autant plus vite que le coup est central |

Le résultat est plus tranché que le livre : les ouvertures centrales ne laissent aucun point
au second joueur, même avec une défense quatre fois plus lente que l'attaque. Les pertes du
niveau 6 en second joueur ne sont donc pas un défaut du bot.

Réserve de méthode : **une seule partie par ouverture**. Ces chiffres illustrent, ils ne
démontrent pas, et ils ne constituent pas un classement. Le classement *estimé* du livre
n'est d'ailleurs pas reproductible d'une passe de sonde à l'autre : voir la section
« Stabilité des scores » ci-dessous.

### Stabilité des scores (`compare_probe_passes.py`)

Les scores de la sonde et du livre ne sont **pas des preuves** : ils viennent d'une
recherche arrêtée par un budget de temps. Deux passes sur la même position peuvent donc
diverger. Ce script compare plusieurs passes et conclut sur leur reproductibilité — il ne
lance aucun calcul, il relit des fichiers déjà présents.

```bash
python script/solver/compare_probe_passes.py \
  --passe "courte=script/solver/preuve_profonde.json" \
  --passe "longue=script/solver/probe_runs/passe_longue.log"
#    -> script/solver/probe_runs/stability.json
```

**Résultat du 25/09/2026** : sur les 6 ouvertures mesurées deux fois (90 s puis 600 s de
budget), 4 varient de plus de 20 points et 5 changent de signe — `(1,2)` vaut −42 puis +5.
L'ordre du classement est entièrement rebattu.

**Conséquence appliquée** : aucun classement d'ouvertures n'est publié, ni dans les cours du
site, ni dans `THEORIE_OUVERTURE.md`. Seul le gain forcé du centre `(3,3)` est présenté comme
une valeur ferme. `build_lessons.py` et `extract_opening_theory.py` lisent `stability.json`
pour l'expliquer dans le texte des leçons.

### Motifs des finales exactes (`mine_final_patterns.py`)

La tablebase tranche les finales mais ne se lit pas. Ce script en extrait ce qui se répète
et ce qui s'enseigne, en séparant deux notions que les joueurs confondent :

- une **case d'alignement** est un endroit où poser une pierre ferait quatre ;
- une **menace jouable** est une case d'alignement qui est *aussi* un coup légal.

Une case d'alignement inaccessible ne menace personne : c'est la « menace fantôme ».
Chaque position est donc classée par ce que le trait peut faire *réellement*.

```bash
python script/solver/mine_final_patterns.py --layers 7 8 9 10 11 --sample 600 --puzzles 9
#    -> script/solver/final_patterns.json (données brutes)
#    -> script/solver/MOTIFS_FINALES.md  (rapport lisible + exercices)
python scripts/check_exercise_lines.py script/solver/final_patterns.json
#    -> rejoue chaque exercice et compte les anomalies (0 attendu)
```

Une position n'est retenue que si son dernier coup porte une pierre adverse, que **tous**
ses enfants sont en base et que la valeur déduite des enfants est celle qui est stockée —
c'est une position « exploitable ». Les exercices, eux, ne partent que si la ligne forcée
se termine sur un alignement du camp gagnant : le camp qui gagne n'y joue jamais un coup
perdant faute d'enfant connu, il s'arrête. Les trous de la base se lisent donc directement
dans le rapport, en nombre d'exercices écartés.

Mesure du 24/09/2026 (couches 7 à 11, 600 positions exploitables par couche) :

| Enseignement | Chiffre |
|--------------|---------|
| Contrôles de cohérence | 3 000 positions, **0 incohérence** — la base ne se contredit jamais |
| Quand le trait peut conclure | il gagne 480 fois sur 480 |
| Quand l'adversaire conclut quoi qu'il arrive | on perd 1 559 fois sur 1 559 |
| La vraie finale (personne ne conclut) | 961 positions : 50 % de gains, 28 % de nulles, 22 % de pertes |
| Gains construits | 77 % passent par une **fourchette** (deux menaces ou plus d'un seul coup) |
| Menace fantôme | présente chez l'adversaire dans **68 %** des positions de bataille |
| Exercices retenus | 7 sur 474 candidats, 12 lignes coupées par un trou, 0 verdict contredit |

### Audit de la tablebase (`4mation-local --verify`)

`4mation-local.exe --verify` relit chaque position stockée, recalcule sa valeur à partir
de ses enfants et la compare à ce qui est écrit. Il distingue les « alias fantômes »
(le même plateau enregistré sous un autre dernier coup : valeur juste, clé inatteignable)
des vrais trous, par échantillonnage des positions indécidables.

Bilan du 24/09/2026 sur 24 426 473 positions : **0 valeur fausse**, 11 076 663 vérifiées,
13 349 810 indécidables dont 94,7 % d'alias fantômes — soit ≈ 0,7 M de vrais trous
(2,9 % de la base). La base ne se contredit jamais ; son défaut est la couverture.
Rapport détaillé, couche par couche : **[AUDIT_TABLEBASE_2026-09-24.md](./AUDIT_TABLEBASE_2026-09-24.md)**.

## API de suivi (dashboard)

| Route | Description |
|-------|-------------|
| `GET /api/solver/status` | Stats live + 20 dernières positions |
| `GET /api/solver/position/{hash}` | Détail d'une position résolue |

Page web : **https://4mation.lab211.fr/solver.html**

## Mode distribué (workers parallèles)

Voir **[README_DISTRIBUTED.md](./README_DISTRIBUTED.md)** pour lancer un worker local (16 processus sur Ryzen 9).

- VPS : `work_queue_filler.py` alimente la file `work_queue`
- Workers : `distributed_worker.py` (PC local, VPS, etc.)
- API : `/api/solver/work/claim|submit|stats|release`

## Déploiement VPS

Le service `solver` dans `deploy/docker-compose.solver.yml` tourne en boucle continue (`restart: unless-stopped`).

```bash
docker compose -f deploy/docker-compose.solver.yml up -d --force-recreate solver
```

L'API et le solveur partagent le volume `4mation-sessions` (`/app/data`).

## Solveur local Rust (100 % hors réseau)

Lancement interactif avec dashboard intégré :

```bat
cd 4mation
lancer_solveur.bat
```

Dashboard : http://127.0.0.1:8765/

### Exploration rétrograde de frontière (base mature)

Au-delà de ~600 000 positions connues, l'explorateur bascule en **rétrograde de frontière** :

- il recharge depuis la DB les positions connues ayant le **plus de cases vides** (la frontière vers l'ouverture) ;
- il génère leurs **parents** (un coup en arrière = +1 case vide) jusqu'à `max_empty=20` (zone solvable) ;
- il alimente la file en continu et se recharge dès qu'elle se vide.

Cela évite le blocage de l'ancien BFS « forward » (qui, partant du plateau vide, ne pouvait jamais atteindre les positions profondes). La progression vers le milieu de partie (cases vides 18→20) est plus lente que l'endgame car les arbres de jeu sont exponentiellement plus grands — c'est attendu, le CPU reste saturé.

Le solveur utilise par défaut **tous les threads logiques** de la machine (`SOLVER_THREADS=%NUMBER_OF_PROCESSORS%`).

### Boucle de test / optimisation automatique

Script PowerShell qui compile, lance le solveur, attend la fin d'un lot, puis valide les métriques (delta DB, taux ok/relâché) :

```powershell
cd 4mation
.\scripts\solver_feedback_loop.ps1 -MaxRounds 5 -RunSeconds 600
```

Paramètres utiles : `-MaxRounds`, `-RunSeconds` (timeout par round), `-MaxIterations`.

La boucle s'arrête dès qu'un round réussit (positions résolues, fail rate < 50 %). Les positions `in_progress` orphelines sont recyclées avant chaque round.
