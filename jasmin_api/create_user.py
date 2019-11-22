#!/usr/bin/env python
import os
from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv())

if __name__ == "__main__":
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "jasmin_api.settings")
    from django.contrib.auth.models import User

    User.objects.create_superuser(
        username=os.getenv("USERNAME"),
        email=os.getenv("USER_EMAIL") or '',
        password=os.getenv("USER_PASSWORD") or 'root'
    )