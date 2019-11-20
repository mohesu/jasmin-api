#!/bin/bash

echo 'Migration'

python /jasmin_api/manage.py migrate
python /jasmin_api/manage.py collectstatic << 'EOF'
yes
EOF

python /jasmin_api/manage.py createsuperuser << 'EOF'
root
zoug!@#
EOF

exec "$@"