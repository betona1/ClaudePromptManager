"""
cpm_tokens: Calculate token usage from Claude Code session files.
Usage: python manage.py cpm_tokens [--sessions-dir PATH]
"""
import json
from pathlib import Path
from collections import defaultdict
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Calculate and update token usage from Claude Code session files'

    def add_arguments(self, parser):
        parser.add_argument('--sessions-dir', type=str, default=None,
                          help='Path to projects directory (default: ~/.claude/projects/)')

    def handle(self, *args, **options):
        from core.models import Project

        dirs = []
        # Local sessions
        local_dir = Path.home() / '.claude' / 'projects'
        if local_dir.exists():
            dirs.append(local_dir)

        # Additional dir
        extra = options.get('sessions_dir')
        if extra:
            p = Path(extra)
            if p.exists():
                dirs.append(p)

        # Also check /tmp for imported session dirs
        for d in Path('/tmp').glob('cpm_import_*/projects'):
            if d.exists():
                dirs.append(d)

        # Aggregate tokens per project name
        project_tokens = defaultdict(lambda: {
            'input': 0, 'output': 0, 'cache_read': 0, 'cache_create': 0
        })

        for base_dir in dirs:
            self.stdout.write(f'Scanning {base_dir}...')
            for pdir in base_dir.iterdir():
                if not pdir.is_dir() or pdir.name in ('memory',):
                    continue

                # Derive project name from directory
                parts = pdir.name.lstrip('-').replace('/', '-').split('-')
                pname = parts[-1] if parts else pdir.name

                for sf in pdir.glob('*.jsonl'):
                    if sf.name == 'memory.jsonl':
                        continue
                    self._scan_session_file(sf, pname, project_tokens)

        # Update DB
        for pname, tokens in project_tokens.items():
            try:
                proj = Project.objects.get(name=pname)
                proj.total_input_tokens = tokens['input']
                proj.total_output_tokens = tokens['output']
                proj.total_cache_read_tokens = tokens['cache_read']
                proj.total_cache_create_tokens = tokens['cache_create']
                proj.save(update_fields=[
                    'total_input_tokens', 'total_output_tokens',
                    'total_cache_read_tokens', 'total_cache_create_tokens'
                ])
                total = tokens['input'] + tokens['output']
                self.stdout.write(f'  {pname}: {total:,} tokens (in={tokens["input"]:,} out={tokens["output"]:,})')
            except Project.DoesNotExist:
                self.stdout.write(self.style.WARNING(f'  {pname}: project not found in DB, skipped'))

        self.stdout.write(self.style.SUCCESS('\nToken calculation complete.'))

    def _scan_session_file(self, sf, pname, project_tokens):
        try:
            with open(sf, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    if entry.get('type') != 'assistant':
                        continue

                    usage = entry.get('message', {}).get('usage', {})
                    if not usage:
                        continue

                    project_tokens[pname]['input'] += usage.get('input_tokens', 0)
                    project_tokens[pname]['output'] += usage.get('output_tokens', 0)
                    project_tokens[pname]['cache_read'] += usage.get('cache_read_input_tokens', 0)
                    project_tokens[pname]['cache_create'] += usage.get('cache_creation_input_tokens', 0)
        except Exception:
            pass
