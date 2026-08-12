"""
DRF Authentication backend that bridges the JWT middleware to DRF's Request.user.

Problem:
  The JWTAuthenticationMiddleware sets `request.user` on the Django HttpRequest.
  But DRF wraps it in its own Request object and with DEFAULT_AUTHENTICATION_CLASSES = [],
  DRF's `request.user` always returns AnonymousUser — ignoring the middleware-set user.

Solution:
  This backend checks if the middleware already authenticated the user
  (via `request._request.user`) and returns it to DRF.
"""

from rest_framework.authentication import BaseAuthentication


class JWTMiddlewareAuthentication(BaseAuthentication):
    """
    Reads the user already set by JWTAuthenticationMiddleware on the Django request.
    This bridges middleware-based auth into DRF's authentication system so that
    `request.user` works correctly in all APIView subclasses.
    """

    def authenticate(self, request):
        # request here is DRF's Request; request._request is the original Django HttpRequest
        django_request = request._request
        user = getattr(django_request, 'user', None)

        if user and getattr(user, 'is_authenticated', False):
            return (user, None)  # (user, auth) — no separate auth token object

        return None  # Let DRF fall through to AnonymousUser
