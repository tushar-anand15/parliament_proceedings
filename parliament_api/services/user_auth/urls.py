from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework.authtoken.views import obtain_auth_token
from . import views

# Create a router for viewsets
router = DefaultRouter()
router.register(r'users', views.UserViewSet, basename='user')
router.register(r'api-keys', views.APIKeyViewSet, basename='apikey')

app_name = 'user_auth'

urlpatterns = [
    # Token authentication
    path('login/', obtain_auth_token, name='api_token_auth'),
    path('logout/', views.LogoutView.as_view(), name='logout'),
    path('register/', views.RegisterView.as_view(), name='register'),
    
    # User management
    path('profile/', views.UserProfileView.as_view(), name='profile'),
    path('change-password/', views.ChangePasswordView.as_view(), name='change_password'),
    
    # Router URLs
    path('', include(router.urls)),
    
    # Additional endpoints
    path('sessions/', views.UserSessionListView.as_view(), name='user-sessions'),
    path('activities/', views.UserActivityListView.as_view(), name='user-activities'),
    path('notifications/', views.UserNotificationListView.as_view(), name='user-notifications'),
] 