"""
Bulk sync existing prompts to Google Sheets.

Usage:
  python3 manage.py cpm_sheets_sync                    # Sync all users
  python3 manage.py cpm_sheets_sync --user betona1     # Sync specific user
  python3 manage.py cpm_sheets_sync --days 30          # Last 30 days only
  python3 manage.py cpm_sheets_sync --project cpm      # Specific project only
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta


class Command(BaseCommand):
    help = 'Bulk sync existing prompts to Google Sheets'

    def add_arguments(self, parser):
        parser.add_argument('--user', type=str, help='GitHub username to sync')
        parser.add_argument('--days', type=int, default=0, help='Only sync last N days (0=all)')
        parser.add_argument('--project', type=str, help='Only sync specific project name')
        parser.add_argument('--dry-run', action='store_true', help='Show what would be synced without writing')

    def handle(self, *args, **options):
        from core.models import UserProfile, Prompt
        from core.google_sheets import is_available, append_prompt_to_sheet, get_service_email

        if not is_available():
            self.stderr.write(self.style.ERROR(
                'Google Sheets not configured. Set GOOGLE_SHEETS_CREDENTIALS environment variable.'
            ))
            return

        self.stdout.write(f'Service account: {get_service_email()}')

        # Find users with Google Sheets enabled
        profiles = UserProfile.objects.filter(
            google_sheet_enabled=True,
        ).exclude(google_sheet_url='')

        if options['user']:
            profiles = profiles.filter(github_username=options['user'])

        if not profiles.exists():
            self.stderr.write(self.style.WARNING('No users with Google Sheets enabled found.'))
            return

        for profile in profiles:
            self.stdout.write(self.style.SUCCESS(
                f'\n=== {profile.github_username} === Sheet: {profile.google_sheet_url}'
            ))

            prompts = Prompt.objects.filter(
                project__owner=profile.user
            ).select_related('project').order_by('created_at')

            if options['days']:
                cutoff = timezone.now() - timedelta(days=options['days'])
                prompts = prompts.filter(created_at__gte=cutoff)

            if options['project']:
                prompts = prompts.filter(project__name=options['project'])

            total = prompts.count()
            self.stdout.write(f'Prompts to sync: {total}')

            if options['dry_run']:
                for p in prompts[:5]:
                    self.stdout.write(f'  [{p.id}] {p.project.name}: {p.content[:60]}...')
                if total > 5:
                    self.stdout.write(f'  ... and {total - 5} more')
                continue

            success = 0
            errors = 0
            for i, prompt in enumerate(prompts, 1):
                try:
                    result = append_prompt_to_sheet(profile, prompt)
                    if result:
                        success += 1
                    else:
                        errors += 1
                except Exception as e:
                    errors += 1
                    if errors <= 3:
                        self.stderr.write(self.style.ERROR(f'  Error: {e}'))
                    elif errors == 4:
                        self.stderr.write(self.style.ERROR('  (suppressing further errors)'))

                if i % 50 == 0:
                    self.stdout.write(f'  Progress: {i}/{total}')

            self.stdout.write(self.style.SUCCESS(
                f'  Done: {success} synced, {errors} errors'
            ))
