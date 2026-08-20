"""
SingleUserMiddleware — no login required.

This app runs as a single-tenant tool: every request is attributed to one
auto-created default user/account, so Gmail OAuth, campaign ownership, and
per-user email settings all work without a signup/login flow.
"""

import uuid
from datetime import datetime
from django.utils.deprecation import MiddlewareMixin
from .models import User, Organization

_DEFAULT_ORG_ID = uuid.uuid5(uuid.NAMESPACE_DNS, "outreachiq-default-account").hex
_DEFAULT_USER_EMAIL = "default@outreachiq.local"

_cached_user_id = None


class SingleUserMiddleware(MiddlewareMixin):
    """Attaches the single default user to every request — no auth required."""

    def process_request(self, request):
        user = self._get_default_user()
        request.user = user
        request.user_id = str(user.id)
        request.org_id = user.account_id
        return None

    @staticmethod
    def _get_default_user():
        global _cached_user_id
        if _cached_user_id:
            try:
                return User.objects.get(id=_cached_user_id)
            except User.DoesNotExist:
                _cached_user_id = None

        org, _ = Organization.objects.get_or_create(
            id=_DEFAULT_ORG_ID,
            defaults={"name": "Default Account"},
        )
        user, _ = User.objects.get_or_create(
            email=_DEFAULT_USER_EMAIL,
            defaults={
                "account_id": org.id,
                "first_name": "Default",
                "last_name": "User",
                "role": "owner",
                "is_active": True,
            },
        )
        _cached_user_id = user.id
        return user


class RateLimitMiddleware(MiddlewareMixin):
    """Simple rate limiting middleware"""

    def __init__(self, get_response):
        self.get_response = get_response
        self.request_counts = {}

    def process_request(self, request):
        # Get client IP
        ip = self.get_client_ip(request)

        # Rate limit: 100 requests per minute per IP
        current_minute = int(datetime.now().timestamp() / 60)
        key = f"{ip}:{current_minute}"

        if key in self.request_counts:
            self.request_counts[key] += 1
            if self.request_counts[key] > 100:
                from django.http import JsonResponse
                return JsonResponse({
                    'error': 'Rate limit exceeded',
                    'message': 'Too many requests. Please try again later.'
                }, status=429)
        else:
            self.request_counts[key] = 1

            # Clean old entries
            old_keys = [k for k in self.request_counts.keys()
                       if int(k.split(':')[1]) < current_minute - 5]
            for old_key in old_keys:
                del self.request_counts[old_key]

        return None

    @staticmethod
    def get_client_ip(request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip
