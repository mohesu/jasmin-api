import logging
import traceback

logging.basicConfig(level=logging.INFO)

from django.core.wsgi import get_wsgi_application

from dotenv import load_dotenv, find_dotenv

import os



"""
WSGI config for jasmin_api project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/1.8/howto/deployment/wsgi/
"""


load_dotenv(find_dotenv())

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "jasmin_api.settings")

application = get_wsgi_application()
