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

## Deploy with SQLite on Render

Vercel's serverless filesystem is ephemeral and cannot safely persist SQLite.
To keep SQLite in production, use a Render Web Service with a persistent disk.
Render persistent disks require a paid service. Keep the service to one instance
when using SQLite.

Configure the Render Web Service from this repository:

- Build command: `pip install -r requirements.txt && python manage.py collectstatic --noinput`
- Start command: `gunicorn nestora.wsgi:application`
- Persistent disk mount path: `/var/data`

Set these Render environment variables:

- `DJANGO_SECRET_KEY`: a newly generated, private Django secret key.
- `DJANGO_DEBUG`: `false`.
- `SQLITE_PATH`: `/var/data/db.sqlite3`.
- `MEDIA_ROOT`: `/var/data/media`.
- `CSRF_TRUSTED_ORIGINS`: the service origin, including `https://`.
- `SSLCOMMERZ_STORE_ID` and `SSLCOMMERZ_STORE_PASSWORD`: optional payment
  gateway credentials; configure them privately.

Render provides `RENDER_EXTERNAL_HOSTNAME`, which Django uses for allowed hosts
and CSRF origins. Do not set `DATABASE_URL` for this SQLite deployment; when it
is set, the project uses PostgreSQL instead. The local SQLite database is not
uploaded or copied to Render.

After confirming the persistent disk is mounted at `/var/data`, the Render
SQLite database needs its Django schema created with `python manage.py migrate`.
Run this once from the Render Shell after confirming the disk is mounted and
`SQLITE_PATH` points to `/var/data/db.sqlite3`. This creates the schema on
Render; it does not transfer or modify the local SQLite database. Do not run
migrations as a pre-deploy command, since that command may not have the mounted
disk available.

Static assets are collected from `static/` into `staticfiles/` during the
build. Uploaded media is stored under `/var/data/media` so it persists with
the disk.

Generate a Django secret key locally with:

```powershell
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Paste the result directly into Render's environment-variable settings. Do not
commit it or send it in chat.
