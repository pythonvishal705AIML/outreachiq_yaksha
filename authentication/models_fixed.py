"""
Authentication models that work with existing database schema
- Uses existing 'accounts' table (read-only)
- Creates new 'auth_users' table (no conflicts)
- All activity tracking tables are new
"""

from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
import uuid
from django.utils import timezone


class OrganizationManager(models.Manager):
    def create_organization(self, name, **extra_fields):
        org = self.model(name=name, **extra_fields)
        org.save(using=self._db)
        return org


class Organization(models.Model):
    """
    Maps to existing 'accounts' table - READ ONLY
    Do not modify this table, it already exists in your database
    """
    id = models.CharField(primary_key=True, max_length=32)
    name = models.TextField()
    subdomain = models.TextField(blank=True, null=True)
    
    # Existing fields from your database
    ghl_location_id = models.CharField(max_length=255, blank=True, null=True)
    ghl_status = models.CharField(max_length=50, blank=True, null=True)
    onboarding_complete = models.BooleanField(default=False)
    logo_url = models.CharField(max_length=200, blank=True, null=True)
    stripe_customer_id = models.CharField(max_length=255, blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    
    objects = OrganizationManager()
    
    class Meta:
        db_table = 'accounts'  # Use existing table
        managed = False  # Don't let Django manage this table
    
    def __str__(self):
        return f"{self.name} ({self.id})"


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
    This won't conflict with your existing tables
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Authentication
    email = models.EmailField(unique=True, db_index=True)
    password = models.CharField(max_length=255)
    
    # Profile
    first_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100, blank=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    
    # Link to existing accounts table
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


class RefreshToken(models.Model):
    """Store refresh tokens for JWT authentication"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='refresh_tokens')
    token = models.CharField(max_length=500, unique=True, db_index=True)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    revoked = models.BooleanField(default=False)
    
    class Meta:
        db_table = 'auth_refresh_tokens'  # Renamed to avoid conflicts
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
        db_table = 'auth_login_attempts'  # Renamed to avoid conflicts
        indexes = [
            models.Index(fields=['email', 'attempted_at']),
            models.Index(fields=['ip_address', 'attempted_at']),
        ]
