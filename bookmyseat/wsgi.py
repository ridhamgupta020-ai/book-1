"""WSGI config for MyBookShow."""
import os
import sys
from pathlib import Path
from django.core.wsgi import get_wsgi_application

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "bookmyseat.settings")
application = get_wsgi_application()

# Automatically verify DB connectivity, run pending migrations, and seed catalog on startup
from bookmyseat.bootstrap import ensure_database_ready  # noqa: E402

ensure_database_ready()

app = application
