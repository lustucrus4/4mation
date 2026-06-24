#!/bin/bash
# Déploiement manuel 4mation sur VPS Hostinger (31.97.197.72)
# À exécuter sur le serveur après SSH

set -euo pipefail

APP_DIR="/opt/4mation"
REPO_DIR="${APP_DIR}/src"

echo "=== Déploiement 4mation ==="

# 1. Frontend statique
sudo mkdir -p /var/www/4mation
sudo rsync -av --delete "${REPO_DIR}/4mation_dashboard_deploy/" /var/www/4mation/

# 2. API Python
cd "${REPO_DIR}"
python3 -m venv "${APP_DIR}/venv"
source "${APP_DIR}/venv/bin/activate"
pip install -r api/requirements.txt

# 3. Service systemd (exemple)
sudo tee /etc/systemd/system/4mation-api.service > /dev/null <<'UNIT'
[Unit]
Description=4mation API Gunicorn
After=network.target

[Service]
User=www-data
WorkingDirectory=/opt/4mation/src
Environment=PYTHONPATH=/opt/4mation/src:/opt/4mation/src/script
ExecStart=/opt/4mation/venv/bin/gunicorn -c api/gunicorn_config.py api.app:app
Restart=always

[Install]
WantedBy=multi-user.target
UNIT

sudo systemctl daemon-reload
sudo systemctl enable --now 4mation-api

# 4. Nginx
sudo cp "${REPO_DIR}/nginx_4mation.conf" /etc/nginx/sites-available/4mation
sudo ln -sf /etc/nginx/sites-available/4mation /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx

# 5. SSL (si certbot disponible)
sudo certbot --nginx -d 4mation.lab211.fr -d api-4mation.lab211.fr

echo "=== Terminé — vérifier https://4mation.lab211.fr et https://api-4mation.lab211.fr/api/health ==="
