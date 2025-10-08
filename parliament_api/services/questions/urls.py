from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views
from .views_optimized_stats import (
    OptimizedQuestionStatsView,
    RefreshQuestionStatsView,
    OptimizedDebateStatsView
)

# Create a router for Lok Sabha questions
ls_router = DefaultRouter()
ls_router.register(r'questions', views.QuestionViewSet)
# ls_router.register(r'lok-sabhas', views.LokSabhaViewSet)  # Will be added later
# ls_router.register(r'sessions', views.SessionViewSet)    # Will be added later
# ls_router.register(r'members', views.MemberViewSet)      # Will be added later
# ls_router.register(r'ministries', views.MinistryViewSet) # Will be added later

app_name = 'questions'

urlpatterns = [
    # Lok Sabha endpoints (consistent structure)
    path('ls/', include(ls_router.urls)),
    path('ls/stats/', views.question_stats, name='ls-question-stats'),
    
    # Optimized statistics endpoints (using materialized views)
    path('optimized-stats/', OptimizedQuestionStatsView.as_view(), name='optimized-question-stats'),
    path('optimized-stats/refresh/', RefreshQuestionStatsView.as_view(), name='refresh-question-stats'),
    path('optimized-stats/debates/', OptimizedDebateStatsView.as_view(), name='optimized-debate-stats'),
    
    # Lok Sabha Master Data endpoints
    path('ls/master-data/', views.QuestionMasterDataView.as_view(), name='ls-question-master-data'),
    path('ls/master-data/list/', views.QuestionMasterDataListView.as_view(), name='ls-question-master-data-list'),
    path('ls/master-data/bulk-download/', views.QuestionMasterDataBulkDownloadView.as_view(), name='ls-question-master-data-bulk-download'),
    
    # Lok Sabha Session-based Testing endpoints
    path('ls/sessions/', views.QuestionSessionTestView.as_view(), name='ls-question-sessions'),
    path('ls/sessions/summary/', views.QuestionSessionSummaryView.as_view(), name='ls-question-session-summary'),
    
    # Lok Sabha Celery task endpoints
    path('ls/task-status/<str:task_id>/', views.QuestionCeleryTaskStatusView.as_view(), name='ls-question-celery-task-status'),
    path('ls/bulk-download/', views.QuestionBulkDownloadView.as_view(), name='ls-question-bulk-download'),
    path('ls/process-queue/', views.QuestionDownloadQueueView.as_view(), name='ls-question-process-queue'),
    path('ls/download-statistics/', views.QuestionDownloadStatisticsView.as_view(), name='ls-question-download-statistics'),
    path('ls/populate/', views.QuestionPopulateView.as_view(), name='ls-question-populate'),
    
    # Rajya Sabha endpoints (consistent structure)
    path('rs/master-data/', views.RSQuestionMasterDataView.as_view(), name='rs-question-master-data'),
    path('rs/master-data/list/', views.RSQuestionMasterDataListView.as_view(), name='rs-question-master-data-list'),
    path('rs/statistics/', views.RSQuestionStatisticsView.as_view(), name='rs-question-statistics'),
    path('rs/scrape/', views.RSQuestionScrapingView.as_view(), name='rs-question-scraping'),
    path('rs/bulk-download/', views.RSQuestionBulkDownloadView.as_view(), name='rs-question-bulk-download'),
    path('rs/initialize/', views.RSQuestionInitializeView.as_view(), name='rs-question-initialize'),
    path('rs/task-status/<str:task_id>/', views.RSQuestionTaskStatusView.as_view(), name='rs-question-task-status'),
    
    # Fast statistics endpoint (optimized for monitoring)
    path('fast-stats/', views.FastDownloadStatsView.as_view(), name='fast-download-stats'),
] 