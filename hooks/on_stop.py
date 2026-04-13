#!/usr/bin/env python3
"""
CPM Hook: Stop
Claude Code calls this when it finishes responding.

stdin JSON:
{
  "session_id": "...",
  "transcript_path": "...",
  "cwd": "...",
  "hook_event_name": "Stop",
  "stop_hook_active": true/false,
  "last_assistant_message": "..."
}

stdout: {} (pass through)
"""
import sys
import json
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from shared import get_db, ensure_tables, redis_publish, remote_post, google_sheets_update


def truncate(text: str, max_len: int = 500) -> str:
    if not text:
        return ''
    return text[:max_len-3] + '...' if len(text) > max_len else text


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

    prompt_id = None
    project_id = None

    try:
        conn = get_db()
        ensure_tables(conn)

        # Find the most recent wip prompt for this session
        row = conn.execute(
            """SELECT id, project_id FROM prompts
               WHERE session_id=? AND status='wip'
               ORDER BY created_at DESC LIMIT 1""",
            (session_id,)
        ).fetchone()

        if row:
            prompt_id = row['id']
            project_id = row['project_id']
            summary = truncate(last_message)
            conn.execute(
                """UPDATE prompts SET
                    response_summary=?,
                    status='success',
                    updated_at=datetime('now','localtime')
                   WHERE id=?""",
                (summary, prompt_id)
            )
            conn.commit()

            redis_publish('cpm:live', {
                'event': 'prompt_done',
                'prompt_id': prompt_id,
                'session_id': session_id,
                'response_summary': summary[:200],
            })

        conn.close()
    except Exception:
        pass  # Never block Claude Code

    # Sync to remote server if configured (CPM_REMOTE_SERVER env)
    try:
        remote_post('hook/stop/', {
            'session_id': session_id,
            'response': truncate(last_message),
        })
    except Exception:
        pass

    # Always output valid JSON first
    print('{}')

    # Google Sheets update (fire-and-forget, after stdout)
    if prompt_id and project_id:
        try:
            import threading
            threading.Thread(
                target=google_sheets_update,
                args=(project_id, prompt_id, truncate(last_message), 'success'),
                daemon=True,
            ).start()
        except Exception:
            pass


if __name__ == '__main__':
    main()
