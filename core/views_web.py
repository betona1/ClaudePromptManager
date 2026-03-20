import json
import os
from datetime import datetime
from pathlib import Path
from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.db.models import Count, Q, Max, Min, Sum
from .models import Project, Terminal, Prompt, Template, Session, ServicePort, Execution


def _format_tokens(n):
    """Format token count: 1234567 -> '1.2M', 12345 -> '12.3K'"""
    if n >= 1_000_000:
        return f'{n / 1_000_000:.1f}M'
    elif n >= 1_000:
        return f'{n / 1_000:.1f}K'
    return str(n)


def _attach_working_days(projects):
    """Attach working_days, first_at, last_at, tokens_display to each project."""
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


def dashboard(request):
    """Main dashboard with overview stats."""
    projects = Project.objects.annotate(
        prompt_count=Count('prompts'),
        latest_at=Max('prompts__created_at'),
    ).order_by('-latest_at')

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

    context = {
        'projects': projects,
        'total': total,
        'total_days': total_days,
        'total_tokens': total_tokens,
        'total_tokens_display': _format_tokens(total_tokens),
        'recent_prompts': recent_prompts,
        'hook_count': Prompt.objects.filter(source='hook').count(),
        'import_count': Prompt.objects.filter(source='import').count(),
        'services': services,
    }
    return render(request, 'dashboard.html', context)


def project_list(request):
    projects = Project.objects.annotate(
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

    context = {
        'project': project,
        'prompts': prompts_page,
        'total': total,
        'working_days': working_days,
        'first_at': date_range['first_at'],
        'last_at': date_range['last_at'],
        'total_tokens': total_tokens,
        'tokens_display': _format_tokens(total_tokens),
        'page': page,
        'total_pages': total_pages,
        'prompt_count': prompt_count,
        'current_status': status or '',
        'current_tag': tag or '',
        'current_source': source or '',
        'current_q': q,
        'sort': sort,
        'md_files': md_files,
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


def remote_execute(request):
    """Remote Claude Code execution page."""
    projects = Project.objects.filter(path__isnull=False).exclude(path='').order_by('name')
    recent_execs = Execution.objects.select_related('project').order_by('-created_at')[:10]
    return render(request, 'remote.html', {
        'projects': projects,
        'recent_execs': recent_execs,
    })
