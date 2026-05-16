"""Django settings for ai_news project."""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY")
if not SECRET_KEY and not DEBUG:
    raise ValueError(
        "DJANGO_SECRET_KEY environment variable is required in production. "
        "Set it before deployment."
    )
if not SECRET_KEY:
    # Development-only fallback
    SECRET_KEY = "django-insecure-dev-key-change-in-production"

DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"

ALLOWED_HOSTS = [host for host in os.environ.get("DJANGO_ALLOWED_HOSTS", "*").split(",") if host]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sitemaps",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "apps.accounts",
    "apps.taxonomy",
    "apps.entities",
    "apps.core",
    "apps.content",
    "apps.editorial",
    "apps.relations",
    "apps.interactions",
    "apps.personalization",
    "apps.search",
    "apps.staffpanel",
    "apps.seo",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "apps.interactions.middleware.VisitorMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": False,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
            "loaders": [
                (
                    "django.template.loaders.cached.Loader",
                    [
                        "django.template.loaders.filesystem.Loader",
                        "django.template.loaders.app_directories.Loader",
                    ],
                ),
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Tehran'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATICFILES_DIRS = [
    BASE_DIR / "static",
]
STATIC_ROOT = BASE_DIR.joinpath('statics')

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LOGIN_URL = "/auth/login/"

# Main cache for the whole project: in-memory (RAM)
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "ram_cache",
        "TIMEOUT": 86400,
        "OPTIONS": {
            "MAX_ENTRIES": 50000,
        },
    }
}


SITE_NAME = os.environ.get("SITE_NAME", "AI News")
SITE_BASE_URL = os.environ.get("SITE_BASE_URL", "https://example.com").rstrip("/")
PUBLISHER_LOGO_URL = os.environ.get("PUBLISHER_LOGO_URL", "/static/images/logo.png")
DEFAULT_OG_IMAGE_URL = os.environ.get("DEFAULT_OG_IMAGE_URL", "/static/images/og-default.jpg")

VISITOR_COOKIE_NAME = "anon_id"
VISITOR_COOKIE_AGE = 60 * 60 * 24 * 365
VISITOR_TOUCH_INTERVAL_SECONDS = 60 * 60

PAGE_CACHE_SECONDS = 60 * 60 * 3
ARTICLE_MAIN_CACHE_SECONDS = 60 * 60 * 24
AJAX_CACHE_SECONDS = 60 * 30
SEARCH_CACHE_SECONDS = 60 * 30

RELATIONS_ALGO_VERSION = os.environ.get("RELATIONS_ALGO_VERSION", "v1")
RELATIONS_TOP_N = int(os.environ.get("RELATIONS_TOP_N", "30"))
RELATIONS_MAX_CANDIDATES = int(os.environ.get("RELATIONS_MAX_CANDIDATES", "600"))
RELATIONS_HORIZON_DAYS = int(os.environ.get("RELATIONS_HORIZON_DAYS", "365"))
RELATIONS_MIN_SCORE = float(os.environ.get("RELATIONS_MIN_SCORE", "0.15"))

RELATIONS_WEIGHT_ENTITY = float(os.environ.get("RELATIONS_WEIGHT_ENTITY", "0.35"))
RELATIONS_WEIGHT_CATEGORY = float(os.environ.get("RELATIONS_WEIGHT_CATEGORY", "0.25"))
RELATIONS_WEIGHT_TITLE = float(os.environ.get("RELATIONS_WEIGHT_TITLE", "0.15"))
RELATIONS_WEIGHT_TAG = float(os.environ.get("RELATIONS_WEIGHT_TAG", "0.10"))
RELATIONS_WEIGHT_TIME = float(os.environ.get("RELATIONS_WEIGHT_TIME", "0.10"))
RELATIONS_WEIGHT_TYPE = float(os.environ.get("RELATIONS_WEIGHT_TYPE", "0.05"))

PERSONALIZATION_ALGO_VERSION = os.environ.get("PERSONALIZATION_ALGO_VERSION", "v1")
INTEREST_WINDOW_DAYS = int(os.environ.get("INTEREST_WINDOW_DAYS", "30"))
INTEREST_TOP_CATEGORIES = int(os.environ.get("INTEREST_TOP_CATEGORIES", "10"))
INTEREST_TOP_ENTITIES = int(os.environ.get("INTEREST_TOP_ENTITIES", "15"))
INTEREST_TOP_TAGS = int(os.environ.get("INTEREST_TOP_TAGS", "15"))
INTEREST_TOP_SEEDS = int(os.environ.get("INTEREST_TOP_SEEDS", "20"))

RECS_TOP_N = int(os.environ.get("RECS_TOP_N", "30"))
RECS_MAX_CANDIDATES = int(os.environ.get("RECS_MAX_CANDIDATES", "1000"))
RECS_RECENT_DAYS = int(os.environ.get("RECS_RECENT_DAYS", "14"))
RECS_EXCLUDE_SEEN_DAYS = int(os.environ.get("RECS_EXCLUDE_SEEN_DAYS", "14"))
RECS_SEED_RELATION_LIMIT = int(os.environ.get("RECS_SEED_RELATION_LIMIT", "20"))

POPULAR_LOOKBACK_DAYS = int(os.environ.get("POPULAR_LOOKBACK_DAYS", "7"))
POPULAR_CANDIDATE_LIMIT = int(os.environ.get("POPULAR_CANDIDATE_LIMIT", "500"))

SEARCH_CANDIDATE_LIMIT = int(os.environ.get("SEARCH_CANDIDATE_LIMIT", "300"))
SEARCH_PAGE_SIZE = int(os.environ.get("SEARCH_PAGE_SIZE", "15"))
DATA_CACHE_VERSION = os.environ.get("DATA_CACHE_VERSION", "v1")

OTP_EXPIRE_SECONDS = int(os.environ.get("OTP_EXPIRE_SECONDS", "300"))
OTP_RATE_LIMIT_SECONDS = int(os.environ.get("OTP_RATE_LIMIT_SECONDS", "60"))
OTP_MAX_ATTEMPTS = int(os.environ.get("OTP_MAX_ATTEMPTS", "5"))

# Email Configuration
EMAIL_BACKEND = os.environ.get("EMAIL_BACKEND", "django.core.mail.backends.smtp.EmailBackend")
EMAIL_HOST = os.environ.get("SMTP_SERVER", "smtp.gmail.com")
EMAIL_PORT = int(os.environ.get("SMTP_PORT", "587"))
EMAIL_HOST_USER = os.environ.get("EMAIL_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_PASSWORD", "")
EMAIL_USE_TLS = os.environ.get("EMAIL_USE_TLS", "1") == "1"

# Warn if email credentials are not configured
if not EMAIL_HOST_USER or not EMAIL_HOST_PASSWORD:
    if not DEBUG:
        import warnings
        warnings.warn(
            "Email credentials (EMAIL_USER, EMAIL_PASSWORD) are not configured. "
            "Email functionality will not work. Configure these environment variables for production.",
            RuntimeWarning,
        )

DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "noreply@example.com")
