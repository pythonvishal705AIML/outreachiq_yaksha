"""
Activity tracking utilities for logging user actions
"""

from .activity_models import (
    UserActivity, PageView, UserSession, 
    APIUsage, FeatureUsage, AuditLog
)
from django.utils import timezone
import time


class ActivityTracker:
    """Utility class for tracking user activities"""
    
    @staticmethod
    def track_activity(user, activity_type, request=None, **kwargs):
        """
        Track a user activity
        
        Args:
            user: User instance
            activity_type: Type of activity (from UserActivity.ACTIVITY_TYPES)
            request: Django request object (optional)
            **kwargs: Additional metadata
        """
        activity_data = {
            'user': user,
            'activity_type': activity_type,
            'ip_address': ActivityTracker._get_client_ip(request) if request else '0.0.0.0',
            'user_agent': request.META.get('HTTP_USER_AGENT', '') if request else '',
            'url': request.path if request else '',
            'method': request.method if request else '',
            'metadata': kwargs.get('metadata', {}),
            'resource_type': kwargs.get('resource_type', ''),
            'resource_id': kwargs.get('resource_id', ''),
            'description': kwargs.get('description', ''),
            'success': kwargs.get('success', True),
            'error_message': kwargs.get('error_message', ''),
        }
        
        # Get or create session
        if request and hasattr(request, 'session_obj'):
            activity_data['session'] = request.session_obj
        
        return UserActivity.objects.create(**activity_data)
    
    @staticmethod
    def track_page_view(user, request, page_title=''):
        """Track a page view"""
        return PageView.objects.create(
            user=user,
            session=getattr(request, 'session_obj', None),
            url=request.path,
            page_title=page_title,
            referrer=request.META.get('HTTP_REFERER', ''),
            ip_address=ActivityTracker._get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', '')
        )
    
    @staticmethod
    def track_api_usage(user, request, response_status, response_time_ms):
        """Track API usage"""
        return APIUsage.objects.create(
            user=user,
            organization=user.organization,
            endpoint=request.path,
            method=request.method,
            response_status=response_status,
            response_time_ms=response_time_ms,
            ip_address=ActivityTracker._get_client_ip(request),
            credits_used=1
        )
    
    @staticmethod
    def track_feature_usage(user, feature_name, feature_category='general'):
        """Track feature usage"""
        feature, created = FeatureUsage.objects.get_or_create(
            user=user,
            feature_name=feature_name,
            defaults={
                'organization': user.organization,
                'feature_category': feature_category
            }
        )
        
        if not created:
            feature.usage_count += 1
            feature.last_used_at = timezone.now()
            feature.save()
        
        return feature
    
    @staticmethod
    def create_audit_log(user, organization, action, resource_type, resource_id, 
                        description, changes=None, request=None):
        """Create an audit log entry"""
        return AuditLog.objects.create(
            user=user,
            organization=organization,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            description=description,
            changes=changes or {},
            ip_address=ActivityTracker._get_client_ip(request) if request else '0.0.0.0',
            user_agent=request.META.get('HTTP_USER_AGENT', '') if request else ''
        )
    
    @staticmethod
    def start_session(user, request):
        """Start a new user session"""
        return UserSession.objects.create(
            user=user,
            session_token=request.session.session_key or '',
            ip_address=ActivityTracker._get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
            device_type=ActivityTracker._detect_device_type(request),
            browser=ActivityTracker._detect_browser(request),
            os=ActivityTracker._detect_os(request)
        )
    
    @staticmethod
    def end_session(session):
        """End a user session"""
        if session:
            session.end_session()
    
    @staticmethod
    def _get_client_ip(request):
        """Get client IP address from request"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR', '0.0.0.0')
        return ip
    
    @staticmethod
    def _detect_device_type(request):
        """Detect device type from user agent"""
        user_agent = request.META.get('HTTP_USER_AGENT', '').lower()
        if 'mobile' in user_agent or 'android' in user_agent:
            return 'mobile'
        elif 'tablet' in user_agent or 'ipad' in user_agent:
            return 'tablet'
        return 'desktop'
    
    @staticmethod
    def _detect_browser(request):
        """Detect browser from user agent"""
        user_agent = request.META.get('HTTP_USER_AGENT', '').lower()
        if 'chrome' in user_agent:
            return 'Chrome'
        elif 'firefox' in user_agent:
            return 'Firefox'
        elif 'safari' in user_agent:
            return 'Safari'
        elif 'edge' in user_agent:
            return 'Edge'
        return 'Unknown'
    
    @staticmethod
    def _detect_os(request):
        """Detect OS from user agent"""
        user_agent = request.META.get('HTTP_USER_AGENT', '').lower()
        if 'windows' in user_agent:
            return 'Windows'
        elif 'mac' in user_agent:
            return 'macOS'
        elif 'linux' in user_agent:
            return 'Linux'
        elif 'android' in user_agent:
            return 'Android'
        elif 'ios' in user_agent or 'iphone' in user_agent:
            return 'iOS'
        return 'Unknown'


class ActivityMiddleware:
    """Middleware to automatically track activities"""
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        # Track request start time
        start_time = time.time()
        
        # Process request
        response = self.get_response(request)
        
        # Calculate response time
        response_time_ms = int((time.time() - start_time) * 1000)
        
        # Track activity if user is authenticated
        if hasattr(request, 'user') and request.user.is_authenticated:
            # Track page view for GET requests
            if request.method == 'GET' and not request.path.startswith('/static/'):
                ActivityTracker.track_page_view(request.user, request)
            
            # Track API usage
            if request.path.startswith('/api/'):
                ActivityTracker.track_api_usage(
                    request.user, 
                    request, 
                    response.status_code, 
                    response_time_ms
                )
        
        return response
