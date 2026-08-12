"""
FIXES:
1. JWTAuthenticationMiddleware — removed select_related('organization')
2. RateLimitMiddleware — moved `from datetime import datetime` to top (was at bottom = NameError)
3. Added /api/auth/health/ to EXEMPT_PATHS
"""

from datetime import datetime
from django.utils.deprecation import MiddlewareMixin
from django.http import JsonResponse
from .jwt_utils import decode_access_token
from .models import User


class JWTAuthenticationMiddleware(MiddlewareMixin):
    """Middleware to authenticate requests using JWT tokens"""

    # Paths that skip auth entirely
    EXEMPT_PATHS = [
        '/api/auth/signup/',
        '/api/auth/login/',
        '/api/auth/refresh/',
        '/api/auth/health/',
        '/api/auth/gmail/callback/',
        # The whole agent API is directly accessible without login — the
        # chat agent itself is not account-gated. Endpoints that genuinely
        # need a real user (Gmail send, per-user settings) still require a
        # token; middleware just doesn't block them at the door, the view /
        # underlying service handles the "no account connected" case.
        '/api/agent/v1/',
        '/api/leads/upload/',  # Lead upload page (lead-upload.html) — no login required
        '/admin/',
        '/static/',
        '/campaign_demo_frontend/',
        '/test_email_config_browser.html',
    ]

    # Paths where auth is required but view handles it (middleware attaches user if token valid)
    AUTH_HANDLED_BY_VIEW = [
        '/api/auth/email-config/',
        '/api/auth/gmail/connect/',
        '/api/auth/gmail/status/',
        '/api/auth/gmail/disconnect/',
        '/api/auth/me/',
        '/api/auth/change-password/',
        '/api/auth/logout/',
    ]

    # Paths where auth is optional: attach user if token present, allow anonymous if not
    OPTIONAL_AUTH_PATHS = []

    def process_request(self, request):
        if request.path == '/' or any(request.path.startswith(path) for path in self.EXEMPT_PATHS):
            return None

        optional = any(request.path.startswith(path) for path in self.OPTIONAL_AUTH_PATHS)
        view_handles_auth = any(request.path.startswith(path) for path in self.AUTH_HANDLED_BY_VIEW)

        auth_header = request.META.get('HTTP_AUTHORIZATION', '')

        if not auth_header.startswith('Bearer '):
            if optional or view_handles_auth:
                return None  # Let view handle authentication
            import logging
            logging.getLogger(__name__).warning(
                f"JWT middleware: no Bearer header on {request.method} {request.path} — header={repr(auth_header[:30])}"
            )
            return JsonResponse({
                'error': 'Authentication required',
                'message': 'Missing or invalid Authorization header'
            }, status=401)

        token = auth_header.split(' ')[1]
        payload = decode_access_token(token)

        if not payload:
            if optional or view_handles_auth:
                return None  # Let view handle invalid token
            return JsonResponse({
                'error': 'Invalid token',
                'message': 'Token is invalid or expired'
            }, status=401)

        try:
            user = User.objects.get(id=payload['user_id'], is_active=True)
            request.user = user
            request.user_id = str(user.id)
            request.org_id = payload.get('org_id')
        except User.DoesNotExist:
            if optional or view_handles_auth:
                return None  # Let view handle user not found
            return JsonResponse({
                'error': 'User not found',
                'message': 'User associated with token does not exist'
            }, status=401)

        return None


class RateLimitMiddleware(MiddlewareMixin):
    """Simple rate limiting middleware"""
    
    def __init__(self, get_response):
        self.get_response = get_response
        self.request_counts = {}
    
    def process_request(self, request):
        # Get client IP
        ip = self.get_client_ip(request)
        
        # Rate limit: 100 requests per minute per IP
        current_minute = int(datetime.now().timestamp() / 60)
        key = f"{ip}:{current_minute}"
        
        if key in self.request_counts:
            self.request_counts[key] += 1
            if self.request_counts[key] > 100:
                return JsonResponse({
                    'error': 'Rate limit exceeded',
                    'message': 'Too many requests. Please try again later.'
                }, status=429)
        else:
            self.request_counts[key] = 1
            
            # Clean old entries
            old_keys = [k for k in self.request_counts.keys() 
                       if int(k.split(':')[1]) < current_minute - 5]
            for old_key in old_keys:
                del self.request_counts[old_key]
        
        return None
    
    @staticmethod
    def get_client_ip(request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip