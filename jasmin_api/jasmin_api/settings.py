import os
import sys
from kubernetes import client, config
from kubernetes.client.rest import ApiException

# Base directory
SETTINGS_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

################################################################################
#         Settings most likely to need overriding in local_settings.py         #
################################################################################

# Jasmin telnet defaults, override in local_settings.py
TELNET_HOST = os.getenv("TELNET_HOST", "localhost")
TELNET_PORT = int(os.getenv("TELNET_PORT", 8990))
TELNET_USERNAME = os.getenv("TELNET_USERNAME", "jcliadmin")
TELNET_PW = os.getenv("TELNET_PW", "jclipwd")  # Note: Avoid storing passwords in plain text
TELNET_TIMEOUT = int(os.getenv("TELNET_TIMEOUT", 10))  # Reasonable value for intranet
JASMIN_K8S = os.getenv("JASMIN_K8S", "True").lower() == "true"  # Manage multiple Kubernetes instances
JASMIN_K8S_NAMESPACE = os.getenv("JASMIN_K8S_NAMESPACE")  # Namespace where Jasmin pods reside
JASMIN_DOCKER = os.getenv("JASMIN_DOCKER", "True").lower() == "true"  # Manage multiple Jasmin Docker instances
JASMIN_DOCKER_PORTS = eval(os.getenv("JASMIN_DOCKER_PORTS", "[]"))  # Evaluate string as list
DEBUG = os.getenv("DEBUG", "False").lower() == "true"

if JASMIN_K8S:
    try:
        config.load_incluster_config()
        K8S_CLIENT = client.CoreV1Api()
        print("Main: K8S API initialized.")
    except config.ConfigException as e:
        print(f"Main: ERROR: Cannot initialize K8S environment, terminating: {e}")
        sys.exit(-1)

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework.authentication.BasicAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    'DEFAULT_FILTER_BACKENDS': ['django_filters.rest_framework.DjangoFilterBackend'],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 10,
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.UserRateThrottle',
        'rest_framework.throttling.AnonRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'user': '1000/day',
        'anon': '100/day',
    },
}

SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', 'fallback-secret-key')

################################################################################
#                            Other settings                                    #
################################################################################

STANDARD_PROMPT = 'jcli : '  # There should be no need to change this
INTERACTIVE_PROMPT = '> '  # Prompt for interactive commands

# This should be OK for REST API - we are not generating URLs
# see https://www.djangoproject.com/weblog/2013/feb/19/security/#s-issue-host-header-poisoning
ALLOWED_HOSTS = ['yourdomain.com', 'www.yourdomain.com']

SWAGGER_SETTINGS = {
    'exclude_namespaces': [],
    'api_version': '',
    'is_authenticated': False,
    'is_superuser': False,
    'info': {
        'description': 'A REST API for managing Jasmin SMS Gateway',
        'title': 'Jasmin Management REST API',
    },
}

# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'rest_api',
    'drf_yasg',
    'health_check',
    'health_check.db',  # Enable database health checks
    # Add more health checks as needed
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'rest_api.middleware.TelnetConnectionMiddleware',  # Custom middleware
]

ROOT_URLCONF = 'jasmin_api.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],  # Add your template directories here
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',  # Required by admin
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'jasmin_api.wsgi.application'

# Database
# https://docs.djangoproject.com/en/3.2/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': os.path.join(BASE_DIR, 'db.sqlite3'),
    }
}

# Internationalization
# https://docs.djangoproject.com/en/3.2/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_L10N = True

USE_TZ = True

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/3.2/howto/static-files/

STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')

# Simplify config to show/hide Swagger docs
SHOW_SWAGGER = True

if SHOW_SWAGGER:
    INSTALLED_APPS.append('rest_framework_swagger')
