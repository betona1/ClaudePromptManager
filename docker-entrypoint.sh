#!/bin/bash
set -e

echo "=== CPM Docker Entrypoint ==="

# Run migrations
echo "Running migrations..."
python manage.py migrate --noinput

# Collect static files
echo "Collecting static files..."
python manage.py collectstatic --noinput 2>/dev/null || true

# Start gunicorn
WORKERS=${GUNICORN_WORKERS:-2}
THREADS=${GUNICORN_THREADS:-2}
BIND=${GUNICORN_BIND:-0.0.0.0:9200}

echo "Starting gunicorn (workers=$WORKERS, threads=$THREADS, bind=$BIND)..."
exec gunicorn cpm.wsgi:application \
    --workers "$WORKERS" \
    --threads "$THREADS" \
    --bind "$BIND" \
    --access-logfile - \
    --error-logfile -
