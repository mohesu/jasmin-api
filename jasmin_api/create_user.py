#!/usr/bin/env python
import os
from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv())

if __name__ == "__main__":
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "jasmin_api.settings")

    from django.contrib.auth import get_user_model

    User = get_user_model()
    User.objects.create_superuser(os.getenv("USERNAME"), os.getenv("USER_EMAIL") or '',  os.getenv("USER_PASSWORD") or 'root')