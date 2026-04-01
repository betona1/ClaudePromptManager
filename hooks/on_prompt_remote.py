#!/usr/bin/env python3
"""
CPM Remote Hook: UserPromptSubmit
Sends prompt to remote CPM server via HTTP API.

Windows Setup:
1. Copy this file to a known path (e.g. C:\\cpm\\hooks\\on_prompt_remote.py)
2. Edit CPM_SERVER below to your server address
3. Configure Claude Code hooks (~/.claude/settings.json):
   {
     "hooks": {
       "UserPromptSubmit": [{
         "type": "command",
         "command": "python C:\\cpm\\hooks\\on_prompt_remote.py"
       }]
     }
   }
"""
import sys
import json
import os
import socket

# ============================================================
# CONFIGURATION - Edit this to your CPM server address
# ============================================================
CPM_SERVER = os.environ.get('CPM_SERVER', 'http://localhost:9200')
# ============================================================


def main():
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

    try:
        import urllib.request
        payload = json.dumps({
            'prompt': prompt_text,
            'session_id': session_id,
            'cwd': cwd,
            'hostname': socket.gethostname(),
        }, ensure_ascii=False).encode('utf-8')

        req = urllib.request.Request(
            f'{CPM_SERVER}/api/hook/prompt/',
            data=payload,
            headers={'Content-Type': 'application/json'},
            method='POST',
        )
        urllib.request.urlopen(req, timeout=5)
    except Exception:
        pass  # Never block Claude Code

    print('{}')


if __name__ == '__main__':
    main()
