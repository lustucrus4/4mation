# 4mation



Jeu **4mation** (plateau 7×7, coups adjacents, alignement de 4) — frontend Vite + API Flask + IA Minimax/MCTS.



## Relation avec `4 mation/`



Ce dossier est la **restructuration Lab211** du projet historique situé dans `../4 mation/`. Le code source d'origine n'a pas été modifié ; les modules utiles ont été **copiés** dans `script/`.



## Structure



```

4mation/

├── 4mation_dashboard_dev/    # Frontend Vite (jeu + mode apprentissage)

├── 4mation_dashboard_deploy/ # Build statique pour Hostinger/VPS

├── api/                      # API Flask (parties, bots, MCTS)

├── script/                   # Moteur, Minimax optimisé, MCTS

├── scripts/deploy_vps.sh     # Script déploiement VPS (SSH manuel)

├── nginx_4mation.conf        # Config Nginx frontend + API

└── README.md

```



## URLs production



| Service | URL |

|---------|-----|

| Jeu | https://4mation.lab211.fr |

| API | https://api-4mation.lab211.fr |



DNS A → `31.97.197.72` (VPS srv910901) — enregistrements `4mation` et `api-4mation` créés via Hostinger MCP.



## Installation locale



### API



```bash

cd 4mation

python -m venv .venv

.venv\Scripts\activate          # Windows

pip install -r api/requirements.txt

```



### Frontend



```bash

cd 4mation_dashboard_dev

npm install

```



## Développement local



Terminal 1 — API (port 5000) :



```bash

cd 4mation

set PYTHONPATH=.

python api/app.py

```



Terminal 2 — Frontend (port 5173) :



```bash

cd 4mation_dashboard_dev

npm run dev

```



## Build frontend



```bash

cd 4mation_dashboard_dev

npm run build

```



Les fichiers sont générés dans `4mation_dashboard_deploy/`.



## API — endpoints



| Méthode | Route | Description |

|---------|-------|-------------|

| POST | `/api/session` | Crée une session (`mode`: `standard` ou `learning`) |

| GET | `/api/state` | État du plateau (sans analyse IA) |

| POST | `/api/reset` | Nouvelle partie |

| POST | `/api/move` | Coup joueur humain (joueur 1) |

| POST | `/api/ai_move` | Coup IA (`bot_id`, défaut `level_3`) |

| POST | `/api/analyze` | Analyse MCTS on-demand (budget 500–5000 ms) |

| POST | `/api/undo` | Annule N coups (`count`, défaut 1) |

| POST | `/api/undo_to` | Revient au coup N (`move_index`, 0 = début) |

| GET | `/api/bots` | Liste des bots |

| GET | `/api/health` | Santé du service |
| GET | `/api/solver/status` | Avancement solveur Phase C (live) |
| GET | `/api/solver/position/{hash}` | Détail position résolue |



### Bots disponibles



| ID | Profondeur | Budget | Levier principal | Description |

|----|------------|--------|------------------|-------------|

| `level_1` | 1 | 60 ms | ~95 % de coups au hasard | Très facile — un débutant gagne presque à tous les coups |

| `level_2` | 2 | 120 ms | ~70 % de coups au hasard | Facile — il voit une menace immédiate, mais se trompe souvent |

| `level_3` | 4 | 300 ms | ~40 % de coups au hasard | Moyen (**défaut**) — joue correctement, laisse encore des ouvertures |

| `level_4` | 8 | 1 200 ms | ~16 % d'erreurs graduées + tablebase | Difficile — moteur + tablebase + livre prouvé |

| `level_5` | 18 | 2 000 ms | ~8 % d'erreurs graduées | Très difficile — très profonde, s'écarte rarement de la preuve |

| `level_6` | 26 | 3 000 ms | aucune erreur | Impossible — joue les **lignes prouvées** sans jamais se tromper |



Les niveaux 1 à 3 sont gradués par un **taux de coup au hasard** — une faute franche,
immédiatement exploitable. Les niveaux 4 à 6 jouent la **même** ligne prouvée (livre
exact + tablebase) : leur seule différence est le **taux d'erreur graduée** (probabilité
de jouer le 2ᵉ choix du moteur au lieu du meilleur). Le niveau 6 a un taux nul : c'est
le seul infaillible **dans la zone résolue**, d'où son nom. Chaque niveau retombe
automatiquement sur le chemin du niveau inférieur si le binaire du moteur est absent.

Il n'existe **que** ces six niveaux : le joueur choisit un *cran de difficulté*, pas un
type de bot. `scripts/check_bot_arena.py` verrouille cet invariant par un test de contrat
(`test_ladder_contract`) — identifiants `level_1`…`level_6` exactement, libellés du
« Très facile » à l'« Impossible », profondeur, budget temps et Elo strictement croissants,
taux d'erreur volontaire strictement décroissant.

#### Limite honnête du niveau 6

« Impossible » signifie *infaillible là où la base prouve la position* (livre d'ouverture
+ tablebase exacte). L'ouverture du 4mation n'est pas résolue : hors de cette zone, le
niveau 6 est le plus fort moteur de l'échelle mais reste faillible. Mesuré : une sonde
qui joue en profondeur 8 avec 6 % d'erreurs marque encore ~0,28 contre lui (~0,17 en
profondeur 6, ~0,03 en profondeur 2 et ~0,01 en profondeur 4). Augmenter la profondeur ne
corrige pas ce taux (mesuré : profondeur 34 / 6 s fait *moins* bien que 26 / 3 s) : le
facteur limitant est la **couverture de la base**, pas la vitesse de recherche.

### Arène mesurée (`scripts/bot_arena.py`)

Les niveaux sont **mesurés** par paire en round-robin (sièges alternés) par
`scripts/bot_arena.py`, rapport `scripts/ARENA_BOTS.md` (Elo Bradley-Terry + IC 95 %).
Mesure du 26/09/2026 : 60 parties par paire (900 parties) et 4 profils de sonde
(96 parties par bot et par profil) :

`level_1` 1109 < `level_2` 1234 < `level_3` 1413 < `level_4` 1640 < `level_5` 1750 < `level_6` 1855.

L'ordre est strictement croissant, avec des écarts de **+125, +179, +227, +110, +105**
Elo. Le plus court (`level_5` → `level_6`) reste le plus délicat : ces deux niveaux jouent
la même ligne prouvée et ne diffèrent que par le taux d'erreur graduée, donc la
confrontation directe ne les sépare pas nettement (0,39 [0,28, 0,52]) — ce sont les quatre
profils de sonde qui tranchent. Attention d'une manière générale : l'Elo sature vers le
haut (dans ce jeu, jouer le centre gagne de force, donc un bot fort gagne presque toujours
dans le siège du premier joueur).

Le rapport fournit donc une seconde mesure, la **courbe de difficulté** : des sondeurs
de référence jouent *toujours en siège 1* (la configuration réelle du site) contre chaque
niveau. Quatre profils, du plus faible au plus fort, couvrent toute l'échelle — un profil
seul ne peut pas séparer les six niveaux, car il sature (un débutant ne marque jamais
contre les niveaux 5-6, un joueur avancé écrase les niveaux 1-3) :

| Profil | Profondeur | Erreurs | Bande de l'échelle qu'il sépare |
|--------|------------|---------|--------------------------------|
| `novice` | 4 | 30 % | niveaux 1 à 4 |
| `debutant` | 2 | 45 % | niveaux 1 à 4 |
| `moyen` | 6 | 15 % | niveaux 3 à 6 |
| `avance` | 8 | 6 % | niveaux 4 à 6 |

Score du sondeur en siège 1, 96 parties par niveau et par profil (plus bas = plus dur) :

| Profil | `level_1` | `level_2` | `level_3` | `level_4` | `level_5` | `level_6` |
|--------|---:|---:|---:|---:|---:|---:|
| `novice` | 0,99 | 0,91 | 0,77 | 0,61 | 0,26 | 0,01 |
| `debutant` | 0,94 | 0,80 | 0,60 | 0,29 | 0,14 | 0,03 |
| `moyen` | 1,00 | 0,96 | 0,91 | 0,72 | 0,51 | 0,17 |
| `avance` | 1,00 | 0,98 | 0,98 | 0,87 | 0,56 | 0,28 |

L'échelle est validée sur **deux affirmations distinctes**, car elles ne mesurent pas la
même chose — et les deux sont vertes :

- **la force** — le niveau supérieur gagne plus souvent en confrontation directe (sièges
  alternés) ou est plus dur à battre pour au moins une sonde. Une paire est validée si la
  confrontation directe ne démontre jamais l'inverse **et** qu'au moins un instrument
  démontre la séparation ; la démonstration porte sur la **différence** des scores
  (intervalle hybride de Newcombe excluant 0), et non sur la comparaison de deux
  intervalles de Wilson isolés, qui serait trop conservatrice. Verdict : **les 5 paires
  adjacentes sont validées**, et chacune est désormais démontrée par les **quatre** profils
  de sonde ;
- **la difficulté ressentie** — la courbe de sonde est **strictement décroissante** sur les
  quatre profils : aucun niveau n'est plus facile à battre que le précédent, pour aucun
  type d'adversaire. Ce point n'allait pas de soi : une version antérieure où `level_5` ne
  s'écartait de la preuve que 4 % du temps le rendait *plus prévisible*, donc plus facile à
  battre que `level_4` (0,89 contre 0,77 pour la sonde `avance`). Le réglage retenu
  (profondeur 18, 8 % d'écarts) fait s'écarter `level_5` plus souvent mais en choisissant
  mieux ses écarts, ce qui restaure la monotonie sans casser la séparation directe. Le
  contrôle est automatisé : `scripts/check_bot_arena.py` échoue si une inversion de
  difficulté réapparaît.

`scripts/ARENA_BOTS.md` conserve les intervalles, les caveats et le verdict paire par
paire.



### Mode apprentissage



- Session `mode: "learning"` : le coach joue après chaque coup humain.

- Frontend affiche le **taux de victoire estimé** de chaque coup légal, calculé par le

  moteur d'analyse (`4mation-engine` en mode analyse, ou la tablebase quand la position

  est exacte).

- Boutons **Annuler coup** et **Nouvelle variante** (undo + rejouer).



> Les pourcentages affichés sont une **estimation calibrée** (échelle mesurée sur les

> finales exactes), sauf quand l'étiquette indique « Exact (tablebase) » ou « Mat forcé

> en N coup(s) » : il s'agit alors d'une valeur prouvée.



## Tests



```bash

cd 4mation

set PYTHONPATH=script

python script/test_optimized_minimax.py

python script/test_mcts_advisor.py

```



## Déploiement production (VPS)



### État actuel



| Étape | Statut |

|-------|--------|

| DNS A `4mation` / `api-4mation` → 31.97.197.72 | ✅ Fait (Hostinger MCP) |

| Build frontend → `4mation_dashboard_deploy/` | ✅ Fait |

| Sites Hostinger shared hosting | ⏭ N/A (projet sur VPS) |

| Déploiement fichiers VPS (SSH) | ✅ Fait |

| Nginx + Gunicorn + SSL certbot | ✅ Fait |



Vérifié le 24/09/2026 : `https://4mation.lab211.fr` et `https://api-4mation.lab211.fr/api/health`

répondent **200**, HTTPS actif, PostgreSQL `ready`, tablebase disponible.



⚠️ La base déployée sur le VPS est **beaucoup plus petite** que celle du poste local

(`/api/health` annonce 1,5 M de positions et 900 entrées de livre, contre 24,4 M et

des dizaines de milliers en local). Le moteur `4mation-engine` est donc plus fort en

local qu'en production : voir la note de déploiement du moteur dans `api/README.md`.



### Procédure VPS (SSH)



1. Cloner/copier le repo dans `/opt/4mation/src` sur le VPS `31.97.197.72`

2. Exécuter `scripts/deploy_vps.sh` (ou étapes manuelles ci-dessous)

3. Copier `4mation_dashboard_deploy/` → `/var/www/4mation/`

4. Lancer Gunicorn :



```bash

cd /opt/4mation/src

export PYTHONPATH=.:script

gunicorn -c api/gunicorn_config.py api.app:app

```



5. Activer `nginx_4mation.conf` (deux vhosts : frontend + reverse proxy API)

6. Certificats SSL :



```bash

sudo certbot --nginx -d 4mation.lab211.fr -d api-4mation.lab211.fr

```



### Frontend production



Configurer `4mation_dashboard_dev/.env.production` :



```

VITE_API_URL=https://api-4mation.lab211.fr

```



Puis `npm run build` et déployer `4mation_dashboard_deploy/`.



## SSO Lab211



Ajouter dans la configuration auth Lab211 (`auth.lab211.fr`) :



- **Origin autorisée** : `https://4mation.lab211.fr`

- **Redirect URI** : `https://4mation.lab211.fr` (callback popup SSO)

- Le bouton **Connexion** est en placeholder dans le frontend.

## Dashboard solveur

Page **https://4mation.lab211.fr/solver.html** — progression Phase C, vitesse, ETA, mini-plateaux des derniers coups calculés. Lien discret depuis la page d'accueil.



## Licence



Projet privé Lab211.

