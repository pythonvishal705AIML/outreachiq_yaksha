from django.utils.deprecation import MiddlewareMixin
from django.http import JsonResponse
from .jwt_utils import decode_access_token
from .models import User


class JWTAuthenticationMiddleware(MiddlewareMixin):
    """Middleware to authenticate requests using JWT tokens"""
    
    # Paths that don't require authentication
    EXEMPT_PATHS = [
        '/api/auth/signup/',
        '/api/auth/login/',
        '/api/auth/refresh/',
        '/api/auth/health/',
        '/admin/',
        '/static/',
    ]
    
    def process_request(self, request):
        # Skip authentication for exempt paths
        if any(request.path.startswith(path) for path in self.EXEMPT_PATHS):
            return None
        
        # Get token from Authorization header
        auth_header = request.META.get('HTTP_AUTHORIZATION', '')
        
        if not auth_header.startswith('Bearer '):
            return JsonResponse({
                'error': 'Authentication required',
                'message': 'Missing or invalid Authorization header'
            }, status=401)
        
        token = auth_header.split(' ')[1]
        
        # Decode and validate token
        payload = decode_access_token(token)
        
        if not payload:
            return JsonResponse({
                'error': 'Invalid token',
                'message': 'Token is invalid or expired'
            }, status=401)
        
        # Get user from database
        try:
            user = User.objects.get(
                id=payload['user_id'],
                is_active=True
            )
            
            # Attach user and IDs to request
            request.user = user
            request.user_id = str(user.id)
            
            # Set all ID aliases for compatibility with existing code
            request.account_id = user.account_id
            request.org_id = user.account_id  # org_id is same as account_id
            request.tenant_id = user.account_id  # tenant_id is same as account_id
            
        except User.DoesNotExist:
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
        from datetime import datetime
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
