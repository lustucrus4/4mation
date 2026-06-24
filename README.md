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

### Bots disponibles

| ID | Profondeur | Description |
|----|------------|-------------|
| `random` | — | Aléatoire |
| `minimax_d2` | 2 | Minimax optimisé, rapide |
| `minimax_d4` | 4 | **Défaut** — débutant |
| `minimax_d6` | 6 | Intermédiaire |
| `minimax_d8` | 8 | Avancé |

### Mode apprentissage

- Session `mode: "learning"` : coach invisible (MCTS) joue après chaque coup humain.
- Frontend affiche le **% victoire MCTS** sur chaque coup légal.
- Boutons **Annuler coup** et **Nouvelle variante** (undo + rejouer).

> En mode classique, les scores Minimax sont des **scores estimés** heuristiques (pas un vrai % victoire).

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
| Déploiement fichiers VPS (SSH) | ❌ **Manuel requis** |
| Nginx + Gunicorn + SSL certbot | ❌ **Manuel requis** |

HTTP actuel : `404` sur les deux domaines (DNS OK, vhosts non configurés sur le VPS).

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

## Licence

Projet privé Lab211.
