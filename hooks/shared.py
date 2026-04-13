"""
CPM Hooks — shared utilities for DB access and Redis publish.
Used by on_prompt.py and on_stop.py.
"""
import os
import sys
import sqlite3
import json
from pathlib import Path
from datetime import datetime


def get_db_path() -> Path:
    if sys.platform == 'win32':
        base = Path(os.environ.get('APPDATA', Path.home() / 'AppData' / 'Roaming'))
    else:
        base = Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local' / 'share'))
    return base / 'cpm' / 'cpm.db'


def get_db() -> sqlite3.Connection:
    db_path = get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def ensure_tables(conn: sqlite3.Connection):
    """Ensure v2 tables exist (safe to call repeatedly)."""
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS projects (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        path TEXT,
        description TEXT,
        created_at TEXT DEFAULT (datetime('now','localtime')),
        updated_at TEXT DEFAULT (datetime('now','localtime'))
    );

    CREATE TABLE IF NOT EXISTS prompts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL,
        terminal_id INTEGER,
        content TEXT NOT NULL,
        response_summary TEXT,
        status TEXT DEFAULT 'wip' CHECK(status IN ('wip','success','fail')),
        tag TEXT,
        note TEXT,
        parent_id INTEGER,
        created_at TEXT DEFAULT (datetime('now','localtime')),
        updated_at TEXT DEFAULT (datetime('now','localtime')),
        session_id TEXT,
        source TEXT DEFAULT 'manual',
        duration_ms INTEGER,
        FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
        FOREIGN KEY (parent_id) REFERENCES prompts(id) ON DELETE SET NULL
    );

    CREATE TABLE IF NOT EXISTS sessions (
        id TEXT PRIMARY KEY,
        project_id INTEGER,
        terminal_id INTEGER,
        project_path TEXT,
        started_at TEXT,
        ended_at TEXT,
        message_count INTEGER DEFAULT 0,
        FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE SET NULL
    );
    """)
    # Add v2 columns if missing (for existing v1 DBs)
    for col, default in [('session_id', None), ('source', "'manual'"), ('duration_ms', None), ('tmux_session', None)]:
        try:
            conn.execute(f"ALTER TABLE prompts ADD COLUMN {col} TEXT"
                        if default is None
                        else f"ALTER TABLE prompts ADD COLUMN {col} TEXT DEFAULT {default}")
        except sqlite3.OperationalError:
            pass  # column already exists
    conn.commit()


def resolve_project_by_path(conn: sqlite3.Connection, cwd: str) -> int:
    """Find or create a project matching the given cwd path."""
    # Exact match first
    row = conn.execute("SELECT id FROM projects WHERE path=?", (cwd,)).fetchone()
    if row:
        return row['id']

    # Check if cwd is a subdirectory of a known project
    rows = conn.execute("SELECT id, path FROM projects WHERE path IS NOT NULL").fetchall()
    for r in rows:
        if r['path'] and cwd.startswith(r['path']):
            return r['id']

    # Auto-create project from directory name
    name = Path(cwd).name
    # Ensure unique name
    base_name = name
    counter = 1
    while True:
        existing = conn.execute("SELECT id FROM projects WHERE name=?", (name,)).fetchone()
        if not existing:
            break
        name = f"{base_name}-{counter}"
        counter += 1

    conn.execute(
        "INSERT INTO projects (name, path, description) VALUES (?, ?, ?)",
        (name, cwd, f"Auto-detected from {cwd}")
    )
    conn.commit()
    row = conn.execute("SELECT id FROM projects WHERE name=?", (name,)).fetchone()
    return row['id']


def auto_detect_github_url(conn: sqlite3.Connection, project_id: int, cwd: str):
    """Auto-detect GitHub URL from git remote and save to project."""
    try:
        import subprocess
        git_dir = os.path.join(cwd, '.git')
        if not os.path.isdir(git_dir):
            return
        # Check if already set
        row = conn.execute("SELECT github_url FROM projects WHERE id=?", (project_id,)).fetchone()
        if row and row['github_url']:
            return
        url = subprocess.check_output(
            ['git', '-C', cwd, 'remote', 'get-url', 'origin'],
            stderr=subprocess.DEVNULL, timeout=3
        ).decode().strip()
        if 'github.com' in url:
            web_url = url.replace('.git', '').replace('git@github.com:', 'https://github.com/')
            try:
                conn.execute("UPDATE projects SET github_url=? WHERE id=?", (web_url, project_id))
                conn.commit()
            except Exception:
                pass  # github_url column may not exist in older DBs
    except Exception:
        pass


def ensure_session(conn: sqlite3.Connection, session_id: str, project_id: int, cwd: str):
    """Create or update session record."""
    row = conn.execute("SELECT id FROM sessions WHERE id=?", (session_id,)).fetchone()
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    if not row:
        conn.execute(
            "INSERT INTO sessions (id, project_id, project_path, started_at, message_count) VALUES (?, ?, ?, ?, 0)",
            (session_id, project_id, cwd, now)
        )
    conn.execute(
        "UPDATE sessions SET message_count = message_count + 1 WHERE id=?",
        (session_id,)
    )
    conn.commit()


def detect_tmux_session():
    """Detect current terminal multiplexer session name.

    Priority:
      1. tmux session name via `tmux display-message -p '#S'` (if $TMUX is set)
      2. TMUX_PANE fallback (if tmux binary missing but pane id inherited)
      3. GNU screen session name ($STY)
    Returns None if not inside a multiplexer. Never raises.
    """
    try:
        if os.environ.get('TMUX'):
            # tmux CLI is the most reliable way to get the human-readable session name
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
            # Fallback to pane id if tmux binary unavailable
            pane = os.environ.get('TMUX_PANE')
            if pane:
                return f'tmux-pane:{pane}'
        sty = os.environ.get('STY')
        if sty:
            return f'screen:{sty}'
    except Exception:
        pass
    return None


def get_remote_server() -> str:
    """Get remote CPM server URL from env. Returns empty string if not set."""
    return os.environ.get('CPM_REMOTE_SERVER', '').rstrip('/')


def get_api_token() -> str:
    """Get CPM API token from env. Returns empty string if not set."""
    return os.environ.get('CPM_API_TOKEN', '')


_self_server_cache = {}


def _is_self_server(server_url: str) -> bool:
    """Return True if the given CPM server URL points at this machine.

    Uses a UDP socket routing probe: when you connect() a UDP socket to
    an IP that is assigned to this host, the kernel picks that same IP
    as the local source. If local == target, the URL is us. This works
    across all interfaces (eth, tailscale, docker) without parsing any
    OS-specific files. Results are cached per process.
    """
    if not server_url:
        return False
    if server_url in _self_server_cache:
        return _self_server_cache[server_url]
    result = False
    try:
        from urllib.parse import urlparse
        import socket
        host = (urlparse(server_url).hostname or '').lower()
        if not host:
            result = False
        elif host in ('localhost', '127.0.0.1', '::1', '0.0.0.0'):
            result = True
        else:
            try:
                my_hostname = socket.gethostname().lower()
                if host == my_hostname or host == my_hostname.split('.')[0]:
                    result = True
            except Exception:
                pass
            if not result:
                try:
                    target_ip = socket.gethostbyname(host)
                    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    try:
                        s.settimeout(1.0)
                        s.connect((target_ip, 1))
                        local_ip = s.getsockname()[0]
                    finally:
                        s.close()
                    if local_ip == target_ip:
                        result = True
                except Exception:
                    pass
    except Exception:
        result = False
    _self_server_cache[server_url] = result
    return result


def remote_post(endpoint: str, data: dict):
    """POST to remote CPM server if configured. Non-blocking, fire-and-forget.

    Skips the POST when the configured server resolves to this machine, to
    avoid duplicate inserts (local hook writes to SQLite directly and the
    API endpoint would write a second row to the same DB).
    """
    server = get_remote_server()
    if not server:
        return
    if _is_self_server(server):
        return  # same host — local hook already persisted this prompt
    try:
        import urllib.request
        url = f"{server}/api/{endpoint}"
        payload = json.dumps(data, ensure_ascii=False).encode('utf-8')
        headers = {'Content-Type': 'application/json'}
        token = get_api_token()
        if token:
            headers['Authorization'] = f'Bearer {token}'
        req = urllib.request.Request(url, data=payload, headers=headers)
        urllib.request.urlopen(req, timeout=5)
    except Exception:
        pass  # Never block Claude Code


def backup_hooks_settings():
    """Backup settings.json when hooks are confirmed working.
    Called from on_prompt.py — if this runs, hooks are alive."""
    try:
        settings_path = Path.home() / '.claude' / 'settings.json'
        backup_path = Path.home() / '.claude' / 'settings.hooks.backup.json'
        if not settings_path.exists():
            return
        with open(settings_path, 'r') as f:
            data = json.load(f)
        # Only backup if hooks section exists and has CPM entries
        hooks = data.get('hooks', {})
        has_cpm = any(
            'cpm' in h.get('command', '').lower()
            for event_hooks in hooks.values()
            for entry in (event_hooks if isinstance(event_hooks, list) else [])
            for h in entry.get('hooks', [])
        )
        if has_cpm:
            with open(backup_path, 'w') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception:
        pass  # Never block Claude Code


def check_hooks_health() -> dict:
    """Check if CPM hooks are active.
    First tries settings.json (local). If not found (e.g. Docker),
    falls back to checking recent DB activity from hook source.
    Returns: {'ok': bool, 'prompt_hook': bool, 'stop_hook': bool, 'backup_exists': bool}
    """
    result = {'ok': False, 'prompt_hook': False, 'stop_hook': False, 'backup_exists': False}
    try:
        settings_path = Path.home() / '.claude' / 'settings.json'
        backup_path = Path.home() / '.claude' / 'settings.hooks.backup.json'
        result['backup_exists'] = backup_path.exists()

        if settings_path.exists():
            with open(settings_path, 'r') as f:
                data = json.load(f)

            hooks = data.get('hooks', {})
            for entry in hooks.get('UserPromptSubmit', []):
                for h in entry.get('hooks', []):
                    if 'on_prompt' in h.get('command', ''):
                        result['prompt_hook'] = True
            for entry in hooks.get('Stop', []):
                for h in entry.get('hooks', []):
                    if 'on_stop' in h.get('command', ''):
                        result['stop_hook'] = True

            result['ok'] = result['prompt_hook'] and result['stop_hook']
            return result

        # Fallback: no settings.json (Docker / remote-only mode)
        # Check if hooks are actively sending data by looking at recent DB activity
        # Try CPM_DATA_DIR first (Docker), then default path
        data_dir = os.environ.get('CPM_DATA_DIR', '')
        if data_dir:
            db_path = Path(data_dir) / 'cpm.db'
        else:
            db_path = get_db_path()

        if db_path and db_path.exists():
            conn = sqlite3.connect(str(db_path), timeout=2)
            cursor = conn.cursor()
            # Check for hook-source prompts in the last 24 hours
            cursor.execute(
                "SELECT COUNT(*) FROM prompts WHERE source IN ('hook','import') "
                "AND created_at >= datetime('now', '-24 hours')"
            )
            recent_count = cursor.fetchone()[0]
            conn.close()

            if recent_count > 0:
                result['ok'] = True
                result['prompt_hook'] = True
                result['stop_hook'] = True
            else:
                # No recent hooks, but check if there are ANY hook prompts ever
                conn = sqlite3.connect(str(db_path), timeout=2)
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT COUNT(*) FROM prompts WHERE source IN ('hook','import')"
                )
                total_hooks = cursor.fetchone()[0]
                conn.close()
                if total_hooks > 0:
                    # Hooks existed before, just no activity in 24h — still OK
                    result['ok'] = True
                    result['prompt_hook'] = True
                    result['stop_hook'] = True
    except Exception:
        pass
    return result


def restore_hooks_from_backup() -> bool:
    """Restore hooks from backup file. Returns True if successful."""
    try:
        settings_path = Path.home() / '.claude' / 'settings.json'
        backup_path = Path.home() / '.claude' / 'settings.hooks.backup.json'
        if not backup_path.exists():
            return False

        with open(backup_path, 'r') as f:
            backup_data = json.load(f)

        backup_hooks = backup_data.get('hooks', {})
        if not backup_hooks:
            return False

        # Load current settings (preserve non-hook settings)
        current_data = {}
        if settings_path.exists():
            with open(settings_path, 'r') as f:
                current_data = json.load(f)

        current_data['hooks'] = backup_hooks

        with open(settings_path, 'w') as f:
            json.dump(current_data, f, indent=2, ensure_ascii=False)
        return True
    except Exception:
        return False


def redis_publish(channel: str, data: dict):
    """Publish to Redis if available. Silently skip if Redis is not running."""
    try:
        import redis
        r = redis.Redis(host='localhost', port=6379, db=0, socket_connect_timeout=1)
        r.publish(channel, json.dumps(data, ensure_ascii=False))
    except Exception:
        pass  # Redis is optional
