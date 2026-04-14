#!/bin/bash
set -e

echo "=== CPM Docker Entrypoint ==="

# Seed screenshots volume (only if empty)
if [ -z "$(ls -A /app/static/screenshots/ 2>/dev/null)" ] && [ -d /app/_screenshots_seed ] && [ "$(ls -A /app/_screenshots_seed/ 2>/dev/null)" ]; then
    echo "Seeding screenshots from build..."
    cp -r /app/_screenshots_seed/* /app/static/screenshots/ 2>/dev/null || true
fi

# Run migrations
echo "Running migrations..."
python manage.py migrate --noinput

# Collect static files
echo "Collecting static files..."
python manage.py collectstatic --noinput 2>/dev/null || true

# Update Site domain from CPM_ALLOWED_HOSTS (no port for HTTPS domains)
python manage.py shell -c "
from django.contrib.sites.models import Site
import os
hosts = os.environ.get('CPM_ALLOWED_HOSTS', '*')
if hosts and hosts != '*':
    domain = hosts.split(',')[0].strip()
    Site.objects.filter(id=1).update(domain=domain, name='CPM')
" 2>/dev/null || true

# Create default admin account if no users exist
python manage.py shell -c "
from django.contrib.auth.models import User
if User.objects.count() == 0:
    admin = User.objects.create_superuser('admin', '', '1234')
    from core.models import UserProfile
    UserProfile.objects.create(
        user=admin,
        github_username='admin',
        is_admin=True,
        is_approved=True,
    )
    print('Default admin account created (admin/1234)')
else:
    # Ensure existing admins are approved
    from core.models import UserProfile
    UserProfile.objects.filter(is_admin=True, is_approved=False).update(is_approved=True)
" 2>/dev/null || true

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
