#!/usr/bin/env python3
"""
CPM Import: 윈도우(또는 Mac/Linux)의 기존 Claude Code 기록을 CPM 서버로 전송.
사용법: python import_history.py

자동으로 ~/.claude/projects/ 아래 세션 파일과 history.jsonl을 읽어서 서버에 전송합니다.
"""
import json
import os
import sys
import socket
from pathlib import Path
from datetime import datetime

# ============================================================
# CONFIGURATION
# ============================================================
CPM_SERVER = os.environ.get('CPM_SERVER', 'http://localhost:9200')
# ============================================================

HOSTNAME = socket.gethostname()


def api_post(endpoint, data):
    """POST JSON to CPM server."""
    import urllib.request
    payload = json.dumps(data, ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(
        f'{CPM_SERVER}{endpoint}',
        data=payload,
        headers={'Content-Type': 'application/json'},
        method='POST',
    )
    try:
        resp = urllib.request.urlopen(req, timeout=30)
        return json.loads(resp.read().decode('utf-8'))
    except Exception as e:
        return {'error': str(e)}


def get_claude_dir():
    """Find .claude directory."""
    home = Path.home()
    claude_dir = home / '.claude'
    if claude_dir.exists():
        return claude_dir
    # Windows AppData fallback
    appdata = os.environ.get('APPDATA', '')
    if appdata:
        alt = Path(appdata) / 'Claude' / 'claude-code'
        if alt.exists():
            return alt
    return claude_dir


def import_history_jsonl(claude_dir):
    """Import from history.jsonl."""
    history_file = claude_dir / 'history.jsonl'
    if not history_file.exists():
        print(f'  history.jsonl not found: {history_file}')
        return 0

    print(f'  Reading {history_file}...')
    imported = 0
    skipped = 0

    with open(history_file, 'r', encoding='utf-8') as f:
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
            if prompt_text.startswith('<') and '>' in prompt_text[:50]:
                continue

            project_path = entry.get('project', '')
            session_id = entry.get('sessionId', '')
            timestamp = entry.get('timestamp')

            created_at = None
            if timestamp:
                try:
                    created_at = datetime.fromtimestamp(timestamp / 1000).isoformat()
                except (ValueError, OSError, TypeError):
                    pass

            result = api_post('/api/hook/import/', {
                'prompt': prompt_text,
                'session_id': session_id,
                'cwd': project_path,
                'hostname': HOSTNAME,
                'created_at': created_at,
                'source': 'import',
            })

            if result.get('status') == 'ok':
                imported += 1
            elif result.get('status') == 'skipped':
                skipped += 1
            else:
                skipped += 1

            # Progress
            total = imported + skipped
            if total % 50 == 0:
                print(f'    ... {imported} imported, {skipped} skipped')

    print(f'  history.jsonl: {imported} imported, {skipped} skipped')
    return imported


def extract_user_messages(session_file):
    """Extract user messages from session JSONL."""
    entries = []
    with open(session_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    messages = []
    for entry in entries:
        if entry.get('type') != 'user':
            continue
        if entry.get('toolUseResult'):
            continue

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
        if content.startswith('<') and '>' in content[:50]:
            continue

        # Find assistant response
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


def import_sessions(claude_dir):
    """Import from projects/*/session.jsonl files."""
    projects_dir = claude_dir / 'projects'
    if not projects_dir.exists():
        print(f'  projects dir not found: {projects_dir}')
        return 0

    print(f'  Reading {projects_dir}...')
    imported = 0
    skipped = 0

    for project_dir in projects_dir.iterdir():
        if not project_dir.is_dir():
            continue
        dir_name = project_dir.name
        if dir_name == 'memory':
            continue

        # Decode project path from directory name
        project_path = '/' + dir_name[1:].replace('-', '/')
        # Windows paths: might start with C-Users-...
        if len(dir_name) > 2 and dir_name[1] == '-' and dir_name[0].isalpha():
            drive = dir_name[0].upper()
            rest = dir_name[2:].replace('-', '\\')
            project_path = f'{drive}:\\{rest}'

        for session_file in project_dir.glob('*.jsonl'):
            session_id = session_file.stem
            if not session_id or session_id == 'memory':
                continue

            messages = extract_user_messages(session_file)
            if not messages:
                continue

            project_name = Path(project_path).name

            for msg in messages:
                created_at = None
                ts = msg.get('timestamp')
                if ts:
                    try:
                        created_at = datetime.fromisoformat(
                            ts.replace('Z', '+00:00')
                        ).replace(tzinfo=None).isoformat()
                    except (ValueError, AttributeError):
                        pass

                result = api_post('/api/hook/import/', {
                    'prompt': msg['content'],
                    'response': msg.get('response_summary', ''),
                    'session_id': session_id,
                    'cwd': project_path,
                    'hostname': HOSTNAME,
                    'created_at': created_at,
                    'source': 'import',
                })

                if result.get('status') == 'ok':
                    imported += 1
                elif result.get('status') == 'skipped':
                    skipped += 1
                else:
                    skipped += 1

        total = imported + skipped
        if total % 50 == 0 and total > 0:
            print(f'    ... {imported} imported, {skipped} skipped')

    print(f'  sessions: {imported} imported, {skipped} skipped')
    return imported


def main():
    print(f'CPM Import — sending to {CPM_SERVER}')
    print(f'Hostname: {HOSTNAME}')
    print()

    # Test connection
    result = api_post('/api/hook/prompt/', {
        'prompt': '',
        'session_id': '',
        'cwd': '',
        'hostname': HOSTNAME,
    })
    if 'error' in result and 'Connection' in result['error']:
        print(f'ERROR: Cannot connect to {CPM_SERVER}')
        print(f'Check server address and firewall.')
        sys.exit(1)

    claude_dir = get_claude_dir()
    print(f'Claude dir: {claude_dir}')
    print()

    total = 0
    total += import_history_jsonl(claude_dir)
    total += import_sessions(claude_dir)

    print(f'\nDone! Total imported: {total} prompts')
    print(f'Check: {CPM_SERVER}')


if __name__ == '__main__':
    main()
