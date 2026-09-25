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

| POST | `/api/ai_move` | Coup IA (`bot_id`, défaut `minimax_d4`) |

| POST | `/api/analyze` | Analyse MCTS on-demand (budget 500–5000 ms) |

| POST | `/api/undo` | Annule N coups (`count`, défaut 1) |

| POST | `/api/undo_to` | Revient au coup N (`move_index`, 0 = début) |

| GET | `/api/bots` | Liste des bots |

| GET | `/api/health` | Santé du service |
| GET | `/api/solver/status` | Avancement solveur Phase C (live) |
| GET | `/api/solver/position/{hash}` | Détail position résolue |



### Bots disponibles



| ID | Profondeur | Budget | Description |

|----|------------|--------|-------------|

| `level_1` | 1 | 120 ms | Débutant — 55 % de coups approximatifs |

| `level_2` | 2 | 250 ms | Facile — 30 % de coups approximatifs |

| `level_3` | 4 | 600 ms | Intermédiaire — **défaut** |

| `level_4` | 6 | 1 000 ms | Avancé — tablebase activée |

| `level_5` | 10 | 1 600 ms | Expert — recherche maximale + tablebase |

| `level_6` | 22 | 2 500 ms | Maître — **moteur Rust** `4mation-engine`, finales exactes |



Chaque niveau s'approprie un Elo à la fin des parties classiques (voir

`api/README.md`). Le niveau 6 retombe automatiquement sur le chemin du niveau 5 si le

binaire du moteur est absent.



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

