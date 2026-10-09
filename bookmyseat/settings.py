"""
Django settings for MyBookShow (bookmyseat).
Configured for Supabase PostgreSQL (session/transaction pooler or direct SSL),
WhiteNoise static asset serving, and Render / Vercel deployment.
"""

import os
from pathlib import Path
import dj_database_url
from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Load local .env file if present (never committed to Git)
load_dotenv(BASE_DIR / ".env")

DEBUG = os.getenv("DEBUG", "False").strip().lower() in ("true", "1", "yes")

SECRET_KEY = os.getenv("SECRET_KEY", "").strip()
if not SECRET_KEY or SECRET_KEY == "replace-with-a-generated-django-secret":
    if not DEBUG:
        raise ImproperlyConfigured(
            "CRITICAL: SECRET_KEY environment variable must be set to a strong secret in production."
        )
    # Explicit development-only fallback when DEBUG=True
    SECRET_KEY = "django-insecure-dev-only-mybookshow-local-key-do-not-use-in-prod"

raw_allowed_hosts = os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1" if DEBUG else "")
ALLOWED_HOSTS = [h.strip() for h in raw_allowed_hosts.split(",") if h.strip()]

# Automatically trust Render and Vercel assigned hostnames when deployed
render_hostname = os.getenv("RENDER_EXTERNAL_HOSTNAME", "").strip()
if render_hostname and render_hostname not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(render_hostname)

vercel_url = os.getenv("VERCEL_URL", "").strip()
if vercel_url and vercel_url not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(vercel_url)

if not DEBUG and not ALLOWED_HOSTS:
    raise ImproperlyConfigured("CRITICAL: ALLOWED_HOSTS must be configured when DEBUG=False.")

raw_csrf_origins = os.getenv("CSRF_TRUSTED_ORIGINS", "")
CSRF_TRUSTED_ORIGINS = [o.strip() for o in raw_csrf_origins.split(",") if o.strip()]
if render_hostname:
    render_origin = f"https://{render_hostname}"
    if render_origin not in CSRF_TRUSTED_ORIGINS:
        CSRF_TRUSTED_ORIGINS.append(render_origin)
if vercel_url:
    vercel_origin = f"https://{vercel_url}"
    if vercel_origin not in CSRF_TRUSTED_ORIGINS:
        CSRF_TRUSTED_ORIGINS.append(vercel_origin)

# Supabase Project Metadata (Project Ref: iqxcgzrfjplernbidkfd)
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://iqxcgzrfjplernbidkfd.supabase.co").strip()
SUPABASE_PUBLISHABLE_KEY = os.getenv("SUPABASE_PUBLISHABLE_KEY", "").strip()

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "whitenoise.runserver_nostatic",
    "django.contrib.staticfiles",
    # MyBookShow applications
    "users",
    "movies",
    "bookings",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "bookmyseat.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "bookmyseat.wsgi.application"
ASGI_APPLICATION = "bookmyseat.asgi.application"

# Database Configuration: Supabase PostgreSQL via DATABASE_URL
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
if not DATABASE_URL:
    if not DEBUG:
        raise ImproperlyConfigured(
            "CRITICAL: DATABASE_URL environment variable is required in production (Supabase PostgreSQL)."
        )
    # Local development fallback only when DEBUG=True and DATABASE_URL is unset
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }
else:
    is_postgres = DATABASE_URL.startswith(("postgres://", "postgresql://"))
    DATABASES = {
        "default": dj_database_url.parse(
            DATABASE_URL,
            conn_max_age=600,
            conn_health_checks=True,
            ssl_require=is_postgres and not DEBUG,
        )
    }
    if is_postgres and ("supabase.co" in DATABASE_URL or "pooler.supabase.com" in DATABASE_URL):
        DATABASES["default"].setdefault("OPTIONS", {})
        DATABASES["default"]["OPTIONS"]["sslmode"] = "require"

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Internationalization & Timezone
LANGUAGE_CODE = "en-in"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True

# Static and Media files (WhiteNoise)
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024  # 5 MB upload ceiling

# Authentication redirects
LOGIN_URL = "users:login"
LOGIN_REDIRECT_URL = "movies:home"
LOGOUT_REDIRECT_URL = "movies:home"

# Production HTTPS & Cookie Security
if not DEBUG:
    SECURE_SSL_REDIRECT = os.getenv("SECURE_SSL_REDIRECT", "True").lower() in ("true", "1")
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    CSRF_COOKIE_HTTPONLY = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_CONTENT_TYPE_NOSNIFF = True

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Safe structured logging that never prints credentials or DATABASE_URL
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "safe": {
            "format": "[{asctime}] {levelname} {name}: {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "safe",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
}
