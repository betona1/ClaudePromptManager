"""
Federation management command.

Usage:
    python manage.py cpm_federation init --name myserver --url https://cpm.example.com
    python manage.py cpm_federation status
    python manage.py cpm_federation sync
"""
import json
import urllib.request
import urllib.error
from datetime import datetime

from django.core.management.base import BaseCommand

from core.models import (
    ServerIdentity, FederatedServer, FederatedSubscription,
    FederatedPrompt, FederatedUser, Project,
)
from core.federation_auth import sign_request


class Command(BaseCommand):
    help = 'Manage CPM Federation (init, status, sync)'

    def add_arguments(self, parser):
        parser.add_argument('action', choices=['init', 'status', 'sync'],
                            help='Action to perform')
        parser.add_argument('--name', type=str, help='Server name (for init)')
        parser.add_argument('--url', type=str, help='Server public URL (for init)')
        parser.add_argument('--description', type=str, default='', help='Server description')
        parser.add_argument('--contact', type=str, default='', help='Admin contact email')

    def handle(self, *args, **options):
        action = options['action']
        if action == 'init':
            self._init(options)
        elif action == 'status':
            self._status()
        elif action == 'sync':
            self._sync()

    def _init(self, options):
        name = options.get('name')
        url = options.get('url')

        if not name or not url:
            self.stderr.write(self.style.ERROR(
                'Usage: python manage.py cpm_federation init --name <name> --url <url>'
            ))
            return

        url = url.rstrip('/')
        identity, created = ServerIdentity.objects.update_or_create(
            defaults={
                'server_name': name,
                'server_url': url,
                'description': options.get('description', ''),
                'admin_contact': options.get('contact', ''),
            },
            server_name=name,
        )

        if created:
            self.stdout.write(self.style.SUCCESS(f'Server identity created: {name}'))
        else:
            self.stdout.write(self.style.SUCCESS(f'Server identity updated: {name}'))

        self.stdout.write(f'  Name: {identity.server_name}')
        self.stdout.write(f'  URL:  {identity.server_url}')
        self.stdout.write(f'  Well-known: {url}/.well-known/cpm-federation')

    def _status(self):
        identity = ServerIdentity.get_instance()
        if not identity:
            self.stderr.write(self.style.WARNING(
                'Federation not initialized. Run: python manage.py cpm_federation init --name <name> --url <url>'
            ))
            return

        self.stdout.write(self.style.SUCCESS('=== Federation Status ==='))
        self.stdout.write(f'Server: {identity.server_name}')
        self.stdout.write(f'URL:    {identity.server_url}')
        self.stdout.write('')

        servers = FederatedServer.objects.all()
        if servers:
            self.stdout.write(f'Peered Servers ({servers.count()}):')
            for s in servers:
                sync_str = s.last_sync_at.strftime('%Y-%m-%d %H:%M') if s.last_sync_at else 'never'
                self.stdout.write(f'  [{s.status}] {s.name or s.url} - last sync: {sync_str}, errors: {s.error_count}')
        else:
            self.stdout.write('No peered servers.')

        subs = FederatedSubscription.objects.filter(is_active=True).select_related('server')
        if subs:
            self.stdout.write(f'\nActive Subscriptions ({subs.count()}):')
            for sub in subs:
                prompt_count = FederatedPrompt.objects.filter(subscription=sub).count()
                self.stdout.write(
                    f'  {sub.remote_project_name}@{sub.server.name} '
                    f'- {prompt_count} prompts, cursor: {sub.last_prompt_id}'
                )
        else:
            self.stdout.write('\nNo active subscriptions.')

        total_fed_prompts = FederatedPrompt.objects.count()
        self.stdout.write(f'\nTotal federated prompts: {total_fed_prompts}')

    def _sync(self):
        """Pull-based sync: fetch new prompts from all active subscriptions."""
        identity = ServerIdentity.get_instance()
        if not identity:
            self.stderr.write(self.style.ERROR('Federation not initialized.'))
            return

        subs = FederatedSubscription.objects.filter(
            is_active=True, server__status='active',
        ).select_related('server')

        if not subs:
            self.stdout.write('No active subscriptions to sync.')
            return

        total_new = 0
        for sub in subs:
            server = sub.server
            self.stdout.write(f'Syncing {sub.remote_project_name}@{server.name}...', ending=' ')

            try:
                # Fetch new prompts after cursor
                url = (
                    f"{server.url}/api/federation/projects/"
                    f"{sub.remote_project_id}/prompts/"
                    f"?after={sub.last_prompt_id}&limit=100"
                )
                req = urllib.request.Request(url)
                resp = urllib.request.urlopen(req, timeout=15)
                data = json.loads(resp.read())

                prompts_data = data.get('prompts', [])
                created_count = 0

                for p in prompts_data:
                    remote_id = p.get('id')
                    if not remote_id:
                        continue

                    # Resolve remote user
                    remote_user = None
                    owner_name = p.get('owner', '')
                    if owner_name:
                        from urllib.parse import urlparse
                        domain = urlparse(server.url).hostname or server.url
                        fed_id = f"{owner_name}@{domain}"
                        remote_user, _ = FederatedUser.objects.get_or_create(
                            federated_id=fed_id,
                            defaults={'username': owner_name, 'server': server}
                        )

                    _, created = FederatedPrompt.objects.get_or_create(
                        subscription=sub,
                        remote_prompt_id=remote_id,
                        defaults={
                            'content': p.get('content', ''),
                            'response_summary': p.get('response_summary', ''),
                            'status': p.get('status', 'wip'),
                            'tag': p.get('tag', ''),
                            'remote_user': remote_user,
                            'remote_created_at': p.get('created_at', datetime.now().isoformat()),
                        }
                    )
                    if created:
                        created_count += 1

                # Update cursor
                if prompts_data:
                    max_id = max(p.get('id', 0) for p in prompts_data)
                    if max_id > sub.last_prompt_id:
                        sub.last_prompt_id = max_id
                        sub.save(update_fields=['last_prompt_id', 'updated_at'])

                server.error_count = 0
                server.last_sync_at = datetime.now()
                server.save(update_fields=['error_count', 'last_sync_at'])

                self.stdout.write(self.style.SUCCESS(f'{created_count} new prompts'))
                total_new += created_count

            except Exception as e:
                server.error_count += 1
                if server.error_count >= 5:
                    server.status = 'suspended'
                    self.stdout.write(self.style.ERROR(f'SUSPENDED (5+ errors)'))
                else:
                    self.stdout.write(self.style.ERROR(f'Error: {e}'))
                server.save(update_fields=['error_count', 'status'])

        self.stdout.write(self.style.SUCCESS(f'\nSync complete. {total_new} new prompts total.'))
