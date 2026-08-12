"""
Analytics and reporting views for SaaS product
"""

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.db.models import Count, Sum, Avg, Q
from django.utils import timezone
from datetime import timedelta
from .activity_models import (
    UserActivity, PageView, UserSession, APIUsage,
    FeatureUsage, UserEngagement, OrganizationUsage
)
from .decorators import require_role


class UserActivityAnalyticsView(APIView):
    """Get user activity analytics"""
    
    def get(self, request):
        user = request.user
        days = int(request.GET.get('days', 30))
        start_date = timezone.now() - timedelta(days=days)
        
        # Activity breakdown
        activities = UserActivity.objects.filter(
            user=user,
            timestamp__gte=start_date
        ).values('activity_type').annotate(
            count=Count('id')
        ).order_by('-count')
        
        # Daily activity
        daily_activity = UserActivity.objects.filter(
            user=user,
            timestamp__gte=start_date
        ).extra(
            select={'date': 'DATE(timestamp)'}
        ).values('date').annotate(
            count=Count('id')
        ).order_by('date')
        
        # Session stats
        sessions = UserSession.objects.filter(
            user=user,
            started_at__gte=start_date
        )
        
        session_stats = {
            'total_sessions': sessions.count(),
            'avg_duration_minutes': sessions.aggregate(
                avg=Avg('duration_seconds')
            )['avg'] / 60 if sessions.exists() else 0,
            'total_page_views': sessions.aggregate(
                total=Sum('page_views')
            )['total'] or 0
        }
        
        return Response({
            'period_days': days,
            'activity_breakdown': list(activities),
            'daily_activity': list(daily_activity),
            'session_stats': session_stats
        })


class OrganizationAnalyticsView(APIView):
    """Get organization-level analytics"""
    
    @require_role('owner', 'admin')
    def get(self, request):
        org = request.user.organization
        days = int(request.GET.get('days', 30))
        start_date = timezone.now() - timedelta(days=days)
        
        # Active users
        active_users = UserActivity.objects.filter(
            user__organization=org,
            timestamp__gte=start_date
        ).values('user').distinct().count()
        
        # Total activities
        total_activities = UserActivity.objects.filter(
            user__organization=org,
            timestamp__gte=start_date
        ).count()
        
        # API usage
        api_usage = APIUsage.objects.filter(
            organization=org,
            timestamp__gte=start_date
        ).aggregate(
            total_calls=Count('id'),
            avg_response_time=Avg('response_time_ms'),
            total_credits=Sum('credits_used')
        )
        
        # Feature usage
        top_features = FeatureUsage.objects.filter(
            organization=org,
            last_used_at__gte=start_date
        ).values('feature_name').annotate(
            users_count=Count('user', distinct=True),
            total_usage=Sum('usage_count')
        ).order_by('-total_usage')[:10]
        
        # User engagement
        engagement = UserEngagement.objects.filter(
            organization=org,
            date__gte=start_date.date()
        ).aggregate(
            avg_engagement_score=Avg('engagement_score'),
            total_sessions=Sum('sessions_count'),
            total_page_views=Sum('page_views_count')
        )
        
        return Response({
            'period_days': days,
            'active_users': active_users,
            'total_activities': total_activities,
            'api_usage': api_usage,
            'top_features': list(top_features),
            'engagement': engagement
        })


class UserDashboardView(APIView):
    """User dashboard with key metrics"""
    
    def get(self, request):
        user = request.user
        today = timezone.now().date()
        
        # Today's activity
        today_activities = UserActivity.objects.filter(
            user=user,
            timestamp__date=today
        ).count()
        
        # Recent activities
        recent_activities = UserActivity.objects.filter(
            user=user
        ).order_by('-timestamp')[:10].values(
            'activity_type', 'description', 'timestamp', 'success'
        )
        
        # Active session
        active_session = UserSession.objects.filter(
            user=user,
            is_active=True
        ).first()
        
        # Feature usage summary
        features_used_today = FeatureUsage.objects.filter(
            user=user,
            last_used_at__date=today
        ).count()
        
        return Response({
            'today_activities': today_activities,
            'recent_activities': list(recent_activities),
            'active_session': {
                'started_at': active_session.started_at if active_session else None,
                'page_views': active_session.page_views if active_session else 0
            } if active_session else None,
            'features_used_today': features_used_today
        })


class ActivityLogView(APIView):
    """Get activity log with filtering"""
    
    def get(self, request):
        user = request.user
        
        # Filters
        activity_type = request.GET.get('activity_type')
        days = int(request.GET.get('days', 7))
        page = int(request.GET.get('page', 1))
        page_size = int(request.GET.get('page_size', 50))
        
        start_date = timezone.now() - timedelta(days=days)
        
        # Query
        activities = UserActivity.objects.filter(
            user=user,
            timestamp__gte=start_date
        )
        
        if activity_type:
            activities = activities.filter(activity_type=activity_type)
        
        # Pagination
        total = activities.count()
        start = (page - 1) * page_size
        end = start + page_size
        
        activities_data = activities[start:end].values(
            'activity_type', 'description', 'timestamp',
            'url', 'method', 'success', 'resource_type', 'resource_id'
        )
        
        return Response({
            'total': total,
            'page': page,
            'page_size': page_size,
            'activities': list(activities_data)
        })
