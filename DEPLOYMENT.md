# MyBookShow — Django 5.1 + Supabase PostgreSQL + Render + Vercel Guide

## 1. Supabase Configuration & CLI

### Project Details
- **Project URL**: `https://iqxcgzrfjplernbidkfd.supabase.co`
- **Project Reference**: `iqxcgzrfjplernbidkfd`
- **Database Name**: `postgres`
- **Primary Schema Manager**: **Django ORM (`manage.py makemigrations` / `manage.py migrate`)**

> **Important Schema Boundary**: All application tables (`movies_*`, `bookings_*`, `users_*`, `auth_*`) are managed exclusively by Django migrations (`movies/migrations/`, `bookings/migrations/`, `users/migrations/`). Do **not** create competing SQL migrations inside `supabase/migrations/` for Django-managed tables.

### Supabase CLI Linking Commands
Run these commands in your local terminal when linking the repository to your Supabase project:

```bash
npm install -g supabase
supabase login
supabase init
supabase link --project-ref iqxcgzrfjplernbidkfd
```

- `supabase login` requires interactive browser/token authentication in your local terminal.
- If `supabase/config.toml` already exists in the repository, skip `supabase init`.
- Never commit `.env`, database passwords, or personal Supabase access tokens to Git.

### Connection String Strategy (`DATABASE_URL`)
- **Render / IPv4-only environments**: Use the **Supabase Session Pooler** connection string (`port 5432` on `*.pooler.supabase.com`), because direct `db.iqxcgzrfjplernbidkfd.supabase.co` resolves to IPv6 by default.
- **SSL Enforcement**: `bookmyseat/settings.py` automatically configures `sslmode=require` whenever connecting to Supabase hosts (`*.supabase.co` or `*.pooler.supabase.com`).

---

## 2. Local Installation & Verification

```bash
# 1. Create and activate a Python 3.12+ virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 2. Install dependencies
pip install --upgrade pip
pip install -r requirements.txt

# 3. Configure environment variables
cp .env.example .env
# Edit .env and set SECRET_KEY, DATABASE_URL (Supabase Session Pooler URI), and SUPABASE_PUBLISHABLE_KEY

# 4. Run Django checks, migrations, static collection, and automated test suite
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py test

# 5. Start local server
python manage.py runserver
```

---

## 3. GitHub Push Instructions

```bash
git init
git status  # Verify .env is ignored by .gitignore
git add .
git commit -m "feat: complete MyBookShow Django + Supabase ticket booking platform"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/mybookshow.git
git push -u origin main
```

---

## 4. Render Deployment (Recommended Primary Host)

> **CRITICAL — Why Render Runs `gunicorn app:app` by Default**:
> If you created your service in Render using **New + → Web Service** (instead of **New + → Blueprint**), Render **ignores `render.yaml`** and uses the commands typed inside the Render Dashboard UI (**Settings → Build & Deploy**), which default to `pip install -r requirements.txt` and `gunicorn app:app`.
>
> **Immediate Fix in Render Dashboard (`Settings → Build & Deploy`)**:
> 1. **Build Command**:
>    ```bash
>    pip install -r requirements.txt && python manage.py collectstatic --noinput && python manage.py migrate --noinput
>    ```
>    *(or `bash ./build.sh` once pushed to GitHub)*
> 2. **Start Command**:
>    ```bash
>    gunicorn bookmyseat.wsgi:application --bind 0.0.0.0:$PORT
>    ```
> 3. Click **Save Changes**, then click **Manual Deploy → Deploy latest commit** (and make sure you have committed & pushed your latest files to GitHub).

1. Push the repository to GitHub.
2. In the [Render Dashboard](https://dashboard.render.com), click **New + -> Blueprint** and select your repository (`render.yaml` is pre-configured).
3. Set the required environment variables in Render:
   - `DEBUG` = `False`
   - `SECRET_KEY` = *(auto-generated or strong 50+ char random string)*
   - `DATABASE_URL` = `postgresql://postgres.iqxcgzrfjplernbidkfd:YOUR_DB_PASSWORD@aws-0-ap-south-1.pooler.supabase.com:5432/postgres?sslmode=require`
   - `ALLOWED_HOSTS` = `.onrender.com,your-custom-domain.com`
   - `CSRF_TRUSTED_ORIGINS` = `https://*.onrender.com`
   - `SUPABASE_URL` = `https://iqxcgzrfjplernbidkfd.supabase.co`
   - `SUPABASE_PUBLISHABLE_KEY` = `your-supabase-publishable-key`
   - `VITE_FIREBASE_API_KEY`, `VITE_FIREBASE_AUTH_DOMAIN`, `VITE_FIREBASE_PROJECT_ID`, `VITE_FIREBASE_STORAGE_BUCKET`, `VITE_FIREBASE_MESSAGING_SENDER_ID`, and `VITE_FIREBASE_APP_ID` = Firebase project's public Web app configuration values.
   - `FIREBASE_ADMIN_CREDENTIALS` = the Firebase service account JSON, stored as a Render secret. Never commit this value.
4. Render executes `./build.sh` (`pip install -r requirements.txt`, `python manage.py collectstatic --noinput`, `python manage.py migrate --noinput`) and starts Gunicorn with:
   ```bash
   gunicorn bookmyseat.wsgi:application --bind 0.0.0.0:$PORT --workers 3 --timeout 60
   ```
5. In Firebase Console, enable **Authentication → Sign-in method → Google** and add the exact Render hostname (for example, `book-1-ya9s.onrender.com`) under **Authentication → Settings → Authorized domains**. Also enable the Google provider for the same Firebase project used by the Admin service account.
6. Deploy the updated commit to Render. The deployment applies Django migrations; then test the Google flow on the deployed login page. The backend only creates a Django session after verifying a Google-provider Firebase ID token with a verified email.

---

## 5. Vercel Deployment & Limitations

- `vercel.json` and `api/index.py` provide a valid WSGI serverless entry point for `@vercel/python` (`python3.12`).
- **Important Runtime Note**: Vercel's serverless Python runtime has a read-only filesystem at runtime, strict cold-start bundle limits (`psycopg2-binary` + `Pillow`), and does not run persistent background workers. Therefore, **Render is the recommended primary production host** for the full Django application.
- If deploying to Vercel:
  1. Configure `SECRET_KEY`, `DEBUG=False`, `DATABASE_URL` (Supabase Pooler with `?sslmode=require`), `ALLOWED_HOSTS=.vercel.app`, and `CSRF_TRUSTED_ORIGINS=https://*.vercel.app` separately in Vercel Project Settings.
  2. Run `python manage.py migrate` during CI/build or from your linked environment rather than concurrently inside serverless request handlers.

---

## 6. Troubleshooting Guide

| Symptom / Error | Root Cause | Resolution |
| :--- | :--- | :--- |
| `No interpreter found for Python 3.12.6 in managed installations` | Vercel's `uv` builder only resolves major.minor (`3.12`) in `.python-version`, not exact patch versions (`3.12.6`). | Keep `.python-version` set to `3.12` (already updated) and delete any `runtime.txt`. |
| `ModuleNotFoundError: No module named 'app'` | Render manual Web Service defaults Start Command to `gunicorn app:app` instead of `gunicorn bookmyseat.wsgi:application`. | Set Render **Start Command** to `gunicorn bookmyseat.wsgi:application` (a root `app.py` WSGI bridge is also included so `gunicorn app:app` works automatically). |
| `ImproperlyConfigured: SECRET_KEY...` | `SECRET_KEY` missing or left as placeholder when `DEBUG=False`. | Set a real random `SECRET_KEY` in Render/Vercel Environment Variables. |
| `OperationalError: Network is unreachable` | Direct Supabase host (`db.<ref>.supabase.co`) uses IPv6, which some PaaS containers lack. | Switch `DATABASE_URL` to the **Supabase IPv4 Session Pooler** (`aws-0-<region>.pooler.supabase.com:5432`). |
| `OperationalError: SSL connection has been closed` | Missing SSL mode or stale pooled connection. | Ensure `?sslmode=require` is present; `CONN_HEALTH_CHECKS=True` is enabled in `settings.py`. |
| `400 Bad Request` in production | Domain not listed in `ALLOWED_HOSTS`. | Add `.onrender.com` or `.vercel.app` to `ALLOWED_HOSTS`. |
| `403 Forbidden (CSRF verification failed)` | HTTPS origin missing from `CSRF_TRUSTED_ORIGINS`. | Set `CSRF_TRUSTED_ORIGINS=https://your-app.onrender.com` (include `https://`). |
| Missing CSS / 404 on `/static/` | `collectstatic` was not run during build. | Verify `./build.sh` runs `python manage.py collectstatic --noinput` and WhiteNoise middleware is active. |
