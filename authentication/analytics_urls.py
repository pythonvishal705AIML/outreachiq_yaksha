from django.urls import path
from .analytics_views import (
    UserActivityAnalyticsView, OrganizationAnalyticsView,
    UserDashboardView, ActivityLogView
)

urlpatterns = [
    path('dashboard/', UserDashboardView.as_view(), name='user_dashboard'),
    path('activity-log/', ActivityLogView.as_view(), name='activity_log'),
    path('analytics/user/', UserActivityAnalyticsView.as_view(), name='user_analytics'),
    path('analytics/organization/', OrganizationAnalyticsView.as_view(), name='org_analytics'),
]
