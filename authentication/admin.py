from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, Organization, RefreshToken, LoginAttempt


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ['name', 'id']
    search_fields = ['name', 'id']
    readonly_fields = ['id']


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    # FIX: replaced 'organization' with 'account_id' (organization is a @property, not a field)
    list_display = ['email', 'full_name', 'account_id', 'role', 'is_active', 'created_at']
    list_filter = ['role', 'is_active', 'email_verified', 'created_at']
    search_fields = ['email', 'first_name', 'last_name']
    readonly_fields = ['id', 'created_at', 'updated_at', 'last_login']
    
    fieldsets = (
        ('Authentication', {
            'fields': ('email', 'password')
        }),
        ('Profile', {
            'fields': ('first_name', 'last_name', 'phone')
        }),
        ('Organization', {
            # FIX: 'organization' is a property, use 'account_id' (the actual DB field)
            'fields': ('account_id', 'role')
        }),
        ('Permissions', {
            'fields': ('is_active', 'is_staff', 'is_superuser', 'email_verified')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at', 'last_login')
        }),
    )
    
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            # FIX: 'organization' -> 'account_id'
            'fields': ('email', 'password1', 'password2', 'first_name', 'last_name', 'account_id', 'role'),
        }),
    )
    
    ordering = ['-created_at']


@admin.register(RefreshToken)
class RefreshTokenAdmin(admin.ModelAdmin):
    list_display = ['user', 'token_preview', 'expires_at', 'revoked', 'created_at']
    list_filter = ['revoked', 'created_at', 'expires_at']
    search_fields = ['user__email', 'token']
    readonly_fields = ['id', 'token', 'created_at']
    
    def token_preview(self, obj):
        return f"{obj.token[:20]}..."
    token_preview.short_description = 'Token'


@admin.register(LoginAttempt)
class LoginAttemptAdmin(admin.ModelAdmin):
    list_display = ['email', 'ip_address', 'success', 'failure_reason', 'attempted_at']
    list_filter = ['success', 'attempted_at']
    search_fields = ['email', 'ip_address']
    readonly_fields = ['id', 'attempted_at']
    
    def has_add_permission(self, request):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False