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
    
    # Master Data endpoints
    path('master-data/', views.QuestionMasterDataView.as_view(), name='question-master-data'),
    path('master-data/list/', views.QuestionMasterDataListView.as_view(), name='question-master-data-list'),
    path('master-data/bulk-download/', views.QuestionMasterDataBulkDownloadView.as_view(), name='question-master-data-bulk-download'),
    
    # Session-based Testing endpoints
    path('sessions/', views.QuestionSessionTestView.as_view(), name='question-sessions'),
    path('sessions/summary/', views.QuestionSessionSummaryView.as_view(), name='question-session-summary'),
    
    # Celery task endpoints
    path('task-status/<str:task_id>/', views.QuestionCeleryTaskStatusView.as_view(), name='question-celery-task-status'),
    path('bulk-download/', views.QuestionBulkDownloadView.as_view(), name='question-bulk-download'),
    path('process-queue/', views.QuestionDownloadQueueView.as_view(), name='question-process-queue'),
    path('download-statistics/', views.QuestionDownloadStatisticsView.as_view(), name='question-download-statistics'),
    path('populate/', views.QuestionPopulateView.as_view(), name='question-populate'),
] 