"""
Compatibility WSGI entry point for Render and PaaS environments.
When a Render Python Web Service is created manually in the dashboard (without
using the render.yaml Blueprint), Render defaults the Start Command to:
    gunicorn app:app

This module ensures the project root is on `sys.path` and bridges both
`app:app` and `app:application` directly to `bookmyseat.wsgi:application`.
"""

import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "bookmyseat.settings")

from bookmyseat.wsgi import application  # noqa: E402

app = application
