#!/bin/sh
set -eu

CERT=/etc/letsencrypt/live/4mation.lab211.fr
test -f "$CERT/fullchain.pem"
test -f "$CERT/privkey.pem"

cat > /etc/nginx/sites-available/4mation <<'EOF'
server {
    listen 80;
    server_name 4mation.lab211.fr;
    location /.well-known/acme-challenge/ { root /var/www/certbot; }
    location / { return 301 https://$host$request_uri; }
}

server {
    listen 443 ssl;
    server_name 4mation.lab211.fr;
    ssl_certificate /etc/letsencrypt/live/4mation.lab211.fr/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/4mation.lab211.fr/privkey.pem;
    include /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;
    root /var/www/4mation;
    index index.html;
    location /assets/ {
        expires 30d;
        add_header Cache-Control "public, immutable";
    }
    location /socket.io/ {
        proxy_pass http://127.0.0.1:8098;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 86400s;
        proxy_send_timeout 86400s;
    }
    location /api/ {
        proxy_pass http://127.0.0.1:8097;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;
        proxy_buffering off;
    }
    location / { try_files $uri $uri/ /index.html; }
}

server {
    listen 80;
    server_name api-4mation.lab211.fr;
    location /.well-known/acme-challenge/ { root /var/www/certbot; }
    location / { return 301 https://$host$request_uri; }
}

server {
    listen 443 ssl;
    server_name api-4mation.lab211.fr;
    ssl_certificate /etc/letsencrypt/live/4mation.lab211.fr/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/4mation.lab211.fr/privkey.pem;
    include /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;
    location /socket.io/ {
        proxy_pass http://127.0.0.1:8098;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 86400s;
        proxy_send_timeout 86400s;
    }
    location / {
        proxy_pass http://127.0.0.1:8097;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
    }
}
EOF

ln -sf /etc/nginx/sites-available/4mation /etc/nginx/sites-enabled/4mation
nginx -t
systemctl enable nginx || true
systemctl start nginx || true
if ! systemctl is-active --quiet nginx 2>/dev/null; then
  nginx || true
fi
systemctl is-active nginx || true
ss -lntp | grep -E ':80|:443' || true
echo RESTORE_OK
