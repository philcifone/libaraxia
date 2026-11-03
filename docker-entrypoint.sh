#!/bin/bash
set -e

echo "Starting Libaraxia initialization..."

mkdir -p /app/instance
export DATABASE_PATH="${DATABASE_PATH:-/app/instance/library.db}"

# Creates the database from create_database.sql if it's missing, otherwise
# backs it up and applies any pending migrations. A database created before
# the migration runner existed needs `python3 manage.py migrate --baseline`
# once (run it with `docker compose run`), and this step stops until then.
python3 manage.py migrate --yes

echo "Starting main application..."
exec "$@"
