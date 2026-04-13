import json
import logging
import threading
import urllib.request
import urllib.error

from django.db.models.signals import post_save
from django.dispatch import receiver
from allauth.account.signals import user_signed_up

logger = logging.getLogger(__name__)


@receiver(user_signed_up)
def create_profile_on_signup(sender, request, user, **kwargs):
    """Create UserProfile when a new user signs up via GitHub OAuth."""
    from core.models import UserProfile, Project

    social_accounts = user.socialaccount_set.filter(provider='github')
    github_username = user.username
    avatar_url = ''
    bio = ''

    if social_accounts.exists():
        sa = social_accounts.first()
        extra = sa.extra_data
        github_username = extra.get('login', user.username)
        avatar_url = extra.get('avatar_url', '')
        bio = extra.get('bio', '') or ''

    profile, created = UserProfile.objects.get_or_create(
        user=user,
        defaults={
            'github_username': github_username,
            'avatar_url': avatar_url,
            'bio': bio,
        }
    )

    # First user ever = admin, claims all existing unowned projects
    if created and UserProfile.objects.count() == 1:
        profile.is_admin = True
        profile.save(update_fields=['is_admin'])
        Project.objects.filter(owner__isnull=True).update(owner=user)


# ── Federation push sync ──

@receiver(post_save, sender='core.Prompt')
def push_prompt_to_federation(sender, instance, created, **kwargs):
    """When a prompt is saved on a public project, push to subscribed servers."""
    if not created:
        return

    # Only push public project prompts
    project = instance.project
    if project.visibility != 'public':
        return

    # Fire and forget in a daemon thread (never block hooks)
    t = threading.Thread(target=_do_push_prompt, args=(instance.id,), daemon=True)
    t.start()


def _do_push_prompt(prompt_id):
    """Push a single prompt to all active federated servers (runs in background thread)."""
    try:
        from core.models import Prompt, FederatedServer, ServerIdentity
        from core.federation_auth import sign_request

        prompt = Prompt.objects.select_related('project', 'project__owner').get(id=prompt_id)
        project = prompt.project
        identity = ServerIdentity.get_instance()
        if not identity:
            return

        owner_username = ''
        if project.owner and hasattr(project.owner, 'profile'):
            try:
                owner_username = project.owner.profile.github_username
            except Exception:
                pass

        payload = json.dumps({
            'project_id': project.id,
            'project_name': project.name,
            'prompts': [{
                'id': prompt.id,
                'content': prompt.content,
                'response_summary': prompt.response_summary or '',
                'status': prompt.status,
                'tag': prompt.tag or '',
                'created_at': prompt.created_at.isoformat(),
                'owner': owner_username,
            }],
        }).encode()

        path = '/api/federation/push/prompts/'

        for server in FederatedServer.objects.filter(status='active'):
            if not server.shared_secret:
                continue
            try:
                headers = sign_request(server.shared_secret, 'POST', path, payload)
                headers['Content-Type'] = 'application/json'
                req = urllib.request.Request(
                    f"{server.url}{path}",
                    data=payload,
                    headers=headers,
                    method='POST',
                )
                urllib.request.urlopen(req, timeout=10)
                server.error_count = 0
                server.save(update_fields=['error_count'])
            except Exception as e:
                logger.warning(f"Federation push to {server.url} failed: {e}")
                server.error_count += 1
                if server.error_count >= 5:
                    server.status = 'suspended'
                server.save(update_fields=['error_count', 'status'])
    except Exception as e:
        logger.warning(f"Federation push error: {e}")
