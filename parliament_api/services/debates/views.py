from django.shortcuts import render
from django.utils import timezone
from django.db import models
from django.db.models import Count, Sum, Min, Max, Q
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, AllowAny
from drf_spectacular.utils import extend_schema
import logging

from .models import Debate, DebateSpeech, DebateTag
from .debate_scraper_service import DebateScraperService
from services.scraper.models import ScrapingJob

logger = logging.getLogger(__name__)


class HealthCheckView(APIView):
    """Health check endpoint for service availability testing"""
    permission_classes = []
    
    def get(self, request):
        """Health check endpoint"""
        return Response({
            'status': 'healthy',
            'service': 'Parliament API',
            'timestamp': timezone.now(),
            'version': '1.0.0'
        })


class DebateViewSet(viewsets.ModelViewSet):
    """Debate management endpoints"""
    queryset = Debate.objects.all()
    permission_classes = []
    
    @extend_schema(
        description="List debates",
        tags=['Debates']
    )
    def list(self, request):
        """List debates with filters"""
        # Get query parameters
        loksabha_no = request.query_params.get('loksabha')
        session_no = request.query_params.get('session')
        status_filter = request.query_params.get('status')
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        
        # Build queryset
        queryset = Debate.objects.all()
        
        if loksabha_no:
            queryset = queryset.filter(lok_sabha__number=loksabha_no)
        if session_no:
            queryset = queryset.filter(session__session_number=session_no)
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        if start_date:
            queryset = queryset.filter(debate_date__gte=start_date)
        if end_date:
            queryset = queryset.filter(debate_date__lte=end_date)
        
        # Order and limit
        debates = queryset.order_by('-debate_date')[:100]
        
        return Response({
            'debates': [
                {
                    'id': debate.id,
                    'debate_id': debate.debate_id,
                    'lok_sabha': debate.lok_sabha.number,
                    'session': debate.session.session_number,
                    'debate_date': debate.debate_date,
                    'debate_type': debate.debate_type,
                    'language': debate.language,
                    'status': debate.status,
                    'pdf_url': debate.pdf_url,
                    'is_downloaded': debate.is_downloaded,
                    'file_size_mb': debate.file_size_mb,
                    'download_attempts': debate.download_attempts,
                    'created_at': debate.created_at
                }
                for debate in debates
            ],
            'total_count': queryset.count()
        })
    
    @extend_schema(
        description="Get debate details",
        tags=['Debates']
    )
    def retrieve(self, request, pk=None):
        """Get debate details"""
        try:
            debate = Debate.objects.get(pk=pk)
        except Debate.DoesNotExist:
            return Response({'error': 'Debate not found'}, status=404)
        
        return Response({
            'debate': {
                'id': debate.id,
                'debate_id': debate.debate_id,
                'lok_sabha': debate.lok_sabha.number,
                'session': debate.session.session_number,
                'debate_date': debate.debate_date,
                'debate_type': debate.debate_type,
                'language': debate.language,
                'status': debate.status,
                'pdf_url': debate.pdf_url,
                'is_downloaded': debate.is_downloaded,
                'file_size_mb': debate.file_size_mb,
                'page_count': debate.page_count,
                'download_attempts': debate.download_attempts,
                'last_download_attempt': debate.last_download_attempt,
                'error_message': debate.error_message,
                'raw_api_data': debate.raw_api_data,
                'created_at': debate.created_at,
                'updated_at': debate.updated_at,
                'last_scraped': debate.last_scraped
            }
        })
    
    @action(detail=True, methods=['post'])
    @extend_schema(
        description="Download PDF for a specific debate",
        tags=['Debates']
    )
    def download_pdf(self, request, pk=None):
        """Trigger PDF download for a debate"""
        try:
            debate = Debate.objects.get(pk=pk)
        except Debate.DoesNotExist:
            return Response({'error': 'Debate not found'}, status=404)
        
        if debate.is_downloaded:
            return Response({
                'message': 'PDF already downloaded',
                'file_size_mb': debate.file_size_mb
            })
        
        # Start download
        service = DebateScraperService()
        success = service.download_debate_pdf(debate)
        
        if success:
            return Response({
                'message': 'PDF downloaded successfully',
                'file_size_mb': debate.file_size_mb
            })
        else:
            return Response({
                'error': 'Failed to download PDF',
                'error_message': debate.error_message
            }, status=500)


class StartDebateScrapingView(APIView):
    """Start debate scraping operation"""
    permission_classes = []
    
    @extend_schema(
        description="Start scraping debates for a Lok Sabha session",
        tags=['Debates']
    )
    def post(self, request):
        """Start debate scraping"""
        loksabha_no = str(request.data.get('loksabha_no'))
        session_no = str(request.data.get('session_no'))
        start_date = request.data.get('start_date')  # Optional: YYYY-MM-DD
        end_date = request.data.get('end_date')      # Optional: YYYY-MM-DD
        download_pdfs = request.data.get('download_pdfs', True)
        job_name = request.data.get('job_name')
        
        # Validate required parameters
        if not loksabha_no or not session_no:
            return Response({
                'error': 'Both loksabha_no and session_no are required'
            }, status=400)
        
        # Check for active debate scraping jobs
        active_jobs = ScrapingJob.objects.filter(
            status__in=['pending', 'running'],
            job_type='debates'
        )
        
        if active_jobs.exists():
            return Response({
                'error': 'Another debate scraping job is already running',
                'active_job_id': active_jobs.first().id
            }, status=400)
        
        try:
            # Create and start scraping
            service = DebateScraperService()
            job = service.start_debate_scraping(
                loksabha_no=loksabha_no,
                session_no=session_no,
                start_date=start_date,
                end_date=end_date,
                job_name=job_name,
                download_pdfs=download_pdfs
            )
            
            return Response({
                'message': 'Debate scraping job started successfully',
                'job_id': job.id,
                'job_name': job.name,
                'status': 'pending',
                'loksabha_no': loksabha_no,
                'session_no': session_no,
                'start_date': start_date,
                'end_date': end_date,
                'download_pdfs': download_pdfs,
                'note': 'Job is running in background. Use /api/debates/status/ to check progress.'
            })
            
        except Exception as e:
            return Response({
                'error': f'Failed to start debate scraping: {str(e)}'
            }, status=500)


class DebateScrapingStatusView(APIView):
    """Get debate scraping status"""
    permission_classes = []
    
    @extend_schema(
        description="Get current debate scraping status",
        tags=['Debates']
    )
    def get(self, request):
        """Get scraping status"""
        # Get active debate jobs
        active_jobs = ScrapingJob.objects.filter(
            status__in=['pending', 'running'],
            job_type='debates'
        )
        
        # Get latest debate job
        latest_job = ScrapingJob.objects.filter(
            job_type='debates'
        ).order_by('-created_at').first()
        
        # Get debate statistics
        service = DebateScraperService()
        stats = service.get_debate_statistics()
        
        return Response({
            'active_jobs': [
                {
                    'id': job.id,
                    'name': job.name,
                    'status': job.status,
                    'progress_percent': job.progress_percent,
                    'debates_processed': job.questions_processed,  # Using same field
                    'debates_created': job.questions_created,
                    'debates_updated': job.questions_updated,
                    'debates_failed': job.questions_failed,
                    'total_expected': job.total_questions_expected,
                    'started_at': job.started_at,
                    'duration_seconds': job.duration.total_seconds() if job.duration else None
                }
                for job in active_jobs
            ],
            'latest_job': {
                'id': latest_job.id,
                'name': latest_job.name,
                'status': latest_job.status,
                'completed_at': latest_job.completed_at,
                'duration_seconds': latest_job.duration.total_seconds() if latest_job.duration else None
            } if latest_job else None,
            'debate_statistics': stats,
            'timestamp': timezone.now()
        })


class DebateStatisticsView(APIView):
    """Get comprehensive debate statistics"""
    permission_classes = []
    
    @extend_schema(
        description="Get detailed statistics about debates in the database",
        tags=['Debates']
    )
    def get(self, request):
        """Get debate statistics"""
        # Get query parameters
        loksabha_no = request.query_params.get('loksabha')
        session_no = request.query_params.get('session')
        
        # Build queryset
        queryset = Debate.objects.all()
        if loksabha_no:
            queryset = queryset.filter(lok_sabha__number=loksabha_no)
        if session_no:
            queryset = queryset.filter(session__session_number=session_no)
        
        # Overall statistics
        total_debates = queryset.count()
        
        # Status breakdown
        status_counts = queryset.values('status').annotate(
            count=Count('id')
        ).order_by('status')
        
        # Debates by Lok Sabha
        loksabha_stats = queryset.values(
            'lok_sabha__number'
        ).annotate(
            count=Count('id'),
            downloaded=Count('id', filter=models.Q(status='completed'))
        ).order_by('lok_sabha__number')
        
        # Debates by Session
        session_stats = queryset.values(
            'lok_sabha__number',
            'session__session_number'
        ).annotate(
            count=Count('id'),
            downloaded=Count('id', filter=models.Q(status='completed'))
        ).order_by('lok_sabha__number', 'session__session_number')
        
        # Date range
        date_range = queryset.aggregate(
            earliest_date=Min('debate_date'),
            latest_date=Max('debate_date')
        )
        
        # File size statistics
        size_stats = queryset.filter(status='completed').aggregate(
            total_size=Sum('file_size'),
            avg_size=models.Avg('file_size'),
            max_size=Max('file_size'),
            min_size=Min('file_size')
        )
        
        # Download statistics
        download_stats = queryset.exclude(download_attempts=0).aggregate(
            total_attempts=Sum('download_attempts'),
            avg_attempts=models.Avg('download_attempts'),
            max_attempts=Max('download_attempts')
        )
        
        # Language breakdown
        language_stats = queryset.values('language').annotate(
            count=Count('id')
        ).order_by('-count')
        
        # Type breakdown
        type_stats = queryset.values('debate_type').annotate(
            count=Count('id')
        ).order_by('-count')
        
        return Response({
            'total_debates': total_debates,
            'status_breakdown': {item['status']: item['count'] for item in status_counts},
            'loksabha_breakdown': list(loksabha_stats),
            'session_breakdown': list(session_stats),
            'date_range': date_range,
            'file_statistics': {
                'total_size_mb': round((size_stats['total_size'] or 0) / (1024 * 1024), 2),
                'average_size_mb': round((size_stats['avg_size'] or 0) / (1024 * 1024), 2),
                'max_size_mb': round((size_stats['max_size'] or 0) / (1024 * 1024), 2),
                'min_size_mb': round((size_stats['min_size'] or 0) / (1024 * 1024), 2)
            },
            'download_statistics': download_stats,
            'language_breakdown': list(language_stats),
            'type_breakdown': list(type_stats),
            'generated_at': timezone.now()
        })


class BulkDownloadDebatesView(APIView):
    """Bulk download debate PDFs"""
    permission_classes = []
    
    @extend_schema(
        description="Queue multiple debates for PDF download",
        tags=['Debates']
    )
    def post(self, request):
        """Queue debates for download"""
        debate_ids = request.data.get('debate_ids', [])
        download_all_pending = request.data.get('download_all_pending', False)
        
        if download_all_pending:
            # Queue all pending debates
            pending_debates = Debate.objects.filter(
                status='pending',
                pdf_url__isnull=False
            ).exclude(pdf_url='')
            
            service = DebateScraperService()
            queued_count = 0
            
            for debate in pending_debates:
                service._queue_pdf_download(debate)
                queued_count += 1
            
            return Response({
                'message': f'Queued {queued_count} debates for download',
                'queued_count': queued_count
            })
        
        elif debate_ids:
            # Queue specific debates
            debates = Debate.objects.filter(id__in=debate_ids)
            
            service = DebateScraperService()
            queued_count = 0
            already_downloaded = 0
            
            for debate in debates:
                if debate.is_downloaded:
                    already_downloaded += 1
                else:
                    service._queue_pdf_download(debate)
                    queued_count += 1
            
            return Response({
                'message': f'Queued {queued_count} debates for download',
                'queued_count': queued_count,
                'already_downloaded': already_downloaded
            })
        
        else:
            return Response({
                'error': 'No debate IDs provided and download_all_pending is false'
            }, status=400)


class DebateDownloadQueueView(APIView):
    """View download queue for debates"""
    permission_classes = []
    
    @extend_schema(
        description="Get debate download queue status",
        tags=['Debates']
    )
    def get(self, request):
        """Get download queue"""
        from services.files.models import DownloadQueue
        
        # Get debate-related downloads
        queue_items = DownloadQueue.objects.filter(
            document_file__file_type='debate'
        ).select_related('document_file').order_by('-created_at')[:50]
        
        # Get statistics
        total_queued = DownloadQueue.objects.filter(
            document_file__file_type='debate',
            status='queued'
        ).count()
        
        total_processing = DownloadQueue.objects.filter(
            document_file__file_type='debate',
            status='processing'
        ).count()
        
        total_completed = DownloadQueue.objects.filter(
            document_file__file_type='debate',
            status='completed'
        ).count()
        
        total_failed = DownloadQueue.objects.filter(
            document_file__file_type='debate',
            status='failed'
        ).count()
        
        return Response({
            'statistics': {
                'queued': total_queued,
                'processing': total_processing,
                'completed': total_completed,
                'failed': total_failed,
                'total': total_queued + total_processing + total_completed + total_failed
            },
            'recent_items': [
                {
                    'id': item.id,
                    'file_name': item.document_file.file_name,
                    'status': item.status,
                    'progress_percent': item.progress_percent,
                    'error_message': item.error_message,
                    'created_at': item.created_at,
                    'started_at': item.started_at,
                    'completed_at': item.completed_at
                }
                for item in queue_items
            ]
        })


class DebateSearchView(APIView):
    """Search debates"""
    permission_classes = []
    
    @extend_schema(
        description="Search debates by various criteria",
        tags=['Debates']
    )
    def get(self, request):
        """Search debates"""
        # Get search parameters
        q = request.query_params.get('q', '')
        loksabha_no = request.query_params.get('loksabha')
        session_no = request.query_params.get('session')
        year = request.query_params.get('year')
        month = request.query_params.get('month')
        status = request.query_params.get('status')
        
        # Build queryset
        queryset = Debate.objects.all()
        
        # Apply filters
        if loksabha_no:
            queryset = queryset.filter(lok_sabha__number=loksabha_no)
        if session_no:
            queryset = queryset.filter(session__session_number=session_no)
        if year:
            queryset = queryset.filter(debate_date__year=year)
        if month:
            queryset = queryset.filter(debate_date__month=month)
        if status:
            queryset = queryset.filter(status=status)
        
        # Order by date
        debates = queryset.order_by('-debate_date')[:100]
        
        return Response({
            'query': q,
            'filters': {
                'loksabha': loksabha_no,
                'session': session_no,
                'year': year,
                'month': month,
                'status': status
            },
            'results': [
                {
                    'id': debate.id,
                    'debate_id': debate.debate_id,
                    'lok_sabha': debate.lok_sabha.number,
                    'session': debate.session.session_number,
                    'debate_date': debate.debate_date,
                    'status': debate.status,
                    'is_downloaded': debate.is_downloaded
                }
                for debate in debates
            ],
            'total_results': queryset.count()
        })
