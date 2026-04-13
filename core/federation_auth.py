"""
Federation HMAC-SHA256 authentication.

Signing: HMAC-SHA256(shared_secret, "METHOD\nPATH\nTIMESTAMP\nBODY_SHA256")
Headers: X-CPM-Signature, X-CPM-Timestamp
"""
import hashlib
import hmac
import json
import time
from functools import wraps

from django.http import JsonResponse

MAX_TIMESTAMP_DRIFT = 300  # ±5 minutes
DAILY_REQUEST_LIMIT = 1000
MAX_CONSECUTIVE_ERRORS = 5


def make_signature(secret, method, path, timestamp, body=b''):
    """Create HMAC-SHA256 signature for a federation request."""
    body_hash = hashlib.sha256(body if isinstance(body, bytes) else body.encode()).hexdigest()
    message = f"{method}\n{path}\n{timestamp}\n{body_hash}"
    return hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()


def verify_signature(secret, method, path, timestamp, body, signature):
    """Verify an incoming federation request signature."""
    expected = make_signature(secret, method, path, timestamp, body)
    return hmac.compare_digest(expected, signature)


def sign_request(secret, method, path, body=b''):
    """Return headers dict for an outgoing federation request."""
    ts = str(int(time.time()))
    sig = make_signature(secret, method, path, ts, body)
    return {
        'X-CPM-Signature': sig,
        'X-CPM-Timestamp': ts,
    }


def require_federation_auth(view_func):
    """Decorator: verify HMAC signature from a peered FederatedServer."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        from datetime import date
        from core.models import FederatedServer

        signature = request.META.get('HTTP_X_CPM_SIGNATURE', '')
        timestamp = request.META.get('HTTP_X_CPM_TIMESTAMP', '')

        if not signature or not timestamp:
            return JsonResponse({'error': 'Missing federation auth headers'}, status=401)

        # Timestamp drift check
        try:
            ts = int(timestamp)
        except ValueError:
            return JsonResponse({'error': 'Invalid timestamp'}, status=401)

        if abs(time.time() - ts) > MAX_TIMESTAMP_DRIFT:
            return JsonResponse({'error': 'Timestamp too old or too far in future'}, status=401)

        # Find which server sent this by trying all active/pending servers
        body = request.body
        method = request.method
        path = request.path

        matched_server = None
        for server in FederatedServer.objects.filter(status__in=['active', 'pending']):
            if not server.shared_secret:
                continue
            if verify_signature(server.shared_secret, method, path, timestamp, body, signature):
                matched_server = server
                break

        if not matched_server:
            return JsonResponse({'error': 'Invalid signature'}, status=403)

        # Rate limiting
        today = date.today()
        if matched_server.requests_reset_date != today:
            matched_server.requests_today = 0
            matched_server.requests_reset_date = today

        if matched_server.requests_today >= DAILY_REQUEST_LIMIT:
            return JsonResponse({'error': 'Daily request limit exceeded'}, status=429)

        matched_server.requests_today += 1
        matched_server.save(update_fields=['requests_today', 'requests_reset_date'])

        # Attach server to request for use in the view
        request.federation_server = matched_server
        return view_func(request, *args, **kwargs)
    return wrapper
