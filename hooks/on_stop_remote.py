#!/usr/bin/env python3
"""
CPM Remote Hook: Stop
Sends response summary to remote CPM server via HTTP API.

Windows Setup:
1. Copy this file to a known path (e.g. C:\\cpm\\hooks\\on_stop_remote.py)
2. Edit CPM_SERVER below to your server address
3. Configure Claude Code hooks (~/.claude/settings.json):
   {
     "hooks": {
       "Stop": [{
         "type": "command",
         "command": "python C:\\cpm\\hooks\\on_stop_remote.py"
       }]
     }
   }
"""
import sys
import json
import os

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

    # Prevent infinite loops
    if data.get('stop_hook_active'):
        print('{}')
        return

    session_id = data.get('session_id', '')
    last_message = data.get('last_assistant_message', '')

    if not session_id or not last_message:
        print('{}')
        return

    try:
        import urllib.request
        payload = json.dumps({
            'session_id': session_id,
            'response': last_message[:500],
        }, ensure_ascii=False).encode('utf-8')

        req = urllib.request.Request(
            f'{CPM_SERVER}/api/hook/stop/',
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
