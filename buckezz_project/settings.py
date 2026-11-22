import os
import sys
import environ
from pathlib import Path

# Build paths inside the project like this: BASE_DIR / 'subdir'.
if getattr(sys, 'frozen', False):
    BASE_DIR = Path(sys.executable).resolve().parent
    BUNDLE_DIR = Path(sys._MEIPASS) if hasattr(sys, '_MEIPASS') else BASE_DIR / '_internal'
else:
    BASE_DIR = Path(__file__).resolve().parent.parent
    BUNDLE_DIR = BASE_DIR

env = environ.Env(
    DEBUG=(bool, False),
)

# Take environment variables from .env file
environ.Env.read_env(os.path.join(BASE_DIR, '.env'))


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/6.0/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = env('SECRET_KEY', default='django-insecure-buckezz-desktop-default-secret-key-change-in-prod')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = env('DEBUG', default=True)

ALLOWED_HOSTS = env.list('ALLOWED_HOSTS', default=[])
# Always allow Tailscale Funnel domains, greatsmallstuff.de, and localhost as guaranteed fallback
ALLOWED_HOSTS += [
    'localhost',
    '127.0.0.1',
    '.ts.net',
    'nas.sunfish-universe.ts.net',
    '.localhost',
    '.buckezz.zaisers.myds.me',
    '.zaisers.myds.me',
    '.greatsmallstuff.de',
]
CSRF_TRUSTED_ORIGINS = env.list('CSRF_TRUSTED_ORIGINS', default=[])
CSRF_TRUSTED_ORIGINS += [
    'https://nas.sunfish-universe.ts.net',
    'https://*.greatsmallstuff.de',
    'https://greatsmallstuff.de',
    'https://*.zaisers.myds.me',
]

# Trust the reverse proxy to determine the scheme (http vs https)
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# Allow iframe-based modals in the Admin Interface
X_FRAME_OPTIONS = 'SAMEORIGIN'

# Authentication Redirects
LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/dashboard/'


# Application definition

INSTALLED_APPS = [
    'design_studio',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    
    # Third-party apps
    'django_htmx',
    'pwa',
    'django_extensions',
    
    # Baukasten kits
    'grid_kit',
    'seed_kit',
    'domain_kit',
    'cal_kit',
    'notify_kit',
    'ops_kit',
    
    # Local apps
    'core',
]

OPS_REQUIRED_KITS = ['design_studio', 'ops_kit', 'grid_kit', 'seed_kit', 'domain_kit']

try:
    from ops_kit.runtime import apply_runtime_installed_apps
    apply_runtime_installed_apps(INSTALLED_APPS, BASE_DIR, protected=OPS_REQUIRED_KITS)
except ImportError:
    pass

MIDDLEWARE = [
    'core.middleware.TenantMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'django_htmx.middleware.HtmxMiddleware',
    'core.middleware.TimezoneMiddleware',
]

ROOT_URLCONF = 'buckezz_project.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BUNDLE_DIR / 'templates', BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'design_studio.context_processors.theme_context',
                'core.context_processors.user_settings',
            ],
        },
    },
]

WSGI_APPLICATION = 'buckezz_project.wsgi.application'


# Database
# https://docs.djangoproject.com/en/6.0/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': env('DB_PATH', default=BASE_DIR / 'db.sqlite3'),
    }
}

DATABASE_ROUTERS = ['core.router.TenantRouter']

# Security: Optional registration key to prevent public abuse of tenant registration
REGISTRATION_CODE = env('REGISTRATION_CODE', default='')



# Password validation
# https://docs.djangoproject.com/en/6.0/ref/settings/#auth-password-validators

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
# https://docs.djangoproject.com/en/6.0/topics/i18n/

LANGUAGE_CODE = 'de-de'

TIME_ZONE = 'Europe/Berlin'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/6.0/howto/static-files/

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BUNDLE_DIR / 'static'] if (BUNDLE_DIR / 'static').exists() else [BASE_DIR / 'static']

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# PWA Settings
PWA_APP_NAME = 'Buckezz 2.0'
PWA_APP_DESCRIPTION = 'One Bucket for Everything'
PWA_APP_THEME_COLOR = '#4f46e5'
PWA_APP_BACKGROUND_COLOR = '#0f172a'
PWA_APP_DISPLAY = 'standalone'
PWA_APP_SCOPE = '/'
PWA_APP_ORIENTATION = 'any'
PWA_APP_START_URL = '/'
PWA_APP_STATUS_BAR_COLOR = 'default'
PWA_APP_ICONS = [
    {
        'src': '/static/images/icon-160.png',
        'sizes': '160x160'
    }
]
PWA_APP_ICONS_APPLE = [
    {
        'src': '/static/images/icon-160.png',
        'sizes': '160x160'
    }
]
PWA_APP_SPLASH_SCREEN = [
    {
        'src': '/static/images/icon-512.png',
        'media': '(device-width: 320px) and (device-height: 568px) and (-webkit-device-pixel-ratio: 2)'
    }
]
PWA_APP_DIR = 'ltr'
PWA_APP_LANG = 'de-DE'
PWA_SERVICE_WORKER_PATH = os.path.join(BUNDLE_DIR, 'static', 'js', 'serviceworker.js') if os.path.exists(os.path.join(BUNDLE_DIR, 'static', 'js', 'serviceworker.js')) else os.path.join(BASE_DIR, 'static', 'js', 'serviceworker.js')

# Email Settings
EMAIL_BACKEND = env('EMAIL_BACKEND', default=env('MAIL_BACKEND', default='django.core.mail.backends.smtp.EmailBackend'))
EMAIL_HOST = env('EMAIL_HOST', default='smtp.gmail.com')
EMAIL_PORT = env.int('EMAIL_PORT', default=587)
EMAIL_USE_TLS = env.bool('EMAIL_USE_TLS', default=True)
EMAIL_USE_SSL = env.bool('EMAIL_USE_SSL', default=False)
EMAIL_HOST_USER = env('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = env('EMAIL_HOST_PASSWORD', default='')
DEFAULT_FROM_EMAIL = env('DEFAULT_FROM_EMAIL', default=env('EMAIL_HOST_USER', default='Buckezz <noreply@buckezz.app>'))

# Calendar & Search Kit Providers
CAL_KIT_EVENT_PROVIDERS = ['core.calendar_provider.get_buckezz_calendar_events']
CAL_KIT_MOVE_HANDLERS = ['core.calendar_provider.move_buckezz_calendar_event']
DOMAIN_SEARCH_PROVIDERS = ['core.search_provider.search_buckezz']

# Design Studio & Baukasten Navigation
OPS_GITHUB_REPO = "bzaiser/buckezz-next"
DESIGN_STUDIO_APP_NAME = env('DESIGN_STUDIO_APP_NAME', default='Buckezz 2.0')
DESIGN_STUDIO_APP_ICON = 'bi-bucket'
DESIGN_STUDIO_MENU_ITEMS = [
    {"id": "home", "url_name": "core:dashboard", "match_urls": ["dashboard", "list_detail", "list_create", "home"], "default_label": "Buckets", "icon": "bi-bucket", "zone": "main", "display": "icon_text", "visible": True, "order": 1},
    {"id": "calendar", "url_name": "cal_kit:calendar", "match_urls": ["calendar"], "default_label": "Kalender", "icon": "bi-calendar3", "zone": "main", "display": "icon_text", "visible": True, "order": 2},
    {"id": "template_studio", "url_name": "core:template_studio", "match_urls": ["template_studio", "template_studio_create", "template_studio_edit"], "default_label": "Vorlagen-Studio", "icon": "bi-ui-checks-grid", "zone": "main", "display": "icon_text", "visible": True, "order": 3, "staff_only": True},
    {"id": "settings", "url_name": "core:settings", "match_urls": ["settings"], "default_label": "Einstellungen", "icon": "bi-gear", "zone": "utility", "display": "icon_only", "visible": True, "order": 1, "locked": True},
    {"id": "django_admin", "url_name": "admin:index", "url": "/admin/", "match_urls": [], "default_label": "Django Admin", "icon": "bi-shield-lock", "zone": "utility", "display": "icon_only", "visible": True, "order": 3, "staff_only": True},
    {"id": "night_mode", "url_name": "design_studio:toggle_night", "match_urls": [], "default_label": "Tag / Nacht", "icon": "bi-moon-stars", "zone": "utility", "display": "icon_only", "visible": True, "order": 4},
]
