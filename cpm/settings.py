"""
CPM v2 Django Settings
"""
import os
import sys
import secrets
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# Load .env file
_env_file = BASE_DIR / '.env'
if _env_file.exists():
    for line in _env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, _, val = line.partition('=')
        os.environ.setdefault(key.strip(), val.strip())

# Data directory
if sys.platform == 'win32':
    _db_base = Path(os.environ.get('APPDATA', Path.home() / 'AppData' / 'Roaming'))
else:
    _db_base = Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local' / 'share'))

CPM_DATA_DIR = Path(os.environ.get('CPM_DATA_DIR', _db_base / 'cpm'))
CPM_DATA_DIR.mkdir(parents=True, exist_ok=True)

# SECRET_KEY: env var → file auto-generate
SECRET_KEY = os.environ.get('CPM_SECRET_KEY', '')
if not SECRET_KEY:
    _secret_file = CPM_DATA_DIR / '.secret_key'
    if _secret_file.exists():
        SECRET_KEY = _secret_file.read_text().strip()
    else:
        SECRET_KEY = secrets.token_urlsafe(50)
        _secret_file.write_text(SECRET_KEY)

DEBUG = os.environ.get('CPM_DEBUG', 'true').lower() in ('true', '1')

ALLOWED_HOSTS = os.environ.get('CPM_ALLOWED_HOSTS', '*').split(',')

# CSRF & Proxy settings for Cloudflare Tunnel (HTTPS)
CSRF_TRUSTED_ORIGINS = [
    f'https://{h.strip()}' for h in os.environ.get('CPM_ALLOWED_HOSTS', '').split(',')
    if h.strip() and h.strip() != '*'
]
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sites',
    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'allauth.socialaccount.providers.github',
    'allauth.socialaccount.providers.google',
    'rest_framework',
    'core',
]

SITE_ID = 1

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'allauth.account.middleware.AccountMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'cpm.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'core.context_processors.github_oauth_available',
            ],
        },
    },
]

WSGI_APPLICATION = 'cpm.wsgi.application'

# DB: SQLite at CPM_DATA_DIR/cpm.db

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': CPM_DATA_DIR / 'cpm.db',
        'OPTIONS': {
            'timeout': 30,
        },
    }
}

# Enable WAL mode for SQLite
DATABASE_WAL_MODE = True

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

LANGUAGE_CODE = 'ko-kr'
TIME_ZONE = 'Asia/Seoul'
USE_I18N = True
USE_TZ = False  # localtime 사용 (v1 호환)

STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'
WHITENOISE_USE_FINDERS = True

# DRF
REST_FRAMEWORK = {
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 50,
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
        'core.authentication.APITokenAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.AllowAny',
    ],
}

# django-allauth (GitHub OAuth)
AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
    'allauth.account.auth_backends.AuthenticationBackend',
]

ACCOUNT_LOGIN_BY_CODE_ENABLED = False
ACCOUNT_LOGIN_METHODS = {'username', 'email'}
ACCOUNT_SIGNUP_FIELDS = ['email*', 'username*']
ACCOUNT_EMAIL_VERIFICATION = 'none'
SOCIALACCOUNT_AUTO_SIGNUP = True
SOCIALACCOUNT_LOGIN_ON_GET = True
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/'
ACCOUNT_LOGOUT_ON_GET = True

SOCIALACCOUNT_PROVIDERS = {
    'github': {
        'SCOPE': ['read:user', 'user:email'],
    },
    'google': {
        'SCOPE': ['profile', 'email'],
        'AUTH_PARAMS': {'access_type': 'online'},
    },
}

# CPM-specific settings
CPM_WEB_PORT = 9200
CPM_WS_PORT = 9201
CPM_HOOKS_DIR = BASE_DIR / 'hooks'

# Delete password (from .env delpasswd)
CPM_DEL_PASSWORD = os.environ.get('delpasswd', '')

# GitHub integration
GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN', '')
GITHUB_USERNAME = os.environ.get('GITHUB_USERNAME', '')

# Google Sheets integration (optional)
GOOGLE_SHEETS_CREDENTIALS = os.environ.get('GOOGLE_SHEETS_CREDENTIALS', '')

# Redis (optional, for Phase 2 real-time)
CPM_REDIS_URL = os.environ.get('CPM_REDIS_URL', 'redis://localhost:6379/0')
CPM_REDIS_CHANNEL = 'cpm:live'
