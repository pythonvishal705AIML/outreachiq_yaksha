from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.contrib.auth import authenticate
from django.utils import timezone
from django.db import transaction
from .models import User, LoginAttempt
from .serializers import (
    SignupSerializer, LoginSerializer, UserSerializer,
    ChangePasswordSerializer, RefreshTokenSerializer
)
from .jwt_utils import (
    generate_access_token, generate_refresh_token,
    verify_refresh_token, revoke_refresh_token, revoke_all_user_tokens
)
import logging

logger = logging.getLogger(__name__)


class SignupView(APIView):
    """User registration endpoint"""
    
    def post(self, request):
        serializer = SignupSerializer(data=request.data)
        
        if not serializer.is_valid():
            return Response({
                'error': 'Validation failed',
                'details': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            with transaction.atomic():
                user = serializer.save()
                
                # Generate tokens
                access_token = generate_access_token(user)
                refresh_token = generate_refresh_token(user)
                
                logger.info(f"New user registered: {user.email}")
                
                return Response({
                    'message': 'User registered successfully',
                    'user': UserSerializer(user).data,
                    'tokens': {
                        'access_token': access_token,
                        'refresh_token': refresh_token
                    }
                }, status=status.HTTP_201_CREATED)
                
        except Exception as e:
            logger.error(f"Signup error: {str(e)}")
            return Response({
                'error': 'Registration failed',
                'message': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class LoginView(APIView):
    """User login endpoint"""
    
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        
        if not serializer.is_valid():
            return Response({
                'error': 'Validation failed',
                'details': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
        
        email = serializer.validated_data['email']
        password = serializer.validated_data['password']
        
        # Get client info
        ip_address = self.get_client_ip(request)
        user_agent = request.META.get('HTTP_USER_AGENT', '')
        
        try:
            user = User.objects.get(email=email)
            
            # Check if user is active
            if not user.is_active:
                self.log_login_attempt(email, ip_address, user_agent, False, 'Account inactive')
                return Response({
                    'error': 'Account inactive',
                    'message': 'Your account has been deactivated'
                }, status=status.HTTP_403_FORBIDDEN)
            
            # Verify password
            if not user.check_password(password):
                self.log_login_attempt(email, ip_address, user_agent, False, 'Invalid password')
                return Response({
                    'error': 'Invalid credentials',
                    'message': 'Email or password is incorrect'
                }, status=status.HTTP_401_UNAUTHORIZED)
            
            # Check organization status
            if user.organization and not user.organization.is_active:
                self.log_login_attempt(email, ip_address, user_agent, False, 'Organization inactive')
                return Response({
                    'error': 'Organization inactive',
                    'message': 'Your organization account is inactive'
                }, status=status.HTTP_403_FORBIDDEN)
            
            # Generate tokens
            access_token = generate_access_token(user)
            refresh_token = generate_refresh_token(user)
            
            # Update last login
            user.last_login = timezone.now()
            user.save(update_fields=['last_login'])
            
            # Log successful login
            self.log_login_attempt(email, ip_address, user_agent, True)
            
            logger.info(f"User logged in: {user.email}")
            
            return Response({
                'message': 'Login successful',
                'user': UserSerializer(user).data,
                'tokens': {
                    'access_token': access_token,
                    'refresh_token': refresh_token
                }
            }, status=status.HTTP_200_OK)
            
        except User.DoesNotExist:
            self.log_login_attempt(email, ip_address, user_agent, False, 'User not found')
            return Response({
                'error': 'Invalid credentials',
                'message': 'Email or password is incorrect'
            }, status=status.HTTP_401_UNAUTHORIZED)
        
        except Exception as e:
            logger.error(f"Login error: {str(e)}")
            return Response({
                'error': 'Login failed',
                'message': 'An error occurred during login'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @staticmethod
    def get_client_ip(request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR', '0.0.0.0')
        return ip
    
    @staticmethod
    def log_login_attempt(email, ip_address, user_agent, success, failure_reason=''):
        try:
            LoginAttempt.objects.create(
                email=email,
                ip_address=ip_address,
                user_agent=user_agent,
                success=success,
                failure_reason=failure_reason
            )
        except Exception as e:
            logger.error(f"Failed to log login attempt: {str(e)}")


class RefreshTokenView(APIView):
    """Refresh access token using refresh token"""
    
    def post(self, request):
        serializer = RefreshTokenSerializer(data=request.data)
        
        if not serializer.is_valid():
            return Response({
                'error': 'Validation failed',
                'details': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
        
        refresh_token = serializer.validated_data['refresh_token']
        
        # Verify refresh token
        user = verify_refresh_token(refresh_token)
        
        if not user:
            return Response({
                'error': 'Invalid token',
                'message': 'Refresh token is invalid or expired'
            }, status=status.HTTP_401_UNAUTHORIZED)
        
        # Generate new access token
        access_token = generate_access_token(user)
        
        return Response({
            'access_token': access_token
        }, status=status.HTTP_200_OK)


class LogoutView(APIView):
    """Logout endpoint - revokes refresh token"""
    
    def post(self, request):
        refresh_token = request.data.get('refresh_token')
        
        if refresh_token:
            revoke_refresh_token(refresh_token)
        
        # Optionally revoke all tokens for the user
        if request.data.get('logout_all_devices'):
            revoke_all_user_tokens(request.user)
        
        return Response({
            'message': 'Logged out successfully'
        }, status=status.HTTP_200_OK)


class MeView(APIView):
    """Get current user profile"""
    
    def get(self, request):
        return Response({
            'user': UserSerializer(request.user).data
        }, status=status.HTTP_200_OK)


class ChangePasswordView(APIView):
    """Change user password"""
    
    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data)
        
        if not serializer.is_valid():
            return Response({
                'error': 'Validation failed',
                'details': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
        
        user = request.user
        
        # Verify old password
        if not user.check_password(serializer.validated_data['old_password']):
            return Response({
                'error': 'Invalid password',
                'message': 'Current password is incorrect'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Set new password
        user.set_password(serializer.validated_data['new_password'])
        user.save()
        
        # Revoke all existing tokens
        revoke_all_user_tokens(user)
        
        logger.info(f"Password changed for user: {user.email}")
        
        return Response({
            'message': 'Password changed successfully'
        }, status=status.HTTP_200_OK)


class HealthCheckView(APIView):
    """Health check endpoint - no auth required"""
    
    def get(self, request):
        return Response({
            'status': 'healthy',
            'service': 'authentication',
            'timestamp': timezone.now().isoformat()
        }, status=status.HTTP_200_OK)
