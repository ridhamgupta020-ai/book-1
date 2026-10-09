"""WSGI config for MyBookShow."""
import os
from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "bookmyseat.settings")
application = get_wsgi_application()
app = application
