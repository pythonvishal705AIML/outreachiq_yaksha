from functools import wraps
from django.http import JsonResponse


def require_role(*roles):
    """Decorator to require specific user roles"""
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not hasattr(request, 'user'):
                return JsonResponse({
                    'error': 'Authentication required'
                }, status=401)
            
            if request.user.role not in roles:
                return JsonResponse({
                    'error': 'Insufficient permissions',
                    'message': f'Required role: {", ".join(roles)}'
                }, status=403)
            
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def require_org_active(view_func):
    """Decorator to check if organization is active"""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not hasattr(request, 'user'):
            return JsonResponse({
                'error': 'Authentication required'
            }, status=401)
        
        if request.user.organization and not request.user.organization.is_active:
            return JsonResponse({
                'error': 'Organization inactive',
                'message': 'Your organization account is inactive'
            }, status=403)
        
        return view_func(request, *args, **kwargs)
    return wrapper
