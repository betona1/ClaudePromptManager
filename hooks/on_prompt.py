#!/usr/bin/env python3
"""
CPM Hook: UserPromptSubmit
Claude Code calls this when a user submits a prompt.

stdin JSON:
{
  "session_id": "...",
  "prompt": "...",
  "cwd": "...",
  "transcript_path": "...",
  "hook_event_name": "UserPromptSubmit",
  "permission_mode": "..."
}

stdout: {} (pass through)
"""
import sys
import json
import os

# Add parent directory to path for shared import
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from shared import get_db, ensure_tables, resolve_project_by_path, ensure_session, auto_detect_github_url, redis_publish


def main():
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        # If we can't parse input, just pass through
        print('{}')
        return

    prompt_text = data.get('prompt', '').strip()
    session_id = data.get('session_id', '')
    cwd = data.get('cwd', os.getcwd())

    if not prompt_text:
        print('{}')
        return

    try:
        conn = get_db()
        ensure_tables(conn)

        project_id = resolve_project_by_path(conn, cwd)
        auto_detect_github_url(conn, project_id, cwd)
        ensure_session(conn, session_id, project_id, cwd)

        cursor = conn.execute(
            """INSERT INTO prompts (project_id, content, status, session_id, source, created_at, updated_at)
               VALUES (?, ?, 'wip', ?, 'hook', datetime('now','localtime'), datetime('now','localtime'))""",
            (project_id, prompt_text, session_id)
        )
        prompt_id = cursor.lastrowid

        conn.execute(
            "UPDATE projects SET updated_at=datetime('now','localtime') WHERE id=?",
            (project_id,)
        )
        conn.commit()

        # Redis publish for real-time updates
        redis_publish('cpm:live', {
            'event': 'new_prompt',
            'prompt_id': prompt_id,
            'project_id': project_id,
            'session_id': session_id,
            'content': prompt_text[:200],
        })

        conn.close()
    except Exception:
        pass  # Never block Claude Code

    print('{}')


if __name__ == '__main__':
    main()
