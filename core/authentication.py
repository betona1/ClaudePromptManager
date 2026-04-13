from rest_framework.authentication import BaseAuthentication


class APITokenAuthentication(BaseAuthentication):
    """Authenticate via Authorization: Bearer <api_token> header.
    Used by hooks on remote machines to identify which user's project to write to.
    """
    keyword = 'Bearer'

    def authenticate(self, request):
        auth_header = request.META.get('HTTP_AUTHORIZATION', '')
        if not auth_header.startswith(f'{self.keyword} '):
            return None

        token = auth_header[len(self.keyword) + 1:].strip()
        if not token:
            return None

        from core.models import UserProfile
        try:
            profile = UserProfile.objects.select_related('user').get(api_token=token)
            return (profile.user, token)
        except UserProfile.DoesNotExist:
            return None  # Allow fallback to anonymous for backward compat
