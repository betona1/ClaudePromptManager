#!/usr/bin/env python3
"""
CPM: Sync local DB prompts to remote server.

Usage (on Windows):
    python sync_to_remote.py http://192.168.219.100:9200

This sends all local prompts to the remote CPM server via /api/hook/import/.
Duplicates are automatically skipped by the server.
"""
import sys
import json
import sqlite3
import socket
import urllib.request
from pathlib import Path


def get_local_db() -> str:
    if sys.platform == 'win32':
        import os
        base = Path(os.environ.get('APPDATA', Path.home() / 'AppData' / 'Roaming'))
    else:
        import os
        base = Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local' / 'share'))
    return str(base / 'cpm' / 'cpm.db')


def main():
    if len(sys.argv) < 2:
        print("Usage: python sync_to_remote.py <SERVER_URL>")
        print("Example: python sync_to_remote.py http://192.168.219.100:9200")
        sys.exit(1)

    server = sys.argv[1].rstrip('/')
    db_path = get_local_db()
    hostname = socket.gethostname()

    print(f"Local DB: {db_path}")
    print(f"Remote server: {server}")
    print(f"Hostname: {hostname}")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Get all prompts with project path info
    rows = conn.execute("""
        SELECT p.content, p.session_id, p.created_at, p.response_summary, p.source, p.status,
               pr.path as project_path, pr.name as project_name
        FROM prompts p
        LEFT JOIN projects pr ON p.project_id = pr.id
        ORDER BY p.created_at
    """).fetchall()

    print(f"Total prompts to sync: {len(rows)}")

    sent = 0
    skipped = 0
    failed = 0

    for row in rows:
        data = {
            'prompt': row['content'] or '',
            'session_id': row['session_id'] or '',
            'cwd': row['project_path'] or '',
            'hostname': hostname,
            'created_at': row['created_at'] or '',
            'response': row['response_summary'] or '',
            'source': 'import',
        }

        if not data['prompt'].strip():
            skipped += 1
            continue

        try:
            payload = json.dumps(data, ensure_ascii=False).encode('utf-8')
            req = urllib.request.Request(
                f"{server}/api/hook/import/",
                data=payload,
                headers={'Content-Type': 'application/json'}
            )
            resp = urllib.request.urlopen(req, timeout=10)
            result = json.loads(resp.read().decode())

            if result.get('status') == 'skipped':
                skipped += 1
            else:
                sent += 1

            if (sent + skipped) % 50 == 0:
                print(f"  Progress: {sent} sent, {skipped} skipped, {failed} failed / {len(rows)} total")
        except Exception as e:
            failed += 1
            if failed <= 3:
                print(f"  Error: {e}")
            if failed == 3:
                print("  (suppressing further errors...)")

    conn.close()
    print(f"\nDone! Sent: {sent}, Skipped: {skipped}, Failed: {failed}")


if __name__ == '__main__':
    main()
