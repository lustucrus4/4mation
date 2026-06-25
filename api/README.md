# API 4mation

API Flask pour les parties, bots, analyse MCTS et comptes joueurs (phase 2).

## Lancement local

```bash
cd 4mation
set PYTHONPATH=.
pip install -r api/requirements.txt
python api/app.py
```

Variables utiles : voir `api/.env.example` (`DATABASE_URL`, `LAB211_*`, chemins DB).

## Production

```bash
export PYTHONPATH=.:script
export DATABASE_URL=postgresql://...
gunicorn -c api/gunicorn_config.py api.app:app
```

Sur le VPS : `deploy/docker-compose.vps.yml` inclut PostgreSQL 16 + l'API.

## Authentification (Lab211)

Les routes `/api/me/*` exigent une session SSO Lab211 (cookie `.lab211.fr`).
L'API relaie le cookie du navigateur vers `GET /api/auth/session?site_key=4mation`.

Le jeu vs bots reste jouable **sans connexion** ; la sauvegarde et l'Elo ne s'appliquent
qu'aux utilisateurs connectés en **mode classique**.

## Endpoints compte (phase 2)

| Méthode | Route | Description |
|---------|-------|-------------|
| GET | `/api/me` | Profil + Elo + 10 dernières parties |
| GET | `/api/me/games?limit=&offset=` | Historique paginé |
| GET | `/api/me/games/<uuid>/review` | Game Review (précision, coups classifiés, graphe) |

## Endpoints jeu (rappel)

- `POST /api/session` — body `{ mode, bot_id? }`
- `POST /api/reset` — body `{ mode, bot_id? }`
- `POST /api/move` / `POST /api/ai_move` — renvoie `saved_game` si partie finie + connecté
- `GET /api/health` — inclut l'état PostgreSQL

## Elo (vs bots)

5 niveaux (`level_1` … `level_5`). Elo de référence bot : 800 → 1800.
K-factor 32. Mise à jour automatique à la fin de chaque partie classique enregistrée.
