import os
from pathlib import Path

import dj_database_url
from django.core.exceptions import ImproperlyConfigured
from django.core.management.utils import get_random_secret_key
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env')
IS_VERCEL = bool(os.environ.get('VERCEL'))

DEBUG = os.environ.get('DJANGO_DEBUG', '').lower() in {'1', 'true', 'yes'}
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY')
if not SECRET_KEY:
    if not DEBUG:
        raise ImproperlyConfigured('Set DJANGO_SECRET_KEY when DEBUG is disabled.')
    SECRET_KEY = get_random_secret_key()

ALLOWED_HOSTS = [
    host.strip()
    for host in os.environ.get(
        'ALLOWED_HOSTS',
        os.environ.get('DJANGO_ALLOWED_HOSTS', ''),
    ).split(',')
    if host.strip()
]
for deployment_host in (
    os.environ.get('VERCEL_URL'),
    os.environ.get('VERCEL_PROJECT_PRODUCTION_URL'),
    os.environ.get('RENDER_EXTERNAL_HOSTNAME'),
):
    if deployment_host and deployment_host not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append(deployment_host)
if DEBUG:
    ALLOWED_HOSTS.extend(
        host for host in ('127.0.0.1', 'localhost') if host not in ALLOWED_HOSTS
    )

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'hms',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'nestora.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'hms.context_processors.nestora_context',
            ],
        },
    },
]

WSGI_APPLICATION = 'nestora.wsgi.application'

if os.environ.get('DATABASE_URL'):
    database_config = dj_database_url.config(
        conn_max_age=0 if IS_VERCEL else 600,
        ssl_require=not DEBUG,
    )
    if (
        (database_config.get('HOST') or '').endswith('.pooler.supabase.com')
        and str(database_config.get('PORT')) == '6543'
    ):
        # Supabase's shared transaction pooler does not support prepared statements.
        database_config.setdefault('OPTIONS', {})['prepare_threshold'] = None
    DATABASES = {'default': database_config}
elif IS_VERCEL:
    raise ImproperlyConfigured('Set DATABASE_URL to a persistent PostgreSQL database on Vercel.')
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': os.environ.get('SQLITE_PATH', BASE_DIR / 'db.sqlite3'),
        }
    }

AUTH_USER_MODEL = 'hms.User'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Dhaka'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'
STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {
        'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage',
    },
}

if IS_VERCEL:
    required_media_settings = (
        'AWS_STORAGE_BUCKET_NAME',
        'AWS_ACCESS_KEY_ID',
        'AWS_SECRET_ACCESS_KEY',
        'AWS_S3_REGION_NAME',
    )
    missing_media_settings = [
        name for name in required_media_settings if not os.environ.get(name)
    ]
    if missing_media_settings:
        raise ImproperlyConfigured(
            'Set persistent S3-compatible media storage environment variables on Vercel: '
            + ', '.join(missing_media_settings)
        )

    STORAGES['default'] = {
        'BACKEND': 'storages.backends.s3.S3Storage',
    }
    AWS_STORAGE_BUCKET_NAME = os.environ['AWS_STORAGE_BUCKET_NAME']
    AWS_ACCESS_KEY_ID = os.environ['AWS_ACCESS_KEY_ID']
    AWS_SECRET_ACCESS_KEY = os.environ['AWS_SECRET_ACCESS_KEY']
    AWS_S3_REGION_NAME = os.environ['AWS_S3_REGION_NAME']
    AWS_S3_ENDPOINT_URL = os.environ.get('AWS_S3_ENDPOINT_URL') or None
    AWS_S3_CUSTOM_DOMAIN = os.environ.get('AWS_S3_CUSTOM_DOMAIN') or None
    AWS_DEFAULT_ACL = None
    AWS_S3_FILE_OVERWRITE = False
    AWS_QUERYSTRING_AUTH = os.environ.get(
        'AWS_QUERYSTRING_AUTH', 'true'
    ).lower() in {'1', 'true', 'yes'}

MEDIA_URL = '/media/'
MEDIA_ROOT = Path(os.environ.get('MEDIA_ROOT', BASE_DIR / 'media'))

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
LOGIN_URL = '/login/'
CSRF_TRUSTED_ORIGINS = [
    'http://127.0.0.1:8000',
    'http://localhost:8000',
]
CSRF_TRUSTED_ORIGINS.extend(
    f'https://{host}'
    for host in (
        os.environ.get('VERCEL_URL'),
        os.environ.get('VERCEL_PROJECT_PRODUCTION_URL'),
        os.environ.get('RENDER_EXTERNAL_HOSTNAME'),
    )
    if host
)
CSRF_TRUSTED_ORIGINS.extend(
    origin.strip()
    for origin in os.environ.get('CSRF_TRUSTED_ORIGINS', '').split(',')
    if origin.strip()
)
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_SSL_REDIRECT = not DEBUG
SECURE_HSTS_SECONDS = 3600 if not DEBUG else 0

# Currency
NESTORA_CURRENCY = '৳'

# SSLCommerz
SSL_COMMERZ_STORE_ID = os.environ.get('SSLCOMMERZ_STORE_ID', '')
SSL_COMMERZ_STORE_PASSWORD = os.environ.get('SSLCOMMERZ_STORE_PASSWORD', '')
# Session API: used to INITIATE a payment session (returns GatewayPageURL).
SSLCOMMERZ_API_URL = os.environ.get(
    'SSLCOMMERZ_API_URL',
    'https://sandbox.sslcommerz.com/gwprocess/v4/api.php',
)
# Validator API: used AFTER payment to verify a transaction via val_id.
SSLCOMMERZ_VALIDATOR_URL = os.environ.get(
    'SSLCOMMERZ_VALIDATOR_URL',
    'https://sandbox.sslcommerz.com/validator/api/validationserverAPI.php',
)

# Email
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
DEFAULT_FROM_EMAIL = 'noreply@tns-hostel.com'

