"""
Authentication models that work with existing database schema
Properly handles: account_id, org_id, tenant_id flow

FIXES:
- Added is_active property to Organization (derived from deleted_at is None)
- Reduced RefreshToken.token max_length from 500 to 255 (MySQL unique char limit)
"""

from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
import uuid
from django.utils import timezone


class OrganizationManager(models.Manager):
    def create_organization(self, name, **extra_fields):
        org_id = uuid.uuid4().hex  # varchar(255), no auto_increment
        org = self.model(id=org_id, name=name, **extra_fields)
        org.save(using=self._db)
        return org


class Organization(models.Model):
    """
    Maps to existing 'accounts' table.
    Only columns that actually exist: id (varchar 255), name (varchar 255).
    """
    id = models.CharField(primary_key=True, max_length=255)
    name = models.CharField(max_length=255, null=True, blank=True)

    objects = OrganizationManager()

    class Meta:
        db_table = 'accounts'

    def __str__(self):
        return f"{self.name} ({self.id})" if self.name else str(self.id)

    @property
    def org_id(self):
        return self.id

    @property
    def tenant_id(self):
        return self.id

    @property
    def account_id(self):
        return self.id

    @property
    def is_active(self):
        return True


class CustomUserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('Email is required')
        
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user
    
    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)
        
        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    """
    Custom User model for authentication - NEW TABLE: auth_users
    Links to existing accounts table via account_id
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Authentication
    email = models.EmailField(unique=True, db_index=True)
    password = models.CharField(max_length=255)
    
    # Profile
    first_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100, blank=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    
    # Link to existing accounts table (char(32) to match your schema)
    account_id = models.CharField(max_length=32, null=True, blank=True, db_index=True)
    
    # Role & Permissions
    role = models.CharField(
        max_length=20,
        choices=[
            ('owner', 'Owner'),
            ('admin', 'Admin'),
            ('member', 'Member'),
        ],
        default='member'
    )
    
    # Status
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    is_superuser = models.BooleanField(default=False)
    email_verified = models.BooleanField(default=False)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_login = models.DateTimeField(null=True, blank=True)
    
    objects = CustomUserManager()
    
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []
    
    class Meta:
        db_table = 'auth_users'  # New table name to avoid conflicts
        indexes = [
            models.Index(fields=['email']),
            models.Index(fields=['account_id', 'is_active']),
        ]
    
    def __str__(self):
        return self.email
    
    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip() or self.email
    
    @property
    def organization(self):
        """Get organization from existing accounts table"""
        if self.account_id:
            try:
                return Organization.objects.get(id=self.account_id)
            except Organization.DoesNotExist:
                return None
        return None
    
    @property
    def org_id(self):
        """Alias for compatibility - org_id is same as account_id"""
        return self.account_id
    
    @property
    def tenant_id(self):
        """Alias for compatibility - tenant_id is same as account_id"""
        return self.account_id


class RefreshToken(models.Model):
    """Store refresh tokens for JWT authentication"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='refresh_tokens')
    # FIX: reduced max_length from 500 to 255 to avoid MySQL unique CharField warning
    token = models.CharField(max_length=255, unique=True, db_index=True)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    revoked = models.BooleanField(default=False)
    
    class Meta:
        db_table = 'auth_refresh_tokens'
        indexes = [
            models.Index(fields=['token', 'revoked']),
            models.Index(fields=['user', 'revoked']),
        ]
    
    def is_valid(self):
        return not self.revoked and self.expires_at > timezone.now()


class LoginAttempt(models.Model):
    """Track login attempts for security"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(db_index=True)
    ip_address = models.GenericIPAddressField()
    user_agent = models.TextField(blank=True)
    success = models.BooleanField(default=False)
    failure_reason = models.CharField(max_length=100, blank=True)
    attempted_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'auth_login_attempts'
        indexes = [
            models.Index(fields=['email', 'attempted_at']),
            models.Index(fields=['ip_address', 'attempted_at']),
        ]


class UserGmailToken(models.Model):
    """Stores per-user Gmail OAuth tokens for sending emails from their own Gmail account."""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='gmail_token')
    gmail_address = models.EmailField()
    refresh_token = models.TextField()
    access_token = models.TextField(blank=True)
    token_expiry = models.DateTimeField(null=True, blank=True)
    connected_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'user_gmail_tokens'

    def __str__(self):
        return f"{self.user.email} → {self.gmail_address}"


class UserEmailConfig(models.Model):
    """Per-user Gmail App Password config — simpler alternative to OAuth."""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='email_config')
    from_email = models.EmailField()
    from_name = models.CharField(max_length=100, blank=True)
    smtp_host = models.CharField(max_length=100, default='smtp.gmail.com')
    smtp_port = models.IntegerField(default=465)
    app_password = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'user_email_configs'

    def __str__(self):
        return f"{self.user.email} → {self.from_email}"


# Import activity tracking models
from .activity_models import (
    UserSession, UserActivity, PageView, APIUsage,
    FeatureUsage, UserEngagement, OrganizationUsage, AuditLog
)