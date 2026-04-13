"""Global template context processors for CPM."""
import os


def github_oauth_available(request):
    """Add github_oauth_available flag to all templates."""
    return {
        'github_oauth_available': bool(
            os.environ.get('GITHUB_OAUTH_CLIENT_ID', '')
            and os.environ.get('GITHUB_OAUTH_SECRET', '')
        ),
    }
