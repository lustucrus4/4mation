# Solveur Rust — 4mation-local & 4mation-worker

Binaires haute performance pour construire la tablebase Connect4/4mation (7×7, frontier, WDL exact).

## Prérequis

- [Rust](https://rustup.rs) (toolchain stable)
- Windows : **Visual Studio Build Tools** avec « Développement Desktop en C++ »

```powershell
rustup default stable
```

## Compilation

```powershell
cd script/solver_rust
cargo build --release
```

Binaires produits :

| Binaire | Rôle |
|---------|------|
| `target/release/4mation-engine.exe` | **Moteur de jeu** — meilleur coup, analyse, finale exacte (voir section dédiée) |
| `target/release/4mation-local.exe` | **Recommandé Legion** — exploration + résolution + SQLite + dashboard (`--dashboard`) |
| `target/release/4mation-dashboard.exe` | Dashboard seul (lecture SQLite, sans solveur) |
| `target/release/4mation-worker.exe` | Worker HTTP (API distribuée, conservé pour compatibilité) |
| `target/release/4mation-proof.exe` | Preuve exacte depuis l'ouverture (voir section dédiée) |

## Lancement local (Legion, 16 cœurs)

Depuis la racine du projet :

```bat
scripts\run_local_solver_rust.bat
```

Ou directement :

```powershell
.\script\solver_rust\target\release\4mation-local.exe `
  --db script\solver\data\tablebase.db `
  --threads 16 `
  --max-empty 12 `
  --solve-batch 500 `
  --min-pending 5000 `
  --dashboard
```

### Options CLI (`4mation-local`)

| Option | Défaut | Description |
|--------|--------|-------------|
| `--db` | `script/solver/data/tablebase.db` | Chemin SQLite |
| `--threads` | `16` | Threads rayon (résolution parallèle) |
| `--max-empty` | `12` | Niveau initial cases vides (12→20→30→40→49) |
| `--solve-batch` | `500` | Positions par lot de résolution |
| `--min-pending` | `5000` | Tampon file avant pause exploration |
| `--sweep-from N` | — | Balayage exhaustif : complète la couche N+1 à partir de N, puis s'arrête |
| `--sweep-to M` | `8` | Dernière couche à compléter (incluse) pour `--sweep-from` |
| `--diag-layer N` | — | Diagnostic : classe les parents irrésolubles (alias fantômes / vrais trous) |
| `--verify` | — | Recalcule chaque valeur depuis ses enfants et la compare au stockage |
| `--max-iterations` | — | Arrêt après N résolutions (tests) |
| `--once` | — | Un cycle puis sortie |
| `--dashboard` | — | Serveur web intégré (port 8765) |
| `--dashboard-port` | `8765` | Port HTTP (`SOLVER_DASHBOARD_PORT`) |
| `--dashboard-host` | `127.0.0.1` | Interface d'écoute (`SOLVER_DASHBOARD_HOST`) |

Variables d'environnement : `SOLVER_THREADS`, `TABLEBASE_MAX_EMPTY`, `SOLVER_DASHBOARD_PORT`.

## Architecture locale

```
4mation-local [--dashboard]
├── explorer.rs     — BFS avant + rétrograde parents (remplace work_queue_filler.py)
├── hasher.rs       — Hash Zobrist identique à position_hasher.py
├── solver.rs       — Résolution rétrograde W/L/D (port retrograde_solver.py)
├── game.rs         — Règles 7×7, frontier, victoire
├── local_db.rs     — Schéma SQLite, inserts groupés, claim/submit bulk
├── local_engine.rs — Boucle : explorer → claim → résoudre (rayon) → écrire
└── dashboard/      — Serveur Axum (thread séparé si --dashboard)
```

Une seule machine, 16 threads. Le dashboard HTTP est hors chemin critique de résolution.

## Tests

```powershell
cargo test
cargo build --release
.\target\release\4mation-local.exe --max-iterations 5 --threads 4 --once
```

## Performance attendue vs mode API distribué

| Goulot | API + filler VPS | 4mation-local (Legion) |
|--------|------------------|------------------------|
| Réseau | Latence claim/submit | Aucun |
| Exploration | Process Python séparé | Rust intégré, même processus |
| Résolution | 16 workers HTTP | 16 threads rayon, cache local |
| SQLite | VPS distant | Disque NVMe local, WAL + bulk |

Ordre de grandeur : **10–30×** plus de positions/minute qu'une chaîne API+VPS+workers Python, selon profondeur des positions. CPU cible : **70–95 %** sur 16 cœurs en fin de partie.

## Worker HTTP (legacy)

```powershell
.\target\release\4mation-worker.exe --api-url https://api-4mation.lab211.fr --threads 16
.\target\release\4mation-worker.exe --local-db ..\solver\data\tablebase.db --threads 16
```

## Symétries (miroir + rotation)

Activé **par défaut** : chaque position est ramenée à sa **forme canonique** parmi les **8 symétries** du carré (groupe D₄ : 4 rotations × miroir horizontal). Les positions équivalentes partagent le même hash → réduction ~4–8× de l'espace exploré.

```bat
REM Défaut : symétries ON
scripts\run_local_solver_stack.bat

REM Ancienne base sans symétries (compatibilité)
script\solver_rust\target\release\4mation-local.exe --no-symmetry --dashboard ...
```

**Migration** : une base remplie sans symétries n'est pas compatible. Pour activer les symétries sur une base existante, repartir de zéro :

```bat
scripts\run_bootstrap_endgame.bat
scripts\run_local_solver_stack.bat
```

Modules : `src/symmetry.rs` (Rust), `script/solver/symmetry.py` (Python).

## Preuve depuis l'ouverture (`4mation-proof`)

Le solveur rétrograde remplit une tablebase case par case. Le milieu de partie est trop grand pour finir en un temps raisonnable sur un PC.

`4mation-proof` prouve directement la position de départ (victoire, nulle ou défaite) :

- une seule fois par position (table de transposition) ;
- une seule fois par symétrie du carré (rotations et miroirs) : 10 premiers coups au lieu de 49 ;
- les mêmes pions atteints par un autre ordre de coups ne sont pas recalculés.

Un motif simplement décalé d'une case n'est pas le même coup : le bord du 7×7 change la suite. Ces positions restent distinctes.

Le tableau de bord suit la preuve sur http://127.0.0.1:8770/. Il indique la profondeur, le débit, le temps de la profondeur suivante et une estimation de fin : les profondeurs suivantes sont projetées comme les deux dernières, jusqu'à la profondeur 22, pour chaque ouverture encore ouverte. Une victoire du joueur 1 termine plus tôt.

```bat
scripts\run_proof_solver.bat
```

Ou, avec un essai de 2 minutes :

```bat
script\solver_rust\target\release\4mation-proof.exe --tt-mb 1024 --seconds 120
```

## Moteur de jeu (`4mation-engine`)

`4mation-engine` répond à deux questions : **quel coup jouer**, et **que vaut
chaque coup**. C'est le binaire qui alimente le bot et l'analyse des parties.

- recherche **alpha-bêta** avec table de transposition, ordonnancement des coups
  et élagage des symétries ;
- scores « mat en N » : le moteur choisit le gain le plus court et la résistance
  la plus longue quand la défaite est inévitable ;
- lecture de la **tablebase** pour les finales : quand la position y est, la
  valeur exacte et le meilleur coup sortent sans recherche (`tb_exact: true`).

### Protocole (une requête JSON par ligne sur stdin, une réponse par ligne)

```powershell
'{"board": [[0,0,0,0,0,0,0], ...], "current_player": 1, "last_move": [3,3], "depth": 16, "time_ms": 1000}' |
  .\target\release\4mation-engine.exe --tt-mb 512 --tb script\solver\data\tablebase.db
```

`last_move` vaut `null` au premier coup. `depth` et `time_ms` sont optionnels et
écrasent les valeurs de la ligne de commande. La table de transposition est
conservée entre les requêtes : le processus est prévu pour rester ouvert.

Deux drapeaux supplémentaires, **par requête** (et non au lancement) — c'est ce qui
permet à un même processus de servir le bot en mode rapide et l'analyse en mode
complet, en partageant sa table :

| Champ | Effet |
|-------|-------|
| `"exact": true` | chaque coup de la racine est recherché en fenêtre pleine : le score de **tous** les coups est exact. Sans lui, les scores des coups non joués ne sont que des bornes — un coup perdant peut s'afficher à −147 au lieu de « perte forcée » |
| `"all_moves": true` | énumère **tous** les coups légaux à la racine. Par défaut la racine est réduite aux orbites de symétrie : le premier coup ne rend alors que **10 coups sur 49**. Vaut `exact` si absent |

Règle simple : *bot* = aucun des deux ; *analyse* = les deux.

Réponse (extrait) :

```json
{"best_move": [3,3], "score": 29, "proven": "aucune preuve", "tb_exact": false,
 "depth": 14, "nodes": 1326557, "elapsed_ms": 700, "truncated": false,
 "exact_root": true, "all_moves": true, "valid_moves_count": 49, "moves": [...]}
```

`proven` vaut `gain`, `perte`, `nulle` (uniquement quand c'est prouvé) ou
`aucune preuve`. `tb_exact` indique que la valeur vient de la tablebase.
Chaque coup de `moves` porte `exact` : en mode normal, seul le meilleur coup et
les coups qui l'améliorent ont un score exact ; les autres sont des bornes.
`valid_moves_count` est le nombre de coups légaux **avant** réduction par
symétrie : une interface peut ainsi annoncer « 12 coups notés sur 49 ».

Si la recherche est coupée par le temps (`truncated: true`), les scores rendus
sont ceux de la dernière profondeur **terminée** : la liste reste complète et
cohérente, seule la profondeur est plus faible.

### Options

| Option | Défaut | Description |
|--------|--------|-------------|
| `--tt-mb` | `128` | Taille de la table de transposition |
| `--depth` | `16` | Profondeur maximale (itératif : s'arrête dès qu'un mat est prouvé) |
| `--time-ms` | `1000` | Budget par recherche, `0` = illimité |
| `--tb` | — | Tablebase SQLite pour les finales |
| `--tb-empty` | `12` | Nombre de cases vides en dessous duquel la tablebase est consultée |
| `--exact` | — | Valeur par défaut du mode analyse pour les requêtes qui ne le précisent pas |
| `--bench N` | — | Mesure le débit puis quitte |

### L'analyse dans le site

Le site ne devine plus les coups : `TablebaseLookup.analyze_position` (coach, revue de
partie, puzzles, explorateur d'ouvertures) interroge le moteur en mode analyse dès que
la position n'est pas prouvée par la tablebase. Le score brut n'étant pas un taux de
victoire, la conversion passe par une sigmoïde dont l'échelle est **mesurée** sur les
finales exactes :

```bash
python script/solver/calibrate_engine_scale.py --samples 150 --depth 8
```

Le script écrit `script/solver/data/engine_scale.json`, lu par l'API et par le
constructeur du livre d'ouverture — une même échelle partout, sinon les taux de victoire
ne veulent plus rien dire d'une couche à l'autre. Voir `api/README.md` pour le détail.

### Performances mesurées (7×7, 512 Mo de table, un cœur)

| Situation | Résultat |
|-----------|----------|
| Début de partie, profondeur exacte sur les 10 coups distincts | profondeur 14 en **0,7 s** (1,3 M nœuds) |
| Plateau vide, recherche continue | profondeur **22** en 8 s (17,6 M nœuds) |
| Position de milieu de partie | profondeur 16 en 15 ms |
| Débit | ~2,2 M nœuds/s |

Classement des 10 premiers coups distincts en mode analyse (profondeur 14, score du point
de vue du joueur 1) : **volontairement non publié ici.**

Ces scores bougent trop pour servir de classement. Mesure du 2026-09-25 : les mêmes
ouvertures chiffrées deux fois (90 s puis 600 s de budget par coup) changent de signe —
par exemple `(1,2)` vaut −42 puis +5. Outil de vérification :
`script/solver/compare_probe_passes.py`, preuves conservées dans
`script/solver/probe_runs/`. Le seul verdict ferme depuis l'ouverture vient de
`4mation-proof` : le centre `(3,3)` gagne de force, mat en 28 demi-coups.

### Validation

`cargo test --release --lib` couvre le moteur, notamment :

- **égalité exacte avec un minimax naïf** (sans table de transposition, sans
  coupure alpha-bêta, sans élagage de symétrie) sur plusieurs positions et
  profondeurs : toute erreur de table, de bornes ou d'ordonnancement casse ce
  test ;
- **score exact de chaque coup** en mode analyse, comparé au minimax naïf ;
- déterminisme, légalité du coup proposé, respect du budget de temps.

La cohérence avec la tablebase a été vérifiée de bout en bout sur des positions
de finale réelles : valeur exacte et coup optimal conformes à la base dans tous
les cas où la position enfant y était présente.

La génération des coups est vérifiée contre le moteur de jeu **Python** sur des
parties aléatoires : les deux listent exactement les mêmes coups légaux, y compris
le cas particulier du voisinage saturé (repli sur les cases libres adjacentes à
l'adversaire). Cette parité est ce qui autorise le site à valider un coup de bot avec
le moteur sans risque de désaccord (`scripts/check_movegen_parity.py`).

## Audit de la tablebase (balayage par couches)

### Le problème que le balayage résout

L'explorateur étend la base **vers l'ouverture** en partant des positions les plus
ouvertes déjà connues : il génère les parents de la couche 12 puis monte vers 13, 14…
Les couches 8 à 11 restent donc trouées quel que soit le temps de calcul investi.
`--sweep-from N --sweep-to M` fait l'inverse, couche par couche et de façon exhaustive :
il prend une couche complète, génère *tous* ses parents et les résout. Une couche
complète en entrée donne une couche complète en sortie. La résolution est immédiate :
tous les enfants d'une position de la couche `n+1` appartiennent à la couche `n`, donc
`resolve_via_children` répond sans recherche.

```powershell
# Répare les couches 2 à 7, du bas vers le haut
.\target\release\4mation-local.exe --db ..\solver\data\tablebase.db --sweep-from 1 --sweep-to 7
```

### Deux bugs de génération corrigés (`explorer.rs`)

Les deux fabriquaient des **positions fantômes**, jamais atteignables en jeu réel :

1. **Dernier coup de la mauvaise couleur.** `parent_last_moves` acceptait n'importe quel
   pion comme dernier coup du parent, y compris un pion de la couleur au trait. Or les
   joueurs alternent : le dernier coup appartient toujours à l'adversaire.
2. **Parent sans dernier coup.** Le repli de `parent_last_moves` émettait `None` pour
   n'importe quelle position ; seul le plateau vide n'a pas de dernier coup.

Effet mesuré sur le balayage 6→7 : **14 177 → 7 015** positions irrésolubles.

### Diagnostic (`--diag-layer N`)

Parcourt la couche N et classe les parents irrésolubles en deux familles, car elles
n'ont pas la même gravité :

- **alias fantôme** : le plateau est résoluble sous un autre dernier coup. L'échec ne
  vient que d'un dernier coup candidat impossible, la position réelle est saine ;
- **vrai trou** : aucun dernier coup ne rend le plateau résoluble. Un enfant réellement
  jouable manque à la base.

Mesure sur la couche 6 → 7 : sur 12 171 733 parents générés, **7 040 322 alias
fantômes (58 %)** et **95 275 vrais trous**.

### Vérification (`--verify`)

Recalcule la valeur de chaque position depuis ses enfants et la compare à la valeur
stockée : `ok` (cohérente), `faux` (contredite), `indécidable` (au moins un enfant
manque). Les valeurs stockées ne contredisent jamais leurs enfants — aucune valeur
fausse n'a été trouvée — mais une large part des positions n'est pas revérifiable,
faute d'enfants présents en base.

### Ce que la tablebase peut et ne peut pas être

Les couches croissent d'un facteur 6 à 9 :

| Cases vides | 4 | 5 | 6 | 7 | 8 (estimé) |
|-------------|---|---|---|---|------------|
| Positions | 25 607 | 241 996 | 2 098 695 | 12 956 341 | ~60–90 M |

La couche 8 seule représente donc 3 à 4 fois la base actuelle (24,4 M lignes, ~3,6 Go),
la couche 9 une vingtaine de Go, la couche 10 près de 100 Go. Une tablebase complète
jusqu'à l'ouverture est **hors de portée** : la position de départ a 49 cases vides. La
tablebase sert aux **finales exactes** (derniers coups) ; le milieu de partie est couvert
par la recherche de `4mation-engine` puis par le livre d'ouverture.

## Reste à faire (évolutions)

- **Brancher `4mation-engine` sur l'API** : ✅ bot de niveau 6 et ✅ analyse de tout le
  site (`TablebaseLookup.analyze_position` → `api/services/engine_analysis.py`, échelle
  score → taux de victoire calibrée sur la tablebase). Voir `api/README.md`
- **Purger les lignes fantômes** : la base contient des états impossibles hérités des
  bugs de génération (58 % des parents de la couche 7, ~404 651 lignes sans dernier
  coup). Inoffensifs pour les coups joués — un vrai coup a toujours un dernier coup
  cohérent — mais ils doublent le volume et faussent les statistiques
- **Réparer la couche 8** : une fois les lignes fantômes purgées, la compléter par
  balayage (`--sweep-from 7`) puis vérifier (`--verify`). C'est la dernière couche
  raisonnable en taille sur un disque de PC
- **Checkpoint du solveur de preuve** : `4mation-proof` ne sauvegarde pas son
  avancement, une interruption fait perdre tout le calcul
- **Livre d'ouverture** : ✅ reconstruit par le moteur en mode analyse, avec l'échelle
  calibrée et le flag `exact` réservé aux positions réellement prouvées
  (`script/solver/build_opening_book_engine.py`). Reste à étendre au-delà de la couche 6
  quand la tablebase sera complétée
- Checkpoint JSON persistant (`filler_checkpoint.json`) comme le filler Python
- Parallélisation de l'exploration BFS (actuellement séquentielle, résolution déjà parallèle)
- Timeout par position (budget nœuds déjà limité à 500k)

## Dashboard local (suivi avancement)

Page web locale calquée sur `4mation_dashboard_dev/solver.html` : progression, débit, ETA, file de travail, mini-plateaux des 20 dernières positions.

**Stack 100 % Rust** — plus de Python/Flask requis pour le dashboard local.

### URL

**http://127.0.0.1:8765/** (port via `SOLVER_DASHBOARD_PORT`)

### Lancement (recommandé — 1 commande)

```bat
REM Solveur + dashboard intégrés (1 fenêtre, 1 processus)
scripts\run_local_solver_stack.bat
```

Équivalent :

```bat
scripts\run_local_solver_rust.bat
```

Le script lance `4mation-local --dashboard` par défaut.

### Dashboard seul (lecture SQLite)

```bat
scripts\run_local_dashboard.bat
```

Binaire :

```powershell
.\script\solver_rust\target\release\4mation-dashboard.exe --db script\solver\data\tablebase.db
```

### Fichiers

| Fichier | Rôle |
|---------|------|
| `web/index.html`, `web/style.css`, `web/solver.js` | UI (auto-refresh 2,5 s) |
| `src/dashboard/` | Serveur Axum + stats SQLite |
| `local_dashboard.py` | **Déprécié** — ancien serveur Flask (conservé pour référence) |

Le dashboard lit la même base SQLite que `4mation-local`. **Aucun impact** sur le dashboard prod Hostinger.

### Contrôle depuis le navigateur (localhost uniquement)

Depuis **http://127.0.0.1:8765/**, la section **Contrôle solveur** permet de :

- **Démarrer le solveur** — lance `scripts\run_local_solver_rust.bat` dans une nouvelle fenêtre `cmd`
- **Arrêter le solveur** — termine `4mation-local.exe` (`taskkill`) ou signale l'arrêt si mode `--dashboard` intégré
- Afficher l'état **actif** / **arrêté** (polling toutes les 3 s)

Endpoints réservés à `127.0.0.1` / `::1` (403 sinon) :

| Méthode | Route | Rôle |
|---------|-------|------|
| `GET` | `/api/solver/status` | Progression, débit, ETA, positions récentes |
| `GET` | `/api/solver/work/stats` | File de travail et workers actifs |
| `GET` | `/api/local/process-status` | `4mation-local.exe` en cours ? |
| `GET` | `/health` | Santé du serveur |
| `POST` | `/api/local/start-solver` | Lance le solveur (whitelist `.bat`) |
| `POST` | `/api/local/stop-solver` | Arrête le solveur |
| `POST` | `/api/local/start-stack` | Lance stack complète (optionnel) |
