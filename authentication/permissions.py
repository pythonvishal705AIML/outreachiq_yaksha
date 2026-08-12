from rest_framework.permissions import BasePermission


class IsOwner(BasePermission):
    """Permission check for organization owner"""
    
    def has_permission(self, request, view):
        return request.user and request.user.role == 'owner'


class IsAdminOrOwner(BasePermission):
    """Permission check for admin or owner"""
    
    def has_permission(self, request, view):
        return request.user and request.user.role in ['owner', 'admin']


class IsSameOrganization(BasePermission):
    """Check if user belongs to the same organization"""
    
    def has_object_permission(self, request, view, obj):
        if hasattr(obj, 'organization'):
            return obj.organization == request.user.organization
        return False
