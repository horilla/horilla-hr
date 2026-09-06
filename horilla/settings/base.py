"""
base.py — Main Django settings for Horilla
"""

import os
import sys
from datetime import timedelta
from os.path import join
from pathlib import Path

import environ
from django.contrib.messages import constants as messages
from django.core.files.storage import FileSystemStorage

# ========================================
# BASE PATH & ENVIRONMENT CONFIGURATION
# ========================================
BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env(
    DEBUG=(bool, True),
    SECRET_KEY=(str, "django-insecure-default-key"),
    ALLOWED_HOSTS=(list, ["*"]),
    CSRF_TRUSTED_ORIGINS=(list, ["http://localhost:8000"]),
    SECURE_SSL_REDIRECT=(bool, False),
)

# Existing process environment (Compose, systemd, CI) wins over .env values.
env.read_env(os.path.join(BASE_DIR, ".env"), overwrite=False)

# ========================================
# CORE DJANGO SETTINGS
# ========================================
SECRET_KEY = env("SECRET_KEY")
DEBUG = env("DEBUG")
ALLOWED_HOSTS = env("ALLOWED_HOSTS")
CSRF_TRUSTED_ORIGINS = env("CSRF_TRUSTED_ORIGINS")
HORILLA_ENV = env("HORILLA_ENV", default="")
REDIS_URL = env("REDIS_URL", default=None)

# Default site ID for django.contrib.sites framework.
SITE_ID = 1

THEME_APP = "horilla_theme"

INSTALLED_APPS = [
    # Default Django apps
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sites",
    # Third-party apps
    "notifications",
    "mathfilters",
    "corsheaders",
    "simple_history",
    "django_filters",
    "widget_tweaks",
    "auditlog",
    "django_apscheduler",
    "axes",
    "rest_framework",
    "rest_framework_simplejwt",
    "drf_yasg",
    # Core Horilla apps
    "horilla_auth",
    THEME_APP,
    "base",
    "employee",
    "recruitment",
    "leave",
    "pms",
    "onboarding",
    "asset",
    "attendance",
    "payroll",
    "accessibility",
    "horilla_audit",
    "horilla_widgets",
    "horilla_crumbs",
    "horilla_documents",
    "horilla_views",
    "horilla_automations",
    "horilla_api",
    "biometric",
    "helpdesk",
    "offboarding",
    "horilla_backup",
    "project",
    "horilla_meet",
    "report",
    "whatsapp",
    "horilla_ldap",
    "horilla_dbtemplate",
    "horilla_tour",
]

# ========================================
# REST FRAMEWORK CONFIGURATION
# ========================================

REST_FRAMEWORK = {
    "DEFAULT_FILTER_BACKENDS": ["django_filters.rest_framework.DjangoFilterBackend"],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "DEFAULT_AUTHENTICATION_CLASSES": (
        # Subclasses JWTAuthentication to also set the company ContextVar that
        # HorillaCompanyManager scopes on. CompanyMiddleware cannot do it for
        # API calls: middleware runs before DRF resolves the token, so it sees
        # AnonymousUser and returns early, leaving queries unscoped. See
        # horilla_api/authentication.py.
        "horilla_api.authentication.TenantScopedJWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "PAGE_SIZE": 20,
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
        "rest_framework.throttling.ScopedRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        # django-axes already locks an account after AXES_FAILURE_LIMIT bad
        # passwords, but it counts failures only: a caller can hammer the
        # login endpoint with valid credentials, or any authenticated
        # endpoint at any rate, without tripping it. These bound that.
        #
        # Deliberately generous. The point is to stop enumeration and
        # runaway clients, not to police normal use -- the HR UI itself is
        # a heavy API consumer, and a limit that fires during ordinary work
        # gets raised until it is meaningless.
        "anon": env("THROTTLE_ANON", default="60/min"),
        "user": env("THROTTLE_USER", default="600/min"),
        # Login is the one unauthenticated write path. Tighter, because a
        # successful-login flood is how you mint tokens in bulk.
        "login": env("THROTTLE_LOGIN", default="12/min"),
        # Export and import walk whole tables and build files; a handful a
        # minute is well past what a person does.
        "bulk": env("THROTTLE_BULK", default="6/min"),
    },
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=60),
    # Only ACCESS_TOKEN_LIFETIME was set, so this inherited SimpleJWT's
    # default of one day by accident rather than by choice. Nothing can
    # present a refresh token today -- the login endpoint returns only the
    # access token and there is no refresh route -- so this bounds a token
    # that is created and discarded. Stated explicitly so that adding a
    # refresh flow later is a deliberate decision about its lifetime.
    "REFRESH_TOKEN_LIFETIME": timedelta(days=1),
    # Embeds a hash of the user's password in each token and rejects the
    # token once the stored hash no longer matches, so changing or resetting
    # a password revokes every token issued before it. Without this an
    # access token stays valid for its full hour after a password reset,
    # which is the one window a compromised account cannot be closed --
    # there is no blacklist for access tokens, and no logout endpoint.
    "CHECK_REVOKE_TOKEN": True,
}

SWAGGER_SETTINGS = {
    "SECURITY_DEFINITIONS": {
        "Bearer": {
            "type": "apiKey",
            "name": "Authorization",
            "in": "header",
            "description": "Enter your Bearer token here",
        },
        "Basic": {"type": "basic", "description": "Basic authentication."},
    },
    "SECURITY": [{"Bearer": []}, {"Basic": []}],
}

APSCHEDULER_DATETIME_FORMAT = "N j, Y, f:s a"

APSCHEDULER_RUN_NOW_TIMEOUT = 25  # Seconds

# ========================================
# MIDDLEWARE
# ========================================
MIDDLEWARE = [
    # First, so every log line emitted while handling the request -- including
    # ones from middleware below -- carries the correlation id.
    "horilla.observability.RequestIDMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "simple_history.middleware.HistoryRequestMiddleware",
    "horilla.horilla_middlewares.DefaultLanguageMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # Horilla-specific middlewares
    "base.middleware.CompanyMiddleware",
    "base.middleware.ForcePasswordChangeMiddleware",
    "base.middleware.TwoFactorAuthMiddleware",
    "accessibility.middlewares.AccessibilityMiddleware",
    "horilla.horilla_middlewares.MethodNotAllowedMiddleware",
    "horilla.horilla_middlewares.SVGSecurityMiddleware",
    "horilla.horilla_middlewares.MissingParameterMiddleware",
    "auditlog.middleware.AuditlogMiddleware",
    # Last: needs request.user from AuthenticationMiddleware, and
    # converts a PermissionDenied from the Axes backend into the
    # lockout response.
    "axes.middleware.AxesMiddleware",
]

ROOT_URLCONF = "horilla.urls"

# ========================================
# DATABASE CONFIGURATION
# ========================================
if env("DATABASE_URL", default=None):
    DATABASES = {"default": env.db()}
else:
    DATABASES = {
        "default": {
            "ENGINE": env("DB_ENGINE", default="django.db.backends.sqlite3"),
            "NAME": env("DB_NAME", default=os.path.join(BASE_DIR, "TestDB.sqlite3")),
            "USER": env("DB_USER", default=""),
            "PASSWORD": env("DB_PASSWORD", default=""),
            "HOST": env("DB_HOST", default=""),
            "PORT": env("DB_PORT", default=""),
            #"OPTIONS": {
            #    "timeout": 30,  # seconds to wait on a locked DB before raising OperationalError
            #},
        }
    }

# SQLite: enable WAL so reads (list/search) don't block session writes from
# concurrent requests like notification polling.
from django.db.backends.signals import connection_created


def _configure_sqlite_connection(sender, connection, **kwargs):
    if connection.vendor != "sqlite":
        return
    with connection.cursor() as cursor:
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.execute("PRAGMA synchronous=NORMAL;")
        cursor.execute("PRAGMA busy_timeout=30000;")


connection_created.connect(_configure_sqlite_connection)

# ========================================
# CACHE (optional Redis when REDIS_URL is set)
# ========================================
# Fresh clones / runserver keep Django's default LocMem cache.
# Docker Compose sets REDIS_URL so the Redis service is actually used
# (requires django-redis in requirements.txt).
if REDIS_URL:
    CACHES = {
        "default": {
            "BACKEND": "django_redis.cache.RedisCache",
            "LOCATION": REDIS_URL,
            "OPTIONS": {
                "CLIENT_CLASS": "django_redis.client.DefaultClient",
            },
            "KEY_PREFIX": "horilla",
        }
    }

# ========================================
# STATIC & MEDIA FILES
# ========================================
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
# STATICFILES_STORAGE = "whitenoise.storage.CompressedStaticFilesStorage"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}

MEDIA_URL = "/media/"
MEDIA_ROOT = os.path.join(BASE_DIR, "media/")

# ========================================
# AUTHENTICATION & SECURITY
# ========================================
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"
    },
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

AUTH_USER_MODEL = "horilla_auth.HorillaUser"

X_FRAME_OPTIONS = "SAMEORIGIN"

# ========================================
# TEMPLATES
# ========================================
# In production (DEBUG=False) these are wrapped in the cached template
# loader so Django compiles each template once per process instead of
# re-parsing it (and re-running horilla_dbtemplate's DB-lookup chain) on
# every include, on every request. Left uncached in DEBUG so template
# edits during development are picked up without restarting the server.
_TEMPLATE_LOADERS = [
    "horilla_dbtemplate.loaders.Loader",
    ("django.template.loaders.filesystem.Loader", [BASE_DIR / THEME_APP / "templates"]),
    "django.template.loaders.app_directories.Loader",
    ("django.template.loaders.filesystem.Loader", [BASE_DIR / "templates"]),
]

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": False,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                # Horilla dynamic context processors
                "horilla.config.get_MENUS",
                "base.context_processors.get_companies",
                "base.context_processors.white_labelling_company",
                "base.context_processors.doc_base_url",
                "base.context_processors.resignation_request_enabled",
                "base.context_processors.timerunner_enabled",
                "base.context_processors.intial_notice_period",
                "base.context_processors.check_candidate_self_tracking",
                "base.context_processors.check_candidate_self_tracking_rating",
                "base.context_processors.get_initial_prefix",
                "base.context_processors.biometric_app_exists",
                "base.context_processors.enable_late_come_early_out_tracking",
                "base.context_processors.enable_profile_edit",
                "base.context_processors.export_access_enabled",
                "base.context_processors.navbar_languages",
                "horilla_tour.context_processors.pending_tours_flag",
                "horilla_crumbs.context_processors.breadcrumbs",
            ],
            "loaders": (
                _TEMPLATE_LOADERS
                if DEBUG
                else [("django.template.loaders.cached.Loader", _TEMPLATE_LOADERS)]
            ),
        },
    },
]

WSGI_APPLICATION = "horilla.wsgi.application"

# ========================================
# INTERNATIONALIZATION
# ========================================
LANGUAGE_CODE = "en-us"
TIME_ZONE = env("TIME_ZONE", default="Asia/Kolkata")
USE_I18N = True
USE_TZ = True

LANGUAGES = (
    ("en", "English (US)"),
    ("de", "Deutsch"),
    ("es", "Español"),
    ("fr", "Français"),
    ("ar", "العربية"),
    ("pt-br", "Português (Brasil)"),
    ("zh-hans", "简体中文"),
    ("zh-hant", "繁體中文"),
    ("it", "Italian"),
    ("tr", "Turkish"),
    ("uk", "Українська"),
    ("ro", "Română"),
)

LOCALE_PATHS = [join(BASE_DIR, "horilla", "locale")]

# ========================================
# LOGGING, MESSAGES, OTHER GLOBALS
# ========================================
# There are ~79 getLogger() call sites and, until now, no LOGGING config, so all
# of them fell through to Django's defaults: unstructured, uncorrelated, and in
# production nothing but gunicorn's access log. JSON when DEBUG is off so log
# aggregators can parse it; human-readable locally.
from horilla.observability import build_logging_config  # noqa: E402

LOGGING = build_logging_config(
    debug=DEBUG, level=env("DJANGO_LOG_LEVEL", default="INFO")
)

# Error tracking. Does nothing unless SENTRY_DSN is set, so an open-source
# install sends nothing anywhere by default. PII is scrubbed in before_send
# rather than trusting the receiving project's config -- a stack trace here can
# hold salaries, bank details and reset tokens.
from horilla.__version__ import __version__ as _horilla_version  # noqa: E402
from horilla.observability import init_sentry  # noqa: E402

SENTRY_DSN = env("SENTRY_DSN", default="")
init_sentry(
    dsn=SENTRY_DSN,
    environment=HORILLA_ENV or ("development" if DEBUG else "production"),
    release=_horilla_version,
    traces_sample_rate=env.float("SENTRY_TRACES_SAMPLE_RATE", default=0.0),
)

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

MESSAGE_TAGS = {
    messages.DEBUG: "oh-alert--warning",
    messages.INFO: "oh-alert--info",
    messages.SUCCESS: "oh-alert--success",
    messages.WARNING: "oh-alert--warning",
    messages.ERROR: "oh-alert--danger",
}

LOGIN_URL = "/login"
SIMPLE_HISTORY_REVERT_DISABLED = True

DJANGO_NOTIFICATIONS_CONFIG = {
    "USE_JSONFIELD": True,
    "SOFT_DELETE": True,
    "USE_WATCHED": True,
    "NOTIFICATIONS_STORAGE": "notifications.storage.DatabaseStorage",
    "TEMPLATE": "notifications.html",
}

# ========================================
# HORILLA-SPECIFIC SETTINGS
# ========================================
WHITE_LABELLING = False
NESTED_SUBORDINATE_VISIBILITY = False
TWO_FACTORS_AUTHENTICATION = False
# When True, /ready/ returns 503 until run_scheduler has registered jobs.
# Off by default so Docker CI (web without the scheduler service) still passes.
HORILLA_REQUIRE_SCHEDULER = env.bool("HORILLA_REQUIRE_SCHEDULER", default=False)

SIDEBARS = [
    "employee",
    "attendance",
    "leave",
    "payroll",
    "recruitment",
    "onboarding",
    "offboarding",
    "pms",
    "project",
    "asset",
    "helpdesk",
    "report",
]

# Audit logging is opt-in: the horilla_audit app registers models explicitly
# through its registry, driven by AuditModelConfig and a default whitelist
# (Employee, EmployeeWorkInformation, EmployeeBankDetails).
AUDITLOG_INCLUDE_ALL_MODELS = False
AUDITLOG_EXCLUDE_TRACKING_MODELS = (
    # "<app_name>",
    # "<app_name>.<model>"
)

EMAIL_BACKEND = "base.backends.ConfiguredEmailBackend"

"""
DB_INIT_PASSWORD: str

The password used for database setup and initialization. This password is a
48-character alphanumeric string generated using a UUID to ensure high entropy and security.
"""
DB_INIT_PASSWORD = env(
    "DB_INIT_PASSWORD", default="d3f6a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d"
)

# ========================================
# PERMISSIONS / CUSTOM LOGIC
# ========================================
# When True, group permissions are scoped per company via
# base.models.CompanyGroupAssignment (resolved by CompanyScopedBackend).
# When False, legacy behavior: user.groups grant permissions globally.
# Instant rollback switch: set the COMPANY_SCOPED_PERMISSIONS env var to False.
COMPANY_SCOPED_PERMISSIONS = env.bool("COMPANY_SCOPED_PERMISSIONS", default=True)

NO_PERMISSION_MODALS = [
    "companygroupassignment",
    "historicalbonuspoint",
    "assetreport",
    "assetdocuments",
    "returnimages",
    "holiday",
    "companyleave",
    "historicalavailableleave",
    "historicalleaverequest",
    "historicalleaveallocationrequest",
    "leaverequestconditionapproval",
    "historicalcompensatoryleaverequest",
    "employeepastleaverestrict",
    "overrideleaverequests",
    "historicalrotatingworktypeassign",
    "employeeshiftday",
    "historicalrotatingshiftassign",
    "historicalworktyperequest",
    "historicalshiftrequest",
    "multipleapprovalmanagers",
    "attachment",
    "announcementview",
    "emaillog",
    "driverviewed",
    "dashboardemployeecharts",
    "attendanceallowedip",
    "tracklatecomeearlyout",
    "historicalcontract",
    "overrideattendance",
    "overrideleaverequest",
    "overrideworkinfo",
    "multiplecondition",
    "historicalpayslip",
    "reimbursementmultipleattachment",
    "workrecord",
    "historicalticket",
    "skill",
    "historicalcandidate",
    "rejectreason",
    "historicalrejectedcandidate",
    "rejectedcandidate",
    "stagefiles",
    "stagenote",
    "questionordering",
    "recruitmentsurveyordering",
    "recruitmentsurveyanswer",
    "recruitmentgeneralsetting",
    "resume",
    "recruitmentmailtemplate",
    "profileeditfeature",
]

FILE_STORAGE = FileSystemStorage(location="csv_tmp/")

HORILLA_DATE_FORMATS = {
    "DD/MM/YY": "%d/%m/%y",
    "DD-MM-YYYY": "%d-%m-%Y",
    "DD.MM.YYYY": "%d.%m.%Y",
    "DD/MM/YYYY": "%d/%m/%Y",
    "MM/DD/YYYY": "%m/%d/%Y",
    "YYYY-MM-DD": "%Y-%m-%d",
    "YYYY/MM/DD": "%Y/%m/%d",
    "MMMM D, YYYY": "%B %d, %Y",
    "DD MMMM, YYYY": "%d %B, %Y",
    "MMM. D, YYYY": "%b. %d, %Y",
    "D MMM. YYYY": "%d %b. %Y",
    "dddd, MMMM D, YYYY": "%A, %B %d, %Y",
}

HORILLA_TIME_FORMATS = {
    "hh:mm A": "%I:%M %p",  # 12-hour format
    "HH:mm": "%H:%M",  # 24-hour format
    "HH:mm:ss.SSSSSS": "%H:%M:%S.%f",  # 24-hour format with seconds and microseconds
}

BIO_DEVICE_THREADS = {}

DYNAMIC_URL_PATTERNS = []

APP_URLS = [
    "base.urls",
    "employee.urls",
]

APPS = [
    "auth",
    "base",
    "employee",
    "horilla_documents",
    "horilla_automations",
]

# ========================================
# LDAP CONFIGURATION (Default)
# ========================================
AUTH_LDAP_SERVER_URI = env("AUTH_LDAP_SERVER_URI", default="ldap://127.0.0.1:389")
AUTH_LDAP_BIND_DN = env("AUTH_LDAP_BIND_DN", default="cn=admin,dc=horilla,dc=com")
AUTH_LDAP_BIND_PASSWORD = env("AUTH_LDAP_BIND_PASSWORD", default="")

AUTH_LDAP_USER_ATTR_MAP = {
    "first_name": "givenName",
    "last_name": "sn",
    "email": "mail",
}

# Default LDAP settings
DEFAULT_LDAP_CONFIG = {
    "LDAP_SERVER": env("LDAP_SERVER", default="ldap://127.0.0.1:389"),
    "BIND_DN": env("BIND_DN", default="cn=admin,dc=horilla,dc=com"),
    "BIND_PASSWORD": env("BIND_PASSWORD", default=""),
    "BASE_DN": env("BASE_DN", default="ou=users,dc=horilla,dc=com"),
}

# CompanyScopedBackend subclasses ModelBackend; it behaves identically while
# COMPANY_SCOPED_PERMISSIONS is False. It must REPLACE ModelBackend (Django
# unions grants across backends, so listing both would keep global perms).
AUTHENTICATION_BACKENDS = [
    # MUST be first: AxesStandaloneBackend short-circuits authenticate() for a
    # locked-out user, so any backend listed ahead of it would still verify the
    # password and let an attacker keep testing credentials.
    "axes.backends.AxesStandaloneBackend",
    "base.auth_backends.CompanyScopedBackend",
    # "django_auth_ldap.backend.LDAPBackend",
]

AUTH_LDAP_ALWAYS_UPDATE_USER = True

# ========================================
# BRUTE-FORCE PROTECTION (django-axes)
# ========================================
# The login view previously accepted unlimited attempts: no counter, no
# lockout, no delay, and no rate limiting at the proxy either.
#
# Lock on the (username, IP) pair rather than IP alone -- IP-only locks out
# everyone behind a shared NAT when one account is attacked, and username-only
# lets an attacker lock a known user out on purpose (a denial-of-service).
AXES_FAILURE_LIMIT = env.int("AXES_FAILURE_LIMIT", default=5)
AXES_COOLOFF_TIME = timedelta(minutes=env.int("AXES_COOLOFF_MINUTES", default=30))
AXES_LOCKOUT_PARAMETERS = [["username", "ip_address"]]
AXES_RESET_ON_SUCCESS = True
# Count only real failures; a lockout response is not itself a new attempt.
AXES_LOCKOUT_TEMPLATE = None
AXES_ENABLE_ADMIN = True
# Behind nginx/ELB the client IP is in X-Forwarded-For. Only trust it when the
# deployment actually sets a proxy count, otherwise a client can spoof the
# header and dodge the IP half of the lock.
AXES_IPWARE_PROXY_COUNT = env.int("AXES_PROXY_COUNT", default=None)
# With no proxy count declared, ipware takes the first X-Forwarded-For value
# as-is, so a client could send a fresh header per attempt and the IP half of
# the lock never matches. Read the header only when AXES_PROXY_COUNT is set;
# the shipped compose sets it to 1 for its nginx.
AXES_IPWARE_META_PRECEDENCE_ORDER = (
    ["HTTP_X_FORWARDED_FOR"] if AXES_IPWARE_PROXY_COUNT else []
) + ["REMOTE_ADDR"]


# ========================================
# PRODUCTION SECURITY GATES
# ========================================
# Fail closed when DEBUG=False or HORILLA_ENV=production. Local DEBUG=True
# tutorials keep insecure-but-documented defaults for open-source onboarding.
from horilla.settings.security import (  # noqa: E402
    apply_secure_defaults,
    is_production_mode,
    validate_production_secrets,
)

IS_PRODUCTION = is_production_mode(DEBUG, HORILLA_ENV)

if IS_PRODUCTION:
    validate_production_secrets(SECRET_KEY, ALLOWED_HOSTS, DB_INIT_PASSWORD)

if IS_PRODUCTION:
    # Same switch as the secrets gate above: HORILLA_ENV=production must not
    # pass secret validation and then ship insecure cookies because DEBUG was
    # left on.
    globals().update(apply_secure_defaults(env, DEBUG))

# Idle-session timeout. Django's default is a fixed two weeks from login;
# saving the session on every request turns SESSION_COOKIE_AGE into an
# inactivity window instead, which is what access-control audits ask for.
SESSION_COOKIE_AGE = env.int("SESSION_COOKIE_AGE", default=12 * 60 * 60)
SESSION_SAVE_EVERY_REQUEST = True

# Rate limiting is production protection, not behaviour the rest of the suite
# should have to work around. Throttle counters live in the cache keyed by
# client IP, and the test client always presents the same one, so every login
# the suite makes accumulates into a single bucket: with six API test modules
# logging in, later tests fail with 429 for reasons unrelated to what they
# assert.
#
# Disabling the rates here rather than clearing the cache per test keeps the
# mechanism in one place. horilla_api/tests/test_throttling.py still proves
# the throttles work, because it sets its own rate on
# SimpleRateThrottle.THROTTLE_RATES -- the class attribute the throttle
# actually reads -- rather than relying on these settings.
if "test" in sys.argv:
    REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"] = {
        scope: None for scope in REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]
    }
