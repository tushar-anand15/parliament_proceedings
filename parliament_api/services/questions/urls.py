from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

# Create a router and register our viewsets
router = DefaultRouter()
router.register(r'questions', views.QuestionViewSet)
# router.register(r'lok-sabhas', views.LokSabhaViewSet)  # Will be added later
# router.register(r'sessions', views.SessionViewSet)    # Will be added later
# router.register(r'members', views.MemberViewSet)      # Will be added later
# router.register(r'ministries', views.MinistryViewSet) # Will be added later

app_name = 'questions'

urlpatterns = [
    path('', include(router.urls)),
    # Additional custom endpoints
    path('stats/', views.question_stats, name='question-stats'),
] 