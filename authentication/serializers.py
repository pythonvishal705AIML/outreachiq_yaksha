from rest_framework import serializers
from .models import User, Organization


class OrganizationSerializer(serializers.ModelSerializer):
    org_id = serializers.CharField(read_only=True)
    is_active = serializers.BooleanField(read_only=True)

    class Meta:
        model = Organization
        fields = ['id', 'org_id', 'name', 'is_active']
        read_only_fields = ['id', 'org_id']


class UserSerializer(serializers.ModelSerializer):
    organization = OrganizationSerializer(read_only=True)
    full_name = serializers.CharField(read_only=True)

    class Meta:
        model = User
        fields = [
            'id', 'email', 'first_name', 'last_name', 'full_name',
            'phone', 'organization', 'role', 'is_active',
            'email_verified', 'created_at', 'last_login'
        ]
        read_only_fields = ['id', 'created_at', 'last_login']
