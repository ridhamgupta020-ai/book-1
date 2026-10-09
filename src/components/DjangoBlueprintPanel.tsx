import React, { useState } from 'react';
import { Copy, Check, Terminal, Database, Server, ShieldCheck } from 'lucide-react';

interface CodeArtifact {
  id: string;
  path: string;
  category: string;
  summary: string;
  content: string;
}

const CODE_ARTIFACTS: CodeArtifact[] = [
  {
    id: 'settings-py',
    path: 'bookmyseat/settings.py',
    category: 'Django Core & Security',
    summary: 'Environment-based SECRET_KEY, DEBUG, DATABASE_URL (Supabase SSL), WhiteNoise, and Asia/Kolkata timezone.',
    content: `import os
from pathlib import Path
import dj_database_url
from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

DEBUG = os.getenv("DEBUG", "False").strip().lower() in ("true", "1", "yes")

SECRET_KEY = os.getenv("SECRET_KEY", "").strip()
if not SECRET_KEY or SECRET_KEY == "replace-with-a-generated-django-secret":
    if not DEBUG:
        raise ImproperlyConfigured("CRITICAL: SECRET_KEY must be set in production.")
    SECRET_KEY = "django-insecure-dev-only-mybookshow-local-key"

SUPABASE_URL = os.getenv("SUPABASE_URL", "https://iqxcgzrfjplernbidkfd.supabase.co").strip()
SUPABASE_PUBLISHABLE_KEY = os.getenv("SUPABASE_PUBLISHABLE_KEY", "").strip()

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
if not DATABASE_URL and not DEBUG:
    raise ImproperlyConfigured("CRITICAL: DATABASE_URL is required in production.")

DATABASES = {
    "default": dj_database_url.parse(
        DATABASE_URL,
        conn_max_age=600,
        conn_health_checks=True,
        ssl_require=not DEBUG,
    )
}
if "supabase.co" in DATABASE_URL or "pooler.supabase.com" in DATABASE_URL:
    DATABASES["default"].setdefault("OPTIONS", {})["sslmode"] = "require"

TIME_ZONE = "Asia/Kolkata"
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"`,
  },
  {
    id: 'bookings-models',
    path: 'bookings/models.py',
    category: 'PostgreSQL Row Locking',
    summary: 'Uses transaction.atomic() and ShowSeat.objects.select_for_update() to prevent concurrent double booking.',
    content: `@classmethod
def create_pending_booking(cls, *, user, show: Show, show_seat_ids: list[int]):
    if not show_seat_ids or len(show_seat_ids) > 10:
        raise ValidationError("Select between 1 and 10 seats.")

    now = timezone.now()
    with transaction.atomic():
        locked_seats = list(
            ShowSeat.objects.select_for_update()
            .select_related("seat")
            .filter(show=show, id__in=show_seat_ids)
            .order_by("id")
        )
        for ss in locked_seats:
            if ss.status == ShowSeat.Status.HELD and ss.held_until and ss.held_until <= now:
                ss.status = ShowSeat.Status.AVAILABLE
                ss.held_by = None
                ss.held_until = None
            if ss.status == ShowSeat.Status.BOOKED:
                raise ValidationError(f"Seat {ss.seat.label} is already booked.")
            if ss.status == ShowSeat.Status.HELD and ss.held_by_id != user.id:
                raise ValidationError(f"Seat {ss.seat.label} is held by another user.")`,
  },
  {
    id: 'env-example',
    path: '.env.example',
    category: 'Environment Template',
    summary: 'Safe placeholder template for Supabase PostgreSQL and Django secrets (excluded from Git via .gitignore).',
    content: `SECRET_KEY=replace-with-a-generated-django-secret
DEBUG=True
DATABASE_URL=postgresql://postgres:YOUR_PASSWORD@YOUR_DATABASE_HOST:5432/postgres
ALLOWED_HOSTS=localhost,127.0.0.1
CSRF_TRUSTED_ORIGINS=
SUPABASE_URL=https://iqxcgzrfjplernbidkfd.supabase.co
SUPABASE_PUBLISHABLE_KEY=your-supabase-publishable-key`,
  },
  {
    id: 'render-yaml',
    path: 'render.yaml, build.sh & gunicorn.conf.py',
    category: 'Render Deployment',
    summary: 'Tailored Render Blueprint, build script, and Gunicorn config engineered to prevent ModuleNotFoundError during deployment.',
    content: `# render.yaml
services:
  - type: web
    name: mybookshow-web
    runtime: python
    region: singapore
    plan: free
    branch: main
    rootDir: .
    buildCommand: "bash ./build.sh"
    startCommand: "gunicorn bookmyseat.wsgi:application --config gunicorn.conf.py --bind 0.0.0.0:\${PORT:-10000}"
    envVars:
      - key: PYTHON_VERSION
        value: "3.12.6"
      - key: PYTHONPATH
        value: "."
      - key: DJANGO_SETTINGS_MODULE
        value: "bookmyseat.settings"
      - key: DEBUG
        value: "False"
      - key: SECRET_KEY
        generateValue: true
      - key: DATABASE_URL
        sync: false

# build.sh
#!/usr/bin/env bash
set -o errexit
set -o pipefail
set -o nounset

PROJECT_ROOT="$(cd "$(dirname "\${BASH_SOURCE[0]}")" && pwd)"
cd "\${PROJECT_ROOT}"
export PYTHONPATH="\${PROJECT_ROOT}:\${PYTHONPATH:-}"
export DJANGO_SETTINGS_MODULE="bookmyseat.settings"

python -m pip install --upgrade pip setuptools wheel
python -m pip install --no-cache-dir -r "\${PROJECT_ROOT}/requirements.txt"
python -c "import bookmyseat.wsgi, app; print('WSGI verified')"
python manage.py check
python manage.py collectstatic --noinput --clear
if [ -n "\${DATABASE_URL:-}" ]; then
    python manage.py migrate --noinput
fi`,
  },
  {
    id: 'supabase-cli',
    path: 'DEPLOYMENT.md (Supabase CLI & Verification)',
    category: 'DevOps & CLI',
    summary: 'Supabase CLI linking commands for project ref iqxcgzrfjplernbidkfd and Django test verification.',
    content: `# 1. Link Supabase Project (Interactive login required in terminal)
npm install -g supabase
supabase login
supabase init
supabase link --project-ref iqxcgzrfjplernbidkfd

# 2. Run Django Verification Suite
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py collectstatic --noinput
python manage.py test`,
  },
];

export const DjangoBlueprintPanel: React.FC = () => {
  const [selectedId, setSelectedId] = useState<string>(CODE_ARTIFACTS[0].id);
  const [copied, setCopied] = useState(false);

  const activeArtifact =
    CODE_ARTIFACTS.find((item) => item.id === selectedId) || CODE_ARTIFACTS[0];

  const handleCopy = async () => {
    await navigator.clipboard.writeText(activeArtifact.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 1800);
  };

  return (
    <section className="mx-auto max-w-[1200px] px-6 py-12">
      <div className="border-b border-slate-800 pb-6">
        <div className="text-xs text-slate-400">
          <span>Full-Stack Repository Deliverables</span>
          <span aria-hidden="true"> · </span>
          <span>Django 5.1.1</span>
          <span aria-hidden="true"> · </span>
          <span>Supabase Project iqxcgzrfjplernbidkfd</span>
        </div>
        <h1 className="mt-2 text-3xl font-bold tracking-tight text-white font-display">
          Django + Supabase PostgreSQL + Render &amp; Vercel Architecture
        </h1>
        <p className="mt-2 max-w-3xl text-sm text-slate-400 leading-relaxed">
          All Django project files (<code className="font-mono text-slate-200">manage.py</code>,{' '}
          <code className="font-mono text-slate-200">bookmyseat/</code>,{' '}
          <code className="font-mono text-slate-200">movies/</code>,{' '}
          <code className="font-mono text-slate-200">bookings/</code>,{' '}
          <code className="font-mono text-slate-200">users/</code>,{' '}
          <code className="font-mono text-slate-200">templates/</code>,{' '}
          <code className="font-mono text-slate-200">render.yaml</code>,{' '}
          <code className="font-mono text-slate-200">vercel.json</code>, and{' '}
          <code className="font-mono text-slate-200">DEPLOYMENT.md</code>) are generated in the workspace root. Inspect key modules and deployment runbooks below.
        </p>
      </div>

      <div className="mt-8 grid grid-cols-1 gap-6 md:grid-cols-3">
        <div className="rounded-xl border border-slate-800 bg-[#111827] p-5">
          <div className="flex items-center gap-2 text-sm font-semibold text-white">
            <Database className="h-4 w-4 text-rose-500" />
            <span>Supabase PostgreSQL &amp; ORM</span>
          </div>
          <p className="mt-2 text-xs text-slate-400 leading-relaxed">
            Configured for project <span className="font-mono text-slate-200">iqxcgzrfjplernbidkfd</span> via{' '}
            <span className="font-mono text-slate-200">dj-database-url</span> with{' '}
            <span className="font-mono text-slate-200">sslmode=require</span> and IPv4 Session Pooler support. Django manages all schema migrations.
          </p>
        </div>

        <div className="rounded-xl border border-slate-800 bg-[#111827] p-5">
          <div className="flex items-center gap-2 text-sm font-semibold text-white">
            <ShieldCheck className="h-4 w-4 text-rose-500" />
            <span>Row-Level Concurrency &amp; Payments</span>
          </div>
          <p className="mt-2 text-xs text-slate-400 leading-relaxed">
            Uses <span className="font-mono text-slate-200">ShowSeat.objects.select_for_update()</span> inside{' '}
            <span className="font-mono text-slate-200">transaction.atomic()</span> with 10-minute seat holds and HMAC-SHA256 idempotent payment verification.
          </p>
        </div>

        <div className="rounded-xl border border-slate-800 bg-[#111827] p-5">
          <div className="flex items-center gap-2 text-sm font-semibold text-white">
            <Server className="h-4 w-4 text-rose-500" />
            <span>Render Primary + Vercel WSGI</span>
          </div>
          <p className="mt-2 text-xs text-slate-400 leading-relaxed">
            Includes <span className="font-mono text-slate-200">render.yaml</span> +{' '}
            <span className="font-mono text-slate-200">build.sh</span> for Gunicorn deployment with WhiteNoise static compression, plus <span className="font-mono text-slate-200">api/index.py</span> for Vercel.
          </p>
        </div>
      </div>

      <div className="mt-8 grid grid-cols-1 gap-6 lg:grid-cols-12">
        <div className="lg:col-span-4 space-y-2">
          {CODE_ARTIFACTS.map((item) => (
            <button
              key={item.id}
              type="button"
              onClick={() => setSelectedId(item.id)}
              className={`w-full rounded-lg border p-3.5 text-left transition-colors ${
                selectedId === item.id
                  ? 'border-rose-500/60 bg-rose-950/20 text-white'
                  : 'border-slate-800 bg-[#111827] text-slate-300 hover:border-slate-700'
              }`}
            >
              <div className="text-[11px] text-slate-400">{item.category}</div>
              <div className="mt-0.5 font-mono text-xs font-semibold text-white">{item.path}</div>
              <div className="mt-1 text-xs text-slate-400 line-clamp-2">{item.summary}</div>
            </button>
          ))}
        </div>

        <div className="lg:col-span-8 rounded-xl border border-slate-800 bg-[#111827] p-5">
          <div className="flex items-center justify-between border-b border-slate-800 pb-3">
            <div className="flex items-center gap-2">
              <Terminal className="h-4 w-4 text-rose-500" />
              <span className="font-mono text-xs font-semibold text-white">{activeArtifact.path}</span>
            </div>
            <button
              type="button"
              onClick={handleCopy}
              className="inline-flex items-center gap-1.5 rounded-md border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs font-medium text-slate-200 hover:bg-slate-700 transition-colors whitespace-nowrap shrink-0"
            >
              {copied ? <Check className="h-3.5 w-3.5 text-emerald-400" /> : <Copy className="h-3.5 w-3.5" />}
              <span>{copied ? 'Copied' : 'Copy Snippet'}</span>
            </button>
          </div>
          <pre className="mt-4 overflow-x-auto font-mono text-xs leading-relaxed text-slate-200">
            <code>{activeArtifact.content}</code>
          </pre>
        </div>
      </div>
    </section>
  );
};
