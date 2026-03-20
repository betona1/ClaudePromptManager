"""
cpm_web: Start CPM web server.
Usage: python manage.py cpm_web [--port 9200]
"""
from django.core.management.base import BaseCommand
from django.conf import settings


class Command(BaseCommand):
    help = 'Start CPM web server'

    def add_arguments(self, parser):
        parser.add_argument('--port', type=int, default=settings.CPM_WEB_PORT,
                          help=f'Port number (default: {settings.CPM_WEB_PORT})')
        parser.add_argument('--host', default='0.0.0.0', help='Host to bind')

    def handle(self, *args, **options):
        port = options['port']
        host = options['host']

        self.stdout.write(self.style.SUCCESS(f'Starting CPM Web Server on http://{host}:{port}'))
        self.stdout.write(f'  Dashboard: http://localhost:{port}/')
        self.stdout.write(f'  API: http://localhost:{port}/api/')
        self.stdout.write('')

        from django.core.management import call_command
        call_command('runserver', f'{host}:{port}', use_reloader=True)
