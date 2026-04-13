#!/usr/bin/env python3
"""
CPM Remote Hook: Sends prompts to CPM server via HTTP API.
Install this on remote machines (MacBook, other servers).

Usage in ~/.claude/settings.json:
{
  "hooks": {
    "UserPromptSubmit": [{
      "matcher": "",
      "hooks": [{"type": "command", "command": "python3 /path/to/remote_hook.py prompt"}]
    }],
    "Stop": [{
      "matcher": "",
      "hooks": [{"type": "command", "command": "python3 /path/to/remote_hook.py stop"}]
    }]
  }
}
"""
import sys
import json
import os
import socket
import urllib.request
import urllib.error

# === CONFIG ===
CPM_SERVER = os.environ.get('CPM_SERVER', 'http://localhost:9200')
CPM_API_TOKEN = os.environ.get('CPM_API_TOKEN', '')
# ==============

HOSTNAME = socket.gethostname()


def _detect_tmux_session():
    """Detect tmux/screen session name. Returns None when not in a multiplexer."""
    try:
        if os.environ.get('TMUX'):
            try:
                import subprocess
                out = subprocess.check_output(
                    ['tmux', 'display-message', '-p', '#S'],
                    stderr=subprocess.DEVNULL, timeout=2
                )
                name = out.decode('utf-8', errors='replace').strip()
                if name:
                    return f'tmux:{name}'
            except Exception:
                pass
            pane = os.environ.get('TMUX_PANE')
            if pane:
                return f'tmux-pane:{pane}'
        sty = os.environ.get('STY')
        if sty:
            return f'screen:{sty}'
    except Exception:
        pass
    return None


def send_prompt():
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        print('{}')
        return

    prompt_text = data.get('prompt', '').strip()
    session_id = data.get('session_id', '')
    cwd = data.get('cwd', os.getcwd())

    if not prompt_text:
        print('{}')
        return

    payload = json.dumps({
        'prompt': prompt_text,
        'session_id': session_id,
        'cwd': cwd,
        'hostname': HOSTNAME,
        'tmux_session': _detect_tmux_session(),
    }).encode('utf-8')

    try:
        headers = {'Content-Type': 'application/json'}
        if CPM_API_TOKEN:
            headers['Authorization'] = f'Bearer {CPM_API_TOKEN}'
        req = urllib.request.Request(
            f"{CPM_SERVER}/api/hook/prompt/",
            data=payload,
            headers=headers,
            method='POST'
        )
        urllib.request.urlopen(req, timeout=5)
    except Exception:
        pass  # Never block Claude Code

    print('{}')


def send_stop():
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        print('{}')
        return

    session_id = data.get('session_id', '')
    response_text = ''

    # Try to get last assistant message
    last_msg = data.get('last_assistant_message', '')
    if isinstance(last_msg, str):
        response_text = last_msg[:500]
    elif isinstance(last_msg, dict):
        content = last_msg.get('content', '')
        if isinstance(content, list):
            texts = [p.get('text', '') for p in content if isinstance(p, dict) and p.get('type') == 'text']
            response_text = '\n'.join(texts)[:500]
        elif isinstance(content, str):
            response_text = content[:500]

    if not session_id:
        print('{}')
        return

    payload = json.dumps({
        'session_id': session_id,
        'response': response_text,
        'hostname': HOSTNAME,
    }).encode('utf-8')

    try:
        headers = {'Content-Type': 'application/json'}
        if CPM_API_TOKEN:
            headers['Authorization'] = f'Bearer {CPM_API_TOKEN}'
        req = urllib.request.Request(
            f"{CPM_SERVER}/api/hook/stop/",
            data=payload,
            headers=headers,
            method='POST'
        )
        urllib.request.urlopen(req, timeout=5)
    except Exception:
        pass

    print('{}')


if __name__ == '__main__':
    action = sys.argv[1] if len(sys.argv) > 1 else 'prompt'
    if action == 'stop':
        send_stop()
    else:
        send_prompt()
