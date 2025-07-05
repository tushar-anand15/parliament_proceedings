from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

# Create a router for viewsets
router = DefaultRouter()
router.register(r'documents', views.DocumentFileViewSet, basename='document-file')
router.register(r'download-batches', views.DownloadBatchViewSet, basename='download-batch')
router.register(r'download-queue', views.DownloadQueueViewSet, basename='download-queue')

app_name = 'files'

urlpatterns = [
    # File management
    path('upload/', views.FileUploadView.as_view(), name='file-upload'),
    path('download/<int:file_id>/', views.FileDownloadView.as_view(), name='file-download'),
    path('preview/<int:file_id>/', views.FilePreviewView.as_view(), name='file-preview'),
    
    # Bulk operations
    path('bulk-download/', views.BulkDownloadView.as_view(), name='bulk-download'),
    path('batch-download/', views.BatchDownloadView.as_view(), name='batch-download'),
    path('batch-status/<int:batch_id>/', views.BatchStatusView.as_view(), name='batch-status'),
    
    # Queue management
    path('queue/add/', views.AddToQueueView.as_view(), name='add-to-queue'),
    path('queue/process/', views.ProcessQueueView.as_view(), name='process-queue'),
    path('queue/status/', views.QueueStatusView.as_view(), name='queue-status'),
    path('queue/clear/', views.ClearQueueView.as_view(), name='clear-queue'),
    
    # Statistics and monitoring
    path('stats/', views.FileStatsView.as_view(), name='file-stats'),
    path('logs/', views.FileAccessLogsView.as_view(), name='file-access-logs'),
    path('storage-info/', views.StorageInfoView.as_view(), name='storage-info'),
    
    # Cleanup operations
    path('cleanup/temp/', views.CleanupTempFilesView.as_view(), name='cleanup-temp'),
    path('cleanup/old/', views.CleanupOldFilesView.as_view(), name='cleanup-old'),
    
    # Router URLs
    path('', include(router.urls)),
] 