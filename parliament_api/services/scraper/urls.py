from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

# Create a router for viewsets
router = DefaultRouter()
router.register(r'jobs', views.ScrapingJobViewSet, basename='scraping-job')
router.register(r'sessions', views.ScrapingSessionViewSet, basename='scraping-session')
router.register(r'errors', views.ScrapingErrorViewSet, basename='scraping-error')
router.register(r'configs', views.ScrapingConfigViewSet, basename='scraping-config')
router.register(r'data-sources', views.DataSourceViewSet, basename='data-source')

app_name = 'scraper'

urlpatterns = [
    # Scraping control endpoints
    path('start/', views.StartScrapingView.as_view(), name='start-scraping'),
    path('stop/', views.StopScrapingView.as_view(), name='stop-scraping'),
    path('status/', views.ScrapingStatusView.as_view(), name='scraping-status'),
    
    # Job management
    path('jobs/latest/', views.LatestJobView.as_view(), name='latest-job'),
    path('jobs/<int:job_id>/', views.JobDetailsView.as_view(), name='job-details'),
    path('jobs/<int:job_id>/logs/', views.JobLogsView.as_view(), name='job-logs'),
    path('jobs/<int:job_id>/restart/', views.RestartJobView.as_view(), name='restart-job'),
    
    # Data management
    path('data/stats/', views.DataStatsView.as_view(), name='data-stats'),
    path('data/validate/', views.ValidateDataView.as_view(), name='validate-data'),
    path('data/cleanup/', views.CleanupDataView.as_view(), name='cleanup-data'),
    
    # Update checking and database statistics
    path('check-updates/', views.CheckForUpdatesView.as_view(), name='check-updates'),
    path('database-stats/', views.DatabaseStatsView.as_view(), name='database-stats'),
    
    # Job management
    path('cleanup-stale-jobs/', views.CleanupStaleJobsView.as_view(), name='cleanup-stale-jobs'),
    
    # Router URLs
    path('', include(router.urls)),
] 