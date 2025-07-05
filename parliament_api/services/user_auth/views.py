from django.shortcuts import render
from django.contrib.auth.models import User
from django.contrib.auth import authenticate, login, logout
from rest_framework import viewsets, status, generics
from rest_framework.decorators import action, api_view
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.authtoken.models import Token
from drf_spectacular.utils import extend_schema, OpenApiParameter
from drf_spectacular.types import OpenApiTypes
from .models import UserProfile, APIKey, UserSession, UserActivity, UserNotification


class RegisterView(APIView):
    """User registration endpoint"""
    permission_classes = [AllowAny]
    
    @extend_schema(
        description="Register a new user account",
        tags=['Authentication']
    )
    def post(self, request):
        """Register a new user"""
        username = request.data.get('username')
        email = request.data.get('email')
        password = request.data.get('password')
        
        if not all([username, email, password]):
            return Response({
                'error': 'Username, email, and password are required'
            }, status=400)
        
        if User.objects.filter(username=username).exists():
            return Response({
                'error': 'Username already exists'
            }, status=400)
        
        if User.objects.filter(email=email).exists():
            return Response({
                'error': 'Email already exists'
            }, status=400)
        
        # Create user
        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            first_name=request.data.get('first_name', ''),
            last_name=request.data.get('last_name', '')
        )
        
        # Create user profile
        UserProfile.objects.create(
            user=user,
            user_type=request.data.get('user_type', 'citizen'),
            organization=request.data.get('organization', '')
        )
        
        # Create token
        token, created = Token.objects.get_or_create(user=user)
        
        return Response({
            'message': 'User registered successfully',
            'token': token.key,
            'user_id': user.id,
            'username': user.username
        }, status=201)


class LogoutView(APIView):
    """User logout endpoint"""
    permission_classes = []
    
    @extend_schema(
        description="Logout user and invalidate token",
        tags=['Authentication']
    )
    def post(self, request):
        """Logout user"""
        try:
            # Delete the user's token
            Token.objects.filter(user=request.user).delete()
            return Response({'message': 'Successfully logged out'})
        except Exception as e:
            return Response({'error': 'Logout failed'}, status=400)


class UserProfileView(APIView):
    """User profile management"""
    permission_classes = []
    
    @extend_schema(
        description="Get current user profile",
        tags=['Authentication']
    )
    def get(self, request):
        """Get user profile"""
        user = request.user
        try:
            profile = user.profile
        except UserProfile.DoesNotExist:
            # Create profile if it doesn't exist
            profile = UserProfile.objects.create(user=user)
        
        return Response({
            'user': {
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'first_name': user.first_name,
                'last_name': user.last_name,
            },
            'profile': {
                'user_type': profile.user_type,
                'organization': profile.organization,
                'subscription_tier': profile.subscription_tier,
                'api_calls_today': profile.api_calls_today,
                'daily_api_limit': profile.daily_api_limit,
                'downloads_this_month': profile.downloads_this_month,
                'monthly_download_limit': profile.monthly_download_limit,
                'is_verified': profile.is_verified,
            }
        })
    
    @extend_schema(
        description="Update user profile",
        tags=['Authentication']
    )
    def put(self, request):
        """Update user profile"""
        user = request.user
        profile, created = UserProfile.objects.get_or_create(user=user)
        
        # Update user fields
        user.first_name = request.data.get('first_name', user.first_name)
        user.last_name = request.data.get('last_name', user.last_name)
        user.email = request.data.get('email', user.email)
        user.save()
        
        # Update profile fields
        profile.organization = request.data.get('organization', profile.organization)
        profile.user_type = request.data.get('user_type', profile.user_type)
        profile.save()
        
        return Response({'message': 'Profile updated successfully'})


class ChangePasswordView(APIView):
    """Change user password"""
    permission_classes = []
    
    @extend_schema(
        description="Change user password",
        tags=['Authentication']
    )
    def post(self, request):
        """Change password"""
        user = request.user
        old_password = request.data.get('old_password')
        new_password = request.data.get('new_password')
        
        if not user.check_password(old_password):
            return Response({'error': 'Invalid old password'}, status=400)
        
        user.set_password(new_password)
        user.save()
        
        # Create new token
        Token.objects.filter(user=user).delete()
        token = Token.objects.create(user=user)
        
        return Response({
            'message': 'Password changed successfully',
            'token': token.key
        })


class UserViewSet(viewsets.ModelViewSet):
    """User management viewset"""
    queryset = User.objects.all()
    permission_classes = []
    
    @extend_schema(tags=['Authentication'])
    def list(self, request):
        """List users (admin only)"""
        if not request.user.is_staff:
            return Response({'error': 'Admin access required'}, status=403)
        
        users = User.objects.all()[:10]  # Limit to 10 for demo
        return Response({
            'users': [
                {
                    'id': user.id,
                    'username': user.username,
                    'email': user.email,
                    'is_active': user.is_active,
                    'date_joined': user.date_joined
                }
                for user in users
            ]
        })


class APIKeyViewSet(viewsets.ModelViewSet):
    """API Key management"""
    permission_classes = []
    
    @extend_schema(tags=['Authentication'])
    def list(self, request):
        """List user's API keys"""
        keys = APIKey.objects.filter(user=request.user, is_active=True)
        return Response({
            'api_keys': [
                {
                    'id': key.id,
                    'name': key.name,
                    'key_prefix': key.key_prefix,
                    'scope': key.scope,
                    'last_used': key.last_used,
                    'created_at': key.created_at
                }
                for key in keys
            ]
        })
    
    @extend_schema(tags=['Authentication'])
    def create(self, request):
        """Create new API key"""
        name = request.data.get('name', 'API Key')
        scope = request.data.get('scope', 'read')
        
        api_key = APIKey.objects.create(
            user=request.user,
            name=name,
            scope=scope
        )
        
        return Response({
            'message': 'API key created',
            'api_key': {
                'id': api_key.id,
                'name': api_key.name,
                'key': api_key.key,  # Only show full key on creation
                'scope': api_key.scope
            }
        }, status=201)


class UserSessionListView(generics.ListAPIView):
    """List user sessions"""
    permission_classes = []
    
    @extend_schema(
        description="List user's active sessions",
        tags=['Authentication']
    )
    def get(self, request):
        """Get user sessions"""
        sessions = UserSession.objects.filter(user=request.user)[:10]
        return Response({
            'sessions': [
                {
                    'id': session.id,
                    'ip_address': session.ip_address,
                    'device_type': session.device_type,
                    'is_active': session.is_active,
                    'created_at': session.created_at,
                    'last_activity': session.last_activity
                }
                for session in sessions
            ]
        })


class UserActivityListView(generics.ListAPIView):
    """List user activities"""
    permission_classes = []
    
    @extend_schema(
        description="List user's recent activities",
        tags=['Authentication']
    )
    def get(self, request):
        """Get user activities"""
        activities = UserActivity.objects.filter(user=request.user)[:20]
        return Response({
            'activities': [
                {
                    'id': activity.id,
                    'activity_type': activity.activity_type,
                    'description': activity.description,
                    'timestamp': activity.timestamp
                }
                for activity in activities
            ]
        })


class UserNotificationListView(generics.ListAPIView):
    """List user notifications"""
    permission_classes = []
    
    @extend_schema(
        description="List user's notifications",
        tags=['Authentication']
    )
    def get(self, request):
        """Get user notifications"""
        notifications = UserNotification.objects.filter(user=request.user)[:10]
        return Response({
            'notifications': [
                {
                    'id': notification.id,
                    'title': notification.title,
                    'message': notification.message,
                    'notification_type': notification.notification_type,
                    'is_read': notification.is_read,
                    'created_at': notification.created_at
                }
                for notification in notifications
            ]
        })
