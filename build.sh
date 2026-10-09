#!/usr/bin/env bash
# ==============================================================================
# MyBookShow — Render Production Build Script (build.sh)
# ==============================================================================
# Resolves `ModuleNotFoundError` and environment drift during Render builds by:
# 1. Anchoring execution to the repository root where `manage.py` resides.
# 2. Exporting `PYTHONPATH` and `DJANGO_SETTINGS_MODULE`.
# 3. Installing dependencies into Render's active virtual environment.
# 4. Verifying WSGI module importability (`bookmyseat.wsgi` & `app`) before
#    collecting static assets and running Supabase PostgreSQL migrations.
# ==============================================================================

set -o errexit
set -o pipefail
set -o nounset

# 1. Anchor working directory to project root (/opt/render/project/src on Render)
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${PROJECT_ROOT}"

export PYTHONPATH="${PROJECT_ROOT}:${PYTHONPATH:-}"
export DJANGO_SETTINGS_MODULE="bookmyseat.settings"

echo "==> [1/5] Verifying Python environment in ${PROJECT_ROOT}..."
python --version
which python
which pip

echo "==> [2/5] Upgrading pip, setuptools, and wheel & installing requirements.txt..."
python -m pip install --upgrade pip setuptools wheel
python -m pip install --no-cache-dir -r "${PROJECT_ROOT}/requirements.txt"

echo "==> [3/5] Verifying WSGI entry points (bookmyseat.wsgi & app compatibility bridge)..."
python -c "
import sys, os
sys.path.insert(0, '${PROJECT_ROOT}')
import bookmyseat.wsgi
import app
assert hasattr(bookmyseat.wsgi, 'application'), 'bookmyseat.wsgi:application missing'
assert hasattr(app, 'app'), 'app:app bridge missing'
print('WSGI entry point verification passed successfully.')
"

echo "==> [4/5] Running Django system check and collecting WhiteNoise static files..."
python manage.py check
python manage.py collectstatic --noinput --clear

echo "==> [5/5] Applying Django database migrations..."
if [ -n "${DATABASE_URL:-}" ]; then
    python manage.py migrate --noinput
else
    echo "Notice: DATABASE_URL is not set during build; skipping remote migration until DATABASE_URL is configured."
fi

echo "==> Build completed successfully."
