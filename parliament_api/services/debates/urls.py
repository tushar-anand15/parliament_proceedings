from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

# Create a router for viewsets
router = DefaultRouter()
router.register(r'', views.DebateViewSet, basename='debate')

app_name = 'debates'

urlpatterns = [
    # Health check for integration testing
    path('health/', views.HealthCheckView.as_view(), name='health-check'),
    
    # Debate scraping control
    path('start-scraping/', views.StartDebateScrapingView.as_view(), name='start-debate-scraping'),
    path('scraping-status/', views.DebateScrapingStatusView.as_view(), name='debate-scraping-status'),
    
    # Statistics and search
    path('statistics/', views.DebateStatisticsView.as_view(), name='debate-statistics'),
    path('search/', views.DebateSearchView.as_view(), name='debate-search'),
    
    # Download management
    path('bulk-download/', views.BulkDownloadDebatesView.as_view(), name='bulk-download-debates'),
    path('download-queue/', views.DebateDownloadQueueView.as_view(), name='debate-download-queue'),
    
    # Router URLs (includes standard CRUD operations)
    path('', include(router.urls)),
]
