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
from shared import (get_db, ensure_tables, resolve_project_by_path,
                    redis_publish, remote_post, google_sheets_update,
                    google_sheets_append)


def truncate(text: str, max_len: int = 500) -> str:
    if not text:
        return ''
    return text[:max_len-3] + '...' if len(text) > max_len else text


def recover_queued_messages(conn, transcript_path, session_id, project_id):
    """Recover mid-turn user messages from transcript queue-operations.

    When a user sends messages while Claude is executing tools, they are
    recorded as type='queue-operation', operation='enqueue' in the transcript
    JSONL but do NOT trigger the UserPromptSubmit hook. This function finds
    those messages and inserts them into the DB.
    """
    if not transcript_path or not os.path.isfile(transcript_path):
        return []

    recovered = []
    try:
        queued_msgs = []
        with open(transcript_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    continue
                if (obj.get('type') == 'queue-operation'
                        and obj.get('operation') == 'enqueue'
                        and obj.get('content', '').strip()):
                    queued_msgs.append({
                        'content': obj['content'].strip(),
                        'timestamp': obj.get('timestamp', ''),
                    })

        if not queued_msgs:
            return []

        # Check which queued messages are already in DB (by exact content + session)
        for msg in queued_msgs:
            existing = conn.execute(
                """SELECT id FROM prompts
                   WHERE session_id=? AND content=? LIMIT 1""",
                (session_id, msg['content'])
            ).fetchone()

            if not existing:
                cursor = conn.execute(
                    """INSERT INTO prompts
                       (project_id, content, status, session_id, source,
                        created_at, updated_at)
                       VALUES (?, ?, 'success', ?, 'hook-queue',
                               datetime('now','localtime'),
                               datetime('now','localtime'))""",
                    (project_id, msg['content'], session_id)
                )
                recovered.append({
                    'id': cursor.lastrowid,
                    'content': msg['content'],
                })

        if recovered:
            conn.commit()

    except Exception:
        pass  # Never block Claude Code

    return recovered


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
    transcript_path = data.get('transcript_path', '')
    cwd = data.get('cwd', os.getcwd())

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

        # Recover mid-turn queued messages from transcript
        if project_id:
            recovered = recover_queued_messages(
                conn, transcript_path, session_id, project_id
            )
        else:
            # Fallback: resolve project from cwd
            try:
                pid = resolve_project_by_path(conn, cwd)
                recovered = recover_queued_messages(
                    conn, transcript_path, session_id, pid
                )
                project_id = pid
            except Exception:
                recovered = []

        conn.close()
    except Exception:
        recovered = []  # Never block Claude Code

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

    # Google Sheets append for recovered queued messages
    if recovered and project_id:
        try:
            import threading
            project_name = os.path.basename(cwd)
            for rec in recovered:
                threading.Thread(
                    target=google_sheets_append,
                    args=(project_id, rec['id'], rec['content'], project_name,
                          'success', ''),
                    daemon=True,
                ).start()
        except Exception:
            pass


if __name__ == '__main__':
    main()
