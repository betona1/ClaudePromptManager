#!/usr/bin/env python3
"""
CPM - Claude Prompt Manager
프로젝트별 Claude Code 프롬프트 관리 CLI 도구
"""

import argparse
import sys
import os
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional, List

# ─── Config ───────────────────────────────────────────────
APP_NAME = "cpm"
DB_NAME = "cpm.db"

def get_data_dir() -> Path:
    """크로스플랫폼 데이터 디렉토리"""
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    data_dir = base / APP_NAME
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir

def get_db_path() -> Path:
    return get_data_dir() / DB_NAME


# ─── Database ─────────────────────────────────────────────
def get_db() -> sqlite3.Connection:
    db_path = get_db_path()
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

def init_db():
    conn = get_db()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS projects (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        path TEXT,
        description TEXT,
        created_at TEXT DEFAULT (datetime('now','localtime')),
        updated_at TEXT DEFAULT (datetime('now','localtime'))
    );

    CREATE TABLE IF NOT EXISTS terminals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        project_id INTEGER,
        session_id TEXT,
        memo TEXT,
        last_activity TEXT,
        created_at TEXT DEFAULT (datetime('now','localtime')),
        FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE SET NULL
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
        FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
        FOREIGN KEY (terminal_id) REFERENCES terminals(id) ON DELETE SET NULL,
        FOREIGN KEY (parent_id) REFERENCES prompts(id) ON DELETE SET NULL
    );

    CREATE TABLE IF NOT EXISTS templates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        content TEXT NOT NULL,
        tag TEXT,
        description TEXT,
        created_at TEXT DEFAULT (datetime('now','localtime'))
    );

    CREATE INDEX IF NOT EXISTS idx_prompts_project ON prompts(project_id);
    CREATE INDEX IF NOT EXISTS idx_prompts_status ON prompts(status);
    CREATE INDEX IF NOT EXISTS idx_prompts_tag ON prompts(tag);
    CREATE INDEX IF NOT EXISTS idx_prompts_parent ON prompts(parent_id);
    """)
    conn.commit()
    conn.close()


# ─── Rich 터미널 출력 (fallback 포함) ────────────────────
try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.text import Text
    from rich import box
    HAS_RICH = True
except ImportError:
    HAS_RICH = False

class Output:
    """rich 있으면 rich 사용, 없으면 plain text"""

    def __init__(self):
        if HAS_RICH:
            self.console = Console()
        else:
            self.console = None

    def print(self, msg=""):
        if self.console:
            self.console.print(msg)
        else:
            print(msg)

    def success(self, msg):
        if self.console:
            self.console.print(f"[green]✓[/green] {msg}")
        else:
            print(f"[OK] {msg}")

    def error(self, msg):
        if self.console:
            self.console.print(f"[red]✗[/red] {msg}")
        else:
            print(f"[ERROR] {msg}")

    def warn(self, msg):
        if self.console:
            self.console.print(f"[yellow]![/yellow] {msg}")
        else:
            print(f"[WARN] {msg}")

    def info(self, msg):
        if self.console:
            self.console.print(f"[cyan]ℹ[/cyan] {msg}")
        else:
            print(f"[INFO] {msg}")

out = Output()


# ─── Helper ───────────────────────────────────────────────
STATUS_ICONS = {"wip": "🔄", "success": "✅", "fail": "❌"}
STATUS_COLORS = {"wip": "yellow", "success": "green", "fail": "red"}
TAG_LIST = ["bug", "feature", "refactor", "docs", "test", "deploy", "config", "other"]

def resolve_project(conn, name_or_id) -> Optional[dict]:
    """프로젝트 이름 또는 ID로 찾기"""
    try:
        pid = int(name_or_id)
        row = conn.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone()
    except (ValueError, TypeError):
        row = conn.execute("SELECT * FROM projects WHERE name=?", (name_or_id,)).fetchone()
    return dict(row) if row else None

def resolve_terminal(conn, name_or_id) -> Optional[dict]:
    try:
        tid = int(name_or_id)
        row = conn.execute("SELECT * FROM terminals WHERE id=?", (tid,)).fetchone()
    except (ValueError, TypeError):
        row = conn.execute("SELECT * FROM terminals WHERE name=?", (name_or_id,)).fetchone()
    return dict(row) if row else None

def truncate(text: str, max_len: int = 50) -> str:
    if not text:
        return ""
    return text[:max_len-2] + ".." if len(text) > max_len else text

def detect_session_id() -> Optional[str]:
    """현재 터미널 세션 ID 자동 감지"""
    # tmux
    sid = os.environ.get("TMUX_PANE")
    if sid:
        return f"tmux:{sid}"
    # screen
    sid = os.environ.get("STY")
    if sid:
        return f"screen:{sid}"
    # generic terminal PID
    ppid = os.environ.get("PPID") or os.environ.get("TERM_SESSION_ID")
    if ppid:
        return f"pid:{ppid}"
    return None


# ─── Project Commands ─────────────────────────────────────
def cmd_project_add(args):
    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO projects (name, path, description) VALUES (?, ?, ?)",
            (args.name, args.path, args.desc)
        )
        conn.commit()
        out.success(f"프로젝트 '{args.name}' 등록 완료")
    except sqlite3.IntegrityError:
        out.error(f"프로젝트 '{args.name}'는 이미 존재합니다")
    conn.close()

def cmd_project_remove(args):
    conn = get_db()
    proj = resolve_project(conn, args.name)
    if not proj:
        out.error(f"프로젝트 '{args.name}'를 찾을 수 없습니다")
        conn.close()
        return
    cnt = conn.execute("SELECT COUNT(*) as c FROM prompts WHERE project_id=?", (proj['id'],)).fetchone()['c']
    if cnt > 0 and not args.force:
        out.warn(f"프로젝트에 {cnt}개의 프롬프트가 있습니다. --force로 삭제하세요")
        conn.close()
        return
    conn.execute("DELETE FROM projects WHERE id=?", (proj['id'],))
    conn.commit()
    out.success(f"프로젝트 '{proj['name']}' 삭제 완료 (프롬프트 {cnt}개 포함)")
    conn.close()

def cmd_project_list(args):
    conn = get_db()
    rows = conn.execute("""
        SELECT p.*, 
            COUNT(pr.id) as total,
            SUM(CASE WHEN pr.status='success' THEN 1 ELSE 0 END) as ok,
            SUM(CASE WHEN pr.status='fail' THEN 1 ELSE 0 END) as ng,
            SUM(CASE WHEN pr.status='wip' THEN 1 ELSE 0 END) as wip
        FROM projects p
        LEFT JOIN prompts pr ON pr.project_id = p.id
        GROUP BY p.id
        ORDER BY p.updated_at DESC
    """).fetchall()
    conn.close()

    if not rows:
        out.info("등록된 프로젝트가 없습니다. 'cpm project add <name>'으로 추가하세요")
        return

    if HAS_RICH:
        table = Table(title="📁 프로젝트 목록", box=box.ROUNDED)
        table.add_column("ID", style="dim", width=4)
        table.add_column("이름", style="cyan bold", min_width=12)
        table.add_column("경로", style="dim", max_width=30)
        table.add_column("설명", max_width=25)
        table.add_column("✅", justify="right", style="green")
        table.add_column("❌", justify="right", style="red")
        table.add_column("🔄", justify="right", style="yellow")
        table.add_column("합계", justify="right", style="bold")
        for r in rows:
            table.add_row(
                str(r['id']), r['name'],
                truncate(r['path'] or "", 30),
                truncate(r['description'] or "", 25),
                str(r['ok'] or 0), str(r['ng'] or 0), str(r['wip'] or 0),
                str(r['total'])
            )
        out.console.print(table)
    else:
        print(f"{'ID':<4} {'이름':<15} {'경로':<30} {'✓':<4} {'✗':<4} {'~':<4}")
        print("-" * 65)
        for r in rows:
            print(f"{r['id']:<4} {r['name']:<15} {truncate(r['path'] or '', 30):<30} "
                  f"{r['ok'] or 0:<4} {r['ng'] or 0:<4} {r['wip'] or 0:<4}")


# ─── Terminal Commands ────────────────────────────────────
def cmd_terminal_add(args):
    conn = get_db()
    project_id = None
    if args.project:
        proj = resolve_project(conn, args.project)
        if not proj:
            out.error(f"프로젝트 '{args.project}'를 찾을 수 없습니다")
            conn.close()
            return
        project_id = proj['id']

    session_id = args.session or detect_session_id()

    try:
        conn.execute(
            "INSERT INTO terminals (name, project_id, session_id, memo) VALUES (?, ?, ?, ?)",
            (args.name, project_id, session_id, args.memo)
        )
        conn.commit()
        out.success(f"터미널 '{args.name}' 등록 (세션: {session_id or 'N/A'})")
    except sqlite3.IntegrityError:
        out.error(f"터미널 '{args.name}'는 이미 존재합니다")
    conn.close()

def cmd_terminal_list(args):
    conn = get_db()
    query = """
        SELECT t.*, p.name as project_name,
            (SELECT content FROM prompts WHERE terminal_id=t.id ORDER BY created_at DESC LIMIT 1) as last_prompt
        FROM terminals t
        LEFT JOIN projects p ON t.project_id = p.id
        ORDER BY t.last_activity DESC NULLS LAST, t.created_at DESC
    """
    rows = conn.execute(query).fetchall()
    conn.close()

    if not rows:
        out.info("등록된 터미널이 없습니다. 'cpm terminal add <name>'으로 추가하세요")
        return

    if HAS_RICH:
        table = Table(title="🖥️  터미널 목록", box=box.ROUNDED)
        table.add_column("ID", style="dim", width=4)
        table.add_column("이름", style="cyan bold", min_width=12)
        table.add_column("프로젝트", style="magenta")
        table.add_column("세션ID", style="dim", max_width=20)
        table.add_column("메모", max_width=20)
        table.add_column("마지막 작업", max_width=30)
        for r in rows:
            table.add_row(
                str(r['id']), r['name'],
                r['project_name'] or "-",
                truncate(r['session_id'] or "", 20),
                truncate(r['memo'] or "", 20),
                truncate(r['last_prompt'] or "", 30)
            )
        out.console.print(table)
    else:
        print(f"{'ID':<4} {'이름':<15} {'프로젝트':<12} {'메모':<20}")
        print("-" * 55)
        for r in rows:
            print(f"{r['id']:<4} {r['name']:<15} {r['project_name'] or '-':<12} "
                  f"{truncate(r['memo'] or '', 20):<20}")

def cmd_terminal_remove(args):
    conn = get_db()
    term = resolve_terminal(conn, args.name)
    if not term:
        out.error(f"터미널 '{args.name}'를 찾을 수 없습니다")
        conn.close()
        return
    conn.execute("DELETE FROM terminals WHERE id=?", (term['id'],))
    conn.commit()
    out.success(f"터미널 '{term['name']}' 삭제 완료")
    conn.close()

def cmd_terminal_memo(args):
    conn = get_db()
    term = resolve_terminal(conn, args.name)
    if not term:
        out.error(f"터미널 '{args.name}'를 찾을 수 없습니다")
        conn.close()
        return
    conn.execute("UPDATE terminals SET memo=? WHERE id=?", (args.memo, term['id']))
    conn.commit()
    out.success(f"터미널 '{term['name']}' 메모 업데이트")
    conn.close()


# ─── Prompt Commands ──────────────────────────────────────
def cmd_prompt_add(args):
    conn = get_db()
    proj = resolve_project(conn, args.project)
    if not proj:
        out.error(f"프로젝트 '{args.project}'를 찾을 수 없습니다")
        conn.close()
        return

    terminal_id = None
    if args.terminal:
        term = resolve_terminal(conn, args.terminal)
        if term:
            terminal_id = term['id']
            conn.execute(
                "UPDATE terminals SET last_activity=datetime('now','localtime') WHERE id=?",
                (terminal_id,)
            )

    tag = args.tag
    if tag and tag not in TAG_LIST:
        out.warn(f"알 수 없는 태그 '{tag}'. 사용 가능: {', '.join(TAG_LIST)}")

    parent_id = args.parent
    if parent_id:
        parent = conn.execute("SELECT id FROM prompts WHERE id=?", (parent_id,)).fetchone()
        if not parent:
            out.warn(f"부모 프롬프트 #{parent_id}를 찾을 수 없습니다. 연결 없이 저장합니다.")
            parent_id = None

    cursor = conn.execute(
        """INSERT INTO prompts (project_id, terminal_id, content, tag, parent_id, status)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (proj['id'], terminal_id, args.content, tag, parent_id, args.status or 'wip')
    )
    prompt_id = cursor.lastrowid

    conn.execute(
        "UPDATE projects SET updated_at=datetime('now','localtime') WHERE id=?",
        (proj['id'],)
    )
    conn.commit()

    tag_str = f" [{tag}]" if tag else ""
    parent_str = f" (← #{parent_id})" if parent_id else ""
    out.success(f"프롬프트 #{prompt_id} 저장{tag_str}{parent_str}")
    conn.close()

def cmd_prompt_status(args):
    conn = get_db()
    row = conn.execute("SELECT * FROM prompts WHERE id=?", (args.id,)).fetchone()
    if not row:
        out.error(f"프롬프트 #{args.id}를 찾을 수 없습니다")
        conn.close()
        return

    updates = ["status=?", "updated_at=datetime('now','localtime')"]
    params = [args.status]

    if args.note:
        updates.append("note=?")
        params.append(args.note)

    params.append(args.id)
    conn.execute(f"UPDATE prompts SET {', '.join(updates)} WHERE id=?", params)
    conn.commit()

    icon = STATUS_ICONS.get(args.status, "?")
    note_str = f" — {args.note}" if args.note else ""
    out.success(f"프롬프트 #{args.id} → {icon} {args.status}{note_str}")
    conn.close()

def cmd_prompt_response(args):
    conn = get_db()
    row = conn.execute("SELECT * FROM prompts WHERE id=?", (args.id,)).fetchone()
    if not row:
        out.error(f"프롬프트 #{args.id}를 찾을 수 없습니다")
        conn.close()
        return

    conn.execute(
        "UPDATE prompts SET response_summary=?, updated_at=datetime('now','localtime') WHERE id=?",
        (args.summary, args.id)
    )
    conn.commit()
    out.success(f"프롬프트 #{args.id} 응답 요약 저장")
    conn.close()

def cmd_prompt_link(args):
    conn = get_db()
    child = conn.execute("SELECT * FROM prompts WHERE id=?", (args.child_id,)).fetchone()
    parent = conn.execute("SELECT * FROM prompts WHERE id=?", (args.parent_id,)).fetchone()
    if not child:
        out.error(f"프롬프트 #{args.child_id}를 찾을 수 없습니다")
        conn.close()
        return
    if not parent:
        out.error(f"프롬프트 #{args.parent_id}를 찾을 수 없습니다")
        conn.close()
        return

    conn.execute("UPDATE prompts SET parent_id=? WHERE id=?", (args.parent_id, args.child_id))
    conn.commit()
    out.success(f"프롬프트 #{args.child_id} → #{args.parent_id} 연결 완료")
    conn.close()

def cmd_prompt_search(args):
    conn = get_db()
    query_parts = ["SELECT pr.*, p.name as project_name FROM prompts pr JOIN projects p ON pr.project_id=p.id WHERE 1=1"]
    params = []

    if args.keyword:
        query_parts.append("AND (pr.content LIKE ? OR pr.response_summary LIKE ? OR pr.note LIKE ?)")
        kw = f"%{args.keyword}%"
        params.extend([kw, kw, kw])

    if args.project:
        proj = resolve_project(conn, args.project)
        if proj:
            query_parts.append("AND pr.project_id=?")
            params.append(proj['id'])

    if args.status:
        query_parts.append("AND pr.status=?")
        params.append(args.status)

    if args.tag:
        query_parts.append("AND pr.tag=?")
        params.append(args.tag)

    query_parts.append("ORDER BY pr.created_at DESC")
    if args.limit:
        query_parts.append("LIMIT ?")
        params.append(args.limit)

    rows = conn.execute(" ".join(query_parts), params).fetchall()
    conn.close()

    if not rows:
        out.info("검색 결과가 없습니다")
        return

    _print_prompt_list(rows)

def _print_prompt_list(rows):
    if HAS_RICH:
        table = Table(box=box.SIMPLE_HEAVY)
        table.add_column("#", style="dim", width=5)
        table.add_column("프로젝트", style="magenta", width=12)
        table.add_column("태그", width=8)
        table.add_column("프롬프트", min_width=35)
        table.add_column("상태", width=4, justify="center")
        table.add_column("응답요약", max_width=25)
        table.add_column("연결", width=5, style="dim")
        table.add_column("일시", style="dim", width=16)

        for r in rows:
            status_icon = STATUS_ICONS.get(r['status'], "?")
            tag_str = r['tag'] or ""
            parent_str = f"←#{r['parent_id']}" if r['parent_id'] else ""
            table.add_row(
                str(r['id']),
                r['project_name'],
                tag_str,
                truncate(r['content'], 40),
                status_icon,
                truncate(r['response_summary'] or "", 25),
                parent_str,
                r['created_at'][:16] if r['created_at'] else ""
            )
        out.console.print(table)
    else:
        print(f"{'#':<5} {'프로젝트':<12} {'태그':<8} {'프롬프트':<40} {'상태':<4} {'일시':<16}")
        print("-" * 90)
        for r in rows:
            icon = STATUS_ICONS.get(r['status'], "?")
            print(f"{r['id']:<5} {r['project_name']:<12} {r['tag'] or '':<8} "
                  f"{truncate(r['content'], 40):<40} {icon:<4} "
                  f"{(r['created_at'] or '')[:16]:<16}")


# ─── Log Command ──────────────────────────────────────────
def cmd_log(args):
    conn = get_db()
    proj = resolve_project(conn, args.project)
    if not proj:
        out.error(f"프로젝트 '{args.project}'를 찾을 수 없습니다")
        conn.close()
        return

    query = """
        SELECT pr.*, p.name as project_name, t.name as terminal_name
        FROM prompts pr
        JOIN projects p ON pr.project_id = p.id
        LEFT JOIN terminals t ON pr.terminal_id = t.id
        WHERE pr.project_id = ?
    """
    params = [proj['id']]

    if args.status:
        query += " AND pr.status=?"
        params.append(args.status)
    if args.tag:
        query += " AND pr.tag=?"
        params.append(args.tag)

    query += " ORDER BY pr.created_at DESC"

    if args.limit:
        query += " LIMIT ?"
        params.append(args.limit)

    rows = conn.execute(query, params).fetchall()
    conn.close()

    if not rows:
        out.info(f"프로젝트 '{proj['name']}'에 프롬프트가 없습니다")
        return

    if HAS_RICH:
        out.console.print(Panel(
            f"[bold cyan]{proj['name']}[/bold cyan]  {proj['description'] or ''}\n"
            f"[dim]{proj['path'] or ''}[/dim]",
            title="📋 프로젝트 로그"
        ))

        table = Table(box=box.SIMPLE_HEAVY)
        table.add_column("#", style="dim", width=5)
        table.add_column("태그", width=8)
        table.add_column("터미널", style="blue", width=12)
        table.add_column("프롬프트", min_width=35)
        table.add_column("상태", width=4, justify="center")
        table.add_column("응답요약", max_width=25)
        table.add_column("노트", max_width=20)
        table.add_column("연결", width=5, style="dim")
        table.add_column("일시", style="dim", width=16)

        for r in rows:
            status_icon = STATUS_ICONS.get(r['status'], "?")
            parent_str = f"←#{r['parent_id']}" if r['parent_id'] else ""
            table.add_row(
                str(r['id']),
                r['tag'] or "",
                r['terminal_name'] or "-",
                truncate(r['content'], 40),
                status_icon,
                truncate(r['response_summary'] or "", 25),
                truncate(r['note'] or "", 20),
                parent_str,
                r['created_at'][:16] if r['created_at'] else ""
            )
        out.console.print(table)
    else:
        print(f"\n=== {proj['name']} ({proj['path'] or ''}) ===\n")
        for r in rows:
            icon = STATUS_ICONS.get(r['status'], "?")
            print(f"  #{r['id']} {icon} [{r['tag'] or '-'}] {truncate(r['content'], 50)}")
            if r['response_summary']:
                print(f"       → {truncate(r['response_summary'], 60)}")
            if r['note']:
                print(f"       📝 {r['note']}")


# ─── Board (Dashboard) ───────────────────────────────────
def cmd_board(args):
    conn = get_db()
    projects = conn.execute("""
        SELECT p.*,
            COUNT(pr.id) as total,
            SUM(CASE WHEN pr.status='success' THEN 1 ELSE 0 END) as ok,
            SUM(CASE WHEN pr.status='fail' THEN 1 ELSE 0 END) as ng,
            SUM(CASE WHEN pr.status='wip' THEN 1 ELSE 0 END) as wip,
            (SELECT content FROM prompts WHERE project_id=p.id ORDER BY created_at DESC LIMIT 1) as latest
        FROM projects p
        LEFT JOIN prompts pr ON pr.project_id = p.id
        GROUP BY p.id
        ORDER BY p.updated_at DESC
    """).fetchall()

    # 전체 통계
    stats = conn.execute("""
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN status='success' THEN 1 ELSE 0 END) as ok,
            SUM(CASE WHEN status='fail' THEN 1 ELSE 0 END) as ng,
            SUM(CASE WHEN status='wip' THEN 1 ELSE 0 END) as wip
        FROM prompts
    """).fetchone()

    # 최근 실패 프롬프트
    recent_fails = conn.execute("""
        SELECT pr.id, pr.content, p.name as project_name, pr.note
        FROM prompts pr JOIN projects p ON pr.project_id=p.id
        WHERE pr.status='fail'
        ORDER BY pr.updated_at DESC LIMIT 5
    """).fetchall()

    conn.close()

    if HAS_RICH:
        # 헤더
        total = stats['total'] or 0
        ok = stats['ok'] or 0
        ng = stats['ng'] or 0
        wip = stats['wip'] or 0

        header_text = (
            f"[bold]전체 프롬프트: {total}[/bold]  "
            f"[green]✅ {ok}[/green]  "
            f"[red]❌ {ng}[/red]  "
            f"[yellow]🔄 {wip}[/yellow]"
        )
        out.console.print(Panel(header_text, title="📊 CPM Dashboard", box=box.DOUBLE))

        # 프로젝트 테이블
        table = Table(title="프로젝트별 현황", box=box.ROUNDED)
        table.add_column("프로젝트", style="cyan bold", min_width=14)
        table.add_column("설명", max_width=20)
        table.add_column("✅", justify="right", style="green", width=4)
        table.add_column("❌", justify="right", style="red", width=4)
        table.add_column("🔄", justify="right", style="yellow", width=4)
        table.add_column("합계", justify="right", style="bold", width=5)
        table.add_column("최근 프롬프트", max_width=35)

        for p in projects:
            table.add_row(
                p['name'],
                truncate(p['description'] or "", 20),
                str(p['ok'] or 0),
                str(p['ng'] or 0),
                str(p['wip'] or 0),
                str(p['total']),
                truncate(p['latest'] or "", 35)
            )
        out.console.print(table)

        # 최근 실패
        if recent_fails:
            out.console.print()
            fail_table = Table(title="⚠️  최근 실패 프롬프트", box=box.SIMPLE)
            fail_table.add_column("#", style="dim", width=5)
            fail_table.add_column("프로젝트", style="magenta", width=12)
            fail_table.add_column("프롬프트", min_width=35)
            fail_table.add_column("노트", max_width=30)
            for f in recent_fails:
                fail_table.add_row(
                    str(f['id']), f['project_name'],
                    truncate(f['content'], 40),
                    truncate(f['note'] or "", 30)
                )
            out.console.print(fail_table)
    else:
        print("\n╔══════════════════════════════════════════╗")
        print("║         CPM Dashboard                    ║")
        print(f"║  전체: {stats['total'] or 0}  ✓{stats['ok'] or 0}  ✗{stats['ng'] or 0}  ~{stats['wip'] or 0}  ║")
        print("╠══════════════════════════════════════════╣")
        for p in projects:
            print(f"║ {p['name']:<14} ✓{p['ok'] or 0:<3} ✗{p['ng'] or 0:<3} ~{p['wip'] or 0:<3} {truncate(p['latest'] or '', 20)}")
        print("╚══════════════════════════════════════════╝")


# ─── Template Commands ────────────────────────────────────
def cmd_template_add(args):
    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO templates (name, content, tag, description) VALUES (?, ?, ?, ?)",
            (args.name, args.content, args.tag, args.desc)
        )
        conn.commit()
        out.success(f"템플릿 '{args.name}' 저장 완료")
    except sqlite3.IntegrityError:
        out.error(f"템플릿 '{args.name}'는 이미 존재합니다")
    conn.close()

def cmd_template_list(args):
    conn = get_db()
    rows = conn.execute("SELECT * FROM templates ORDER BY created_at DESC").fetchall()
    conn.close()

    if not rows:
        out.info("등록된 템플릿이 없습니다")
        return

    if HAS_RICH:
        table = Table(title="📝 프롬프트 템플릿", box=box.ROUNDED)
        table.add_column("ID", style="dim", width=4)
        table.add_column("이름", style="cyan bold", min_width=15)
        table.add_column("태그", width=8)
        table.add_column("내용", min_width=40)
        table.add_column("설명", max_width=25)
        for r in rows:
            table.add_row(
                str(r['id']), r['name'], r['tag'] or "",
                truncate(r['content'], 45),
                truncate(r['description'] or "", 25)
            )
        out.console.print(table)
    else:
        for r in rows:
            print(f"  [{r['id']}] {r['name']} ({r['tag'] or '-'}): {truncate(r['content'], 50)}")

def cmd_template_use(args):
    conn = get_db()
    try:
        tid = int(args.name)
        row = conn.execute("SELECT * FROM templates WHERE id=?", (tid,)).fetchone()
    except ValueError:
        row = conn.execute("SELECT * FROM templates WHERE name=?", (args.name,)).fetchone()

    if not row:
        out.error(f"템플릿 '{args.name}'를 찾을 수 없습니다")
        conn.close()
        return

    proj = resolve_project(conn, args.project)
    if not proj:
        out.error(f"프로젝트 '{args.project}'를 찾을 수 없습니다")
        conn.close()
        return

    content = row['content']
    cursor = conn.execute(
        """INSERT INTO prompts (project_id, content, tag, status)
           VALUES (?, ?, ?, 'wip')""",
        (proj['id'], content, row['tag'])
    )
    conn.execute("UPDATE projects SET updated_at=datetime('now','localtime') WHERE id=?", (proj['id'],))
    conn.commit()

    prompt_id = cursor.lastrowid
    out.success(f"템플릿 '{row['name']}' → 프롬프트 #{prompt_id}로 저장")
    out.print(f"  내용: {content}")
    conn.close()

def cmd_template_remove(args):
    conn = get_db()
    try:
        tid = int(args.name)
        row = conn.execute("SELECT * FROM templates WHERE id=?", (tid,)).fetchone()
    except ValueError:
        row = conn.execute("SELECT * FROM templates WHERE name=?", (args.name,)).fetchone()
    if not row:
        out.error(f"템플릿 '{args.name}'를 찾을 수 없습니다")
        conn.close()
        return
    conn.execute("DELETE FROM templates WHERE id=?", (row['id'],))
    conn.commit()
    out.success(f"템플릿 '{row['name']}' 삭제 완료")
    conn.close()


# ─── Export / Import ──────────────────────────────────────
def cmd_export(args):
    conn = get_db()
    data = {
        "exported_at": datetime.now().isoformat(),
        "projects": [dict(r) for r in conn.execute("SELECT * FROM projects").fetchall()],
        "terminals": [dict(r) for r in conn.execute("SELECT * FROM terminals").fetchall()],
        "prompts": [dict(r) for r in conn.execute("SELECT * FROM prompts").fetchall()],
        "templates": [dict(r) for r in conn.execute("SELECT * FROM templates").fetchall()],
    }
    conn.close()

    output_path = args.output or "cpm_export.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    out.success(f"내보내기 완료: {output_path}")
    out.info(f"  프로젝트: {len(data['projects'])}개, 프롬프트: {len(data['prompts'])}개")

def cmd_import(args):
    if not os.path.exists(args.input):
        out.error(f"파일을 찾을 수 없습니다: {args.input}")
        return

    with open(args.input, "r", encoding="utf-8") as f:
        data = json.load(f)

    conn = get_db()
    imported = {"projects": 0, "terminals": 0, "prompts": 0, "templates": 0}

    for p in data.get("projects", []):
        try:
            conn.execute(
                "INSERT OR IGNORE INTO projects (name, path, description, created_at, updated_at) VALUES (?,?,?,?,?)",
                (p['name'], p.get('path'), p.get('description'), p.get('created_at'), p.get('updated_at'))
            )
            imported['projects'] += 1
        except Exception:
            pass

    for t in data.get("terminals", []):
        try:
            conn.execute(
                "INSERT OR IGNORE INTO terminals (name, session_id, memo, created_at) VALUES (?,?,?,?)",
                (t['name'], t.get('session_id'), t.get('memo'), t.get('created_at'))
            )
            imported['terminals'] += 1
        except Exception:
            pass

    for tpl in data.get("templates", []):
        try:
            conn.execute(
                "INSERT OR IGNORE INTO templates (name, content, tag, description, created_at) VALUES (?,?,?,?,?)",
                (tpl['name'], tpl['content'], tpl.get('tag'), tpl.get('description'), tpl.get('created_at'))
            )
            imported['templates'] += 1
        except Exception:
            pass

    conn.commit()
    conn.close()
    out.success(f"가져오기 완료: 프로젝트 {imported['projects']}, 터미널 {imported['terminals']}, 템플릿 {imported['templates']}")
    out.warn("프롬프트는 프로젝트 ID 매핑이 필요하여 수동 확인이 필요합니다")


# ─── Show (프롬프트 상세 보기) ────────────────────────────
def cmd_show(args):
    conn = get_db()
    row = conn.execute("""
        SELECT pr.*, p.name as project_name, t.name as terminal_name
        FROM prompts pr
        JOIN projects p ON pr.project_id = p.id
        LEFT JOIN terminals t ON pr.terminal_id = t.id
        WHERE pr.id = ?
    """, (args.id,)).fetchone()

    if not row:
        out.error(f"프롬프트 #{args.id}를 찾을 수 없습니다")
        conn.close()
        return

    # 자식 프롬프트 (후속작업)
    children = conn.execute(
        "SELECT id, content, status FROM prompts WHERE parent_id=? ORDER BY created_at",
        (args.id,)
    ).fetchall()

    conn.close()

    if HAS_RICH:
        icon = STATUS_ICONS.get(row['status'], "?")
        color = STATUS_COLORS.get(row['status'], "white")

        detail = (
            f"[bold]프롬프트 #{row['id']}[/bold]  {icon}\n\n"
            f"[bold]프로젝트:[/bold] {row['project_name']}\n"
            f"[bold]터미널:[/bold]  {row['terminal_name'] or '-'}\n"
            f"[bold]태그:[/bold]    {row['tag'] or '-'}\n"
            f"[bold]상태:[/bold]    [{color}]{row['status']}[/{color}]\n"
            f"[bold]생성:[/bold]    {row['created_at']}\n"
            f"[bold]수정:[/bold]    {row['updated_at']}\n"
        )
        if row['parent_id']:
            detail += f"[bold]부모:[/bold]    ← #{row['parent_id']}\n"

        detail += f"\n[bold]내용:[/bold]\n{row['content']}\n"

        if row['response_summary']:
            detail += f"\n[bold]응답 요약:[/bold]\n{row['response_summary']}\n"

        if row['note']:
            detail += f"\n[bold]노트:[/bold]\n{row['note']}\n"

        if children:
            detail += "\n[bold]후속 작업:[/bold]\n"
            for c in children:
                ci = STATUS_ICONS.get(c['status'], "?")
                detail += f"  → #{c['id']} {ci} {truncate(c['content'], 50)}\n"

        out.console.print(Panel(detail, box=box.ROUNDED))
    else:
        r = row
        print(f"\n=== 프롬프트 #{r['id']} ({r['status']}) ===")
        print(f"프로젝트: {r['project_name']}")
        print(f"터미널: {r['terminal_name'] or '-'}")
        print(f"태그: {r['tag'] or '-'}")
        print(f"일시: {r['created_at']}")
        print(f"\n{r['content']}")
        if r['response_summary']:
            print(f"\n[응답] {r['response_summary']}")
        if r['note']:
            print(f"\n[노트] {r['note']}")
        if children:
            print("\n[후속작업]")
            for c in children:
                print(f"  → #{c['id']} ({c['status']}) {truncate(c['content'], 50)}")


# ─── Stats ────────────────────────────────────────────────
def cmd_stats(args):
    conn = get_db()
    stats = conn.execute("""
        SELECT
            (SELECT COUNT(*) FROM projects) as projects,
            (SELECT COUNT(*) FROM prompts) as prompts,
            (SELECT COUNT(*) FROM terminals) as terminals,
            (SELECT COUNT(*) FROM templates) as templates,
            (SELECT COUNT(*) FROM prompts WHERE status='success') as ok,
            (SELECT COUNT(*) FROM prompts WHERE status='fail') as ng,
            (SELECT COUNT(*) FROM prompts WHERE status='wip') as wip
    """).fetchone()

    tag_stats = conn.execute("""
        SELECT tag, COUNT(*) as cnt FROM prompts WHERE tag IS NOT NULL
        GROUP BY tag ORDER BY cnt DESC
    """).fetchall()

    conn.close()

    if HAS_RICH:
        info = (
            f"[bold]프로젝트:[/bold] {stats['projects']}개\n"
            f"[bold]프롬프트:[/bold] {stats['prompts']}개  "
            f"([green]✅{stats['ok']}[/green] [red]❌{stats['ng']}[/red] [yellow]🔄{stats['wip']}[/yellow])\n"
            f"[bold]터미널:[/bold]  {stats['terminals']}개\n"
            f"[bold]템플릿:[/bold]  {stats['templates']}개\n"
        )
        if tag_stats:
            info += "\n[bold]태그별 현황:[/bold]\n"
            for t in tag_stats:
                info += f"  {t['tag']}: {t['cnt']}개\n"

        info += f"\n[dim]DB 위치: {get_db_path()}[/dim]"
        out.console.print(Panel(info, title="📈 CPM 통계"))
    else:
        print(f"\n프로젝트: {stats['projects']}, 프롬프트: {stats['prompts']}, 터미널: {stats['terminals']}")
        print(f"✓{stats['ok']} ✗{stats['ng']} ~{stats['wip']}")
        print(f"DB: {get_db_path()}")


# ─── CLI Parser ───────────────────────────────────────────
def build_parser():
    parser = argparse.ArgumentParser(
        prog="cpm",
        description="CPM - Claude Prompt Manager: 프로젝트별 Claude Code 프롬프트 관리"
    )
    sub = parser.add_subparsers(dest="command", help="사용 가능한 명령어")

    # --- project ---
    p_proj = sub.add_parser("project", aliases=["p"], help="프로젝트 관리")
    p_proj_sub = p_proj.add_subparsers(dest="subcmd")

    p_add = p_proj_sub.add_parser("add", help="프로젝트 추가")
    p_add.add_argument("name", help="프로젝트 이름")
    p_add.add_argument("--path", "-p", help="프로젝트 경로")
    p_add.add_argument("--desc", "-d", help="설명")

    p_rm = p_proj_sub.add_parser("remove", aliases=["rm"], help="프로젝트 삭제")
    p_rm.add_argument("name", help="프로젝트 이름 또는 ID")
    p_rm.add_argument("--force", "-f", action="store_true")

    p_proj_sub.add_parser("list", aliases=["ls"], help="프로젝트 목록")

    # --- terminal ---
    p_term = sub.add_parser("terminal", aliases=["t"], help="터미널 관리")
    p_term_sub = p_term.add_subparsers(dest="subcmd")

    t_add = p_term_sub.add_parser("add", help="터미널 추가")
    t_add.add_argument("name", help="터미널 이름 (예: myvoice-1)")
    t_add.add_argument("--project", "-p", help="연결할 프로젝트")
    t_add.add_argument("--session", "-s", help="세션 ID (미지정시 자동 감지)")
    t_add.add_argument("--memo", "-m", help="메모")

    t_rm = p_term_sub.add_parser("remove", aliases=["rm"], help="터미널 삭제")
    t_rm.add_argument("name", help="터미널 이름 또는 ID")

    t_memo = p_term_sub.add_parser("memo", help="터미널 메모 업데이트")
    t_memo.add_argument("name", help="터미널 이름 또는 ID")
    t_memo.add_argument("memo", help="메모 내용")

    p_term_sub.add_parser("list", aliases=["ls"], help="터미널 목록")

    # --- prompt ---
    p_prompt = sub.add_parser("prompt", aliases=["pr"], help="프롬프트 관리")
    p_prompt_sub = p_prompt.add_subparsers(dest="subcmd")

    pr_add = p_prompt_sub.add_parser("add", help="프롬프트 저장")
    pr_add.add_argument("project", help="프로젝트 이름 또는 ID")
    pr_add.add_argument("content", help="프롬프트 내용")
    pr_add.add_argument("--tag", "-t", choices=TAG_LIST, help="태그")
    pr_add.add_argument("--terminal", "-T", help="터미널 이름 또는 ID")
    pr_add.add_argument("--parent", "-P", type=int, help="부모 프롬프트 ID (후속작업)")
    pr_add.add_argument("--status", "-s", choices=["wip", "success", "fail"], default="wip")

    pr_status = p_prompt_sub.add_parser("status", aliases=["st"], help="상태 변경")
    pr_status.add_argument("id", type=int, help="프롬프트 ID")
    pr_status.add_argument("status", choices=["wip", "success", "fail"])
    pr_status.add_argument("--note", "-n", help="노트")

    pr_resp = p_prompt_sub.add_parser("response", aliases=["res"], help="응답 요약 저장")
    pr_resp.add_argument("id", type=int, help="프롬프트 ID")
    pr_resp.add_argument("summary", help="응답 요약 내용")

    pr_link = p_prompt_sub.add_parser("link", help="프롬프트 연결")
    pr_link.add_argument("child_id", type=int, help="자식 프롬프트 ID")
    pr_link.add_argument("parent_id", type=int, help="부모 프롬프트 ID")

    pr_search = p_prompt_sub.add_parser("search", aliases=["s"], help="프롬프트 검색")
    pr_search.add_argument("keyword", nargs="?", help="검색어")
    pr_search.add_argument("--project", "-p", help="프로젝트 필터")
    pr_search.add_argument("--status", "-s", choices=["wip", "success", "fail"])
    pr_search.add_argument("--tag", "-t", choices=TAG_LIST)
    pr_search.add_argument("--limit", "-l", type=int, default=20)

    # --- show ---
    p_show = sub.add_parser("show", help="프롬프트 상세 보기")
    p_show.add_argument("id", type=int, help="프롬프트 ID")

    # --- log ---
    p_log = sub.add_parser("log", aliases=["l"], help="프로젝트별 프롬프트 이력")
    p_log.add_argument("project", help="프로젝트 이름 또는 ID")
    p_log.add_argument("--status", "-s", choices=["wip", "success", "fail"])
    p_log.add_argument("--tag", "-t", choices=TAG_LIST)
    p_log.add_argument("--limit", "-l", type=int, default=30)

    # --- board ---
    sub.add_parser("board", aliases=["b"], help="전체 대시보드")

    # --- template ---
    p_tpl = sub.add_parser("template", aliases=["tpl"], help="프롬프트 템플릿 관리")
    p_tpl_sub = p_tpl.add_subparsers(dest="subcmd")

    tpl_add = p_tpl_sub.add_parser("add", help="템플릿 추가")
    tpl_add.add_argument("name", help="템플릿 이름")
    tpl_add.add_argument("content", help="템플릿 내용")
    tpl_add.add_argument("--tag", "-t", choices=TAG_LIST)
    tpl_add.add_argument("--desc", "-d", help="설명")

    tpl_use = p_tpl_sub.add_parser("use", help="템플릿으로 프롬프트 생성")
    tpl_use.add_argument("name", help="템플릿 이름 또는 ID")
    tpl_use.add_argument("project", help="대상 프로젝트")

    tpl_rm = p_tpl_sub.add_parser("remove", aliases=["rm"], help="템플릿 삭제")
    tpl_rm.add_argument("name", help="템플릿 이름 또는 ID")

    p_tpl_sub.add_parser("list", aliases=["ls"], help="템플릿 목록")

    # --- stats ---
    sub.add_parser("stats", help="전체 통계")

    # --- export / import ---
    p_export = sub.add_parser("export", help="JSON으로 내보내기")
    p_export.add_argument("--output", "-o", help="출력 파일 경로")

    p_import = sub.add_parser("import", help="JSON에서 가져오기")
    p_import.add_argument("input", help="입력 JSON 파일 경로")

    return parser


# ─── Command Router ───────────────────────────────────────
def main():
    init_db()
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    cmd = args.command
    subcmd = getattr(args, 'subcmd', None)

    routes = {
        # project
        ("project", "add"): cmd_project_add,
        ("p", "add"): cmd_project_add,
        ("project", "remove"): cmd_project_remove,
        ("project", "rm"): cmd_project_remove,
        ("p", "remove"): cmd_project_remove,
        ("p", "rm"): cmd_project_remove,
        ("project", "list"): cmd_project_list,
        ("project", "ls"): cmd_project_list,
        ("p", "list"): cmd_project_list,
        ("p", "ls"): cmd_project_list,
        # terminal
        ("terminal", "add"): cmd_terminal_add,
        ("t", "add"): cmd_terminal_add,
        ("terminal", "remove"): cmd_terminal_remove,
        ("terminal", "rm"): cmd_terminal_remove,
        ("t", "remove"): cmd_terminal_remove,
        ("t", "rm"): cmd_terminal_remove,
        ("terminal", "memo"): cmd_terminal_memo,
        ("t", "memo"): cmd_terminal_memo,
        ("terminal", "list"): cmd_terminal_list,
        ("terminal", "ls"): cmd_terminal_list,
        ("t", "list"): cmd_terminal_list,
        ("t", "ls"): cmd_terminal_list,
        # prompt
        ("prompt", "add"): cmd_prompt_add,
        ("pr", "add"): cmd_prompt_add,
        ("prompt", "status"): cmd_prompt_status,
        ("prompt", "st"): cmd_prompt_status,
        ("pr", "status"): cmd_prompt_status,
        ("pr", "st"): cmd_prompt_status,
        ("prompt", "response"): cmd_prompt_response,
        ("prompt", "res"): cmd_prompt_response,
        ("pr", "response"): cmd_prompt_response,
        ("pr", "res"): cmd_prompt_response,
        ("prompt", "link"): cmd_prompt_link,
        ("pr", "link"): cmd_prompt_link,
        ("prompt", "search"): cmd_prompt_search,
        ("prompt", "s"): cmd_prompt_search,
        ("pr", "search"): cmd_prompt_search,
        ("pr", "s"): cmd_prompt_search,
        # template
        ("template", "add"): cmd_template_add,
        ("tpl", "add"): cmd_template_add,
        ("template", "use"): cmd_template_use,
        ("tpl", "use"): cmd_template_use,
        ("template", "remove"): cmd_template_remove,
        ("template", "rm"): cmd_template_remove,
        ("tpl", "remove"): cmd_template_remove,
        ("tpl", "rm"): cmd_template_remove,
        ("template", "list"): cmd_template_list,
        ("template", "ls"): cmd_template_list,
        ("tpl", "list"): cmd_template_list,
        ("tpl", "ls"): cmd_template_list,
    }

    # 서브커맨드 없는 명령어
    simple_routes = {
        "board": cmd_board, "b": cmd_board,
        "show": cmd_show,
        "log": cmd_log, "l": cmd_log,
        "stats": cmd_stats,
        "export": cmd_export,
        "import": cmd_import,
    }

    if cmd in simple_routes:
        simple_routes[cmd](args)
    elif (cmd, subcmd) in routes:
        routes[(cmd, subcmd)](args)
    elif subcmd is None:
        # 서브커맨드 없이 메인 커맨드만 입력한 경우
        # project, terminal, prompt, template → list 기본 실행
        default_list = {
            "project": cmd_project_list, "p": cmd_project_list,
            "terminal": cmd_terminal_list, "t": cmd_terminal_list,
            "template": cmd_template_list, "tpl": cmd_template_list,
        }
        if cmd in default_list:
            default_list[cmd](args)
        else:
            parser.print_help()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
