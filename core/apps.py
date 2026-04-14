import os

from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'

    def ready(self):
        import core.signals  # noqa: F401

        from django.db.models.signals import post_migrate
        post_migrate.connect(_auto_create_social_apps, sender=self)


def _auto_create_social_apps(sender, **kwargs):
    """Create SocialApps from env vars after migrate."""
    try:
        from allauth.socialaccount.models import SocialApp
        from django.contrib.sites.models import Site

        site = Site.objects.first()

        providers = [
            ('github', 'GitHub', 'GITHUB_OAUTH_CLIENT_ID', 'GITHUB_OAUTH_SECRET'),
            ('google', 'Google', 'GOOGLE_OAUTH_CLIENT_ID', 'GOOGLE_OAUTH_SECRET'),
        ]

        for provider, name, id_env, secret_env in providers:
            client_id = os.environ.get(id_env, '')
            secret = os.environ.get(secret_env, '')
            if not client_id or not secret:
                continue

            app, created = SocialApp.objects.get_or_create(
                provider=provider,
                defaults={
                    'name': name,
                    'client_id': client_id,
                    'secret': secret,
                }
            )
            if not created and (app.client_id != client_id or app.secret != secret):
                app.client_id = client_id
                app.secret = secret
                app.save(update_fields=['client_id', 'secret'])

            if site and not app.sites.filter(id=site.id).exists():
                app.sites.add(site)
    except Exception:
        pass
