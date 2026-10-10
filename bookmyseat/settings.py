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

IS_RENDER = os.getenv("RENDER", "").lower() == "true" or bool(os.getenv("RENDER_EXTERNAL_HOSTNAME"))
IS_VERCEL = os.getenv("VERCEL", "") == "1" or bool(os.getenv("VERCEL_URL"))

DEBUG = os.getenv("DEBUG", "False").strip().lower() in ("true", "1", "yes")

SECRET_KEY = os.getenv("SECRET_KEY", "").strip()
if not SECRET_KEY or SECRET_KEY == "replace-with-a-generated-django-secret":
    if not DEBUG and not (IS_RENDER or IS_VERCEL):
        raise ImproperlyConfigured(
            "CRITICAL: SECRET_KEY environment variable must be set to a strong secret in production."
        )
    # Safe fallback if platform env var has not been entered in dashboard yet
    SECRET_KEY = os.getenv(
        "RENDER_SERVICE_ID",
        os.getenv("VERCEL_PROJECT_ID", "django-insecure-mybookshow-fallback-key-change-in-env"),
    ) + "-mybookshow-hmac-signing-key"

raw_allowed_hosts = os.getenv(
    "ALLOWED_HOSTS",
    "localhost,127.0.0.1,.onrender.com,.vercel.app",
)
ALLOWED_HOSTS = [h.strip() for h in raw_allowed_hosts.split(",") if h.strip()]

render_hostname = os.getenv("RENDER_EXTERNAL_HOSTNAME", "").strip()
if render_hostname and render_hostname not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(render_hostname)

vercel_url = os.getenv("VERCEL_URL", "").strip()
if vercel_url and vercel_url not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(vercel_url)

if ".onrender.com" not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(".onrender.com")
if ".vercel.app" not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(".vercel.app")

raw_csrf_origins = os.getenv(
    "CSRF_TRUSTED_ORIGINS",
    "https://*.onrender.com,https://*.vercel.app",
)
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

FIREBASE_WEB_CONFIG = {
    "apiKey": os.getenv("VITE_FIREBASE_API_KEY", "").strip(),
    "authDomain": os.getenv("VITE_FIREBASE_AUTH_DOMAIN", "").strip(),
    "projectId": os.getenv("VITE_FIREBASE_PROJECT_ID", "").strip(),
    "storageBucket": os.getenv("VITE_FIREBASE_STORAGE_BUCKET", "").strip(),
    "messagingSenderId": os.getenv("VITE_FIREBASE_MESSAGING_SENDER_ID", "").strip(),
    "appId": os.getenv("VITE_FIREBASE_APP_ID", "").strip(),
}

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
_is_placeholder_db = (
    not DATABASE_URL
    or "YOUR_PASSWORD" in DATABASE_URL
    or "YOUR_DATABASE_HOST" in DATABASE_URL
)

if _is_placeholder_db:
    sqlite_path = Path("/tmp/db.sqlite3") if (IS_VERCEL or IS_RENDER) else (BASE_DIR / "db.sqlite3")
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": sqlite_path,
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
STATICFILES_DIRS = [BASE_DIR / "static"] if (BASE_DIR / "static").exists() else []
STATIC_ROOT = BASE_DIR / "staticfiles"

# Enable WhiteNoise finders so Render and Vercel serve static/ even if collectstatic was skipped
WHITENOISE_USE_FINDERS = True
WHITENOISE_AUTOREFRESH = DEBUG

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        # Use CompressedStaticFilesStorage so missing manifest files never trigger HTTP 500
        "BACKEND": "whitenoise.storage.CompressedStaticFilesStorage",
    },
}

MEDIA_URL = "/media/"
MEDIA_ROOT = Path("/tmp/media") if IS_VERCEL else (BASE_DIR / "media")
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024  # 5 MB upload ceiling

# Authentication redirects
LOGIN_URL = "users:login"
LOGIN_REDIRECT_URL = "movies:home"
LOGOUT_REDIRECT_URL = "movies:home"

# Production HTTPS & Cookie Security
if not DEBUG:
    SECURE_SSL_REDIRECT = os.getenv("SECURE_SSL_REDIRECT", "False").lower() in ("true", "1")
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    CSRF_COOKIE_HTTPONLY = True
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
