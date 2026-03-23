import json
import os
from datetime import datetime, date, timedelta
from pathlib import Path
from django.conf import settings
from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.db.models import Count, Q, Max, Min, Sum, Exists, OuterRef
from django.db.models.functions import TruncHour, TruncDate
from .models import Project, ProjectScreenshot, Terminal, Prompt, Template, Session, ServicePort, Execution


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
    """Main dashboard with overview stats."""
    projects = Project.objects.prefetch_related('screenshots', 'todos').annotate(
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

    # Today's prompts
    today = date.today()
    today_count = Prompt.objects.filter(created_at__date=today).count()

    context = {
        'projects': projects,
        'total': total,
        'total_days': total_days,
        'total_tokens': total_tokens,
        'total_tokens_display': _format_tokens(total_tokens),
        'recent_prompts': recent_prompts,
        'today_count': today_count,
        'hook_count': Prompt.objects.filter(source='hook').count(),
        'import_count': Prompt.objects.filter(source='import').count(),
        'services': services,
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

    if filename == 'cpm-hooks.zip':
        # Build zip with both hook files + settings.json template
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
            for fname in ['on_prompt_remote.py', 'on_stop_remote.py', 'import_history.py']:
                hook_path = Path(settings.BASE_DIR) / 'hooks' / fname
                if hook_path.exists():
                    content = hook_path.read_text(encoding='utf-8')
                    content = content.replace(
                        "CPM_SERVER = os.environ.get('CPM_SERVER', 'http://localhost:9200')",
                        f"CPM_SERVER = os.environ.get('CPM_SERVER', '{server_url}')"
                    )
                    zf.writestr(f'cpm/{fname}', content)

            # Include a ready-to-use settings.json
            settings_json = json.dumps({
                "hooks": {
                    "UserPromptSubmit": [{
                        "type": "command",
                        "command": "python C:\\cpm\\on_prompt_remote.py"
                    }],
                    "Stop": [{
                        "type": "command",
                        "command": "python C:\\cpm\\on_stop_remote.py"
                    }]
                }
            }, indent=2, ensure_ascii=False)
            zf.writestr('cpm/settings.json', settings_json)

            # README
            readme = f"""CPM Remote Hooks
================

1. cpm 폴더를 C:\\ 에 복사  ->  C:\\cpm\\
2. settings.json 을 %USERPROFILE%\\.claude\\ 에 복사
   (Windows Terminal에서 실행하는 Claude Code CLI 설정 위치)
3. Claude Code 재시작하면 자동 기록!

기존 기록 가져오기:
  python C:\\cpm\\import_history.py

서버: {server_url}

* Python이 설치되어 있어야 합니다.
* 이미 settings.json이 있으면 hooks 부분만 합쳐주세요.
"""
            zf.writestr('cpm/README.txt', readme)

        buf.seek(0)
        response = HttpResponse(buf.read(), content_type='application/zip')
        response['Content-Disposition'] = 'attachment; filename="cpm-hooks.zip"'
        return response

    # Single file download (fallback)
    allowed = {'on_prompt_remote.py', 'on_stop_remote.py'}
    if filename not in allowed:
        return HttpResponse('Not found', status=404)

    hook_path = Path(settings.BASE_DIR) / 'hooks' / filename
    if not hook_path.exists():
        return HttpResponse('File not found', status=404)

    content = hook_path.read_text(encoding='utf-8')
    content = content.replace(
        "CPM_SERVER = os.environ.get('CPM_SERVER', 'http://localhost:9200')",
        f"CPM_SERVER = os.environ.get('CPM_SERVER', '{server_url}')"
    )

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
