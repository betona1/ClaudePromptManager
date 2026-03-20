"""
cpm_import: Import prompts from Claude Code history and session files.
Usage: python manage.py cpm_import [--history] [--sessions] [--all]
"""
import json
import os
from pathlib import Path
from datetime import datetime
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Import prompts from Claude Code history.jsonl and session files'

    def add_arguments(self, parser):
        parser.add_argument('--history', action='store_true',
                          help='Import from ~/.claude/history.jsonl')
        parser.add_argument('--sessions', action='store_true',
                          help='Import from ~/.claude/projects/*/session.jsonl files')
        parser.add_argument('--all', action='store_true',
                          help='Import both history and sessions')
        parser.add_argument('--file', type=str, default=None,
                          help='Path to history.jsonl file (overrides default ~/.claude/history.jsonl)')
        parser.add_argument('--sessions-dir', type=str, default=None,
                          help='Path to projects directory (overrides default ~/.claude/projects/)')
        parser.add_argument('--label', type=str, default=None,
                          help='Label for imported data (e.g. server name)')

    def handle(self, *args, **options):
        if not any([options['history'], options['sessions'], options['all'], options['file'], options['sessions_dir']]):
            options['all'] = True  # Default: import everything

        label = options.get('label') or ''
        total = 0

        history_file = options.get('file')
        sessions_dir = options.get('sessions_dir')

        if history_file or options['history'] or options['all']:
            h_path = Path(history_file) if history_file else None
            total += self._import_history(history_path=h_path, label=label)
        if sessions_dir or options['sessions'] or options['all']:
            s_path = Path(sessions_dir) if sessions_dir else None
            total += self._import_sessions(projects_dir=s_path, label=label)

        self.stdout.write(self.style.SUCCESS(f'\nTotal imported: {total} prompts'))

    def _import_history(self, history_path=None, label='') -> int:
        """Import from history.jsonl file."""
        if history_path is None:
            history_path = Path.home() / '.claude' / 'history.jsonl'
        if not history_path.exists():
            self.stdout.write(self.style.WARNING(f'Not found: {history_path}'))
            return 0

        self.stdout.write(f'Importing from {history_path}...')

        from core.models import Project, Prompt, Session
        imported = 0
        skipped = 0
        project_cache = {}

        with open(history_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue

                prompt_text = entry.get('display', '').strip()
                if not prompt_text:
                    continue
                # Skip system noise
                if prompt_text.startswith('<task-notification>') or prompt_text.startswith('<system-reminder>'):
                    continue
                if prompt_text.startswith('<') and '>' in prompt_text[:50]:
                    continue

                project_path = entry.get('project', '')
                session_id = entry.get('sessionId', '')
                timestamp = entry.get('timestamp')

                # Get or create project
                if project_path not in project_cache:
                    project_name = Path(project_path).name if project_path else 'unknown'
                    proj, _ = Project.objects.get_or_create(
                        name=project_name,
                        defaults={
                            'path': project_path,
                            'description': f'Imported from history.jsonl'
                        }
                    )
                    # Update path if project already existed without one
                    if not proj.path and project_path:
                        proj.path = project_path
                        proj.save(update_fields=['path'])
                    project_cache[project_path] = proj

                proj = project_cache[project_path]

                # Convert timestamp (ms epoch) to datetime
                created_at = None
                if timestamp:
                    try:
                        created_at = datetime.fromtimestamp(timestamp / 1000)
                    except (ValueError, OSError, TypeError):
                        created_at = None

                # Skip duplicates: same content + session + similar time
                existing = Prompt.objects.filter(
                    content=prompt_text,
                    session_id=session_id,
                    source='import'
                ).exists()
                if existing:
                    skipped += 1
                    continue

                prompt = Prompt(
                    project=proj,
                    content=prompt_text,
                    status='success',
                    session_id=session_id,
                    source='import',
                )
                prompt.save()
                # auto_now_add ignores manual values, so override with raw UPDATE
                if created_at:
                    Prompt.objects.filter(id=prompt.id).update(
                        created_at=created_at, updated_at=created_at
                    )
                imported += 1

                # Ensure session record
                if session_id:
                    Session.objects.get_or_create(
                        id=session_id,
                        defaults={
                            'project': proj,
                            'project_path': project_path,
                            'started_at': created_at,
                        }
                    )

        self.stdout.write(f'  history.jsonl: {imported} imported, {skipped} skipped (duplicates)')
        return imported

    def _import_sessions(self, projects_dir=None, label='') -> int:
        """Import from projects/*/session.jsonl files."""
        if projects_dir is None:
            projects_dir = Path.home() / '.claude' / 'projects'
        if not projects_dir.exists():
            self.stdout.write(self.style.WARNING(f'Not found: {projects_dir}'))
            return 0

        self.stdout.write(f'Importing from {projects_dir}...')

        from core.models import Project, Prompt, Session
        imported = 0
        skipped = 0

        for project_dir in projects_dir.iterdir():
            if not project_dir.is_dir():
                continue

            # Decode project path from directory name
            dir_name = project_dir.name
            if dir_name == 'memory':
                continue
            project_path = dir_name.replace('-', '/', 1)  # first dash is leading /
            # Fix: directory names encode paths as dash-separated
            project_path = '/' + dir_name[1:].replace('-', '/')

            for session_file in project_dir.glob('*.jsonl'):
                session_id = session_file.stem
                if not session_id or session_id == 'memory':
                    continue

                # Check if already imported
                existing_count = Prompt.objects.filter(
                    session_id=session_id, source='import'
                ).count()

                user_messages = self._extract_user_messages(session_file)
                if existing_count >= len(user_messages):
                    continue  # Already fully imported

                # Get or create project
                project_name = Path(project_path).name if project_path else dir_name
                proj, _ = Project.objects.get_or_create(
                    name=project_name,
                    defaults={
                        'path': project_path,
                        'description': f'Imported from session files'
                    }
                )
                if not proj.path and project_path:
                    proj.path = project_path
                    proj.save(update_fields=['path'])

                for msg in user_messages:
                    content = msg.get('content', '')
                    if not content:
                        continue
                    # Skip system noise
                    if content.startswith('<task-notification>') or content.startswith('<system-reminder>'):
                        continue
                    if content.startswith('<') and '>' in content[:50]:
                        continue

                    # Skip duplicates
                    if Prompt.objects.filter(
                        content=content,
                        session_id=session_id,
                        source='import'
                    ).exists():
                        skipped += 1
                        continue

                    created_at = None
                    ts = msg.get('timestamp')
                    if ts:
                        try:
                            created_at = datetime.fromisoformat(ts.replace('Z', '+00:00')).replace(tzinfo=None)
                        except (ValueError, AttributeError):
                            pass

                    # Look for the assistant response
                    response = msg.get('response_summary', '')

                    prompt = Prompt(
                        project=proj,
                        content=content,
                        response_summary=response if response else None,
                        status='success',
                        session_id=session_id,
                        source='import',
                    )
                    prompt.save()
                    if created_at:
                        Prompt.objects.filter(id=prompt.id).update(
                            created_at=created_at, updated_at=created_at
                        )
                    imported += 1

                # Ensure session record
                if user_messages:
                    first_ts = user_messages[0].get('timestamp')
                    started = None
                    if first_ts:
                        try:
                            started = datetime.fromisoformat(first_ts.replace('Z', '+00:00')).replace(tzinfo=None)
                        except (ValueError, AttributeError):
                            pass
                    Session.objects.update_or_create(
                        id=session_id,
                        defaults={
                            'project': proj,
                            'project_path': project_path,
                            'started_at': started,
                            'message_count': len(user_messages),
                        }
                    )

        self.stdout.write(f'  sessions: {imported} imported, {skipped} skipped')
        return imported

    def _extract_user_messages(self, session_file: Path) -> list:
        """Extract user prompt messages from a session JSONL file."""
        messages = []
        entries = []

        with open(session_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    entries.append(entry)
                except json.JSONDecodeError:
                    continue

        # Build a map of uuid -> entry for linking
        uuid_map = {}
        for entry in entries:
            uid = entry.get('uuid')
            if uid:
                uuid_map[uid] = entry

        # Extract user messages (not tool results)
        for entry in entries:
            if entry.get('type') != 'user':
                continue
            if entry.get('toolUseResult'):
                continue  # Skip tool use results

            msg_data = entry.get('message', {})
            if isinstance(msg_data, dict):
                content_parts = msg_data.get('content', [])
                if isinstance(content_parts, list):
                    text_parts = []
                    for part in content_parts:
                        if isinstance(part, dict) and part.get('type') == 'text':
                            text_parts.append(part.get('text', ''))
                        elif isinstance(part, str):
                            text_parts.append(part)
                    content = '\n'.join(text_parts).strip()
                elif isinstance(content_parts, str):
                    content = content_parts.strip()
                else:
                    content = ''
            else:
                content = str(msg_data).strip()

            if not content:
                continue

            # Find the next assistant response
            response_summary = ''
            parent_uuid = entry.get('uuid')
            if parent_uuid:
                for other in entries:
                    if other.get('type') == 'assistant' and other.get('parentUuid') == parent_uuid:
                        resp_msg = other.get('message', {})
                        if isinstance(resp_msg, dict):
                            resp_parts = resp_msg.get('content', [])
                            if isinstance(resp_parts, list):
                                texts = []
                                for p in resp_parts:
                                    if isinstance(p, dict) and p.get('type') == 'text':
                                        texts.append(p.get('text', ''))
                                response_summary = '\n'.join(texts).strip()[:500]
                        break

            messages.append({
                'content': content,
                'timestamp': entry.get('timestamp', ''),
                'response_summary': response_summary,
            })

        return messages
