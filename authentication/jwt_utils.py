import jwt
from datetime import datetime, timedelta
from django.conf import settings
from .models import RefreshToken, User
import secrets


# JWT Configuration
JWT_SECRET = getattr(settings, 'JWT_SECRET_KEY', settings.SECRET_KEY)
JWT_ALGORITHM = 'HS256'
ACCESS_TOKEN_LIFETIME = timedelta(hours=8)
REFRESH_TOKEN_LIFETIME = timedelta(days=30)


def generate_access_token(user):
    """Generate JWT access token"""
    payload = {
        'user_id': str(user.id),
        'email': user.email,
        'org_id': str(user.organization.org_id) if user.organization else None,
        'role': user.role,
        'exp': datetime.utcnow() + ACCESS_TOKEN_LIFETIME,
        'iat': datetime.utcnow(),
        'type': 'access'
    }
    
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return token


def generate_refresh_token(user):
    """Generate and store refresh token"""
    token_string = secrets.token_urlsafe(64)
    expires_at = datetime.utcnow() + REFRESH_TOKEN_LIFETIME
    
    refresh_token = RefreshToken.objects.create(
        user=user,
        token=token_string,
        expires_at=expires_at
    )
    
    return refresh_token.token


def decode_access_token(token):
    """Decode and validate access token"""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        
        if payload.get('type') != 'access':
            return None
        
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def verify_refresh_token(token_string):
    """Verify refresh token and return user"""
    try:
        refresh_token = RefreshToken.objects.select_related('user').get(
            token=token_string,
            revoked=False
        )
        
        if not refresh_token.is_valid():
            return None
        
        return refresh_token.user
    except RefreshToken.DoesNotExist:
        return None


def revoke_refresh_token(token_string):
    """Revoke a refresh token"""
    try:
        refresh_token = RefreshToken.objects.get(token=token_string)
        refresh_token.revoked = True
        refresh_token.save()
        return True
    except RefreshToken.DoesNotExist:
        return False


def revoke_all_user_tokens(user):
    """Revoke all refresh tokens for a user"""
    RefreshToken.objects.filter(user=user, revoked=False).update(revoked=True)
