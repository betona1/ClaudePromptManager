"""
Federation API views for server-to-server communication.
"""
import json
import urllib.request
import urllib.error
from datetime import datetime

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST, require_GET
from django.db.models import Count, Q

from .models import (
    ServerIdentity, FederatedServer, FederatedSubscription,
    FederatedPrompt, FederatedUser, FederatedComment,
    Project, Prompt, UserProfile,
)
from .federation_auth import (
    require_federation_auth, sign_request, make_signature,
    MAX_CONSECUTIVE_ERRORS,
)


# ── Public metadata ──

@require_GET
def well_known(request):
    """Public federation metadata endpoint."""
    identity = ServerIdentity.get_instance()
    if not identity:
        return JsonResponse({'error': 'Federation not initialized'}, status=404)

    return JsonResponse({
        'protocol_version': '1.0',
        'server_name': identity.server_name,
        'server_url': identity.server_url,
        'description': identity.description,
        'user_count': UserProfile.objects.count(),
        'public_project_count': Project.objects.filter(visibility='public').count(),
    })


# ── Pairing protocol ──

@csrf_exempt
@require_POST
def pair_request(request):
    """Receive a pairing request from a remote server.
    Body: { "server_url": "...", "server_name": "...", "token": "..." }
    """
    identity = ServerIdentity.get_instance()
    if not identity:
        return JsonResponse({'error': 'Federation not initialized'}, status=404)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    remote_url = data.get('server_url', '').rstrip('/')
    remote_name = data.get('server_name', '')
    remote_token = data.get('token', '')

    if not remote_url or not remote_token:
        return JsonResponse({'error': 'Missing server_url or token'}, status=400)

    server, created = FederatedServer.objects.get_or_create(
        url=remote_url,
        defaults={
            'name': remote_name,
            'status': 'pending',
            'their_token': remote_token,
        }
    )

    if not created:
        if server.status == 'blocked':
            return JsonResponse({'error': 'Server is blocked'}, status=403)
        server.their_token = remote_token
        server.name = remote_name or server.name
        server.status = 'pending'
        server.save(update_fields=['their_token', 'name', 'status', 'updated_at'])

    return JsonResponse({
        'status': 'pending',
        'server_name': identity.server_name,
        'server_url': identity.server_url,
        'token': server.our_token,
        'message': 'Pairing request received. Admin approval required.',
    })


@csrf_exempt
@require_POST
def pair_accept(request):
    """Accept a pending pairing request (admin only).
    Body: { "server_url": "..." }
    """
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Login required'}, status=401)

    try:
        profile = request.user.profile
        if not profile.is_admin:
            return JsonResponse({'error': 'Admin only'}, status=403)
    except UserProfile.DoesNotExist:
        return JsonResponse({'error': 'Admin only'}, status=403)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    remote_url = data.get('server_url', '').rstrip('/')
    try:
        server = FederatedServer.objects.get(url=remote_url)
    except FederatedServer.DoesNotExist:
        return JsonResponse({'error': 'Server not found'}, status=404)

    if server.status == 'blocked':
        return JsonResponse({'error': 'Server is blocked'}, status=403)

    # Derive shared secret and activate
    server.status = 'active'
    server.derive_shared_secret()

    # Notify remote server
    identity = ServerIdentity.get_instance()
    if identity:
        _notify_pair_accepted(server, identity)

    return JsonResponse({
        'status': 'active',
        'server': server.name or server.url,
    })


def _notify_pair_accepted(server, identity):
    """Notify remote server that pairing was accepted."""
    try:
        payload = json.dumps({
            'server_url': identity.server_url,
            'server_name': identity.server_name,
            'token': server.our_token,
            'status': 'active',
        }).encode()

        path = '/api/federation/pair/confirm/'
        headers = sign_request(server.shared_secret, 'POST', path, payload)
        headers['Content-Type'] = 'application/json'

        req = urllib.request.Request(
            f"{server.url}{path}",
            data=payload,
            headers=headers,
            method='POST',
        )
        urllib.request.urlopen(req, timeout=10)
    except Exception:
        pass  # Non-blocking


@csrf_exempt
@require_POST
def pair_confirm(request):
    """Receive confirmation that our pairing request was accepted.
    Called by remote server after admin approves.
    """
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    remote_url = data.get('server_url', '').rstrip('/')
    remote_token = data.get('token', '')

    try:
        server = FederatedServer.objects.get(url=remote_url)
    except FederatedServer.DoesNotExist:
        return JsonResponse({'error': 'Unknown server'}, status=404)

    if data.get('status') == 'active':
        server.their_token = remote_token or server.their_token
        server.status = 'active'
        server.derive_shared_secret()

    return JsonResponse({'status': server.status})


# ── Server management (admin) ──

@csrf_exempt
@require_POST
def server_action(request):
    """Admin actions: block, unblock, delete a federated server.
    Body: { "server_id": N, "action": "block|unblock|delete" }
    """
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Login required'}, status=401)
    try:
        if not request.user.profile.is_admin:
            return JsonResponse({'error': 'Admin only'}, status=403)
    except UserProfile.DoesNotExist:
        return JsonResponse({'error': 'Admin only'}, status=403)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    server_id = data.get('server_id')
    action = data.get('action', '')

    try:
        server = FederatedServer.objects.get(id=server_id)
    except FederatedServer.DoesNotExist:
        return JsonResponse({'error': 'Server not found'}, status=404)

    if action == 'block':
        server.status = 'blocked'
        server.save(update_fields=['status', 'updated_at'])
    elif action == 'unblock':
        server.status = 'active'
        server.error_count = 0
        server.save(update_fields=['status', 'error_count', 'updated_at'])
    elif action == 'delete':
        server.delete()
        return JsonResponse({'status': 'deleted'})
    else:
        return JsonResponse({'error': 'Unknown action'}, status=400)

    return JsonResponse({'status': server.status})


@csrf_exempt
@require_POST
def add_server(request):
    """Admin: initiate pairing with a remote server.
    Body: { "server_url": "https://remote-cpm.example.com" }
    """
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Login required'}, status=401)
    try:
        if not request.user.profile.is_admin:
            return JsonResponse({'error': 'Admin only'}, status=403)
    except UserProfile.DoesNotExist:
        return JsonResponse({'error': 'Admin only'}, status=403)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    remote_url = data.get('server_url', '').rstrip('/')
    if not remote_url:
        return JsonResponse({'error': 'Missing server_url'}, status=400)

    identity = ServerIdentity.get_instance()
    if not identity:
        return JsonResponse({'error': 'Federation not initialized. Run: python manage.py cpm_federation init'}, status=400)

    # 1. Fetch remote metadata
    try:
        meta_req = urllib.request.Request(f"{remote_url}/.well-known/cpm-federation")
        meta_resp = urllib.request.urlopen(meta_req, timeout=10)
        meta = json.loads(meta_resp.read())
    except Exception as e:
        return JsonResponse({'error': f'Cannot reach remote server: {e}'}, status=400)

    # 2. Create local record
    server, created = FederatedServer.objects.get_or_create(
        url=remote_url,
        defaults={
            'name': meta.get('server_name', ''),
            'description': meta.get('description', ''),
            'status': 'pending',
        }
    )

    # 3. Send pairing request to remote
    try:
        payload = json.dumps({
            'server_url': identity.server_url,
            'server_name': identity.server_name,
            'token': server.our_token,
        }).encode()

        req = urllib.request.Request(
            f"{remote_url}/api/federation/pair/request/",
            data=payload,
            headers={'Content-Type': 'application/json'},
            method='POST',
        )
        resp = urllib.request.urlopen(req, timeout=10)
        resp_data = json.loads(resp.read())

        # Store their token
        if resp_data.get('token'):
            server.their_token = resp_data['token']
            server.save(update_fields=['their_token', 'updated_at'])

    except Exception as e:
        return JsonResponse({
            'status': 'created_locally',
            'error': f'Pairing request failed: {e}',
            'server_id': server.id,
        })

    return JsonResponse({
        'status': 'pending',
        'server_id': server.id,
        'remote_name': meta.get('server_name', ''),
        'message': 'Pairing request sent. Waiting for remote admin approval.',
    })


# ── Public project feed (for remote servers to browse) ──

@require_GET
def public_projects(request):
    """List public projects (for remote server browsing)."""
    projects = Project.objects.filter(visibility='public').annotate(
        prompt_count=Count('prompts'),
    ).order_by('-updated_at')[:50]

    return JsonResponse({
        'projects': [
            {
                'id': p.id,
                'name': p.name,
                'description': p.description or '',
                'prompt_count': p.prompt_count,
                'owner': p.owner.profile.github_username if p.owner and hasattr(p.owner, 'profile') else '',
                'updated_at': p.updated_at.isoformat(),
            }
            for p in projects
        ]
    })


@require_GET
def public_project_prompts(request, project_id):
    """List prompts from a public project (for sync / browsing).
    Query params: ?after=<prompt_id>&limit=50
    """
    try:
        project = Project.objects.get(id=project_id, visibility='public')
    except Project.DoesNotExist:
        return JsonResponse({'error': 'Project not found or not public'}, status=404)

    after = int(request.GET.get('after', 0))
    limit = min(int(request.GET.get('limit', 50)), 100)

    prompts = Prompt.objects.filter(
        project=project, id__gt=after,
    ).order_by('id')[:limit]

    owner_username = ''
    if project.owner and hasattr(project.owner, 'profile'):
        owner_username = project.owner.profile.github_username

    return JsonResponse({
        'project_id': project.id,
        'project_name': project.name,
        'prompts': [
            {
                'id': p.id,
                'content': p.content,
                'response_summary': p.response_summary or '',
                'status': p.status,
                'tag': p.tag or '',
                'created_at': p.created_at.isoformat(),
                'owner': owner_username,
            }
            for p in prompts
        ]
    })


# ── Subscription management ──

@csrf_exempt
@require_POST
def subscribe(request):
    """Subscribe to a remote project.
    Body: { "server_id": N, "remote_project_id": N, "remote_project_name": "..." }
    """
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Login required'}, status=401)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    server_id = data.get('server_id')
    remote_project_id = data.get('remote_project_id')
    remote_project_name = data.get('remote_project_name', '')

    try:
        server = FederatedServer.objects.get(id=server_id, status='active')
    except FederatedServer.DoesNotExist:
        return JsonResponse({'error': 'Server not found or not active'}, status=404)

    sub, created = FederatedSubscription.objects.get_or_create(
        server=server,
        remote_project_id=remote_project_id,
        defaults={'remote_project_name': remote_project_name}
    )

    if not created:
        sub.is_active = True
        sub.save(update_fields=['is_active', 'updated_at'])

    return JsonResponse({
        'status': 'subscribed',
        'subscription_id': sub.id,
        'created': created,
    })


@csrf_exempt
@require_POST
def unsubscribe(request):
    """Unsubscribe from a remote project.
    Body: { "subscription_id": N }
    """
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Login required'}, status=401)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    sub_id = data.get('subscription_id')
    try:
        sub = FederatedSubscription.objects.get(id=sub_id)
        sub.is_active = False
        sub.save(update_fields=['is_active', 'updated_at'])
    except FederatedSubscription.DoesNotExist:
        return JsonResponse({'error': 'Subscription not found'}, status=404)

    return JsonResponse({'status': 'unsubscribed'})


# ── Push sync endpoint (receive prompts from remote) ──

@csrf_exempt
@require_POST
@require_federation_auth
def push_prompts(request):
    """Receive pushed prompts from a peered server.
    Body: { "project_id": N, "project_name": "...", "prompts": [...] }
    """
    server = request.federation_server

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    remote_project_id = data.get('project_id')
    remote_project_name = data.get('project_name', '')
    prompts_data = data.get('prompts', [])

    if not remote_project_id or not prompts_data:
        return JsonResponse({'error': 'Missing project_id or prompts'}, status=400)

    # Find or create subscription
    sub, _ = FederatedSubscription.objects.get_or_create(
        server=server,
        remote_project_id=remote_project_id,
        defaults={'remote_project_name': remote_project_name, 'is_active': True}
    )

    created_count = 0
    for p in prompts_data:
        remote_id = p.get('id')
        if not remote_id:
            continue

        # Resolve remote user
        remote_user = None
        owner_name = p.get('owner', '')
        if owner_name:
            from urllib.parse import urlparse
            domain = urlparse(server.url).hostname or server.url
            fed_id = f"{owner_name}@{domain}"
            remote_user, _ = FederatedUser.objects.get_or_create(
                federated_id=fed_id,
                defaults={
                    'username': owner_name,
                    'server': server,
                }
            )

        _, created = FederatedPrompt.objects.get_or_create(
            subscription=sub,
            remote_prompt_id=remote_id,
            defaults={
                'content': p.get('content', ''),
                'response_summary': p.get('response_summary', ''),
                'status': p.get('status', 'wip'),
                'tag': p.get('tag', ''),
                'remote_user': remote_user,
                'remote_created_at': p.get('created_at', datetime.now().isoformat()),
            }
        )
        if created:
            created_count += 1

    # Update sync cursor
    if prompts_data:
        max_id = max(p.get('id', 0) for p in prompts_data)
        if max_id > sub.last_prompt_id:
            sub.last_prompt_id = max_id
            sub.save(update_fields=['last_prompt_id', 'updated_at'])

    # Reset error count on success
    server.error_count = 0
    server.last_sync_at = datetime.now()
    server.save(update_fields=['error_count', 'last_sync_at', 'updated_at'])

    return JsonResponse({
        'status': 'ok',
        'received': len(prompts_data),
        'created': created_count,
    })


# ── Push comment endpoint ──

@csrf_exempt
@require_POST
@require_federation_auth
def push_comment(request):
    """Receive a comment from a peered server.
    Body: { "prompt_id": N, "project_id": N, "author": "user@server",
            "content": "...", "remote_comment_id": "..." }
    """
    server = request.federation_server

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    prompt_id = data.get('prompt_id')
    content = data.get('content', '').strip()
    author_fed_id = data.get('author', '')
    remote_comment_id = data.get('remote_comment_id', '')

    if not content:
        return JsonResponse({'error': 'Empty comment'}, status=400)

    # Find local prompt
    prompt = None
    federated_prompt = None

    if prompt_id:
        try:
            prompt = Prompt.objects.get(id=prompt_id)
        except Prompt.DoesNotExist:
            pass

    if not prompt:
        # Maybe it's a federated prompt
        remote_prompt_id = data.get('remote_prompt_id')
        if remote_prompt_id:
            try:
                federated_prompt = FederatedPrompt.objects.get(
                    subscription__server=server,
                    remote_prompt_id=remote_prompt_id,
                )
            except FederatedPrompt.DoesNotExist:
                pass

    if not prompt and not federated_prompt:
        return JsonResponse({'error': 'Prompt not found'}, status=404)

    author_name = author_fed_id.split('@')[0] if '@' in author_fed_id else author_fed_id

    FederatedComment.objects.get_or_create(
        remote_comment_id=remote_comment_id,
        defaults={
            'prompt': prompt,
            'federated_prompt': federated_prompt,
            'author_name': author_name,
            'author_federated_id': author_fed_id,
            'content': content,
        }
    )

    return JsonResponse({'status': 'ok'})


# ── Federation status API ──

@require_GET
def federation_status(request):
    """Get federation status for the UI."""
    identity = ServerIdentity.get_instance()

    servers = FederatedServer.objects.all()
    subscriptions = FederatedSubscription.objects.filter(is_active=True).select_related('server')

    # Recent federated prompts for feed
    feed_prompts = FederatedPrompt.objects.select_related(
        'subscription__server', 'remote_user'
    ).order_by('-remote_created_at')[:30]

    return JsonResponse({
        'initialized': identity is not None,
        'identity': {
            'server_name': identity.server_name,
            'server_url': identity.server_url,
            'description': identity.description,
        } if identity else None,
        'servers': [
            {
                'id': s.id,
                'url': s.url,
                'name': s.name,
                'status': s.status,
                'last_sync_at': s.last_sync_at.isoformat() if s.last_sync_at else None,
                'error_count': s.error_count,
                'requests_today': s.requests_today,
                'created_at': s.created_at.isoformat(),
            }
            for s in servers
        ],
        'subscriptions': [
            {
                'id': sub.id,
                'server_name': sub.server.name or sub.server.url,
                'server_id': sub.server.id,
                'remote_project_id': sub.remote_project_id,
                'remote_project_name': sub.remote_project_name,
                'last_prompt_id': sub.last_prompt_id,
                'is_active': sub.is_active,
            }
            for sub in subscriptions
        ],
        'feed': [
            {
                'id': fp.id,
                'content': fp.content[:200],
                'response_summary': (fp.response_summary or '')[:200],
                'status': fp.status,
                'tag': fp.tag,
                'server_name': fp.subscription.server.name or fp.subscription.server.url,
                'project_name': fp.subscription.remote_project_name,
                'remote_user': fp.remote_user.federated_id if fp.remote_user else '',
                'remote_created_at': fp.remote_created_at.isoformat(),
            }
            for fp in feed_prompts
        ],
    })


# ── Explore remote server projects ──

@require_GET
def explore_server(request, server_id):
    """Fetch public projects from a remote server (proxy for UI)."""
    try:
        server = FederatedServer.objects.get(id=server_id, status='active')
    except FederatedServer.DoesNotExist:
        return JsonResponse({'error': 'Server not found or not active'}, status=404)

    try:
        req = urllib.request.Request(f"{server.url}/api/federation/projects/")
        resp = urllib.request.urlopen(req, timeout=10)
        data = json.loads(resp.read())
    except Exception as e:
        return JsonResponse({'error': f'Cannot reach server: {e}'}, status=502)

    # Mark which projects we're already subscribed to
    subscribed_ids = set(
        FederatedSubscription.objects.filter(
            server=server, is_active=True,
        ).values_list('remote_project_id', flat=True)
    )

    for p in data.get('projects', []):
        p['subscribed'] = p['id'] in subscribed_ids

    return JsonResponse(data)
