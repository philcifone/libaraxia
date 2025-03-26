#!/bin/bash
set -e

echo "Starting Libaraxia initialization..."

# Create instance directory if it doesn't exist
mkdir -p /app/instance

# Database file path
DB_FILE="/app/instance/library.db"

# Only create the database if it doesn't exist
if [ ! -f "$DB_FILE" ]; then
    echo "Database not found. Creating fresh database..."
    # Create database from SQL file
    sqlite3 "$DB_FILE" < create_database.sql
    echo "Database structure created. First user to register will become admin."
else
    echo "Database already exists. Skipping initialization."
fi

echo "Starting main application..."
exec "$@"