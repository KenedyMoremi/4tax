import os
from pathlib import Path
from dotenv import load_dotenv
from .database import database_config
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent
IS_VERCEL = os.environ.get('VERCEL') == '1'
if not IS_VERCEL:
    load_dotenv(BASE_DIR / '.env', override=False)
DEBUG = False if IS_VERCEL else os.environ.get('DJANGO_DEBUG', '1') == '1'
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', '')
if not SECRET_KEY:
    if not DEBUG:
        raise ImproperlyConfigured('Set DJANGO_SECRET_KEY in production.')
    SECRET_KEY = 'development-only-key-do-not-use-in-production'
ALLOWED_HOSTS = [host.strip() for host in os.environ.get('DJANGO_ALLOWED_HOSTS', '' if IS_VERCEL else 'localhost,127.0.0.1,testserver').split(',') if host.strip()]
VERCEL_HOSTS = [os.environ[key] for key in ['VERCEL_URL', 'VERCEL_PROJECT_PRODUCTION_URL'] if os.environ.get(key)] if IS_VERCEL else []
ALLOWED_HOSTS = list(dict.fromkeys(ALLOWED_HOSTS + VERCEL_HOSTS))
if IS_VERCEL and not os.environ.get('DATABASE_URL'):
    raise ImproperlyConfigured('Set DATABASE_URL in the Vercel project environment.')
INSTALLED_APPS = ['django.contrib.admin', 'django.contrib.auth', 'django.contrib.contenttypes', 'django.contrib.sessions', 'django.contrib.messages', 'django.contrib.staticfiles', 'bookkeeping.apps.BookkeepingConfig', 'whatsapp.apps.WhatsAppConfig', 'business_profiles.apps.BusinessProfilesConfig', 'bookings.apps.BookingsConfig', 'pos.apps.PosConfig', 'recommendations.apps.RecommendationsConfig']
MIDDLEWARE = ['django.middleware.security.SecurityMiddleware', 'django.contrib.sessions.middleware.SessionMiddleware', 'django.middleware.common.CommonMiddleware', 'django.middleware.csrf.CsrfViewMiddleware', 'django.contrib.auth.middleware.AuthenticationMiddleware', 'django.contrib.messages.middleware.MessageMiddleware', 'django.middleware.clickjacking.XFrameOptionsMiddleware']
ROOT_URLCONF = 'config.urls'
TEMPLATES = [{'BACKEND': 'django.template.backends.django.DjangoTemplates', 'DIRS': [BASE_DIR / 'templates'], 'APP_DIRS': True, 'OPTIONS': {'context_processors': ['django.template.context_processors.request', 'django.contrib.auth.context_processors.auth', 'django.contrib.messages.context_processors.messages', 'bookkeeping.context_processors.workspace']}}]
WSGI_APPLICATION = 'config.wsgi.application'
DATABASES = {'default': database_config(os.environ.get('DATABASE_URL', ''), os.environ.get('DJANGO_DB_PATH', BASE_DIR / 'db.sqlite3'))}
AUTH_PASSWORD_VALIDATORS = [{'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'}, {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'}, {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'}, {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'}]
# Keep the deployed model identity; the Python implementation is shared.
AUTH_USER_MODEL = 'books.User'
LANGUAGE_CODE = 'en'
TIME_ZONE = 'Africa/Maseru'
USE_I18N = True
USE_TZ = True
STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
LOGIN_REDIRECT_URL = 'dashboard'
LOGOUT_REDIRECT_URL = 'login'
LOGIN_URL = 'login'
if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

CSRF_TRUSTED_ORIGINS = [origin for origin in os.environ.get('DJANGO_CSRF_TRUSTED_ORIGINS', '').split(',') if origin]

if IS_VERCEL:
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    CSRF_TRUSTED_ORIGINS = list(dict.fromkeys(CSRF_TRUSTED_ORIGINS + [f'https://{host}' for host in VERCEL_HOSTS]))

if not DEBUG:
    STORAGES = {
        'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
        'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.ManifestStaticFilesStorage'},
    }

# WhatsApp is opt-in until provider credentials and the public webhook are configured.
WHATSAPP_ENABLED = os.environ.get('WHATSAPP_ENABLED', '0') == '1'
TWILIO_ACCOUNT_SID = os.environ.get('TWILIO_ACCOUNT_SID', '')
TWILIO_AUTH_TOKEN = os.environ.get('TWILIO_AUTH_TOKEN', '')
TWILIO_WHATSAPP_FROM = os.environ.get('TWILIO_WHATSAPP_FROM', '')
TWILIO_WEBHOOK_URL = os.environ.get('TWILIO_WEBHOOK_URL', '')
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY', '')
OPENAI_BOOKKEEPING_MODEL = os.environ.get('OPENAI_BOOKKEEPING_MODEL', 'gpt-5.4-mini')
WHATSAPP_HOURLY_LIMIT = 30
WHATSAPP_SEND_INTERVAL_SECONDS = 3  # Twilio Sandbox sender limit; run one sender worker.

BOOKKEEPING_AI_PROVIDER = os.environ.get('BOOKKEEPING_AI_PROVIDER', 'groq')
GROQ_API_KEY = os.environ.get('GROQ_API_KEY', '')
GROQ_BOOKKEEPING_MODEL = os.environ.get('GROQ_BOOKKEEPING_MODEL', 'openai/gpt-oss-120b')

WHATSAPP_LINK_SECRET = os.environ.get('WHATSAPP_LINK_SECRET', SECRET_KEY)

# Trusted issuer and public JWKS endpoint for USSD owner tokens. Empty disables the API.
REGISTRATION_AUTH_ISSUER = os.environ.get('REGISTRATION_AUTH_ISSUER', '')
REGISTRATION_AUTH_JWKS_URL = os.environ.get('REGISTRATION_AUTH_JWKS_URL', '')

GROQ_RECOMMENDATIONS_API_KEY = os.environ.get('GROQ_RECOMMENDATIONS_API_KEY', '')
GROQ_RECOMMENDATIONS_MODEL = os.environ.get('GROQ_RECOMMENDATIONS_MODEL', 'openai/gpt-oss-120b')

GROQ_STOCK_VISION_MODEL = os.environ.get('GROQ_STOCK_VISION_MODEL', 'qwen/qwen3.8-27b')
