import os
import json
import base64
import socket
import subprocess
import urllib.request
import urllib.error
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from django.conf import settings
from django.db.models import Count, Q
from django.http import StreamingHttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from rest_framework import viewsets, filters
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.response import Response
from .models import Project, ProjectScreenshot, ProjectTodo, Terminal, Prompt, Template, Session, ServicePort, Execution, GitHubAccount
from .serializers import (
    ProjectSerializer, ProjectTodoSerializer, TerminalSerializer,
    PromptSerializer, PromptDetailSerializer, TemplateSerializer,
    SessionSerializer, ServicePortSerializer,
)


class ProjectViewSet(viewsets.ModelViewSet):
    serializer_class = ProjectSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'path', 'description']
    ordering_fields = ['name', 'created_at', 'updated_at']
    ordering = ['-updated_at']

    def get_queryset(self):
        return Project.objects.annotate(
            prompt_count=Count('prompts'),
            success_count=Count('prompts', filter=Q(prompts__status='success')),
            fail_count=Count('prompts', filter=Q(prompts__status='fail')),
            wip_count=Count('prompts', filter=Q(prompts__status='wip')),
        )


class TerminalViewSet(viewsets.ModelViewSet):
    queryset = Terminal.objects.select_related('project').all()
    serializer_class = TerminalSerializer
    filter_backends = [filters.SearchFilter]
    search_fields = ['name', 'memo']


class PromptViewSet(viewsets.ModelViewSet):
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['content', 'response_summary', 'note']
    ordering_fields = ['created_at', 'updated_at', 'status']

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return PromptDetailSerializer
        return PromptSerializer

    def get_queryset(self):
        qs = Prompt.objects.select_related('project', 'terminal').all()

        # Filter by project
        project = self.request.query_params.get('project')
        if project:
            try:
                pid = int(project)
                qs = qs.filter(project_id=pid)
            except ValueError:
                qs = qs.filter(project__name=project)

        # Filter by status
        status = self.request.query_params.get('status')
        if status:
            qs = qs.filter(status=status)

        # Filter by tag
        tag = self.request.query_params.get('tag')
        if tag:
            qs = qs.filter(tag=tag)

        # Filter by source
        source = self.request.query_params.get('source')
        if source:
            qs = qs.filter(source=source)

        # Filter by session
        session_id = self.request.query_params.get('session')
        if session_id:
            qs = qs.filter(session_id=session_id)

        return qs


class TemplateViewSet(viewsets.ModelViewSet):
    queryset = Template.objects.all()
    serializer_class = TemplateSerializer
    filter_backends = [filters.SearchFilter]
    search_fields = ['name', 'content', 'description']


class SessionViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Session.objects.select_related('project').all()
    serializer_class = SessionSerializer
    filter_backends = [filters.SearchFilter]
    search_fields = ['id', 'project_path']


class ServicePortViewSet(viewsets.ModelViewSet):
    queryset = ServicePort.objects.select_related('project').all()
    serializer_class = ServicePortSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['server_name', 'ip', 'service_name', 'remarks']
    ordering_fields = ['server_name', 'port', 'status']


def _auto_detect_github_url(project, cwd):
    """Auto-detect GitHub URL from git remote in project directory."""
    try:
        git_dir = os.path.join(cwd, '.git')
        if not os.path.isdir(git_dir):
            return
        url = subprocess.check_output(
            ['git', '-C', cwd, 'remote', 'get-url', 'origin'],
            stderr=subprocess.DEVNULL, timeout=3
        ).decode().strip()
        if 'github.com' in url:
            web_url = url.replace('.git', '').replace('git@github.com:', 'https://github.com/')
            project.github_url = web_url
            project.save(update_fields=['github_url'])
    except Exception:
        pass


@api_view(['POST'])
@authentication_classes([])
@permission_classes([])
def hook_prompt(request):
    """Remote hook endpoint: receive prompt from external machines."""
    data = request.data
    prompt_text = data.get('prompt', '').strip()
    session_id = data.get('session_id', '')
    cwd = data.get('cwd', '')
    hostname = data.get('hostname', '')

    if not prompt_text:
        return Response({'status': 'skipped', 'reason': 'empty prompt'})

    # Resolve project from cwd
    from pathlib import PurePosixPath, PureWindowsPath
    try:
        project_name = PurePosixPath(cwd).name or PureWindowsPath(cwd).name
    except Exception:
        project_name = 'unknown'

    if not project_name:
        project_name = 'unknown'

    proj, _ = Project.objects.get_or_create(
        name=project_name,
        defaults={'path': cwd, 'description': f'Auto-created from {hostname}'}
    )

    # Auto-detect GitHub URL if not set
    if not proj.github_url and cwd:
        _auto_detect_github_url(proj, cwd)

    prompt = Prompt.objects.create(
        project=proj,
        content=prompt_text,
        status='wip',
        session_id=session_id,
        source='hook',
    )

    # Ensure session
    if session_id:
        Session.objects.get_or_create(
            id=session_id,
            defaults={'project': proj, 'project_path': cwd}
        )

    return Response({'status': 'ok', 'prompt_id': prompt.id, 'project': proj.name})


@api_view(['POST'])
@authentication_classes([])
@permission_classes([])
def hook_import(request):
    """Import endpoint: receive historical prompts with dedup."""
    data = request.data
    prompt_text = data.get('prompt', '').strip()
    session_id = data.get('session_id', '')
    cwd = data.get('cwd', '')
    hostname = data.get('hostname', '')
    created_at_str = data.get('created_at')
    response_text = data.get('response', '').strip()
    source = data.get('source', 'import')

    if not prompt_text:
        return Response({'status': 'skipped', 'reason': 'empty'})

    # Resolve project
    from pathlib import PurePosixPath, PureWindowsPath
    try:
        project_name = PureWindowsPath(cwd).name or PurePosixPath(cwd).name
    except Exception:
        project_name = 'unknown'
    if not project_name:
        project_name = 'unknown'

    proj, _ = Project.objects.get_or_create(
        name=project_name,
        defaults={'path': cwd, 'description': f'Imported from {hostname}'}
    )

    # Auto-detect GitHub URL
    if not proj.github_url and cwd:
        _auto_detect_github_url(proj, cwd)

    # Dedup: same content + session_id + source=import
    if Prompt.objects.filter(content=prompt_text, session_id=session_id, source='import').exists():
        return Response({'status': 'skipped', 'reason': 'duplicate'})

    prompt = Prompt.objects.create(
        project=proj,
        content=prompt_text,
        response_summary=response_text[:500] if response_text else None,
        status='success',
        session_id=session_id,
        source=source,
    )

    # Override created_at if provided
    if created_at_str:
        try:
            ts = datetime.fromisoformat(created_at_str)
            Prompt.objects.filter(id=prompt.id).update(created_at=ts, updated_at=ts)
        except (ValueError, TypeError):
            pass

    # Ensure session
    if session_id:
        Session.objects.get_or_create(
            id=session_id,
            defaults={'project': proj, 'project_path': cwd}
        )

    return Response({'status': 'ok', 'prompt_id': prompt.id, 'project': proj.name})


@api_view(['POST'])
@authentication_classes([])
@permission_classes([])
def hook_stop(request):
    """Remote hook endpoint: receive stop event from external machines."""
    data = request.data
    session_id = data.get('session_id', '')
    response_text = data.get('response', '').strip()

    if not session_id:
        return Response({'status': 'skipped'})

    # Find the most recent wip prompt for this session
    prompt = Prompt.objects.filter(
        session_id=session_id, status='wip', source='hook'
    ).order_by('-created_at').first()

    if prompt and response_text:
        prompt.response_summary = response_text[:500]
        prompt.status = 'success'
        prompt.save(update_fields=['response_summary', 'status', 'updated_at'])
        return Response({'status': 'ok', 'prompt_id': prompt.id})

    return Response({'status': 'no_wip_found'})


@api_view(['GET'])
def stats_api(request):
    """Global statistics."""
    total = Prompt.objects.count()
    return Response({
        'total_prompts': total,
        'success': Prompt.objects.filter(status='success').count(),
        'fail': Prompt.objects.filter(status='fail').count(),
        'wip': Prompt.objects.filter(status='wip').count(),
        'projects': Project.objects.count(),
        'terminals': Terminal.objects.count(),
        'sessions': Session.objects.count(),
        'templates': Template.objects.count(),
        'sources': {
            'hook': Prompt.objects.filter(source='hook').count(),
            'import': Prompt.objects.filter(source='import').count(),
            'manual': Prompt.objects.filter(source='manual').count(),
        }
    })


# Common port → service name mapping
COMMON_PORTS = {
    22: 'SSH', 80: 'HTTP', 443: 'HTTPS', 3000: 'Node.js', 3306: 'MySQL',
    3307: 'MariaDB', 5173: 'Vite', 5432: 'PostgreSQL', 5555: 'Prisma Studio',
    6379: 'Redis', 8000: 'Django', 8001: 'Django API', 8003: 'Django API',
    8010: 'Web App', 8020: 'FastAPI', 8080: 'HTTP App', 9090: 'FastAPI',
    9200: 'CPM', 11434: 'Ollama',
}


def _check_port(host, port, timeout=0.5):
    """Check if a TCP port is open."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            return s.connect_ex((host, port)) == 0
    except Exception:
        return False


def _auto_link_project(host, port, sp):
    """Try to auto-link a ServicePort to a Project by matching URL/port."""
    if sp.project:
        return  # already linked
    from urllib.parse import urlparse
    # Build lookup: port → project from project URLs
    for proj in Project.objects.exclude(url__isnull=True).exclude(url=''):
        try:
            parsed = urlparse(proj.url)
            p_host = parsed.hostname or ''
            p_port = parsed.port
            if not p_port:
                p_port = 443 if parsed.scheme == 'https' else 80
            # Match: same port, and host matches (same IP, or localhost variants)
            local_hosts = {'127.0.0.1', 'localhost', '0.0.0.0'}
            host_match = (p_host == host
                          or (p_host in local_hosts and host in local_hosts)
                          or host in local_hosts)
            if p_port == port and host_match:
                sp.project = proj
                sp.save(update_fields=['project'])
                return
        except Exception:
            continue


@api_view(['POST'])
def discover_services(request):
    """Scan ports and update ServicePort records. Auto-link to projects."""
    host = request.data.get('host', '127.0.0.1')
    ports = request.data.get('ports', [])
    port_range = request.data.get('port_range', [])

    # Build port list
    scan_ports = set(int(p) for p in ports)
    if port_range and len(port_range) == 2:
        scan_ports.update(range(int(port_range[0]), int(port_range[1]) + 1))
    if not scan_ports:
        # Default: common ports
        scan_ports = set(COMMON_PORTS.keys())

    # Scan with ThreadPoolExecutor
    results = {'open': [], 'closed': [], 'linked': []}
    with ThreadPoolExecutor(max_workers=50) as executor:
        futures = {executor.submit(_check_port, host, p): p for p in scan_ports}
        for future in as_completed(futures):
            port = futures[future]
            if future.result():
                results['open'].append(port)
                service_name = COMMON_PORTS.get(port, f'Port {port}')
                sp, _ = ServicePort.objects.update_or_create(
                    ip=host, port=port,
                    defaults={
                        'server_name': host,
                        'service_name': service_name,
                        'status': 'active',
                    }
                )
                # Auto-link to project
                if not sp.project:
                    _auto_link_project(host, port, sp)
                    if sp.project:
                        results['linked'].append({'port': port, 'project': sp.project.name})
            else:
                results['closed'].append(port)
                ServicePort.objects.filter(ip=host, port=port).update(status='inactive')

    results['open'].sort()
    results['closed'].sort()
    return Response({
        'status': 'ok',
        'host': host,
        'open_count': len(results['open']),
        'open_ports': results['open'],
        'linked': results['linked'],
    })


# ── Project Favorite Toggle ────────────────────────────────────

@api_view(['POST'])
def toggle_favorite(request, pk):
    """Toggle favorited status of a project."""
    try:
        project = Project.objects.get(pk=pk)
    except Project.DoesNotExist:
        return Response({'error': 'Project not found'}, status=404)

    project.favorited = not project.favorited
    project.save(update_fields=['favorited'])
    return Response({'status': 'ok', 'favorited': project.favorited})


# ── Project Todos ──────────────────────────────────────────────

@api_view(['GET', 'POST'])
def project_todos(request, pk):
    """List or create todos for a project."""
    try:
        project = Project.objects.get(pk=pk)
    except Project.DoesNotExist:
        return Response({'error': 'Project not found'}, status=404)

    if request.method == 'GET':
        todos = project.todos.all()
        serializer = ProjectTodoSerializer(todos, many=True)
        total = todos.count()
        completed = todos.filter(is_completed=True).count()
        return Response({
            'status': 'ok',
            'project_id': project.id,
            'project_name': project.name,
            'total': total,
            'completed': completed,
            'todos': serializer.data,
        })

    # POST: create new todo
    title = request.data.get('title', '').strip()
    if not title:
        return Response({'error': 'title is required'}, status=400)

    category = request.data.get('category', 'task')
    if category not in ('task', 'deploy'):
        category = 'task'

    max_order = project.todos.filter(category=category).order_by('-sort_order').values_list('sort_order', flat=True).first()
    next_order = (max_order or 0) + 1

    todo = ProjectTodo.objects.create(
        project=project,
        title=title,
        category=category,
        sort_order=next_order,
    )
    return Response({
        'status': 'ok',
        'todo': ProjectTodoSerializer(todo).data,
    })


@api_view(['PATCH', 'DELETE'])
def project_todo_detail(request, pk):
    """Update or delete a single todo."""
    try:
        todo = ProjectTodo.objects.get(pk=pk)
    except ProjectTodo.DoesNotExist:
        return Response({'error': 'Todo not found'}, status=404)

    if request.method == 'DELETE':
        todo.delete()
        return Response({'status': 'ok'})

    # PATCH
    if 'title' in request.data:
        todo.title = request.data['title'].strip()
    if 'is_completed' in request.data:
        was_completed = todo.is_completed
        todo.is_completed = bool(request.data['is_completed'])
        if todo.is_completed and not was_completed:
            todo.completed_at = datetime.now()
        elif not todo.is_completed:
            todo.completed_at = None
    if 'category' in request.data:
        cat = request.data['category']
        if cat in ('task', 'deploy'):
            todo.category = cat
    if 'sort_order' in request.data:
        todo.sort_order = int(request.data['sort_order'])

    todo.save()
    return Response({
        'status': 'ok',
        'todo': ProjectTodoSerializer(todo).data,
    })


# ── Project Delete (password protected) ───────────────────────

@api_view(['POST'])
def delete_project(request, pk):
    """Delete a project after password verification."""
    password = request.data.get('password', '')
    del_password = settings.CPM_DEL_PASSWORD

    if not del_password:
        return Response({'error': 'Delete password not configured (set delpasswd in .env)'}, status=403)

    if password != del_password:
        return Response({'error': 'Incorrect password'}, status=403)

    try:
        project = Project.objects.get(pk=pk)
    except Project.DoesNotExist:
        return Response({'error': 'Project not found'}, status=404)

    name = project.name
    # Delete related screenshots files
    for ss in project.screenshots.all():
        filepath = Path(settings.BASE_DIR) / 'static' / ss.filepath
        if filepath.exists():
            filepath.unlink()

    project.delete()  # CASCADE deletes prompts, screenshots, etc.

    return Response({'status': 'ok', 'deleted': name})


# ── Remote Execution ────────────────────────────────────────────

@api_view(['POST'])
def execute_prompt(request):
    """Start a Claude Code execution. Returns execution ID."""
    prompt_text = request.data.get('prompt', '').strip()
    project_id = request.data.get('project_id')

    if not prompt_text:
        return Response({'error': 'prompt is required'}, status=400)

    # Check concurrent limit
    active = Execution.objects.filter(status__in=['queued', 'running']).exists()
    if active:
        return Response({'error': 'Another execution is already running'}, status=409)

    # Resolve project and cwd
    project = None
    cwd = ''
    if project_id:
        project = Project.objects.filter(id=project_id).first()
    if project and project.path:
        cwd = project.path

    if not cwd or not os.path.isdir(cwd):
        return Response({'error': 'Valid project with path required'}, status=400)

    # Create Prompt record for CPM tracking
    prompt_record = Prompt.objects.create(
        project=project,
        content=prompt_text,
        status='wip',
        source='manual',
    )

    execution = Execution.objects.create(
        project=project,
        prompt=prompt_record,
        command=prompt_text,
        cwd=cwd,
        status='queued',
    )

    return Response({
        'execution_id': execution.id,
        'status': 'queued',
        'stream_url': f'/api/execute/{execution.id}/stream/',
    })


def execution_stream(request, execution_id):
    """SSE endpoint that streams Claude Code output."""
    from .executor import execute_claude

    try:
        execution = Execution.objects.get(id=execution_id)
    except Execution.DoesNotExist:
        return JsonResponse({'error': 'Not found'}, status=404)

    if execution.status not in ('queued', 'running'):
        return JsonResponse({
            'status': execution.status,
            'output': execution.output,
            'error': execution.error,
            'exit_code': execution.exit_code,
        })

    def event_stream():
        for event_type, data in execute_claude(
            execution.id, execution.command, execution.cwd
        ):
            yield f"event: {event_type}\ndata: {data}\n\n"

    response = StreamingHttpResponse(
        event_stream(),
        content_type='text/event-stream'
    )
    response['Cache-Control'] = 'no-cache'
    response['X-Accel-Buffering'] = 'no'
    return response


@api_view(['POST'])
def cancel_execution_view(request, execution_id):
    """Cancel a running execution."""
    from .executor import cancel_execution
    success = cancel_execution(execution_id)
    return Response({'cancelled': success})


@api_view(['GET'])
def execution_list(request):
    """List recent executions."""
    execs = Execution.objects.select_related('project').order_by('-created_at')[:20]
    data = [{
        'id': e.id,
        'command': e.command[:100],
        'project_name': e.project.name if e.project else None,
        'status': e.status,
        'exit_code': e.exit_code,
        'duration_ms': e.duration_ms,
        'created_at': e.created_at.isoformat() if e.created_at else None,
    } for e in execs]
    return Response(data)


# ── Screenshot Upload ──────────────────────────────────────────

@csrf_exempt
@require_POST
def upload_screenshot(request, pk):
    """Upload screenshot for a project (multipart file or base64 JSON). Max 100 images."""
    try:
        project = Project.objects.get(pk=pk)
    except Project.DoesNotExist:
        return JsonResponse({'error': 'Project not found'}, status=404)

    # Check 100-image limit
    current_count = project.screenshots.count()
    if current_count >= 100:
        return JsonResponse({'error': 'Maximum 100 screenshots allowed'}, status=400)

    screenshots_dir = Path(settings.BASE_DIR) / 'static' / 'screenshots'
    screenshots_dir.mkdir(parents=True, exist_ok=True)

    # Determine next number for filename
    next_num = current_count + 1

    content_type = request.content_type or ''

    if 'multipart/form-data' in content_type:
        uploaded = request.FILES.get('file')
        if not uploaded:
            return JsonResponse({'error': 'No file provided'}, status=400)
        if not uploaded.content_type.startswith('image/'):
            return JsonResponse({'error': 'File must be an image'}, status=400)
        if uploaded.size > 10 * 1024 * 1024:
            return JsonResponse({'error': 'File too large (max 10MB)'}, status=400)

        ext = uploaded.name.rsplit('.', 1)[-1].lower() if '.' in uploaded.name else 'png'
        if ext not in ('png', 'jpg', 'jpeg', 'gif', 'webp'):
            ext = 'png'

        filename = f'{project.name}_{next_num}.{ext}'
        # Avoid filename collision
        while (screenshots_dir / filename).exists():
            next_num += 1
            filename = f'{project.name}_{next_num}.{ext}'

        with open(screenshots_dir / filename, 'wb') as f:
            for chunk in uploaded.chunks():
                f.write(chunk)

    elif 'application/json' in content_type:
        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        image_data = body.get('image', '')
        if not image_data:
            return JsonResponse({'error': 'No image data'}, status=400)

        if ',' in image_data:
            header, data = image_data.split(',', 1)
            ext = 'png'
            if 'jpeg' in header or 'jpg' in header:
                ext = 'jpg'
            elif 'webp' in header:
                ext = 'webp'
        else:
            data = image_data
            ext = 'png'

        try:
            image_bytes = base64.b64decode(data)
        except Exception:
            return JsonResponse({'error': 'Invalid base64 data'}, status=400)

        if len(image_bytes) > 10 * 1024 * 1024:
            return JsonResponse({'error': 'Image too large (max 10MB)'}, status=400)

        filename = f'{project.name}_{next_num}.{ext}'
        while (screenshots_dir / filename).exists():
            next_num += 1
            filename = f'{project.name}_{next_num}.{ext}'

        with open(screenshots_dir / filename, 'wb') as f:
            f.write(image_bytes)
    else:
        return JsonResponse({'error': 'Unsupported content type'}, status=400)

    filepath_rel = f'screenshots/{filename}'

    # Create ProjectScreenshot record
    max_order = project.screenshots.count()
    ss = ProjectScreenshot.objects.create(
        project=project,
        filepath=filepath_rel,
        order=max_order,
    )

    # Update Project.screenshot to first image
    first = project.screenshots.first()
    if first:
        project.screenshot = first.filepath
        project.save(update_fields=['screenshot', 'updated_at'])

    return JsonResponse({
        'status': 'ok',
        'screenshot_id': ss.id,
        'screenshot': filepath_rel,
        'url': f'/static/{filepath_rel}',
        'count': project.screenshots.count(),
    })


# ── GitHub Sync ────────────────────────────────────────────────

def _github_api(endpoint, token):
    """Call GitHub API and return parsed JSON."""
    url = f'https://api.github.com{endpoint}'
    req = urllib.request.Request(url, headers={
        'Authorization': f'token {token}',
        'Accept': 'application/vnd.github.v3+json',
        'User-Agent': 'CPM-Sync',
    })
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode())


def _migrate_env_github_account():
    """One-time migration: import GITHUB_TOKEN/USERNAME from .env into DB."""
    token = getattr(settings, 'GITHUB_TOKEN', '') or ''
    username = getattr(settings, 'GITHUB_USERNAME', '') or ''
    if token and username and not GitHubAccount.objects.filter(username__iexact=username).exists():
        try:
            user_data = _github_api('/user', token)
            GitHubAccount.objects.create(
                username=user_data.get('login', username),
                token=token,
                display_name=user_data.get('name', '') or '',
                avatar_url=user_data.get('avatar_url', '') or '',
            )
        except Exception:
            # Fallback: save without API validation
            GitHubAccount.objects.create(username=username, token=token)


@api_view(['GET'])
def github_accounts_list(request):
    """List all GitHub accounts."""
    _migrate_env_github_account()
    accounts = GitHubAccount.objects.all()
    data = [{
        'id': a.id,
        'username': a.username,
        'display_name': a.display_name,
        'avatar_url': a.avatar_url,
        'created_at': a.created_at.isoformat() if a.created_at else None,
    } for a in accounts]
    return Response({'accounts': data})


@api_view(['POST'])
def github_accounts_add(request):
    """Add a GitHub account. Validates token with GitHub API."""
    token = request.data.get('token', '').strip()
    username = request.data.get('username', '').strip()

    if not token or not username:
        return Response({'error': 'token and username are required'}, status=400)

    if GitHubAccount.objects.filter(username__iexact=username).exists():
        return Response({'error': f'"{username}" is already registered'}, status=400)

    # Validate token
    try:
        user_data = _github_api('/user', token)
    except urllib.error.HTTPError as e:
        return Response({'error': f'GitHub API error: {e.code}'}, status=400)
    except Exception as e:
        return Response({'error': f'Connection error: {str(e)}'}, status=400)

    account = GitHubAccount.objects.create(
        username=user_data.get('login', username),
        token=token,
        display_name=user_data.get('name', '') or '',
        avatar_url=user_data.get('avatar_url', '') or '',
    )

    return Response({
        'status': 'ok',
        'id': account.id,
        'username': account.username,
        'display_name': account.display_name,
        'avatar_url': account.avatar_url,
    })


@api_view(['POST'])
def github_accounts_delete(request, pk):
    """Delete a GitHub account. Requires delete password."""
    password = request.data.get('password', '')
    del_password = settings.CPM_DEL_PASSWORD

    if not del_password:
        return Response({'error': 'Delete password not configured (set delpasswd in .env)'}, status=403)
    if password != del_password:
        return Response({'error': 'Incorrect password'}, status=403)

    try:
        account = GitHubAccount.objects.get(pk=pk)
    except GitHubAccount.DoesNotExist:
        return Response({'error': 'Account not found'}, status=404)

    name = account.username
    account.delete()
    return Response({'status': 'ok', 'deleted': name})


@api_view(['GET'])
def github_repos(request):
    """Fetch GitHub repos for a specific account and compare with CPM projects."""
    account_id = request.query_params.get('account_id')
    if not account_id:
        return Response({'error': 'account_id is required'}, status=400)

    try:
        account = GitHubAccount.objects.get(id=account_id)
    except GitHubAccount.DoesNotExist:
        return Response({'error': 'Account not found'}, status=404)

    # Fetch all repos (paginated)
    repos = []
    page = 1
    while True:
        try:
            batch = _github_api(
                f'/users/{account.username}/repos?per_page=100&page={page}&sort=updated',
                account.token,
            )
        except urllib.error.HTTPError as e:
            return Response({'error': f'GitHub API error: {e.code}'}, status=400)
        except Exception as e:
            return Response({'error': f'Connection error: {str(e)}'}, status=400)

        if not batch:
            break
        repos.extend(batch)
        if len(batch) < 100:
            break
        page += 1

    # Get all CPM projects
    projects = {p.name.lower(): p for p in Project.objects.all()}
    projects_by_url = {}
    for p in Project.objects.exclude(github_url__isnull=True).exclude(github_url=''):
        projects_by_url[p.github_url.rstrip('/').lower()] = p

    result = []
    for repo in repos:
        repo_name = repo['name']
        repo_url = repo['html_url']
        repo_desc = repo.get('description') or ''
        is_fork = repo.get('fork', False)

        matched_project = projects_by_url.get(repo_url.lower())
        if not matched_project:
            matched_project = projects.get(repo_name.lower())

        if matched_project:
            missing_fields = []
            if not matched_project.description and repo_desc:
                missing_fields.append('description')
            if not matched_project.github_url:
                missing_fields.append('github_url')

            status = 'incomplete' if missing_fields else 'matched'
            result.append({
                'name': repo_name,
                'description': repo_desc,
                'html_url': repo_url,
                'fork': is_fork,
                'status': status,
                'project_id': matched_project.id,
                'project_name': matched_project.name,
                'missing_fields': missing_fields,
            })
        else:
            result.append({
                'name': repo_name,
                'description': repo_desc,
                'html_url': repo_url,
                'fork': is_fork,
                'status': 'missing',
                'project_id': None,
                'project_name': None,
                'missing_fields': [],
            })

    return Response({
        'status': 'ok',
        'username': account.username,
        'total': len(repos),
        'repos': result,
    })


@api_view(['POST'])
def github_sync(request):
    """Sync selected repos: create missing projects, update incomplete ones."""
    repos = request.data.get('repos', [])

    if not repos:
        return Response({'error': 'No repos selected'}, status=400)

    created = []
    updated = []

    for repo in repos:
        name = repo.get('name', '')
        html_url = repo.get('html_url', '')
        description = repo.get('description', '')
        status = repo.get('status', '')
        project_id = repo.get('project_id')

        if status == 'missing':
            proj = Project.objects.create(
                name=name,
                description=description or f'GitHub: {name}',
                github_url=html_url,
            )
            created.append({'name': proj.name, 'id': proj.id})

        elif status == 'incomplete' and project_id:
            try:
                proj = Project.objects.get(id=project_id)
                changed = []
                if not proj.description and description:
                    proj.description = description
                    changed.append('description')
                if not proj.github_url and html_url:
                    proj.github_url = html_url
                    changed.append('github_url')
                if changed:
                    proj.save(update_fields=changed + ['updated_at'])
                    updated.append({'name': proj.name, 'id': proj.id, 'fields': changed})
            except Project.DoesNotExist:
                pass

    return Response({
        'status': 'ok',
        'created': created,
        'updated': updated,
    })


@csrf_exempt
def delete_screenshot(request, pk):
    """Delete a single screenshot by ProjectScreenshot ID."""
    if request.method != 'DELETE':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    try:
        ss = ProjectScreenshot.objects.select_related('project').get(pk=pk)
    except ProjectScreenshot.DoesNotExist:
        return JsonResponse({'error': 'Screenshot not found'}, status=404)

    project = ss.project

    # Delete file
    filepath = Path(settings.BASE_DIR) / 'static' / ss.filepath
    if filepath.exists():
        filepath.unlink()

    ss.delete()

    # Re-order remaining
    for i, remaining in enumerate(project.screenshots.all()):
        if remaining.order != i:
            remaining.order = i
            remaining.save(update_fields=['order'])

    # Update Project.screenshot to first image (or clear)
    first = project.screenshots.first()
    project.screenshot = first.filepath if first else ''
    project.save(update_fields=['screenshot', 'updated_at'])

    return JsonResponse({'status': 'ok', 'count': project.screenshots.count()})
