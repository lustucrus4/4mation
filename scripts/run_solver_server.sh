#!/usr/bin/env bash
# Démarre le solveur Phase C en arrière-plan sur le VPS Hostinger
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_DIR="${SCRIPT_DIR}/../deploy"

echo "=== 4mation — lancement solveur background (Phase C) ==="

if ! docker volume inspect 4mation-sessions >/dev/null 2>&1; then
  echo "Création du volume 4mation-sessions…"
  docker volume create 4mation-sessions
fi

cd "${DEPLOY_DIR}"
docker compose -f docker-compose.solver.yml up -d --remove-orphans

echo "Solveur démarré. Logs : docker logs -f 4mation-solver"
docker ps --filter name=4mation-solver --format "table {{.Names}}\t{{.Status}}"
