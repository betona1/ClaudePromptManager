import os
import socket
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from django.db.models import Count, Q
from django.http import StreamingHttpResponse, JsonResponse
from rest_framework import viewsets, filters
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.response import Response
from .models import Project, Terminal, Prompt, Template, Session, ServicePort, Execution
from .serializers import (
    ProjectSerializer, TerminalSerializer, PromptSerializer,
    PromptDetailSerializer, TemplateSerializer, SessionSerializer,
    ServicePortSerializer,
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


@api_view(['POST'])
def discover_services(request):
    """Scan ports and update ServicePort records."""
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
    results = {'open': [], 'closed': []}
    with ThreadPoolExecutor(max_workers=50) as executor:
        futures = {executor.submit(_check_port, host, p): p for p in scan_ports}
        for future in as_completed(futures):
            port = futures[future]
            if future.result():
                results['open'].append(port)
                service_name = COMMON_PORTS.get(port, f'Port {port}')
                ServicePort.objects.update_or_create(
                    ip=host, port=port,
                    defaults={
                        'server_name': host,
                        'service_name': service_name,
                        'status': 'active',
                    }
                )
            else:
                results['closed'].append(port)
                # Mark existing as inactive
                ServicePort.objects.filter(ip=host, port=port).update(status='inactive')

    results['open'].sort()
    results['closed'].sort()
    return Response({
        'status': 'ok',
        'host': host,
        'open_count': len(results['open']),
        'open_ports': results['open'],
    })


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
