"""
Gunicorn configuration file for Render deployment (gunicorn.conf.py).
Ensures `/opt/render/project/src` is on `sys.path` and sets the default WSGI
application so Gunicorn never fails with `ModuleNotFoundError: No module named 'app'`.
"""

import multiprocessing
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "bookmyseat.settings")

# Canonical WSGI application target
wsgi_app = "bookmyseat.wsgi:application"

# Bind to Render's injected PORT environment variable
port = os.getenv("PORT", "10000")
bind = f"0.0.0.0:{port}"

# Worker configuration
workers = int(os.getenv("WEB_CONCURRENCY", min(multiprocessing.cpu_count() * 2 + 1, 3)))
threads = int(os.getenv("PYTHON_MAX_THREADS", "2"))
timeout = 60
keepalive = 5

# Safe production logging to stdout/stderr
accesslog = "-"
errorlog = "-"
loglevel = "info"
