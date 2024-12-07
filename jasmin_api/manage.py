import logging
import traceback

logging.basicConfig(level=logging.INFO)

from django.core.management import execute_from_command_line

from dotenv import load_dotenv, find_dotenv

import os

import sys



#!/usr/bin/env python
load_dotenv(find_dotenv())

if __name__ == "__main__":
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "jasmin_api.settings")


    execute_from_command_line(sys.argv)
