import os
import sys
from pathlib import Path

# Add project root to sys.path so bookmyseat is importable in Vercel serverless runtime
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "bookmyseat.settings")

from django.core.wsgi import get_wsgi_application

app = get_wsgi_application()
