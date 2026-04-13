import os

from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'

    def ready(self):
        import core.signals  # noqa: F401

        # Auto-create GitHub SocialApp after migrations are done
        from django.db.models.signals import post_migrate
        post_migrate.connect(_auto_create_github_socialapp, sender=self)


def _auto_create_github_socialapp(sender, **kwargs):
    """Create GitHub SocialApp from env vars after migrate."""
    try:
        client_id = os.environ.get('GITHUB_OAUTH_CLIENT_ID', '')
        secret = os.environ.get('GITHUB_OAUTH_SECRET', '')
        if not client_id or not secret:
            return

        from allauth.socialaccount.models import SocialApp
        from django.contrib.sites.models import Site

        app, created = SocialApp.objects.get_or_create(
            provider='github',
            defaults={
                'name': 'GitHub',
                'client_id': client_id,
                'secret': secret,
            }
        )
        if not created and (app.client_id != client_id or app.secret != secret):
            app.client_id = client_id
            app.secret = secret
            app.save(update_fields=['client_id', 'secret'])

        site = Site.objects.first()
        if site and not app.sites.filter(id=site.id).exists():
            app.sites.add(site)
    except Exception:
        pass
