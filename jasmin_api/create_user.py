#!/usr/bin/env python
import os
from dotenv import load_dotenv, find_dotenv
from django.contrib.auth import get_user_model

load_dotenv(find_dotenv)


User = get_user_model()
User.objects.create_superuser(os.getenv("USERNAME"), os.getenv("USER_EMAIL") or '',  os.getenv("USER_PASSWORD") or 'root')