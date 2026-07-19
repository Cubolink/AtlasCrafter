"""Django settings for AtlasCrafter."""

import os

from pathlib import Path
from urllib.parse import unquote, urlparse

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/

def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


load_dotenv(BASE_DIR / ".env")


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def env_path(name: str, default: Path) -> Path:
    value = Path(os.getenv(name, str(default)))
    if not value.is_absolute():
        value = BASE_DIR / value
    return value


SECRET_KEY = os.getenv(
    "DJANGO_SECRET_KEY",
    "django-insecure-local-development-key-change-me",
)
DEBUG = env_bool("DJANGO_DEBUG", True)
ALLOWED_HOSTS = [
    host.strip()
    for host in os.getenv("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
    if host.strip()
]


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'guardian',
    'accounts',
    'projects',
    'bluemap_configs',
    'renders',
    'schedules',
    'viewer',
    'assets',
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

ROOT_URLCONF = 'config.urls'

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
                'projects.context_processors.sidebar_projects',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'


def database_config() -> dict:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        return {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": os.getenv("SQLITE_DB_PATH", BASE_DIR / "db.sqlite3"),
        }

    parsed = urlparse(database_url)
    if parsed.scheme in {"postgres", "postgresql"}:
        return {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": unquote(parsed.path.lstrip("/")),
            "USER": unquote(parsed.username or ""),
            "PASSWORD": unquote(parsed.password or ""),
            "HOST": parsed.hostname or "",
            "PORT": str(parsed.port or ""),
        }
    if parsed.scheme == "sqlite":
        db_path = unquote(parsed.path)
        if parsed.netloc and parsed.netloc != ".":
            db_path = f"//{parsed.netloc}{db_path}"
        return {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": db_path,
        }
    raise ValueError(f"Unsupported DATABASE_URL scheme: {parsed.scheme}")


# Database
# https://docs.djangoproject.com/en/5.2/ref/settings/#databases

DATABASES = {
    "default": database_config(),
}

AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
    'guardian.backends.ObjectPermissionBackend',
]

ANONYMOUS_USER_NAME = 'anonymous'


# Password validation
# https://docs.djangoproject.com/en/5.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/5.2/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = os.getenv('DJANGO_TIME_ZONE', 'UTC')

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.2/howto/static-files/

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STORAGES = {
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
    'staticfiles': {
        'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage',
    },
}

LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'dashboard'
LOGOUT_REDIRECT_URL = 'login'

SOURCE_WORLDS_DIR = env_path('SOURCE_WORLDS_DIR', BASE_DIR / 'data' / 'source-worlds')
BLUEMAP_RESOURCE_SOURCES_DIR = env_path(
    'BLUEMAP_RESOURCE_SOURCES_DIR',
    BASE_DIR / 'data' / 'resource-sources',
)
BLUEMAP_CONFIG_DIR = env_path('BLUEMAP_CONFIG_DIR', BASE_DIR / 'data' / 'bluemap' / 'config')
BLUEMAP_WEBROOT_DIR = env_path('BLUEMAP_WEBROOT_DIR', BASE_DIR / 'data' / 'bluemap' / 'web')
BLUEMAP_TMP_DIR = env_path('BLUEMAP_TMP_DIR', BASE_DIR / 'data' / 'tmp')
BLUEMAP_CLI_PATH = os.getenv('BLUEMAP_CLI_PATH', 'bluemap')
BLUEMAP_JAVA_PATH = os.getenv('BLUEMAP_JAVA_PATH', 'java')
BLUEMAP_RENDER_TIMEOUT_SECONDS = int(os.getenv('BLUEMAP_RENDER_TIMEOUT_SECONDS', '3600'))
BLUEMAP_RENDER_WORKER_CONCURRENCY = int(os.getenv('BLUEMAP_RENDER_WORKER_CONCURRENCY', '1'))
BLUEMAP_RENDER_WORKER_POLL_SECONDS = int(os.getenv('BLUEMAP_RENDER_WORKER_POLL_SECONDS', '5'))
INTERNAL_ACCEL_ROOT = os.getenv('INTERNAL_ACCEL_ROOT', '/_protected_bluemap/')
X_FRAME_OPTIONS = 'SAMEORIGIN'

# Default primary key field type
# https://docs.djangoproject.com/en/5.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
