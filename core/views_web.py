import json
import os
from datetime import datetime, date, timedelta
from pathlib import Path
from django.conf import settings
from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.db.models import Count, Q, Max, Min, Sum, Exists, OuterRef
from django.db.models.functions import TruncHour, TruncDate
from .models import (
    Project, ProjectScreenshot, Terminal, Prompt, Template, Session,
    ServicePort, Execution, UserProfile, Follow,
    ServerIdentity, FederatedServer, FederatedSubscription, FederatedPrompt,
)
from .permissions import visible_projects_queryset, can_view_project


def _format_tokens(n):
    """Format token count: 1234567 -> '1.2M', 12345 -> '12.3K'"""
    if n >= 1_000_000:
        return f'{n / 1_000_000:.1f}M'
    elif n >= 1_000:
        return f'{n / 1_000:.1f}K'
    return str(n)


def _attach_working_days(projects):
    """Attach working_days, first_at, last_at, tokens_display, today_count to each project."""
    today = date.today()
    for p in projects:
        dates = Prompt.objects.filter(project_id=p.id).dates('created_at', 'day')
        p.working_days = len(dates)
        r = Prompt.objects.filter(project_id=p.id).aggregate(
            first_at=Min('created_at'), last_at=Max('created_at')
        )
        p.first_at = r['first_at']
        p.last_at = r['last_at']
        p.total_tokens = p.total_input_tokens + p.total_output_tokens
        p.tokens_display = _format_tokens(p.total_tokens)
        p.today_count = Prompt.objects.filter(project_id=p.id, created_at__date=today).count()


def dashboard(request):
    """Main dashboard with overview stats and user tabs."""
    user = request.user
    tab = request.GET.get('tab', '')

    # Base queryset respecting visibility
    base_qs = visible_projects_queryset(user)

    # Tab filtering
    if user.is_authenticated:
        if not tab:
            tab = 'mine'
        if tab == 'mine':
            projects_qs = base_qs.filter(owner=user)
        elif tab == 'friends':
            friend_ids = list(
                Follow.objects.filter(follower=user).values_list('following_id', flat=True)
            )
            mutual_ids = list(
                Follow.objects.filter(follower_id__in=friend_ids, following=user)
                .values_list('follower_id', flat=True)
            )
            projects_qs = base_qs.filter(owner_id__in=mutual_ids).exclude(owner=user)
        else:  # community
            tab = 'community'
            projects_qs = base_qs.filter(visibility='public')
    else:
        tab = 'community'
        projects_qs = base_qs

    # Tab counts
    tab_counts = {}
    if user.is_authenticated:
        tab_counts['mine'] = base_qs.filter(owner=user).count()
        tab_counts['community'] = base_qs.filter(visibility='public').count()
        friend_ids = list(
            Follow.objects.filter(follower=user).values_list('following_id', flat=True)
        )
        mutual_ids = list(
            Follow.objects.filter(follower_id__in=friend_ids, following=user)
            .values_list('follower_id', flat=True)
        )
        tab_counts['friends'] = base_qs.filter(owner_id__in=mutual_ids).exclude(owner=user).count()

    projects = projects_qs.prefetch_related('screenshots', 'todos').annotate(
        prompt_count=Count('prompts', distinct=True),
        latest_at=Max('prompts__created_at'),
        hook_prompt_count=Count('prompts', filter=Q(prompts__source__in=['hook', 'import']), distinct=True),
        todo_total=Count('todos', distinct=True),
        todo_completed=Count('todos', filter=Q(todos__is_completed=True), distinct=True),
        has_docker=Exists(ServicePort.objects.filter(project=OuterRef('pk'), is_docker=True)),
    ).order_by('-favorited', '-latest_at')

    total = Prompt.objects.count()

    recent_prompts = Prompt.objects.select_related('project').order_by('-created_at')[:15]

    # Calculate total working days (distinct dates across all prompts)
    total_days = len(Prompt.objects.dates('created_at', 'day'))

    _attach_working_days(projects)

    # Total tokens
    token_agg = Project.objects.aggregate(
        total_in=Sum('total_input_tokens'),
        total_out=Sum('total_output_tokens'),
    )
    total_tokens = (token_agg['total_in'] or 0) + (token_agg['total_out'] or 0)

    services = ServicePort.objects.select_related('project').all()

    # Period prompt counts (today / yesterday / last 7 days / last 30 days)
    today = date.today()
    yesterday = today - timedelta(days=1)
    week_start = today - timedelta(days=6)   # last 7 days inclusive
    month_start = today - timedelta(days=29)  # last 30 days inclusive
    today_count = Prompt.objects.filter(created_at__date=today).count()
    yesterday_count = Prompt.objects.filter(created_at__date=yesterday).count()
    week_count = Prompt.objects.filter(created_at__date__gte=week_start, created_at__date__lte=today).count()
    month_count = Prompt.objects.filter(created_at__date__gte=month_start, created_at__date__lte=today).count()

    # Hook health check
    import sys
    sys.path.insert(0, str(settings.CPM_HOOKS_DIR))
    from shared import check_hooks_health
    hooks_health = check_hooks_health()

    context = {
        'projects': projects,
        'total': total,
        'total_days': total_days,
        'total_tokens': total_tokens,
        'total_tokens_display': _format_tokens(total_tokens),
        'recent_prompts': recent_prompts,
        'today_count': today_count,
        'yesterday_count': yesterday_count,
        'week_count': week_count,
        'month_count': month_count,
        'hook_count': Prompt.objects.filter(source='hook').count(),
        'import_count': Prompt.objects.filter(source='import').count(),
        'services': services,
        'hooks_ok': hooks_health['ok'],
        'hooks_health': hooks_health,
        'tab': tab,
        'tab_counts': tab_counts,
    }
    return render(request, 'dashboard.html', context)


def project_list(request):
    projects = Project.objects.prefetch_related('screenshots').annotate(
        prompt_count=Count('prompts'),
        latest_at=Max('prompts__created_at'),
    ).order_by('-latest_at')

    _attach_working_days(projects)

    return render(request, 'projects.html', {'projects': projects})


def project_detail(request, pk):
    project = get_object_or_404(Project, pk=pk)

    if not can_view_project(request.user, project):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden('This project is private.')

    # Sort
    sort = request.GET.get('sort', 'desc')
    order = 'created_at' if sort == 'asc' else '-created_at'
    prompts = project.prompts.select_related('terminal').order_by(order)

    # Filters
    status = request.GET.get('status')
    if status:
        prompts = prompts.filter(status=status)
    tag = request.GET.get('tag')
    if tag:
        prompts = prompts.filter(tag=tag)
    source = request.GET.get('source')
    if source:
        prompts = prompts.filter(source=source)
    tmux = request.GET.get('tmux', '').strip()
    if tmux:
        if tmux == '__none__':
            prompts = prompts.filter(Q(tmux_session__isnull=True) | Q(tmux_session=''))
        else:
            prompts = prompts.filter(tmux_session=tmux)

    # In-project search
    q = request.GET.get('q', '').strip()
    if q:
        prompts = prompts.filter(
            Q(content__icontains=q) |
            Q(response_summary__icontains=q) |
            Q(note__icontains=q)
        )

    total = project.prompts.count()

    # Working days
    working_days = len(project.prompts.dates('created_at', 'day'))
    date_range = project.prompts.aggregate(first_at=Min('created_at'), last_at=Max('created_at'))

    prompt_count = prompts.count()

    # Pagination
    page = int(request.GET.get('page', 1))
    per_page = 50
    start = (page - 1) * per_page
    prompts_page = prompts[start:start + per_page]
    total_pages = (prompt_count + per_page - 1) // per_page

    total_tokens = project.total_input_tokens + project.total_output_tokens

    # MD files
    md_files = []
    if project.path and os.path.isdir(project.path):
        for f in sorted(Path(project.path).glob('*.md')):
            md_files.append({'name': f.name, 'size': f.stat().st_size})

    # Screenshots
    screenshots = project.screenshots.all()

    # Todos
    todos = project.todos.all()
    todo_total = todos.count()
    todo_completed = todos.filter(is_completed=True).count()

    # Service Ports
    services = ServicePort.objects.filter(project=project).select_related('project')

    # Token breakdown
    token_breakdown = {
        'input': project.total_input_tokens,
        'output': project.total_output_tokens,
        'cache_read': project.total_cache_read_tokens,
        'cache_create': project.total_cache_create_tokens,
        'total': total_tokens,
        'input_display': _format_tokens(project.total_input_tokens),
        'output_display': _format_tokens(project.total_output_tokens),
        'cache_read_display': _format_tokens(project.total_cache_read_tokens),
        'cache_create_display': _format_tokens(project.total_cache_create_tokens),
    }

    # Sessions
    sessions = Session.objects.filter(project=project).order_by('-started_at')[:10]
    session_count = Session.objects.filter(project=project).count()

    # Executions
    executions = Execution.objects.filter(project=project).order_by('-created_at')[:10]

    # Today's count & hook count
    today = date.today()
    today_count = project.prompts.filter(created_at__date=today).count()
    hook_count = project.prompts.filter(source__in=['hook', 'import']).count()

    # tmux sub-categories for this project
    tmux_groups_qs = (
        project.prompts
        .values('tmux_session')
        .annotate(count=Count('id'))
        .order_by('-count')
    )
    tmux_groups = []
    unknown_count = 0
    for r in tmux_groups_qs:
        name = r['tmux_session']
        if not name:
            unknown_count += r['count']
            continue
        tmux_groups.append({'name': name, 'count': r['count']})
    if unknown_count:
        tmux_groups.append({'name': '', 'count': unknown_count, 'unknown': True})

    context = {
        'project': project,
        'prompts': prompts_page,
        'total': total,
        'working_days': working_days,
        'first_at': date_range['first_at'],
        'last_at': date_range['last_at'],
        'total_tokens': total_tokens,
        'tokens_display': _format_tokens(total_tokens),
        'token_breakdown': token_breakdown,
        'page': page,
        'total_pages': total_pages,
        'prompt_count': prompt_count,
        'current_status': status or '',
        'current_tag': tag or '',
        'current_source': source or '',
        'current_tmux': tmux,
        'tmux_groups': tmux_groups,
        'current_q': q,
        'sort': sort,
        'md_files': md_files,
        'screenshots': screenshots,
        'todos': todos,
        'todo_total': todo_total,
        'todo_completed': todo_completed,
        'services': services,
        'sessions': sessions,
        'session_count': session_count,
        'executions': executions,
        'today_count': today_count,
        'hook_count': hook_count,
    }
    return render(request, 'project_detail.html', context)


def prompt_list(request):
    # Sort
    sort = request.GET.get('sort', 'desc')
    order = 'created_at' if sort == 'asc' else '-created_at'
    prompts = Prompt.objects.select_related('project', 'terminal').order_by(order)

    # Filters
    status = request.GET.get('status')
    if status:
        prompts = prompts.filter(status=status)
    tag = request.GET.get('tag')
    if tag:
        prompts = prompts.filter(tag=tag)
    source = request.GET.get('source')
    if source:
        prompts = prompts.filter(source=source)
    project_name = request.GET.get('project')
    if project_name:
        prompts = prompts.filter(project__name=project_name)

    # Search
    q = request.GET.get('q', '').strip()
    if q:
        prompts = prompts.filter(
            Q(content__icontains=q) |
            Q(response_summary__icontains=q) |
            Q(note__icontains=q)
        )

    # Pagination
    page = int(request.GET.get('page', 1))
    per_page = 50
    total_count = prompts.count()
    start = (page - 1) * per_page
    prompts_page = prompts[start:start + per_page]
    total_pages = (total_count + per_page - 1) // per_page

    # Project list for filter dropdown
    all_projects = Project.objects.order_by('name').values_list('name', flat=True)

    context = {
        'prompts': prompts_page,
        'total_count': total_count,
        'page': page,
        'total_pages': total_pages,
        'current_status': status or '',
        'current_tag': tag or '',
        'current_source': source or '',
        'current_project': project_name or '',
        'current_q': q,
        'sort': sort,
        'all_projects': all_projects,
    }
    return render(request, 'prompts.html', context)


def prompt_detail(request, pk):
    prompt = get_object_or_404(
        Prompt.objects.select_related('project', 'terminal', 'parent'),
        pk=pk
    )
    children = prompt.children.all().order_by('created_at')

    context = {
        'prompt': prompt,
        'children': children,
    }
    return render(request, 'prompt_detail.html', context)


def project_md(request, pk, filename):
    """View a markdown file from a project directory."""
    project = get_object_or_404(Project, pk=pk)

    if not project.path or not os.path.isdir(project.path):
        return render(request, 'project_md.html', {
            'project': project, 'filename': filename,
            'error': 'Project path not accessible.',
        })

    # Security: only allow .md files in project root, no path traversal
    if '/' in filename or '\\' in filename or '..' in filename:
        return render(request, 'project_md.html', {
            'project': project, 'filename': filename,
            'error': 'Invalid filename.',
        })

    filepath = Path(project.path) / filename
    if not filepath.exists() or not filepath.suffix == '.md':
        return render(request, 'project_md.html', {
            'project': project, 'filename': filename,
            'error': 'File not found.',
        })

    content = filepath.read_text(encoding='utf-8', errors='replace')

    return render(request, 'project_md.html', {
        'project': project,
        'filename': filename,
        'content': content,
    })


def search(request):
    q = request.GET.get('q', '').strip()
    results = []
    if q:
        results = Prompt.objects.select_related('project').filter(
            Q(content__icontains=q) |
            Q(response_summary__icontains=q) |
            Q(note__icontains=q)
        ).order_by('-created_at')[:100]

    return render(request, 'search.html', {
        'q': q,
        'results': results,
        'count': len(results),
    })


def export_view(request):
    """Export data as JSON download."""
    project_name = request.GET.get('project')

    data = {
        'exported_at': datetime.now().isoformat(),
        'version': 'v2',
    }

    projects_qs = Project.objects.all()
    if project_name:
        projects_qs = projects_qs.filter(name=project_name)

    data['projects'] = list(projects_qs.values())
    project_ids = list(projects_qs.values_list('id', flat=True))

    data['prompts'] = list(Prompt.objects.filter(
        project_id__in=project_ids
    ).values())
    data['sessions'] = list(Session.objects.filter(
        project_id__in=project_ids
    ).values())

    content = json.dumps(data, ensure_ascii=False, indent=2, default=str)

    filename = f'cpm_export_{project_name or "all"}_{datetime.now().strftime("%Y%m%d")}.json'
    response = HttpResponse(content, content_type='application/json')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


def setup_guide(request):
    """Setup guide page for remote hooks (Windows etc.) + GitHub sync."""
    host = request.get_host()
    scheme = 'https' if request.is_secure() else 'http'
    server_url = f'{scheme}://{host}'
    return render(request, 'setup.html', {'server_url': server_url})


def download_hook(request, filename):
    """Download hook files as zip or individual file."""
    import zipfile
    import io

    host = request.get_host()
    scheme = 'https' if request.is_secure() else 'http'
    server_url = f'{scheme}://{host}'

    def _replace_server(content):
        return content.replace(
            "CPM_SERVER = os.environ.get('CPM_SERVER', 'http://localhost:9200')",
            f"CPM_SERVER = os.environ.get('CPM_SERVER', '{server_url}')"
        )

    if filename == 'cpm-hooks-windows.zip':
        # Windows zip: remote-only hooks (no local DB)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
            for fname in ['on_prompt_remote.py', 'on_stop_remote.py', 'import_history.py']:
                hook_path = Path(settings.BASE_DIR) / 'hooks' / fname
                if hook_path.exists():
                    zf.writestr(f'cpm-hooks/{fname}', _replace_server(hook_path.read_text(encoding='utf-8')))

            # settings.json for Windows
            settings_json = json.dumps({
                "hooks": {
                    "UserPromptSubmit": [{
                        "matcher": "",
                        "hooks": [{"type": "command", "command": "python C:\\cpm-hooks\\on_prompt_remote.py"}]
                    }],
                    "Stop": [{
                        "matcher": "",
                        "hooks": [{"type": "command", "command": "python C:\\cpm-hooks\\on_stop_remote.py"}]
                    }]
                }
            }, indent=2, ensure_ascii=False)
            zf.writestr('cpm-hooks/settings.json', settings_json)

            readme = f"""CPM Remote Hooks — Windows Setup
=================================

[한국어 안내]

이 패키지는 Windows PC에서 Claude Code 프롬프트를
원격 CPM 서버({server_url})로 자동 전송하는 hook 파일입니다.

━━━ 설치 방법 ━━━

1단계: 파일 복사
  - cpm-hooks 폴더를 C:\\ 에 복사 → C:\\cpm-hooks\\

2단계: hooks 설정
  - settings.json을 아래 위치에 복사:
    %USERPROFILE%\\.claude\\settings.json
  - 이미 settings.json이 있으면 "hooks" 부분만 병합

3단계: Claude Code 재시작
  - 터미널을 닫고 다시 열면 자동 적용

━━━ 기존 기록 가져오기 ━━━

  python C:\\cpm-hooks\\import_history.py

  - ~/.claude/projects/ 아래 세션 기록과 history.jsonl을 읽어서 서버에 전송
  - 이미 전송된 기록은 자동 건너뜀 (중복 방지)
  - 한 번만 실행하면 됩니다

━━━ 파일 설명 ━━━

  on_prompt_remote.py  — 프롬프트 전송 hook (UserPromptSubmit)
  on_stop_remote.py    — 응답 완료 전송 hook (Stop)
  import_history.py    — 기존 Claude Code 기록 일괄 전송
  settings.json        — Claude Code hooks 설정 파일

━━━ 문제 해결 ━━━

  - Python 설치 확인: python --version
  - 서버 접속 확인: 브라우저에서 {server_url} 열기
  - 경로 확인: C:\\cpm-hooks\\on_prompt_remote.py 파일 존재 확인
  - 방화벽: 서버 포트(9200) 열려있는지 확인

서버: {server_url}
"""
            zf.writestr('cpm-hooks/README.txt', readme)

        buf.seek(0)
        response = HttpResponse(buf.read(), content_type='application/zip')
        response['Content-Disposition'] = 'attachment; filename="cpm-hooks-windows.zip"'
        return response

    elif filename == 'cpm-hooks-linux.zip':
        # Linux zip: full hooks with local DB + remote sync
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
            # Full hooks (local + remote)
            for fname in ['on_prompt.py', 'on_stop.py', 'shared.py']:
                hook_path = Path(settings.BASE_DIR) / 'hooks' / fname
                if hook_path.exists():
                    zf.writestr(f'cpm-hooks/{fname}', hook_path.read_text(encoding='utf-8'))

            # Remote-only hooks (alternative)
            for fname in ['remote_hook.py', 'on_prompt_remote.py', 'on_stop_remote.py']:
                hook_path = Path(settings.BASE_DIR) / 'hooks' / fname
                if hook_path.exists():
                    zf.writestr(f'cpm-hooks/remote-only/{fname}', _replace_server(hook_path.read_text(encoding='utf-8')))

            # Import tools
            for fname in ['import_history.py', 'sync_to_remote.py']:
                hook_path = Path(settings.BASE_DIR) / 'hooks' / fname
                if hook_path.exists():
                    zf.writestr(f'cpm-hooks/{fname}', _replace_server(hook_path.read_text(encoding='utf-8')))

            # settings.json for Linux (Mode A: local + remote)
            settings_a = json.dumps({
                "hooks": {
                    "UserPromptSubmit": [{
                        "matcher": "",
                        "hooks": [{"type": "command", "command": "python3 ~/cpm-hooks/on_prompt.py"}]
                    }],
                    "Stop": [{
                        "matcher": "",
                        "hooks": [{"type": "command", "command": "python3 ~/cpm-hooks/on_stop.py"}]
                    }]
                }
            }, indent=2, ensure_ascii=False)
            zf.writestr('cpm-hooks/settings-local-remote.json', settings_a)

            # settings.json for Linux (Mode B: remote only)
            settings_b = json.dumps({
                "hooks": {
                    "UserPromptSubmit": [{
                        "matcher": "",
                        "hooks": [{"type": "command", "command": "python3 ~/cpm-hooks/remote-only/remote_hook.py prompt"}]
                    }],
                    "Stop": [{
                        "matcher": "",
                        "hooks": [{"type": "command", "command": "python3 ~/cpm-hooks/remote-only/remote_hook.py stop"}]
                    }]
                }
            }, indent=2, ensure_ascii=False)
            zf.writestr('cpm-hooks/settings-remote-only.json', settings_b)

            # setup.sh — auto install script
            setup_sh = f"""#!/bin/bash
# CPM Hooks 자동 설치 스크립트
# 사용법: bash setup.sh

set -e

SERVER="{server_url}"
HOOK_DIR="$HOME/cpm-hooks"
CLAUDE_DIR="$HOME/.claude"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  CPM Hooks Installer (Linux)"
echo "  서버: $SERVER"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# 1. hooks 파일 복사
echo "[1/4] Hook 파일 설치..."
mkdir -p "$HOOK_DIR"
cp -r ./*.py "$HOOK_DIR/" 2>/dev/null || true
cp -r ./remote-only "$HOOK_DIR/" 2>/dev/null || true
chmod +x "$HOOK_DIR"/*.py
echo "  → $HOOK_DIR/"

# 2. 환경변수 설정
echo "[2/4] 환경변수 설정..."
SHELL_RC="$HOME/.bashrc"
if [ -n "$ZSH_VERSION" ] || [ -f "$HOME/.zshrc" ]; then
    SHELL_RC="$HOME/.zshrc"
fi

if ! grep -q "CPM_REMOTE_SERVER" "$SHELL_RC" 2>/dev/null; then
    echo "" >> "$SHELL_RC"
    echo "# CPM Remote Server" >> "$SHELL_RC"
    echo "export CPM_REMOTE_SERVER=$SERVER" >> "$SHELL_RC"
    echo "  → $SHELL_RC 에 CPM_REMOTE_SERVER=$SERVER 추가됨"
else
    echo "  → 이미 설정됨 (skip)"
fi
export CPM_REMOTE_SERVER=$SERVER

# 3. Claude Code hooks 설정
echo "[3/4] Claude Code hooks 설정..."
mkdir -p "$CLAUDE_DIR"
SETTINGS="$CLAUDE_DIR/settings.json"

if [ ! -f "$SETTINGS" ]; then
    cp settings-local-remote.json "$SETTINGS" 2>/dev/null || true
    echo "  → $SETTINGS 생성됨"
else
    echo "  → $SETTINGS 이미 존재"
    echo "    수동으로 hooks 부분을 병합해주세요."
    echo "    참고: settings-local-remote.json"
fi

# 4. 연결 테스트
echo "[4/4] 서버 연결 테스트..."
if python3 -c "import urllib.request; urllib.request.urlopen('$SERVER/api/', timeout=5)" 2>/dev/null; then
    echo "  → 연결 성공!"
else
    echo "  → 연결 실패. 서버 주소/방화벽 확인 필요"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  설치 완료!"
echo ""
echo "  기존 기록 가져오기:"
echo "    python3 $HOOK_DIR/import_history.py"
echo ""
echo "  Claude Code를 재시작하면 자동 기록됩니다."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
"""
            zf.writestr('cpm-hooks/setup.sh', setup_sh)

            readme = f"""CPM Remote Hooks — Linux Setup
================================

[한국어 안내]

이 패키지는 Linux PC에서 Claude Code 프롬프트를
원격 CPM 서버({server_url})로 자동 전송하는 hook 파일입니다.

━━━ 자동 설치 (권장) ━━━

  cd cpm-hooks
  bash setup.sh

━━━ 수동 설치 ━━━

1단계: 파일 복사
  cp -r cpm-hooks ~/cpm-hooks

2단계: 환경변수 설정 (~/.bashrc 또는 ~/.zshrc)
  export CPM_REMOTE_SERVER={server_url}

3단계: Claude Code hooks 설정
  cp ~/cpm-hooks/settings-local-remote.json ~/.claude/settings.json
  (이미 settings.json이 있으면 "hooks" 부분만 병합)

4단계: Claude Code 재시작

━━━ 모드 선택 ━━━

  A) 로컬 저장 + 원격 전송 (settings-local-remote.json)
     - 로컬 DB에도 저장하고 서버에도 전송
     - CPM_REMOTE_SERVER 환경변수 필요
     - 파일: on_prompt.py, on_stop.py, shared.py

  B) 원격 전용 (settings-remote-only.json)
     - 서버에만 전송 (로컬 DB 없음)
     - 파일: remote-only/remote_hook.py

━━━ 기존 기록 가져오기 ━━━

  python3 ~/cpm-hooks/import_history.py

  또는 로컬 DB가 있는 경우:
  python3 ~/cpm-hooks/sync_to_remote.py {server_url}

━━━ 파일 설명 ━━━

  on_prompt.py        — 로컬+원격 프롬프트 hook
  on_stop.py          — 로컬+원격 응답 hook
  shared.py           — 공유 유틸리티 (DB, Redis, remote_post)
  import_history.py   — Claude Code 기록 일괄 전송
  sync_to_remote.py   — 로컬 DB → 서버 동기화
  setup.sh            — 자동 설치 스크립트
  remote-only/        — 원격 전용 hook 파일들

서버: {server_url}
"""
            zf.writestr('cpm-hooks/README.txt', readme)

        buf.seek(0)
        response = HttpResponse(buf.read(), content_type='application/zip')
        response['Content-Disposition'] = 'attachment; filename="cpm-hooks-linux.zip"'
        return response

    elif filename == 'cpm-hooks.zip':
        # Legacy: redirect to Windows zip for backward compat
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
            for fname in ['on_prompt_remote.py', 'on_stop_remote.py', 'import_history.py']:
                hook_path = Path(settings.BASE_DIR) / 'hooks' / fname
                if hook_path.exists():
                    zf.writestr(f'cpm-hooks/{fname}', _replace_server(hook_path.read_text(encoding='utf-8')))
            settings_json = json.dumps({
                "hooks": {
                    "UserPromptSubmit": [{
                        "matcher": "",
                        "hooks": [{"type": "command", "command": "python C:\\cpm-hooks\\on_prompt_remote.py"}]
                    }],
                    "Stop": [{
                        "matcher": "",
                        "hooks": [{"type": "command", "command": "python C:\\cpm-hooks\\on_stop_remote.py"}]
                    }]
                }
            }, indent=2, ensure_ascii=False)
            zf.writestr('cpm-hooks/settings.json', settings_json)
        buf.seek(0)
        response = HttpResponse(buf.read(), content_type='application/zip')
        response['Content-Disposition'] = 'attachment; filename="cpm-hooks.zip"'
        return response

    # Single file download (fallback)
    allowed = {'on_prompt_remote.py', 'on_stop_remote.py', 'remote_hook.py', 'import_history.py', 'sync_to_remote.py'}
    if filename not in allowed:
        return HttpResponse('Not found', status=404)

    hook_path = Path(settings.BASE_DIR) / 'hooks' / filename
    if not hook_path.exists():
        return HttpResponse('File not found', status=404)

    content = hook_path.read_text(encoding='utf-8')
    content = _replace_server(content)

    response = HttpResponse(content, content_type='text/plain; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


def remote_execute(request):
    """Remote Claude Code execution page."""
    projects = Project.objects.filter(path__isnull=False).exclude(path='').order_by('name')
    recent_execs = Execution.objects.select_related('project').order_by('-created_at')[:10]
    return render(request, 'remote.html', {
        'projects': projects,
        'recent_execs': recent_execs,
    })


def statistics(request):
    """Statistics page with daily/weekly/monthly breakdowns."""
    mode = request.GET.get('mode', 'daily')
    date_str = request.GET.get('date')

    # Parse base date
    try:
        base_date = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else date.today()
    except ValueError:
        base_date = date.today()

    # Calculate time range based on mode
    if mode == 'weekly':
        # Monday of the week
        start_date = base_date - timedelta(days=base_date.weekday())
        end_date = start_date + timedelta(days=6)
        prev_date = (start_date - timedelta(days=7)).isoformat()
        next_date = (start_date + timedelta(days=7)).isoformat()
        date_label = f"{start_date.strftime('%m/%d')} ~ {end_date.strftime('%m/%d')}"
    elif mode == 'monthly':
        start_date = base_date.replace(day=1)
        # Last day of month
        if start_date.month == 12:
            end_date = start_date.replace(year=start_date.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            end_date = start_date.replace(month=start_date.month + 1, day=1) - timedelta(days=1)
        # Prev/next month
        prev_month = start_date - timedelta(days=1)
        next_month = end_date + timedelta(days=1)
        prev_date = prev_month.replace(day=1).isoformat()
        next_date = next_month.isoformat()
        date_label = base_date.strftime('%Y-%m')
    else:  # daily
        start_date = base_date
        end_date = base_date
        prev_date = (base_date - timedelta(days=1)).isoformat()
        next_date = (base_date + timedelta(days=1)).isoformat()
        date_label = base_date.strftime('%Y-%m-%d')

    # Query prompts in range
    prompts_qs = Prompt.objects.filter(
        created_at__date__gte=start_date,
        created_at__date__lte=end_date,
    )
    total_count = prompts_qs.count()

    # Summary stats
    status_counts = dict(prompts_qs.values_list('status').annotate(c=Count('id')).values_list('status', 'c'))
    success_count = status_counts.get('success', 0)
    success_rate = round(success_count / total_count * 100) if total_count else 0

    # Days in range
    num_days = (end_date - start_date).days + 1
    active_days = prompts_qs.dates('created_at', 'day').count()
    avg_per_day = round(total_count / active_days, 1) if active_days else 0

    # Token usage in period
    project_ids = list(prompts_qs.values_list('project_id', flat=True).distinct())
    # Approximate: sum tokens from projects that had activity in period
    period_tokens = prompts_qs.count()  # We don't have per-prompt tokens, use count as proxy

    # ── Chart Data ──

    # 1. Activity timeline
    if mode == 'daily':
        timeline_qs = prompts_qs.annotate(
            period=TruncHour('created_at')
        ).values('period').annotate(count=Count('id')).order_by('period')
        # Fill all 24 hours
        timeline_map = {r['period'].hour: r['count'] for r in timeline_qs}
        activity_labels = [f'{h}:00' for h in range(24)]
        activity_data = [timeline_map.get(h, 0) for h in range(24)]
    elif mode == 'weekly':
        timeline_qs = prompts_qs.annotate(
            period=TruncDate('created_at')
        ).values('period').annotate(count=Count('id')).order_by('period')
        timeline_map = {r['period']: r['count'] for r in timeline_qs}
        days = [start_date + timedelta(days=i) for i in range(7)]
        day_names = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
        activity_labels = [f"{d.strftime('%m/%d')} {day_names[i]}" for i, d in enumerate(days)]
        activity_data = [timeline_map.get(d, 0) for d in days]
    else:  # monthly
        timeline_qs = prompts_qs.annotate(
            period=TruncDate('created_at')
        ).values('period').annotate(count=Count('id')).order_by('period')
        timeline_map = {r['period']: r['count'] for r in timeline_qs}
        days = [start_date + timedelta(days=i) for i in range(num_days)]
        activity_labels = [d.strftime('%m/%d') for d in days]
        activity_data = [timeline_map.get(d, 0) for d in days]

    # 2. Status distribution
    status_labels = ['Success', 'Fail', 'WIP']
    status_data = [
        status_counts.get('success', 0),
        status_counts.get('fail', 0),
        status_counts.get('wip', 0),
    ]

    # 3. Tag distribution
    tag_qs = prompts_qs.exclude(tag__isnull=True).exclude(tag='').values('tag').annotate(
        count=Count('id')
    ).order_by('-count')
    tag_labels = [r['tag'].capitalize() for r in tag_qs]
    tag_data = [r['count'] for r in tag_qs]

    # 4. Project ranking
    project_qs = prompts_qs.values('project__name').annotate(
        count=Count('id')
    ).order_by('-count')[:10]
    project_labels = [r['project__name'] or 'Unknown' for r in project_qs]
    project_data = [r['count'] for r in project_qs]

    # 5. Source distribution
    source_qs = prompts_qs.values('source').annotate(count=Count('id')).order_by('-count')
    source_labels = [r['source'].capitalize() for r in source_qs]
    source_data = [r['count'] for r in source_qs]

    # Recent prompts in period
    recent_prompts = prompts_qs.select_related('project').order_by('-created_at')[:20]

    chart_data = json.dumps({
        'activity': {'labels': activity_labels, 'data': activity_data},
        'status': {'labels': status_labels, 'data': status_data},
        'tags': {'labels': tag_labels, 'data': tag_data},
        'projects': {'labels': project_labels, 'data': project_data},
        'source': {'labels': source_labels, 'data': source_data},
    }, ensure_ascii=False)

    context = {
        'mode': mode,
        'base_date': base_date.isoformat(),
        'date_label': date_label,
        'prev_date': prev_date,
        'next_date': next_date,
        'total_count': total_count,
        'success_rate': success_rate,
        'avg_per_day': avg_per_day,
        'active_days': active_days,
        'chart_data': chart_data,
        'recent_prompts': recent_prompts,
    }
    return render(request, 'statistics.html', context)


# ── User pages ──

def user_profile(request, username):
    """Public user profile page."""
    from django.contrib.auth.models import User
    profile = get_object_or_404(UserProfile, github_username=username)
    profile_user = profile.user

    # Projects visible to current viewer
    projects_qs = visible_projects_queryset(request.user).filter(owner=profile_user)
    projects = projects_qs.annotate(
        prompt_count=Count('prompts'),
        latest_at=Max('prompts__created_at'),
    ).order_by('-latest_at')
    _attach_working_days(projects)

    # Follow status
    is_following = False
    is_friend = False
    if request.user.is_authenticated and request.user != profile_user:
        is_following = Follow.objects.filter(follower=request.user, following=profile_user).exists()
        is_friend = is_following and Follow.objects.filter(follower=profile_user, following=request.user).exists()

    follower_count = Follow.objects.filter(following=profile_user).count()
    following_count = Follow.objects.filter(follower=profile_user).count()

    context = {
        'profile': profile,
        'profile_user': profile_user,
        'projects': projects,
        'is_following': is_following,
        'is_friend': is_friend,
        'follower_count': follower_count,
        'following_count': following_count,
    }
    return render(request, 'user_profile.html', context)


def follow_user(request, username):
    """Follow a user."""
    from django.shortcuts import redirect
    if not request.user.is_authenticated:
        return redirect('github_login')
    target_profile = get_object_or_404(UserProfile, github_username=username)
    if request.user != target_profile.user:
        Follow.objects.get_or_create(follower=request.user, following=target_profile.user)
    return redirect('user-profile', username=username)


def unfollow_user(request, username):
    """Unfollow a user."""
    from django.shortcuts import redirect
    if not request.user.is_authenticated:
        return redirect('github_login')
    target_profile = get_object_or_404(UserProfile, github_username=username)
    Follow.objects.filter(follower=request.user, following=target_profile.user).delete()
    return redirect('user-profile', username=username)


def user_settings(request):
    """User settings page (API token, bio)."""
    from django.shortcuts import redirect
    if not request.user.is_authenticated:
        return redirect('github_login')

    profile = request.user.profile

    if request.method == 'POST':
        action = request.POST.get('action', '')
        if action == 'update_bio':
            profile.bio = request.POST.get('bio', '').strip()[:500]
            profile.save(update_fields=['bio', 'updated_at'])
        elif action == 'regenerate_token':
            profile.regenerate_token()
        return redirect('user-settings')

    context = {
        'profile': profile,
    }
    return render(request, 'user_settings.html', context)


# ── Federation page ──

def federation_page(request):
    """Federation page with Servers / Feed / Explore tabs."""
    tab = request.GET.get('tab', 'feed')

    identity = ServerIdentity.get_instance()
    servers = FederatedServer.objects.all()
    subscriptions = FederatedSubscription.objects.filter(is_active=True).select_related('server')

    # Feed: local public prompts + federated prompts merged
    local_prompts = Prompt.objects.filter(
        project__visibility='public',
    ).select_related('project', 'project__owner').order_by('-created_at')[:50]

    fed_prompts = FederatedPrompt.objects.select_related(
        'subscription__server', 'remote_user',
    ).order_by('-remote_created_at')[:50]

    # Merge into unified feed
    feed_items = []
    for p in local_prompts:
        owner_name = ''
        avatar_url = ''
        if p.project.owner and hasattr(p.project.owner, 'profile'):
            try:
                owner_name = p.project.owner.profile.github_username
                avatar_url = p.project.owner.profile.avatar_url
            except Exception:
                pass
        feed_items.append({
            'type': 'local',
            'id': p.id,
            'content': p.content[:300],
            'response_summary': (p.response_summary or '')[:200],
            'status': p.status,
            'tag': p.tag or '',
            'project_name': p.project.name,
            'project_id': p.project.id,
            'server_name': identity.server_name if identity else 'Local',
            'owner': owner_name,
            'avatar_url': avatar_url,
            'created_at': p.created_at,
            'tmux_session': p.tmux_session or '',
        })
    for fp in fed_prompts:
        feed_items.append({
            'type': 'remote',
            'id': fp.id,
            'content': fp.content[:300],
            'response_summary': (fp.response_summary or '')[:200],
            'status': fp.status,
            'tag': fp.tag,
            'project_name': fp.subscription.remote_project_name,
            'project_id': None,
            'server_name': fp.subscription.server.name or fp.subscription.server.url,
            'owner': fp.remote_user.federated_id if fp.remote_user else '',
            'avatar_url': '',
            'created_at': fp.remote_created_at,
            'tmux_session': '',
        })

    feed_items.sort(key=lambda x: x['created_at'], reverse=True)
    feed_items = feed_items[:50]

    # Is admin check
    is_admin = False
    if request.user.is_authenticated:
        try:
            is_admin = request.user.profile.is_admin
        except UserProfile.DoesNotExist:
            pass

    context = {
        'tab': tab,
        'identity': identity,
        'servers': servers,
        'subscriptions': subscriptions,
        'feed_items': feed_items,
        'is_admin': is_admin,
    }
    return render(request, 'federation.html', context)
