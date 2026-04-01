"""
CPM Telegram Bot — long-polling command.

Listens for messages on all active TelegramBot records.
Responds to "전체" / "all" with a dashboard summary.

Usage:
    python manage.py cpm_telegram
    python manage.py cpm_telegram --timeout 60
"""
import json
import signal
import time
import urllib.request
import urllib.error
from datetime import date

from django.core.management.base import BaseCommand
from django.db.models import Count, Q, Max, Min, Sum

from core.models import Project, Prompt, TelegramBot


# Commands that trigger dashboard
DASHBOARD_CMDS = {'전체', 'all', '/all', '/dashboard'}
HELP_CMDS = {'/start', '/help'}


def _format_tokens(n):
    if n >= 1_000_000:
        return f'{n / 1_000_000:.1f}M'
    elif n >= 1_000:
        return f'{n / 1_000:.1f}K'
    return str(n)


class Command(BaseCommand):
    help = 'Run Telegram bot long-polling for CPM dashboard commands'

    def add_arguments(self, parser):
        parser.add_argument(
            '--timeout', type=int, default=30,
            help='Long-polling timeout in seconds (default: 30)',
        )

    def handle(self, *args, **options):
        self._shutdown = False
        poll_timeout = options['timeout']

        def on_signal(signum, frame):
            self.stdout.write('\nShutting down...')
            self._shutdown = True

        signal.signal(signal.SIGINT, on_signal)
        signal.signal(signal.SIGTERM, on_signal)

        self.stdout.write(self.style.SUCCESS('Starting CPM Telegram Bot...'))
        self.stdout.write(f'Poll timeout: {poll_timeout}s  |  Press Ctrl+C to stop.\n')

        offsets = {}  # bot_id -> update offset

        while not self._shutdown:
            bots = list(TelegramBot.objects.filter(is_active=True))
            if not bots:
                self.stdout.write('No active bots. Waiting 10s...')
                time.sleep(10)
                continue

            for bot in bots:
                if self._shutdown:
                    break

                offset = offsets.get(bot.id, 0)
                try:
                    result = self._telegram_request('getUpdates', bot.bot_token, {
                        'offset': offset,
                        'timeout': poll_timeout,
                        'allowed_updates': ['message'],
                    }, timeout=poll_timeout + 5)
                except urllib.error.HTTPError as e:
                    if e.code == 409:
                        self.stderr.write(
                            self.style.WARNING(
                                f'@{bot.bot_username}: 409 Conflict — '
                                'another polling instance running?'
                            )
                        )
                    else:
                        self.stderr.write(f'@{bot.bot_username}: HTTP {e.code}')
                    time.sleep(5)
                    continue
                except Exception as e:
                    self.stderr.write(f'@{bot.bot_username}: {e}')
                    time.sleep(5)
                    continue

                updates = result.get('result', [])
                for update in updates:
                    update_id = update.get('update_id', 0)
                    offsets[bot.id] = max(offsets.get(bot.id, 0), update_id + 1)
                    self._handle_update(bot, update)

        self.stdout.write(self.style.SUCCESS('Telegram bot stopped.'))

    # ── Telegram API ──────────────────────────────────────

    def _telegram_request(self, method, token, data=None, timeout=10):
        url = f'https://api.telegram.org/bot{token}/{method}'
        if data:
            payload = json.dumps(data).encode('utf-8')
            req = urllib.request.Request(url, data=payload, headers={
                'Content-Type': 'application/json',
            })
        else:
            req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())

    def _send_message(self, token, chat_id, text):
        MAX_LEN = 4096
        chunks = self._split_message(text, MAX_LEN)
        for chunk in chunks:
            try:
                self._telegram_request('sendMessage', token, {
                    'chat_id': chat_id,
                    'text': chunk,
                    'parse_mode': 'HTML',
                    'disable_web_page_preview': True,
                })
            except Exception as e:
                self.stderr.write(f'Send failed to {chat_id}: {e}')

    def _split_message(self, text, max_len):
        if len(text) <= max_len:
            return [text]
        chunks = []
        current = ''
        for line in text.split('\n'):
            if current and len(current) + len(line) + 1 > max_len - 50:
                chunks.append(current)
                current = line
            else:
                current += ('\n' if current else '') + line
        if current:
            chunks.append(current)
        return chunks

    # ── Update Handler ────────────────────────────────────

    def _handle_update(self, bot, update):
        message = update.get('message') or update.get('edited_message')
        if not message:
            return

        text = (message.get('text') or '').strip()
        chat_id = message.get('chat', {}).get('id')
        if not chat_id:
            return

        cmd = text.lower()
        ts = time.strftime('%H:%M:%S')

        if cmd in DASHBOARD_CMDS:
            self.stdout.write(f'[{ts}] @{bot.bot_username}: "{text}" from {chat_id}')
            html = self._build_dashboard()
            self._send_message(bot.bot_token, chat_id, html)
            self.stdout.write(f'[{ts}] @{bot.bot_username}: Dashboard sent ({len(html)} chars)')

        elif cmd in HELP_CMDS:
            self.stdout.write(f'[{ts}] @{bot.bot_username}: "{text}" from {chat_id}')
            self._send_message(bot.bot_token, chat_id, self._help_text())

    # ── Dashboard Builder ─────────────────────────────────

    def _build_dashboard(self):
        today = date.today()

        projects = Project.objects.prefetch_related('todos').annotate(
            prompt_count=Count('prompts', distinct=True),
            latest_at=Max('prompts__created_at'),
            todo_total=Count('todos', distinct=True),
            todo_completed=Count('todos', filter=Q(todos__is_completed=True), distinct=True),
        ).order_by('-favorited', '-latest_at')

        total_prompts = Prompt.objects.count()
        today_count = Prompt.objects.filter(created_at__date=today).count()
        total_days = len(Prompt.objects.dates('created_at', 'day'))

        token_agg = Project.objects.aggregate(
            total_in=Sum('total_input_tokens'),
            total_out=Sum('total_output_tokens'),
        )
        total_tokens = (token_agg['total_in'] or 0) + (token_agg['total_out'] or 0)

        lines = []
        lines.append(f'\U0001f4ca <b>CPM Dashboard</b>  ({today.strftime("%m/%d")})')
        lines.append(
            f'Today: <b>{today_count}</b> | '
            f'Total: <b>{total_prompts:,}</b> | '
            f'Days: <b>{total_days}</b> | '
            f'Tokens: <b>{_format_tokens(total_tokens)}</b>'
        )
        lines.append('')

        if not projects.exists():
            lines.append('No projects yet.')
            return '\n'.join(lines)

        for p in projects:
            p_dates = Prompt.objects.filter(project_id=p.id).dates('created_at', 'day')
            working_days = len(p_dates)
            p_today = Prompt.objects.filter(project_id=p.id, created_at__date=today).count()
            p_tokens = p.total_input_tokens + p.total_output_tokens

            fav = '\u2764\ufe0f ' if p.favorited else ''
            today_badge = f' \U0001f525{p_today}' if p_today else ''
            lines.append(f'{fav}<b>{_esc(p.name)}</b>  [{p.prompt_count}]{today_badge}')

            details = f'  Days: {working_days}'
            if p_tokens:
                details += f' | Tokens: {_format_tokens(p_tokens)}'
            lines.append(details)

            if p.todo_total:
                done = p.todo_completed
                total = p.todo_total
                bar = _progress_bar(done, total)
                lines.append(f'  Goals: {bar} {done}/{total}')

            lines.append('')

        return '\n'.join(lines)

    def _help_text(self):
        return (
            '<b>CPM Telegram Bot</b>\n\n'
            'Commands:\n'
            '  <b>전체</b> or <b>all</b> — Dashboard summary\n'
            '  <b>/help</b> — This message'
        )


def _esc(text):
    """Escape HTML special characters for Telegram."""
    return (
        text.replace('&', '&amp;')
        .replace('<', '&lt;')
        .replace('>', '&gt;')
    )


def _progress_bar(done, total):
    """Simple text progress bar."""
    if total == 0:
        return ''
    filled = round(done / total * 5)
    return '\u2588' * filled + '\u2591' * (5 - filled)
