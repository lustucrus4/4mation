"""Configuration Gunicorn pour l'API 4mation."""

import os

bind = os.environ.get("GUNICORN_BIND", "127.0.0.1:5000")
# 4 workers recommandé si plusieurs machines locales (16+ clients claim/submit).
workers = int(os.environ.get("GUNICORN_WORKERS", "4"))
timeout = 120
worker_class = "sync"
proc_name = "4mation_api"
accesslog = "-"
errorlog = "-"
loglevel = "info"
max_requests = 1000
max_requests_jitter = 50
