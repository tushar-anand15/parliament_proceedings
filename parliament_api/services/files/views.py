from django.shortcuts import render
from django.http import HttpResponse, FileResponse, Http404
from django.utils import timezone
from django.conf import settings
from rest_framework import viewsets, status, generics
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.parsers import MultiPartParser, FormParser
from drf_spectacular.utils import extend_schema
import os
import mimetypes
from .models import DocumentFile, DownloadQueue, DownloadBatch, FileAccessLog


class DocumentFileViewSet(viewsets.ModelViewSet):
    """Document file management"""
    queryset = DocumentFile.objects.all()
    permission_classes = []
    
    @extend_schema(
        description="List document files",
        tags=['Files']
    )
    def list(self, request):
        """List document files"""
        files = DocumentFile.objects.all().order_by('-created_at')[:50]
        return Response({
            'files': [
                {
                    'id': file.id,
                    'original_filename': file.original_filename,
                    'file_type': file.file_type,
                    'file_size': file.file_size,
                    'is_processed': file.is_processed,
                    'download_count': file.download_count,
                    'created_at': file.created_at,
                    'question': file.question.id if file.question else None
                }
                for file in files
            ]
        })
    
    @extend_schema(
        description="Get file details",
        tags=['Files']
    )
    def retrieve(self, request, pk=None):
        """Get file details"""
        try:
            file = DocumentFile.objects.get(pk=pk)
        except DocumentFile.DoesNotExist:
            return Response({'error': 'File not found'}, status=404)
        
        return Response({
            'file': {
                'id': file.id,
                'original_filename': file.original_filename,
                'file_type': file.file_type,
                'file_size': file.file_size,
                'file_hash': file.file_hash,
                'is_processed': file.is_processed,
                'download_count': file.download_count,
                'metadata': file.metadata,
                'created_at': file.created_at,
                'updated_at': file.updated_at,
                'question': file.question.id if file.question else None
            }
        })


class DownloadQueueViewSet(viewsets.ModelViewSet):
    """Download queue management"""
    queryset = DownloadQueue.objects.all()
    permission_classes = []
    
    @extend_schema(
        description="List download queue items",
        tags=['Files']
    )
    def list(self, request):
        """List download queue"""
        queue_items = DownloadQueue.objects.all().order_by('-created_at')[:20]
        return Response({
            'queue_items': [
                {
                    'id': item.id,
                    'url': item.url,
                    'filename': item.filename,
                    'priority': item.priority,
                    'status': item.status,
                    'download_attempts': item.download_attempts,
                    'created_at': item.created_at,
                    'downloaded_at': item.downloaded_at
                }
                for item in queue_items
            ]
        })


class DownloadBatchViewSet(viewsets.ModelViewSet):
    """Download batch management"""
    queryset = DownloadBatch.objects.all()
    permission_classes = []
    
    @extend_schema(
        description="List download batches",
        tags=['Files']
    )
    def list(self, request):
        """List download batches"""
        batches = DownloadBatch.objects.all().order_by('-created_at')[:10]
        return Response({
            'batches': [
                {
                    'id': batch.id,
                    'name': batch.name,
                    'status': batch.status,
                    'total_files': batch.total_files,
                    'completed_files': batch.completed_files,
                    'failed_files': batch.failed_files,
                    'created_at': batch.created_at,
                    'completed_at': batch.completed_at
                }
                for batch in batches
            ]
        })


class FileUploadView(APIView):
    """File upload endpoint"""
    permission_classes = []
    parser_classes = [MultiPartParser, FormParser]
    
    @extend_schema(
        description="Upload a file",
        tags=['Files']
    )
    def post(self, request):
        """Upload file"""
        if 'file' not in request.FILES:
            return Response({'error': 'No file provided'}, status=400)
        
        uploaded_file = request.FILES['file']
        question_id = request.data.get('question_id')
        
        # Create document file record
        doc_file = DocumentFile.objects.create(
            original_filename=uploaded_file.name,
            file_size=uploaded_file.size,
            file_type=uploaded_file.content_type or 'application/octet-stream',
            uploaded_by=request.user,
            question_id=question_id if question_id else None
        )
        
        # Save the file (simplified - in production, use proper file storage)
        # doc_file.file_path = f"uploads/{doc_file.id}_{uploaded_file.name}"
        
        return Response({
            'message': 'File uploaded successfully',
            'file_id': doc_file.id,
            'filename': doc_file.original_filename
        }, status=201)


class FileDownloadView(APIView):
    """File download endpoint with GCS presigned URLs"""
    permission_classes = [IsAuthenticated]
    
    @extend_schema(
        description="Get secure download URL for a file",
        tags=['Files'],
        responses={
            200: {
                'description': 'Download URL generated successfully',
                'content': {
                    'application/json': {
                        'example': {
                            'download_url': 'https://storage.googleapis.com/...',
                            'expires_at': '2025-01-01T12:00:00Z',
                            'file_name': 'document.pdf'
                        }
                    }
                }
            }
        }
    )
    def get(self, request, file_id):
        """Get secure download URL for file"""
        try:
            doc_file = DocumentFile.objects.get(id=file_id)
        except DocumentFile.DoesNotExist:
            return Response({'error': 'File not found'}, status=404)
        
        # Check if file is available
        if not doc_file.is_downloaded:
            return Response({
                'error': 'File not available for download',
                'status': doc_file.status
            }, status=400)
        
        # Log file access
        FileAccessLog.objects.create(
            document_file=doc_file,
            user=request.user if request.user.is_authenticated else None,
            access_type='download',
            ip_address=request.META.get('REMOTE_ADDR'),
            user_agent=request.META.get('HTTP_USER_AGENT', '')
        )
        
        # Try to get GCS presigned URL first
        if doc_file.is_in_gcs:
            presigned_url = doc_file.get_gcs_presigned_url(expiration_minutes=60)
            if presigned_url:
                from datetime import datetime, timedelta
                expires_at = datetime.utcnow() + timedelta(minutes=60)
                
                return Response({
                    'download_url': presigned_url,
                    'expires_at': expires_at.isoformat() + 'Z',
                    'file_name': doc_file.file_name,
                    'file_size': doc_file.file_size,
                    'storage_type': 'gcs'
                })
        
        # Fallback to local file serving
        if doc_file.file_path:
            return Response({
                'download_url': f'/api/files/serve/{doc_file.id}/',
                'file_name': doc_file.file_name,
                'file_size': doc_file.file_size,
                'storage_type': 'local'
            })
        
        return Response({
            'error': 'File not accessible',
            'message': 'File is not available in any storage location'
        }, status=500)


class FilePreviewView(APIView):
    """File preview endpoint"""
    permission_classes = []
    
    @extend_schema(
        description="Preview a file",
        tags=['Files']
    )
    def get(self, request, file_id):
        """Preview file"""
        try:
            doc_file = DocumentFile.objects.get(id=file_id)
        except DocumentFile.DoesNotExist:
            return Response({'error': 'File not found'}, status=404)
        
        # Log file access
        FileAccessLog.objects.create(
            file=doc_file,
            user=request.user,
            access_type='preview',
            ip_address=request.META.get('REMOTE_ADDR')
        )
        
        return Response({
            'file': {
                'id': doc_file.id,
                'filename': doc_file.original_filename,
                'file_type': doc_file.file_type,
                'file_size': doc_file.file_size,
                'preview_url': f'/api/files/preview-content/{doc_file.id}/',
                'metadata': doc_file.metadata
            }
        })


class BulkDownloadView(APIView):
    """Bulk file download"""
    permission_classes = []
    
    @extend_schema(
        description="Download multiple files",
        tags=['Files']
    )
    def post(self, request):
        """Bulk download files"""
        file_ids = request.data.get('file_ids', [])
        
        if not file_ids:
            return Response({'error': 'No file IDs provided'}, status=400)
        
        # Create download batch
        batch = DownloadBatch.objects.create(
            name=f"Bulk Download {timezone.now().strftime('%Y%m%d_%H%M%S')}",
            created_by=request.user,
            total_files=len(file_ids)
        )
        
        # Add files to batch (simplified implementation)
        valid_files = DocumentFile.objects.filter(id__in=file_ids)
        
        return Response({
            'message': 'Bulk download initiated',
            'batch_id': batch.id,
            'total_files': valid_files.count(),
            'download_url': f'/api/files/batch-download/{batch.id}/'
        })


class BatchDownloadView(APIView):
    """Batch download processing"""
    permission_classes = []
    
    @extend_schema(
        description="Process batch download",
        tags=['Files']
    )
    def post(self, request):
        """Create new batch download"""
        urls = request.data.get('urls', [])
        batch_name = request.data.get('name', f"Batch {timezone.now().strftime('%Y%m%d_%H%M%S')}")
        
        if not urls:
            return Response({'error': 'No URLs provided'}, status=400)
        
        # Create batch
        batch = DownloadBatch.objects.create(
            name=batch_name,
            created_by=request.user,
            total_files=len(urls)
        )
        
        # Add URLs to download queue
        for i, url in enumerate(urls):
            DownloadQueue.objects.create(
                url=url,
                filename=f"file_{i+1}",
                batch=batch,
                priority=1
            )
        
        return Response({
            'message': 'Batch download created',
            'batch_id': batch.id,
            'total_files': len(urls)
        }, status=201)


class BatchStatusView(APIView):
    """Batch download status"""
    permission_classes = []
    
    @extend_schema(
        description="Get batch download status",
        tags=['Files']
    )
    def get(self, request, batch_id):
        """Get batch status"""
        try:
            batch = DownloadBatch.objects.get(id=batch_id)
        except DownloadBatch.DoesNotExist:
            return Response({'error': 'Batch not found'}, status=404)
        
        queue_items = DownloadQueue.objects.filter(batch=batch)
        
        return Response({
            'batch': {
                'id': batch.id,
                'name': batch.name,
                'status': batch.status,
                'total_files': batch.total_files,
                'completed_files': batch.completed_files,
                'failed_files': batch.failed_files,
                'progress': (batch.completed_files / max(batch.total_files, 1)) * 100,
                'created_at': batch.created_at,
                'completed_at': batch.completed_at
            },
            'queue_items': [
                {
                    'id': item.id,
                    'url': item.url,
                    'filename': item.filename,
                    'status': item.status,
                    'downloaded_at': item.downloaded_at
                }
                for item in queue_items
            ]
        })


class AddToQueueView(APIView):
    """Add items to download queue"""
    permission_classes = []
    
    @extend_schema(
        description="Add URLs to download queue",
        tags=['Files']
    )
    def post(self, request):
        """Add to queue"""
        urls = request.data.get('urls', [])
        priority = request.data.get('priority', 5)
        
        if not urls:
            return Response({'error': 'No URLs provided'}, status=400)
        
        created_items = []
        for url in urls:
            item = DownloadQueue.objects.create(
                url=url,
                filename=os.path.basename(url),
                priority=priority,
                added_by=request.user
            )
            created_items.append(item.id)
        
        return Response({
            'message': f'Added {len(urls)} items to queue',
            'queue_item_ids': created_items
        }, status=201)


class ProcessQueueView(APIView):
    """Process download queue"""
    permission_classes = []
    
    @extend_schema(
        description="Process pending downloads in queue",
        tags=['Files']
    )
    def post(self, request):
        """Process queue"""
        max_items = request.data.get('max_items', 10)
        
        # Get pending items
        pending_items = DownloadQueue.objects.filter(
            status='pending'
        ).order_by('priority', 'created_at')[:max_items]
        
        processed_count = 0
        for item in pending_items:
            # TODO: Implement actual download logic
            item.status = 'processing'
            item.save()
            processed_count += 1
        
        return Response({
            'message': f'Started processing {processed_count} items',
            'processed_items': processed_count
        })


class QueueStatusView(APIView):
    """Download queue status"""
    permission_classes = []
    
    @extend_schema(
        description="Get download queue status",
        tags=['Files']
    )
    def get(self, request):
        """Get queue status"""
        from django.db.models import Count
        
        status_counts = DownloadQueue.objects.values('status').annotate(
            count=Count('id')
        )
        
        total_items = DownloadQueue.objects.count()
        
        return Response({
            'total_items': total_items,
            'status_breakdown': {
                item['status']: item['count']
                for item in status_counts
            },
            'recent_items': [
                {
                    'id': item.id,
                    'url': item.url,
                    'filename': item.filename,
                    'status': item.status,
                    'created_at': item.created_at
                }
                for item in DownloadQueue.objects.order_by('-created_at')[:10]
            ]
        })


class ClearQueueView(APIView):
    """Clear download queue"""
    permission_classes = []
    
    @extend_schema(
        description="Clear download queue",
        tags=['Files']
    )
    def post(self, request):
        """Clear queue"""
        status_filter = request.data.get('status', 'all')
        
        if status_filter == 'all':
            deleted_count = DownloadQueue.objects.all().count()
            DownloadQueue.objects.all().delete()
        else:
            deleted_count = DownloadQueue.objects.filter(status=status_filter).count()
            DownloadQueue.objects.filter(status=status_filter).delete()
        
        return Response({
            'message': f'Cleared {deleted_count} items from queue'
        })


class FileStatsView(APIView):
    """File statistics"""
    permission_classes = []
    
    @extend_schema(
        description="Get file statistics",
        tags=['Files']
    )
    def get(self, request):
        """Get file stats"""
        from django.db.models import Sum, Count, Avg
        
        # File statistics
        file_stats = DocumentFile.objects.aggregate(
            total_files=Count('id'),
            total_size=Sum('file_size'),
            avg_size=Avg('file_size'),
            total_downloads=Sum('download_count')
        )
        
        # Queue statistics
        queue_stats = DownloadQueue.objects.aggregate(
            total_queued=Count('id')
        )
        
        # Batch statistics
        batch_stats = DownloadBatch.objects.aggregate(
            total_batches=Count('id')
        )
        
        return Response({
            'files': {
                'total_files': file_stats['total_files'] or 0,
                'total_size_bytes': file_stats['total_size'] or 0,
                'average_size_bytes': file_stats['avg_size'] or 0,
                'total_downloads': file_stats['total_downloads'] or 0
            },
            'queue': {
                'total_queued': queue_stats['total_queued'] or 0
            },
            'batches': {
                'total_batches': batch_stats['total_batches'] or 0
            },
            'generated_at': timezone.now()
        })


class FileAccessLogsView(APIView):
    """File access logs"""
    permission_classes = []
    
    @extend_schema(
        description="Get file access logs",
        tags=['Files']
    )
    def get(self, request):
        """Get access logs"""
        logs = FileAccessLog.objects.all().order_by('-accessed_at')[:50]
        
        return Response({
            'logs': [
                {
                    'id': log.id,
                    'file_id': log.file.id,
                    'filename': log.file.original_filename,
                    'user': log.user.username,
                    'access_type': log.access_type,
                    'ip_address': log.ip_address,
                    'accessed_at': log.accessed_at
                }
                for log in logs
            ]
        })


class StorageInfoView(APIView):
    """Storage information"""
    permission_classes = []
    
    @extend_schema(
        description="Get storage information",
        tags=['Files']
    )
    def get(self, request):
        """Get storage info"""
        import shutil
        
        # Get disk usage (simplified)
        try:
            total, used, free = shutil.disk_usage('/')
            disk_info = {
                'total_bytes': total,
                'used_bytes': used,
                'free_bytes': free,
                'usage_percent': (used / total) * 100
            }
        except:
            disk_info = {
                'total_bytes': 0,
                'used_bytes': 0,
                'free_bytes': 0,
                'usage_percent': 0
            }
        
        return Response({
            'disk_usage': disk_info,
            'file_storage': {
                'total_files': DocumentFile.objects.count(),
                'storage_used': DocumentFile.objects.aggregate(
                    total=Sum('file_size')
                )['total'] or 0
            }
        })


class CleanupTempFilesView(APIView):
    """Cleanup temporary files"""
    permission_classes = []
    
    @extend_schema(
        description="Cleanup temporary files",
        tags=['Files']
    )
    def post(self, request):
        """Cleanup temp files"""
        # This would clean up temporary files in a real implementation
        return Response({
            'message': 'Temporary files cleanup completed',
            'cleaned_files': 0  # Would be actual count
        })


class CleanupOldFilesView(APIView):
    """Cleanup old files"""
    permission_classes = []
    
    @extend_schema(
        description="Cleanup old files",
        tags=['Files']
    )
    def post(self, request):
        """Cleanup old files"""
        days_to_keep = request.data.get('days_to_keep', 90)
        cutoff_date = timezone.now() - timezone.timedelta(days=days_to_keep)
        
        # Delete old file access logs
        old_logs = FileAccessLog.objects.filter(accessed_at__lt=cutoff_date)
        log_count = old_logs.count()
        old_logs.delete()
        
        return Response({
            'message': 'Old files cleanup completed',
            'deleted_logs': log_count,
            'cutoff_date': cutoff_date
        })
