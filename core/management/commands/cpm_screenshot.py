"""
cpm_screenshot: Capture screenshots of project web UIs.
Usage: python manage.py cpm_screenshot [--project NAME]
"""
import os
from pathlib import Path
from django.core.management.base import BaseCommand
from django.conf import settings

os.environ['DJANGO_ALLOW_ASYNC_UNSAFE'] = 'true'


SCREENSHOTS_DIR = Path(settings.BASE_DIR) / 'static' / 'screenshots'


class Command(BaseCommand):
    help = 'Capture screenshots of project web UIs using Playwright'

    def add_arguments(self, parser):
        parser.add_argument('--project', type=str, default=None,
                          help='Capture only this project')
        parser.add_argument('--set-url', nargs=2, metavar=('PROJECT', 'URL'),
                          help='Set URL for a project: --set-url ai100 http://localhost:8001')

    def handle(self, *args, **options):
        from core.models import Project

        # Set URL mode
        if options['set_url']:
            name, url = options['set_url']
            try:
                proj = Project.objects.get(name=name)
                proj.url = url
                proj.save(update_fields=['url'])
                self.stdout.write(self.style.SUCCESS(f'{name}: URL set to {url}'))
            except Project.DoesNotExist:
                self.stdout.write(self.style.ERROR(f'Project "{name}" not found'))
            return

        SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

        # Filter projects
        projects = Project.objects.exclude(url__isnull=True).exclude(url='')
        if options['project']:
            projects = projects.filter(name=options['project'])

        if not projects.exists():
            self.stdout.write(self.style.WARNING('No projects with URLs configured.'))
            self.stdout.write('Set URLs with: python manage.py cpm_screenshot --set-url <project> <url>')
            return

        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            self.stdout.write(self.style.ERROR('Playwright not installed. Run: pip install playwright && playwright install chromium'))
            return

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)

            for proj in projects:
                self.stdout.write(f'Capturing {proj.name} ({proj.url})...')
                try:
                    page = browser.new_page(viewport={'width': 1280, 'height': 720})
                    page.goto(proj.url, timeout=15000, wait_until='networkidle')
                    page.wait_for_timeout(1000)  # Extra wait for JS rendering

                    filename = f'{proj.name}.png'
                    filepath = SCREENSHOTS_DIR / filename
                    page.screenshot(path=str(filepath))
                    page.close()

                    proj.screenshot = f'screenshots/{filename}'
                    proj.save(update_fields=['screenshot'])
                    self.stdout.write(self.style.SUCCESS(f'  -> {filepath}'))
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f'  Failed: {e}'))

            browser.close()

        self.stdout.write(self.style.SUCCESS('\nScreenshot capture complete.'))
