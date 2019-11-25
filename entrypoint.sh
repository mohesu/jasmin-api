#!/bin/bash

echo 'Migrate'
python /jasmin_api/manage.py migrate
echo 'Static Collect'
python /jasmin_api/manage.py collectstatic << 'EOF'
yes
EOF
echo 'Creating user'
python /jasmin_api/create_user.py
echo 'User created'
exec "$@"