#!/usr/bin/env python3

import traceback

from django.contrib.auth import get_user_model
from django.core.exceptions import ImproperlyConfigured
from django.core.management import execute_from_command_line
from dotenv import load_dotenv, find_dotenv
import logging
import os
import sys

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Load environment variables from .env file
dotenv_path = find_dotenv()
if dotenv_path:
    load_dotenv(dotenv_path)
    logger.info(f"Loaded environment variables from {dotenv_path}")
else:
    logger.warning("No .env file found. Proceeding with environment variables only.")

def get_env_variable(var_name, default=None, required=False):
    """Retrieve environment variable or return exception."""
    value = os.getenv(var_name, default)
    if required and not value:
        logger.error(f"Environment variable '{var_name}' is required but not set.")
        raise ImproperlyConfigured(f"Missing required environment variable: {var_name}")
    return value

def main():
    """Main function to create a superuser."""
    # Set default Django settings module
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "jasmin_api.settings")

    # Initialize Django
    try:
        import django
        django.setup()
    except ImportError as exc:
        logger.error("Django is not installed or could not be imported.")
        raise exc

    User = get_user_model()

    # Retrieve environment variables
    username = get_env_variable("USERNAME", required=True)
    email = get_env_variable("USER_EMAIL", default='')
    password = get_env_variable("USER_PASSWORD", default='root')

    # Validate password strength
    if password == 'root':
        logger.warning("Using default password 'root'. It's highly recommended to set a strong password via USER_PASSWORD environment variable.")

    # Check if user already exists
    if User.objects.filter(username=username).exists():
        logger.info(f"Superuser '{username}' already exists. Skipping creation.")
    else:
        try:
            User.objects.create_superuser(
                username=username,
                email=email,
                password=password
            )
            logger.info(f"Superuser '{username}' created successfully.")
        except Exception as e:
            logger.error(f"Failed to create superuser '{username}'. Error: {e}")
            sys.exit(1)

    # Optionally, you can add additional user setup here

if __name__ == "__main__":
    main()
