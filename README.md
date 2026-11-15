# Nestora Hostel Management System

Nestora is a Django hostel management system.

## Local development

The local database remains SQLite (`db.sqlite3`):

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python manage.py migrate
python manage.py runserver
```

The existing local database and uploaded media are excluded from Git. They are
not removed or uploaded by this deployment setup.

## Vercel

Vercel detects Django from `manage.py` and uses
`WSGI_APPLICATION = 'nestora.wsgi.application'` with
`nestora/wsgi.py:application`. No `vercel.json` or custom API entry point is
needed for this standard Django WSGI project. Vercel collects and serves Django
static files automatically; WhiteNoise is also configured as a compatible
static-file fallback.

Before deploying, add these environment variables in the Vercel project for
the environments you use (Production, Preview, and Development as appropriate):

- `DJANGO_SECRET_KEY`: a newly generated, private Django secret key.
- `DJANGO_DEBUG`: `false`.
- `ALLOWED_HOSTS`: comma-separated hostnames; Vercel deployment hostnames are
  added automatically.
- `CSRF_TRUSTED_ORIGINS`: comma-separated full origins, including `https://`,
  for custom domains. Vercel deployment origins are added automatically.
- `DATABASE_URL`: a persistent production database connection URL.

The project keeps SQLite as its local default. Vercel's serverless filesystem
is ephemeral, so SQLite cannot provide reliable persistent application data
there. The existing local SQLite database is not converted or copied. For a
functional production deployment, use a separate managed persistent database
and apply the Django schema migrations to that database; this does not import
or alter the local SQLite data. If no production database is configured, the
Django settings intentionally stop Vercel startup instead of silently using a
non-persistent database.

Static assets are collected from `static/` into `staticfiles/`. User-uploaded
media is different: Vercel function storage is not persistent. Configure a
durable object-storage backend (for example, S3-compatible storage or Vercel
Blob) before relying on profile, hostel, or room uploads in production.

Generate a Django secret key locally with:

```powershell
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Paste the result directly into Vercel's environment-variable settings. Do not
commit it or send it in chat.
