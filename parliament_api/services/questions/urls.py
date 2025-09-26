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
    
    # Celery task endpoints
    path('task-status/<str:task_id>/', views.QuestionCeleryTaskStatusView.as_view(), name='question-celery-task-status'),
    path('bulk-download/', views.QuestionBulkDownloadView.as_view(), name='question-bulk-download'),
    path('process-queue/', views.QuestionDownloadQueueView.as_view(), name='question-process-queue'),
    path('download-statistics/', views.QuestionDownloadStatisticsView.as_view(), name='question-download-statistics'),
] 