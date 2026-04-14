"""Global template context processors for CPM."""
import os


def github_oauth_available(request):
    """Add OAuth availability flags to all templates."""
    return {
        'github_oauth_available': bool(
            os.environ.get('GITHUB_OAUTH_CLIENT_ID', '')
            and os.environ.get('GITHUB_OAUTH_SECRET', '')
        ),
        'google_oauth_available': bool(
            os.environ.get('GOOGLE_OAUTH_CLIENT_ID', '')
            and os.environ.get('GOOGLE_OAUTH_SECRET', '')
        ),
    }
