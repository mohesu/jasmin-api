#!/bin/bash
set -e  # Exit immediately if a command exits with a non-zero status

echo 'Running database migrations...'
python manage.py migrate

echo 'Collecting static files...'
yes | python manage.py collectstatic --noinput

echo 'Creating default user...'
python create_user.py  # Ensure this script handles idempotency
echo 'Default user created successfully.'

# Start the main application
exec "$@"
