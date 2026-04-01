"""
cpm_setup: Install Claude Code hooks and initialize DB.
Usage: python manage.py cpm_setup
"""
import json
from pathlib import Path
from django.core.management.base import BaseCommand
from django.conf import settings


class Command(BaseCommand):
    help = 'Install Claude Code hooks and initialize CPM database'

    def handle(self, *args, **options):
        self._install_hooks()
        self._run_migrations()
        self.stdout.write(self.style.SUCCESS('\nCPM setup complete!'))
        self.stdout.write('  Hooks installed to ~/.claude/settings.json')
        self.stdout.write('  DB ready at ' + str(settings.DATABASES['default']['NAME']))
        self.stdout.write('\nNext steps:')
        self.stdout.write('  1. Start Claude Code in any project — prompts auto-captured')
        self.stdout.write('  2. Run: python manage.py cpm_web  (start web UI)')
        self.stdout.write('  3. Open: http://localhost:9200')

    def _install_hooks(self):
        settings_path = Path.home() / '.claude' / 'settings.json'
        settings_path.parent.mkdir(parents=True, exist_ok=True)

        # Load existing settings
        if settings_path.exists():
            with open(settings_path, 'r') as f:
                try:
                    data = json.load(f)
                except json.JSONDecodeError:
                    data = {}
        else:
            data = {}

        hooks_dir = str(settings.CPM_HOOKS_DIR)
        on_prompt_cmd = f"python3 {hooks_dir}/on_prompt.py"
        on_stop_cmd = f"python3 {hooks_dir}/on_stop.py"

        # Build hooks config
        hooks = data.get('hooks', {})

        # UserPromptSubmit
        prompt_hooks = hooks.get('UserPromptSubmit', [])
        # Remove existing CPM hooks
        prompt_hooks = [h for h in prompt_hooks if not self._is_cpm_hook(h, hooks_dir)]
        prompt_hooks.append({
            'matcher': '',
            'hooks': [{
                'type': 'command',
                'command': on_prompt_cmd,
            }]
        })
        hooks['UserPromptSubmit'] = prompt_hooks

        # Stop
        stop_hooks = hooks.get('Stop', [])
        stop_hooks = [h for h in stop_hooks if not self._is_cpm_hook(h, hooks_dir)]
        stop_hooks.append({
            'matcher': '',
            'hooks': [{
                'type': 'command',
                'command': on_stop_cmd,
            }]
        })
        hooks['Stop'] = stop_hooks

        data['hooks'] = hooks

        with open(settings_path, 'w') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        self.stdout.write(self.style.SUCCESS(f'Hooks installed: {settings_path}'))

    def _is_cpm_hook(self, hook_entry: dict, hooks_dir: str) -> bool:
        """Check if a hook entry belongs to CPM."""
        for h in hook_entry.get('hooks', []):
            cmd = h.get('command', '')
            if hooks_dir in cmd:
                return True
        return False

    def _run_migrations(self):
        from django.core.management import call_command
        call_command('migrate', verbosity=0)
        self.stdout.write(self.style.SUCCESS('Database migrated'))
