from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.utils import timezone
from .serializers import UserSerializer
import logging

logger = logging.getLogger(__name__)


class MeView(APIView):
    """Get current (default) user profile"""

    def get(self, request):
        return Response({
            'user': UserSerializer(request.user).data
        }, status=status.HTTP_200_OK)


class HealthCheckView(APIView):
    """Health check endpoint - no auth required"""

    def get(self, request):
        return Response({
            'status': 'healthy',
            'service': 'authentication',
            'timestamp': timezone.now().isoformat()
        }, status=status.HTTP_200_OK)
