# API 4mation

API Flask pour les parties, bots Minimax et analyse MCTS (mode coach).

## Lancement

```bash
cd ..
set PYTHONPATH=.
python api/app.py
```

## Production

```bash
export PYTHONPATH=.:script
gunicorn -c api/gunicorn_config.py api.app:app
```

## Endpoints principaux

- `POST /api/analyze` — MCTS on-demand (budget temps configurable)
- `POST /api/undo` / `POST /api/undo_to` — navigation dans l'historique
- `POST /api/session` — `mode: "learning"` pour le coach MCTS

Voir le README racine pour la liste complète.
