# Nestora Hostel Management System

Nestora is a Django hostel management system. It has one Django app (`hms`),
uses a custom `hms.User` model, and stores hostel/room/bed, renter, booking,
payment, meal, complaint, notice, visitor, and related records in Django models.

## Local development

SQLite remains the default database for local development. Uploaded files are
stored in the local `media/` directory unless S3-compatible storage is
configured.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python manage.py migrate
python manage.py runserver
```

The local `db.sqlite3` and `media/` files are not tracked by Git. Keep a
separate backup of both; a Vercel deployment cannot read the local copies.

## Production architecture

- **Application:** Vercel's Python runtime runs the existing WSGI application,
  `nestora.wsgi.application`. Vercel currently detects Django from `manage.py`
  and `WSGI_APPLICATION`, and collects `STATIC_ROOT` during the build. No
  `vercel.json`, alternate entrypoint, or startup migration is needed.
- **Database:** Supabase PostgreSQL is selected only when `DATABASE_URL` is set.
  Without it, local development uses SQLite. On Vercel, a missing database URL
  is an explicit configuration error. Vercel uses Supabase's shared
  transaction-mode pooler; Django disables prepared statements for that URL
  and persistent Django connections are disabled on Vercel.
- **Static files:** Django WhiteNoise manifest storage remains configured.
  Vercel collects and serves static assets from its CDN.
- **Uploaded media:** Vercel's filesystem is temporary. On Vercel, Nestora
  requires S3-compatible storage settings (for example, an AWS S3 bucket or
  Cloudflare R2 bucket) and fails during configuration if they are missing.
  Local development continues to use `MEDIA_ROOT`.
- **Migrations:** Vercel does not run schema migrations when a function starts.
  Create the schema and import a SQLite fixture once, manually, using the
  procedure below.

This follows Vercel's current
[Django deployment guide](https://vercel.com/docs/frameworks/full-stack/django)
and [Python runtime documentation](https://vercel.com/docs/functions/runtimes/python).

## Create a Supabase database

1. Sign in to Supabase and create a project. Review the current plan and pricing
   yourself; this repository does not create any external service or incur
   charges.
2. In the project's **Connect** dialog, select **Transaction pooler** for the
   Vercel application and copy the full URL. It uses port `6543` and a host
   ending in `.pooler.supabase.com`; use the values Supabase provides rather
   than constructing the host or username yourself.
3. Keep the full `DATABASE_URL` private. Supabase connection strings use TLS.
   The project's settings require SSL whenever `DJANGO_DEBUG=false`.
4. Do not copy the production URL into source code, `.env.example`, a ticket, or
   a public log.

Supabase Storage is not configured by this change. Uploaded media still uses
the S3-compatible storage described below.

## Persistent media storage

Create an S3-compatible bucket and access credentials with permission to read,
write, and list objects in that bucket. AWS S3 uses its normal regional
endpoint; Cloudflare R2 uses the account's S3 API endpoint and region `auto`.
Choose a public custom domain for images only if that is appropriate for your
application. Otherwise, leave `AWS_S3_CUSTOM_DOMAIN` unset and use the
storage-generated signed URLs.

Nestora keeps each `ImageField` path as its object key. To copy current files
before switching the application to cloud storage, use AWS CLI credentials
configured outside Git and sync the contents of `media/` to the bucket root.
For example:

```powershell
aws s3 sync .\media\ s3://<bucket-name>/ --no-progress
```

For Cloudflare R2, also pass its endpoint:

```powershell
aws s3 sync .\media\ s3://<bucket-name>/ `
  --endpoint-url https://<account-id>.r2.cloudflarestorage.com `
  --no-progress
```

Do not add `--delete`: this procedure should copy files, not remove existing
objects. Verify the copied object keys before deploying.

## Vercel environment variables

Add these to the Vercel project's **Production** environment. Add them to
Preview only if preview deployments should use separate, non-production
resources.

| Variable | Value |
| --- | --- |
| `DJANGO_SECRET_KEY` | A newly generated private Django secret key. |
| `DJANGO_DEBUG` | `false` |
| `DATABASE_URL` | Supabase **Transaction pooler** connection string for Vercel. |
| `ALLOWED_HOSTS` | Comma-separated hostnames, without scheme; include the production Vercel hostname and any custom domain. |
| `CSRF_TRUSTED_ORIGINS` | Comma-separated origins with scheme, e.g. `https://your-domain.example`. |
| `AWS_STORAGE_BUCKET_NAME` | Media bucket name. |
| `AWS_ACCESS_KEY_ID` | S3-compatible access key ID. |
| `AWS_SECRET_ACCESS_KEY` | S3-compatible secret access key. |
| `AWS_S3_REGION_NAME` | AWS region, or `auto` for Cloudflare R2. |
| `AWS_S3_ENDPOINT_URL` | S3-compatible endpoint; leave unset for AWS S3. |
| `AWS_S3_CUSTOM_DOMAIN` | Optional media hostname only (no scheme), if configured. |
| `AWS_QUERYSTRING_AUTH` | `true` for signed URLs; use `false` only when the bucket/custom domain is intentionally public. |

Vercel supplies deployment hostnames such as `VERCEL_URL`; Nestora adds them to
allowed hosts and trusted HTTPS origins. Add custom domains to both
`ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS`. Secure cookies, HTTPS redirects,
and Vercel's forwarded HTTPS scheme are enabled when `DJANGO_DEBUG=false`.

Generate a secret locally and enter it directly in Vercel's environment
settings:

```powershell
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Never commit or publish the generated value.

### SSLCommerz

Set `SSLCOMMERZ_STORE_ID` and `SSLCOMMERZ_STORE_PASSWORD` as Vercel secrets.
The default API and validator URLs remain the SSLCommerz **sandbox**. For live
payments, use live credentials and set:

- `SSLCOMMERZ_API_URL=https://securepay.sslcommerz.com/gwprocess/v4/api.php`
- `SSLCOMMERZ_VALIDATOR_URL=https://securepay.sslcommerz.com/validator/api/validationserverAPI.php`

The existing success, failure, cancel, and IPN paths are generated from the
current request. Behind Vercel, `SECURE_PROXY_SSL_HEADER` makes those callback
URLs use HTTPS. Configure the production domain in SSLCommerz and verify the
gateway's callback/IPN delivery with its sandbox before enabling live payments.
Payment callbacks are `/payments/success/`, `/payments/fail/`, and
`/payments/ipn/`; the IPN and gateway POST callbacks are already CSRF-exempt.

## Safe SQLite-to-Supabase transfer

This transfer copies application records; it does not delete or modify
`db.sqlite3`. Treat the fixture and database backup as sensitive because they
contain renter information and payment records. Keep them outside Git and
restrict access to them.

1. Stop local writes and take a separate SQLite backup. Use a new, unique
   destination; do not overwrite the original database or an earlier backup:

   ```powershell
   $backupDir = Join-Path $env:USERPROFILE 'secure-backups'
   New-Item -ItemType Directory -Path $backupDir -Force | Out-Null
   $backup = Join-Path $backupDir "nestora-$(Get-Date -Format yyyyMMdd-HHmmss).sqlite3"
   if (Test-Path $backup) { throw "Backup already exists: $backup" }
   Copy-Item .\db.sqlite3 $backup
   ```

2. If the application has uploads, sync `media/` to the external bucket as
   described above. Confirm the objects are present before serving the
   imported database.
3. With the local SQLite configuration active, export all serialized Django
   data to the ignored `migration-data/` directory. The content types and
   permission rows are intentionally omitted because `migrate` creates them
   for the target schema; natural foreign keys preserve references to them.
   Application, user, group, payment, and admin-log records are included.
   Database sessions are excluded because they are short-lived login state and
   are signed with the Django secret key; users should sign in again after
   cutover. New sessions are stored in Supabase by Django's database session
   backend.

   ```powershell
   New-Item -ItemType Directory -Path .\migration-data -Force | Out-Null
   python manage.py dumpdata `
     --natural-foreign --natural-primary `
     --exclude=contenttypes --exclude=auth.permission --exclude=sessions `
     --output=.\migration-data\nestora.json
   ```

4. Link the repository to Vercel with the Vercel CLI and pull the Production
   environment into Vercel's ignored local cache. Do not display or commit it:

   ```powershell
   vercel link
   vercel pull --environment=production
   ```

5. Supabase recommends a direct connection for migrations and other native
   database operations. If your local network cannot reach the direct
   connection, use the shared **Session pooler** URL (port `5432`). Set
   `DATABASE_URL` in this PowerShell process to that migration URL; do not
   replace the Transaction pooler URL in Vercel's settings. Then review the
   migration plan. The command loads other pulled variables without overriding
   the process's migration URL:

   ```powershell
   python -c "import os; from dotenv import load_dotenv; load_dotenv('.vercel/.env.production.local'); os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'nestora.settings'); from django.core.management import call_command; call_command('migrate', plan=True)"
   ```

   Confirm that the URL targets the intended Supabase project and the plan is
   the expected schema setup. Only import into a newly created, empty target.
   Do not load this fixture into a database with existing application data.

6. Apply migrations once, manually, against Supabase. No migration runs on
   each Vercel startup:

   ```powershell
   python -c "import os; from dotenv import load_dotenv; load_dotenv('.vercel/.env.production.local'); os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'nestora.settings'); from django.core.management import call_command; call_command('migrate', interactive=False)"
   ```

7. Load the fixture into the migrated, still-empty target:

   ```powershell
   python -c "import os; from dotenv import load_dotenv; load_dotenv('.vercel/.env.production.local'); os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'nestora.settings'); from django.core.management import call_command; call_command('loaddata', r'migration-data\nestora.json')"
   ```

   `loaddata` expects a clean target; do not rerun it on a populated database.
   Compare source and destination model counts and check that user/group
   permissions, bookings, payments, meal bills, and image URLs are present
   before sending production traffic. Retain the original SQLite file and
   backup until these checks are complete. Securely remove the export fixture
   when it is no longer needed.

## Deploy and verify

1. Import the Git repository into Vercel and set the environment variables
   above. Vercel's current Django integration detects `manage.py` and
   `nestora.wsgi.application`; no custom build/start command or migration hook
   is required. Vercel collects static files during the build.
2. Deploy after the Supabase schema/data and media have been prepared. Check the
   deployment build and function logs for configuration errors without
   printing environment values.
3. Test the actual assigned production URL: homepage, login/logout, admin,
   static assets, an existing database record, and an uploaded image. Verify
   that a new record and upload remain available after a new deployment or
   function restart.
4. Test SSLCommerz sandbox initiation and callbacks against the HTTPS
   production domain before switching to live credentials. Verify the IPN is
   received and the corresponding payment record is updated.

The deployment is not considered verified until its actual production URL,
database persistence, media storage, and payment callbacks have been tested.
