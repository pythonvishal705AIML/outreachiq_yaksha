"""
Activity tracking models for SaaS product analytics
Tracks all user movements and interactions on the website
"""

from django.db import models
import uuid
from django.utils import timezone


class UserSession(models.Model):
    """Track user sessions for analytics"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey('User', on_delete=models.CASCADE, related_name='sessions')
    
    # Session Info
    session_token = models.CharField(max_length=255, unique=True, db_index=True)
    ip_address = models.GenericIPAddressField()
    user_agent = models.TextField()
    device_type = models.CharField(max_length=50, blank=True)  # mobile, desktop, tablet
    browser = models.CharField(max_length=100, blank=True)
    os = models.CharField(max_length=100, blank=True)
    
    # Location (optional - can be added via IP geolocation)
    country = models.CharField(max_length=100, blank=True)
    city = models.CharField(max_length=100, blank=True)
    
    # Session Timing
    started_at = models.DateTimeField(auto_now_add=True)
    last_activity_at = models.DateTimeField(auto_now=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    duration_seconds = models.IntegerField(default=0)
    
    # Activity Metrics
    page_views = models.IntegerField(default=0)
    actions_count = models.IntegerField(default=0)
    
    is_active = models.BooleanField(default=True)
    
    class Meta:
        db_table = 'user_sessions'
        indexes = [
            models.Index(fields=['user', 'started_at']),
            models.Index(fields=['is_active']),
            models.Index(fields=['session_token']),
        ]
    
    def __str__(self):
        return f"Session {self.user.email} - {self.started_at}"
    
    def end_session(self):
        """End the session and calculate duration"""
        self.ended_at = timezone.now()
        self.is_active = False
        self.duration_seconds = int((self.ended_at - self.started_at).total_seconds())
        self.save()


class UserActivity(models.Model):
    """Track all user activities and movements on the website"""
    
    ACTIVITY_TYPES = [
        # Authentication
        ('login', 'Login'),
        ('logout', 'Logout'),
        ('signup', 'Signup'),
        ('password_change', 'Password Change'),
        
        # Page Views
        ('page_view', 'Page View'),
        ('dashboard_view', 'Dashboard View'),
        
        # Lead Management
        ('lead_search', 'Lead Search'),
        ('lead_view', 'Lead View'),
        ('lead_create', 'Lead Create'),
        ('lead_update', 'Lead Update'),
        ('lead_delete', 'Lead Delete'),
        ('lead_export', 'Lead Export'),
        ('lead_import', 'Lead Import'),
        
        # Campaign Management
        ('campaign_create', 'Campaign Create'),
        ('campaign_view', 'Campaign View'),
        ('campaign_update', 'Campaign Update'),
        ('campaign_delete', 'Campaign Delete'),
        ('campaign_launch', 'Campaign Launch'),
        ('campaign_pause', 'Campaign Pause'),
        
        # Email Actions
        ('email_send', 'Email Send'),
        ('email_open', 'Email Open'),
        ('email_click', 'Email Click'),
        ('email_reply', 'Email Reply'),
        
        # Organization
        ('org_settings_view', 'Organization Settings View'),
        ('org_settings_update', 'Organization Settings Update'),
        ('user_invite', 'User Invite'),
        ('user_remove', 'User Remove'),
        
        # Billing
        ('billing_view', 'Billing View'),
        ('subscription_upgrade', 'Subscription Upgrade'),
        ('subscription_downgrade', 'Subscription Downgrade'),
        ('payment_success', 'Payment Success'),
        ('payment_failed', 'Payment Failed'),
        
        # API Usage
        ('api_call', 'API Call'),
        ('api_error', 'API Error'),
        
        # Other
        ('file_upload', 'File Upload'),
        ('file_download', 'File Download'),
        ('search', 'Search'),
        ('filter_apply', 'Filter Apply'),
        ('export_data', 'Export Data'),
        ('settings_change', 'Settings Change'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey('User', on_delete=models.CASCADE, related_name='activities')
    session = models.ForeignKey(UserSession, on_delete=models.SET_NULL, null=True, blank=True)
    
    # Activity Details
    activity_type = models.CharField(max_length=50, choices=ACTIVITY_TYPES, db_index=True)
    description = models.TextField(blank=True)
    
    # Context
    url = models.TextField(blank=True)
    method = models.CharField(max_length=10, blank=True)  # GET, POST, PUT, DELETE
    ip_address = models.GenericIPAddressField()
    user_agent = models.TextField(blank=True)
    
    # Metadata
    metadata = models.JSONField(default=dict, blank=True)  # Store additional context
    
    # Resource Info (what was acted upon)
    resource_type = models.CharField(max_length=50, blank=True)  # lead, campaign, user, etc.
    resource_id = models.CharField(max_length=255, blank=True)
    
    # Status
    success = models.BooleanField(default=True)
    error_message = models.TextField(blank=True)
    
    # Timing
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    duration_ms = models.IntegerField(null=True, blank=True)  # How long the action took
    
    class Meta:
        db_table = 'user_activities'
        indexes = [
            models.Index(fields=['user', 'timestamp']),
            models.Index(fields=['activity_type', 'timestamp']),
            models.Index(fields=['session', 'timestamp']),
            models.Index(fields=['resource_type', 'resource_id']),
        ]
        ordering = ['-timestamp']
    
    def __str__(self):
        return f"{self.user.email} - {self.activity_type} - {self.timestamp}"


class PageView(models.Model):
    """Track page views for analytics"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey('User', on_delete=models.CASCADE, related_name='page_views', null=True, blank=True)
    session = models.ForeignKey(UserSession, on_delete=models.SET_NULL, null=True, blank=True)
    
    # Page Info
    url = models.TextField()
    page_title = models.CharField(max_length=255, blank=True)
    referrer = models.TextField(blank=True)
    
    # User Info
    ip_address = models.GenericIPAddressField()
    user_agent = models.TextField()
    
    # Timing
    viewed_at = models.DateTimeField(auto_now_add=True, db_index=True)
    time_on_page_seconds = models.IntegerField(null=True, blank=True)
    
    # Engagement
    scroll_depth_percent = models.IntegerField(null=True, blank=True)
    interactions_count = models.IntegerField(default=0)
    
    class Meta:
        db_table = 'page_views'
        indexes = [
            models.Index(fields=['user', 'viewed_at']),
            models.Index(fields=['session', 'viewed_at']),
            models.Index(fields=['url']),
        ]


class APIUsage(models.Model):
    """Track API usage for rate limiting and analytics"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey('User', on_delete=models.CASCADE, related_name='api_usage')
    organization = models.ForeignKey('Organization', on_delete=models.CASCADE, related_name='api_usage')
    
    # API Details
    endpoint = models.CharField(max_length=255, db_index=True)
    method = models.CharField(max_length=10)
    
    # Request Info
    request_data = models.JSONField(default=dict, blank=True)
    response_status = models.IntegerField()
    response_time_ms = models.IntegerField()
    
    # Usage Tracking
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    ip_address = models.GenericIPAddressField()
    
    # Billing
    credits_used = models.IntegerField(default=1)
    
    class Meta:
        db_table = 'api_usage'
        indexes = [
            models.Index(fields=['user', 'timestamp']),
            models.Index(fields=['organization', 'timestamp']),
            models.Index(fields=['endpoint', 'timestamp']),
        ]


class FeatureUsage(models.Model):
    """Track which features users are using"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey('User', on_delete=models.CASCADE, related_name='feature_usage')
    organization = models.ForeignKey('Organization', on_delete=models.CASCADE, related_name='feature_usage')
    
    # Feature Info
    feature_name = models.CharField(max_length=100, db_index=True)
    feature_category = models.CharField(max_length=50)
    
    # Usage Stats
    first_used_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(auto_now=True)
    usage_count = models.IntegerField(default=1)
    
    # Engagement
    total_time_spent_seconds = models.IntegerField(default=0)
    
    class Meta:
        db_table = 'feature_usage'
        unique_together = ('user', 'feature_name')
        indexes = [
            models.Index(fields=['user', 'last_used_at']),
            models.Index(fields=['organization', 'feature_name']),
        ]


class UserEngagement(models.Model):
    """Daily engagement metrics per user"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey('User', on_delete=models.CASCADE, related_name='engagement_metrics')
    organization = models.ForeignKey('Organization', on_delete=models.CASCADE, related_name='engagement_metrics')
    
    # Date
    date = models.DateField(db_index=True)
    
    # Activity Metrics
    sessions_count = models.IntegerField(default=0)
    total_time_seconds = models.IntegerField(default=0)
    page_views_count = models.IntegerField(default=0)
    actions_count = models.IntegerField(default=0)
    
    # Feature Usage
    features_used = models.JSONField(default=list)
    
    # Engagement Score (0-100)
    engagement_score = models.IntegerField(default=0)
    
    class Meta:
        db_table = 'user_engagement'
        unique_together = ('user', 'date')
        indexes = [
            models.Index(fields=['user', 'date']),
            models.Index(fields=['organization', 'date']),
        ]


class OrganizationUsage(models.Model):
    """Track organization-level usage for billing and analytics"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey('Organization', on_delete=models.CASCADE, related_name='usage_metrics')
    
    # Period
    period_start = models.DateTimeField(db_index=True)
    period_end = models.DateTimeField()
    
    # Usage Metrics
    active_users_count = models.IntegerField(default=0)
    total_sessions = models.IntegerField(default=0)
    total_page_views = models.IntegerField(default=0)
    total_api_calls = models.IntegerField(default=0)
    
    # Resource Usage
    leads_created = models.IntegerField(default=0)
    campaigns_created = models.IntegerField(default=0)
    emails_sent = models.IntegerField(default=0)
    
    # Storage
    storage_used_mb = models.FloatField(default=0)
    
    # Billing
    credits_used = models.IntegerField(default=0)
    overage_charges = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    class Meta:
        db_table = 'organization_usage'
        indexes = [
            models.Index(fields=['organization', 'period_start']),
        ]


class AuditLog(models.Model):
    """Comprehensive audit log for compliance and security"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Who
    user = models.ForeignKey('User', on_delete=models.SET_NULL, null=True, blank=True)
    organization = models.ForeignKey('Organization', on_delete=models.CASCADE)
    
    # What
    action = models.CharField(max_length=100, db_index=True)
    resource_type = models.CharField(max_length=50)
    resource_id = models.CharField(max_length=255)
    
    # Details
    description = models.TextField()
    changes = models.JSONField(default=dict, blank=True)  # Before/after values
    
    # When
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    
    # Where
    ip_address = models.GenericIPAddressField()
    user_agent = models.TextField(blank=True)
    
    # Context
    metadata = models.JSONField(default=dict, blank=True)
    
    class Meta:
        db_table = 'audit_logs'
        indexes = [
            models.Index(fields=['organization', 'timestamp']),
            models.Index(fields=['user', 'timestamp']),
            models.Index(fields=['action', 'timestamp']),
            models.Index(fields=['resource_type', 'resource_id']),
        ]
        ordering = ['-timestamp']
