# hostel_management_system

Nestora is a Django-based hostel management system.

## Run locally

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python manage.py migrate
python manage.py runserver
```

Local development uses SQLite when `DATABASE_URL` is unset. To load sample
hostel data, set these variables to strong, unique passwords before running
`python manage.py seed_nestora`:

- `NESTORA_DEMO_ADMIN_PASSWORD`
- `NESTORA_DEMO_MANAGER_PASSWORD`
- `NESTORA_DEMO_RENTER_PASSWORD`

## Deploy with SQLite on Render

Vercel's function filesystem is temporary and is not suitable for a persistent
SQLite database. To keep SQLite in production, deploy as a Render web service
with a persistent disk. Render persistent disks require a paid service.

Create a Render **Web Service** from this GitHub repository and configure:

- Build command: `pip install -r requirements.txt && python manage.py collectstatic --noinput`
- Start command: `gunicorn nestora.wsgi:application`
- Pre-deploy command: `python manage.py migrate`
- Persistent disk mount path: `/var/data`

Set these Render environment variables:

- `DJANGO_SECRET_KEY`: a newly generated, private Django secret key.
- `DJANGO_DEBUG`: `false`.
- `SQLITE_PATH`: `/var/data/db.sqlite3`.
- `MEDIA_ROOT`: `/var/data/media`.
- `CSRF_TRUSTED_ORIGINS`: your service origin, including `https://`.
- `SSLCOMMERZ_STORE_ID` and `SSLCOMMERZ_STORE_PASSWORD`: optional payment
  gateway credentials; configure current credentials privately in Render.

Keep the service to one instance when using SQLite. The Render disk stores the
production database and uploaded files persistently.

To generate a Django secret key locally, run:

```powershell
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Do not commit `.env` files, production credentials, database files, or uploaded
media.
