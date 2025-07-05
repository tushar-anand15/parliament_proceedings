from django.shortcuts import render
from django.utils import timezone
from rest_framework import viewsets, status, generics
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, AllowAny
from drf_spectacular.utils import extend_schema
import logging

logger = logging.getLogger(__name__)
from .models import ScrapingJob, ScrapingSession, ScrapingError, ScrapingConfig, DataSource
from services.questions.models import Question
from .scraper_service import ParliamentQuestionsScraperService


class ScrapingJobViewSet(viewsets.ModelViewSet):
    """Scraping job management"""
    queryset = ScrapingJob.objects.all()
    permission_classes = []
    
    @extend_schema(
        description="List scraping jobs",
        tags=['Scraper']
    )
    def list(self, request):
        """List recent scraping jobs"""
        jobs = ScrapingJob.objects.all().order_by('-created_at')[:20]
        return Response({
            'jobs': [
                {
                    'id': job.id,
                    'job_type': job.job_type,
                    'status': job.status,
                    'progress': job.progress,
                    'total_items': job.total_items,
                    'processed_items': job.processed_items,
                    'created_at': job.created_at,
                    'started_at': job.started_at,
                    'completed_at': job.completed_at,
                    'error_message': job.error_message
                }
                for job in jobs
            ]
        })
    
    @extend_schema(
        description="Create new scraping job",
        tags=['Scraper']
    )
    def create(self, request):
        """Create a new scraping job"""
        job_type = request.data.get('job_type', 'questions')
        config_data = request.data.get('config', {})
        
        job = ScrapingJob.objects.create(
            job_type=job_type,
            created_by=request.user,
            config=config_data
        )
        
        return Response({
            'message': 'Scraping job created',
            'job_id': job.id,
            'status': job.status
        }, status=201)


class ScrapingSessionViewSet(viewsets.ModelViewSet):
    """Scraping session management"""
    queryset = ScrapingSession.objects.all()
    permission_classes = []
    
    @extend_schema(
        description="List scraping sessions",
        tags=['Scraper']
    )
    def list(self, request):
        """List scraping sessions"""
        sessions = ScrapingSession.objects.all().order_by('-created_at')[:10]
        return Response({
            'sessions': [
                {
                    'id': session.id,
                    'session_type': session.session_type,
                    'lok_sabha': session.lok_sabha,
                    'session_number': session.session_number,
                    'is_active': session.is_active,
                    'total_questions': session.total_questions,
                    'scraped_questions': session.scraped_questions,
                    'last_scraped_date': session.last_scraped_date,
                    'created_at': session.created_at
                }
                for session in sessions
            ]
        })


class ScrapingErrorViewSet(viewsets.ModelViewSet):
    """Scraping error tracking"""
    queryset = ScrapingError.objects.all()
    permission_classes = []
    
    @extend_schema(
        description="List scraping errors",
        tags=['Scraper']
    )
    def list(self, request):
        """List recent scraping errors"""
        errors = ScrapingError.objects.all().order_by('-created_at')[:50]
        return Response({
            'errors': [
                {
                    'id': error.id,
                    'error_type': error.error_type,
                    'error_message': error.error_message,
                    'context': error.context,
                    'is_resolved': error.is_resolved,
                    'created_at': error.created_at
                }
                for error in errors
            ]
        })


class ScrapingConfigViewSet(viewsets.ModelViewSet):
    """Scraping configuration management"""
    queryset = ScrapingConfig.objects.all()
    permission_classes = []
    
    @extend_schema(
        description="List scraping configurations",
        tags=['Scraper']
    )
    def list(self, request):
        """List scraping configurations"""
        configs = ScrapingConfig.objects.filter(is_active=True)
        return Response({
            'configs': [
                {
                    'id': config.id,
                    'name': config.name,
                    'description': config.description,
                    'config_data': config.config_data,
                    'is_active': config.is_active,
                    'created_at': config.created_at
                }
                for config in configs
            ]
        })


class DataSourceViewSet(viewsets.ModelViewSet):
    """Data source management"""
    queryset = DataSource.objects.all()
    permission_classes = []
    
    @extend_schema(
        description="List data sources",
        tags=['Scraper']
    )
    def list(self, request):
        """List available data sources"""
        sources = DataSource.objects.filter(is_active=True)
        return Response({
            'data_sources': [
                {
                    'id': source.id,
                    'name': source.name,
                    'base_url': source.base_url,
                    'source_type': source.source_type,
                    'is_active': source.is_active,
                    'last_accessed': source.last_accessed,
                    'success_rate': source.success_rate
                }
                for source in sources
            ]
        })


class StartScrapingView(APIView):
    """Start scraping operation"""
    permission_classes = []
    
    @extend_schema(
        description="Start a new scraping operation",
        tags=['Scraper']
    )
    def _cleanup_stale_jobs(self):
        """Clean up jobs that are stuck in running/pending state"""
        from datetime import timedelta
        
        # Consider jobs stale if they've been running for more than 2 hours without activity
        stale_threshold = timezone.now() - timedelta(hours=2)
        
        stale_jobs = ScrapingJob.objects.filter(
            status__in=['pending', 'running'],
            last_activity__lt=stale_threshold
        )
        
        if stale_jobs.exists():
            stale_count = stale_jobs.count()
            logger.warning(f"Found {stale_count} stale jobs, marking as failed")
            
            for job in stale_jobs:
                job.status = 'failed'
                job.error_message = f"Job marked as stale - no activity since {job.last_activity}"
                job.completed_at = timezone.now()
                job.save()
                
            logger.info(f"Cleaned up {stale_count} stale jobs")
    
    def post(self, request):
        """Start scraping"""
        loksabha_no = str(request.data.get('loksabha_no', '17'))
        session_no = request.data.get('session_no')  # Optional
        force_update = request.data.get('force_update', False)
        job_name = request.data.get('job_name')
        
        # Validate loksabha_no
        if not loksabha_no.isdigit():
            return Response({
                'error': 'Invalid loksabha_no. Must be a number (e.g., "17")'
            }, status=400)
        
        # Clean up stale jobs first (jobs that might be stuck)
        self._cleanup_stale_jobs()
        
        # Check for truly active jobs (not stale ones)
        active_jobs = ScrapingJob.objects.filter(
            status__in=['pending', 'running']
        )
        
        
        active_job_info = []
        
        try:
            # Create and start scraping using the service
            service = ParliamentQuestionsScraperService()
            job = service.start_scraping(
                loksabha_no=loksabha_no,
                session_no=session_no,
                job_name=job_name,
                force_update=force_update
            )
            
            response_data = {
                'message': 'Scraping job queued successfully',
                'job_id': job.id,
                'job_name': job.name,
                'status': 'pending',
                'loksabha_no': loksabha_no,
                'session_no': session_no,
                'force_update': force_update,
                'note': 'Job is running in background. Use /api/scraper/status/ to check progress.'
            }
            
            if active_job_info:
                response_data['other_active_jobs'] = active_job_info
                response_data['note'] += f' ({len(active_job_info)} other jobs also running)'
            
            return Response(response_data)
            
        except Exception as e:
            return Response({
                'error': f'Failed to start scraping: {str(e)}'
            }, status=500)


class StopScrapingView(APIView):
    """Stop scraping operation"""
    permission_classes = []
    
    @extend_schema(
        description="Stop active scraping operation",
        tags=['Scraper']
    )
    def post(self, request):
        """Stop scraping"""
        job_id = request.data.get('job_id')
        
        if job_id:
            try:
                job = ScrapingJob.objects.get(id=job_id)
            except ScrapingJob.DoesNotExist:
                return Response({'error': 'Job not found'}, status=404)
        else:
            # Stop the most recent active job
            job = ScrapingJob.objects.filter(
                status__in=['pending', 'running']
            ).order_by('-created_at').first()
            
            if not job:
                return Response({'error': 'No active scraping job found'}, status=404)
        
        job.status = 'cancelled'
        job.completed_at = timezone.now()
        job.save()
        
        return Response({
            'message': 'Scraping stopped successfully',
            'job_id': job.id
        })


class ScrapingStatusView(APIView):
    """Get scraping status"""
    permission_classes = []
    
    @extend_schema(
        description="Get current scraping status",
        tags=['Scraper']
    )
    def get(self, request):
        """Get scraping status"""
        # Get active jobs
        active_jobs = ScrapingJob.objects.filter(
            status__in=['pending', 'running']
        )
        
        # Get latest completed job
        latest_job = ScrapingJob.objects.order_by('-created_at').first()
        
        return Response({
            'active_jobs': [
                {
                    'id': job.id,
                    'name': job.name,
                    'job_type': job.job_type,
                    'status': job.status,
                    'progress_percent': job.progress_percent,
                    'questions_processed': job.questions_processed,
                    'questions_created': job.questions_created,
                    'questions_updated': job.questions_updated,
                    'questions_failed': job.questions_failed,
                    'total_expected': job.total_questions_expected,
                    'started_at': job.started_at,
                    'duration_seconds': job.duration.total_seconds() if job.duration else None,
                    'processing_rate': round(job.questions_processed / max(job.duration.total_seconds() / 60, 1), 1) if job.duration else 0  # questions per minute
                }
                for job in active_jobs
            ],
            'latest_job': {
                'id': latest_job.id,
                'name': latest_job.name,
                'job_type': latest_job.job_type,
                'status': latest_job.status,
                'progress_percent': latest_job.progress_percent,
                'questions_processed': latest_job.questions_processed,
                'questions_created': latest_job.questions_created,
                'questions_updated': latest_job.questions_updated,
                'questions_failed': latest_job.questions_failed,
                'completed_at': latest_job.completed_at,
                'duration_seconds': latest_job.duration.total_seconds() if latest_job.duration else None
            } if latest_job else None,
            'system_status': 'operational',
            'timestamp': timezone.now()
        })


class LatestJobView(APIView):
    """Get latest job details"""
    permission_classes = []
    
    @extend_schema(
        description="Get details of the latest scraping job",
        tags=['Scraper']
    )
    def get(self, request):
        """Get latest job"""
        job = ScrapingJob.objects.order_by('-created_at').first()
        
        if not job:
            return Response({'error': 'No jobs found'}, status=404)
        
        return Response({
            'job': {
                'id': job.id,
                'name': job.name,
                'job_type': job.job_type,
                'status': job.status,
                'progress_percent': job.progress_percent,
                'questions_processed': job.questions_processed,
                'questions_created': job.questions_created,
                'questions_updated': job.questions_updated,
                'questions_failed': job.questions_failed,
                'total_expected': job.total_questions_expected,
                'created_at': job.created_at,
                'started_at': job.started_at,
                'completed_at': job.completed_at,
                'error_message': job.error_message,
                'duration_seconds': job.duration.total_seconds() if job.duration else None
            }
        })


class JobLogsView(APIView):
    """Get job logs"""
    permission_classes = []
    
    @extend_schema(
        description="Get logs for a specific scraping job",
        tags=['Scraper']
    )
    def get(self, request, job_id):
        """Get job logs"""
        try:
            job = ScrapingJob.objects.get(id=job_id)
        except ScrapingJob.DoesNotExist:
            return Response({'error': 'Job not found'}, status=404)
        
        # Get errors for this job
        errors = ScrapingError.objects.filter(job=job)
        
        return Response({
            'job_id': job.id,
            'logs': job.logs,
            'errors': [
                {
                    'error_type': error.error_type,
                    'error_message': error.error_message,
                    'context': error.context,
                    'created_at': error.created_at
                }
                for error in errors
            ]
        })


class RestartJobView(APIView):
    """Restart a failed job"""
    permission_classes = []
    
    @extend_schema(
        description="Restart a failed scraping job",
        tags=['Scraper']
    )
    def post(self, request, job_id):
        """Restart job"""
        try:
            old_job = ScrapingJob.objects.get(id=job_id)
        except ScrapingJob.DoesNotExist:
            return Response({'error': 'Job not found'}, status=404)
        
        if old_job.status not in ['failed', 'cancelled']:
            return Response({
                'error': 'Only failed or cancelled jobs can be restarted'
            }, status=400)
        
        # Create new job with same config
        new_job = ScrapingJob.objects.create(
            job_type=old_job.job_type,
            created_by=request.user,
            config=old_job.config
        )
        
        return Response({
            'message': 'Job restarted successfully',
            'old_job_id': old_job.id,
            'new_job_id': new_job.id
        })


class DataStatsView(APIView):
    """Get data statistics"""
    permission_classes = []
    
    @extend_schema(
        description="Get statistics about scraped data",
        tags=['Scraper']
    )
    def get(self, request):
        """Get data stats"""
        from django.db.models import Count
        
        # Get question statistics
        question_stats = Question.objects.aggregate(
            total_questions=Count('id')
        )
        
        # Get job statistics
        job_stats = ScrapingJob.objects.aggregate(
            total_jobs=Count('id')
        )
        
        completed_jobs = ScrapingJob.objects.filter(status='completed').count()
        failed_jobs = ScrapingJob.objects.filter(status='failed').count()
        
        return Response({
            'questions': {
                'total': question_stats['total_questions'] or 0
            },
            'jobs': {
                'total': job_stats['total_jobs'] or 0,
                'completed': completed_jobs,
                'failed': failed_jobs,
                'success_rate': (completed_jobs / max(job_stats['total_jobs'] or 1, 1)) * 100
            },
            'last_updated': timezone.now()
        })


class ValidateDataView(APIView):
    """Validate scraped data"""
    permission_classes = []
    
    @extend_schema(
        description="Validate consistency of scraped data",
        tags=['Scraper']
    )
    def post(self, request):
        """Validate data"""
        # Basic validation checks
        validation_results = {
            'questions_without_session': Question.objects.filter(session__isnull=True).count(),
            'questions_without_member': Question.objects.filter(asked_by__isnull=True).count(),
            'empty_question_text': Question.objects.filter(question_text='').count(),
            'duplicate_questions': 0  # TODO: implement duplicate detection
        }
        
        total_issues = sum(validation_results.values())
        
        return Response({
            'validation_results': validation_results,
            'total_issues': total_issues,
            'data_quality_score': max(0, 100 - (total_issues * 5)),  # Simple scoring
            'validated_at': timezone.now()
        })


class CleanupDataView(APIView):
    """Cleanup old data"""
    permission_classes = []
    
    @extend_schema(
        description="Cleanup old scraping data and logs",
        tags=['Scraper']
    )
    def post(self, request):
        """Cleanup data"""
        days_to_keep = request.data.get('days_to_keep', 30)
        cutoff_date = timezone.now() - timezone.timedelta(days=days_to_keep)
        
        # Delete old errors
        old_errors = ScrapingError.objects.filter(
            created_at__lt=cutoff_date,
            is_resolved=True
        )
        error_count = old_errors.count()
        old_errors.delete()
        
        # Delete old completed jobs (keep failed ones for analysis)
        old_jobs = ScrapingJob.objects.filter(
            created_at__lt=cutoff_date,
            status='completed'
        )
        job_count = old_jobs.count()
        old_jobs.delete()
        
        return Response({
            'message': 'Cleanup completed',
            'deleted_errors': error_count,
            'deleted_jobs': job_count,
        })


class CheckForUpdatesView(APIView):
    """Check for new questions available in API"""
    permission_classes = []
    
    @extend_schema(
        description="Check if there are new questions available on the API compared to database",
        tags=['Scraper']
    )
    def post(self, request):
        """Check for updates"""
        loksabha_no = str(request.data.get('loksabha_no', '17'))
        session_no = request.data.get('session_no')
        
        # Validate loksabha_no
        if not loksabha_no.isdigit():
            return Response({
                'error': 'Invalid loksabha_no. Must be a number (e.g., "17")'
            }, status=400)
        
        try:
            service = ParliamentQuestionsScraperService()
            
            # Quick database count (fast)
            db_count = service._get_existing_questions_count(loksabha_no, session_no)
            
            # For API count, we'll return a quick response and note
            return Response({
                'database_count': db_count,
                'loksabha_no': loksabha_no,
                'session_no': session_no,
                'note': 'Database count retrieved. For full API comparison, start a scraping job to get latest count.',
                'recommendation': 'Use /api/scraper/start/ to begin scraping and get accurate comparison.'
            })
            
        except Exception as e:
            return Response({
                'error': f'Failed to check updates: {str(e)}'
            }, status=500)


class DatabaseStatsView(APIView):
    """Get comprehensive database statistics"""
    permission_classes = []
    
    @extend_schema(
        description="Get detailed statistics about scraped questions in the database",
        tags=['Scraper']
    )
    def get(self, request):
        """Get database stats"""
        from django.db.models import Count, Q
        from services.questions.models import LokSabha, Session
        
        # Overall statistics
        total_questions = Question.objects.count()
        total_members = Question.objects.values('members__name').distinct().count()
        total_ministries = Question.objects.values('ministries__name').distinct().count()
        
        # Questions by Lok Sabha
        loksabha_stats = []
        for loksabha in LokSabha.objects.all():
            question_count = Question.objects.filter(lok_sabha=loksabha).count()
            if question_count > 0:
                loksabha_stats.append({
                    'loksabha_number': loksabha.number,
                    'question_count': question_count,
                    'is_current': loksabha.is_current
                })
        
        # Questions by Session (grouped by Lok Sabha)
        session_stats = []
        for loksabha in LokSabha.objects.all():
            sessions = Session.objects.filter(lok_sabha=loksabha)
            for session in sessions:
                question_count = Question.objects.filter(session=session).count()
                if question_count > 0:
                    session_stats.append({
                        'loksabha_number': loksabha.number,
                        'session_number': session.session_number,
                        'session_name': session.name if hasattr(session, 'name') and session.name else f"Session {session.session_number}",
                        'question_count': question_count,
                        'is_current_loksabha': loksabha.is_current
                    })
        
        # Also get questions with no session assigned
        questions_without_session = Question.objects.filter(session__isnull=True).count()
        if questions_without_session > 0:
            # Group by Lok Sabha for questions without session
            for loksabha in LokSabha.objects.all():
                no_session_count = Question.objects.filter(
                    lok_sabha=loksabha, 
                    session__isnull=True
                ).count()
                if no_session_count > 0:
                    session_stats.append({
                        'loksabha_number': loksabha.number,
                        'session_number': None,
                        'session_name': 'No Session Assigned',
                        'question_count': no_session_count,
                        'is_current_loksabha': loksabha.is_current
                    })
        
        # Sort session stats by Lok Sabha and session number
        session_stats.sort(key=lambda x: (
            int(x['loksabha_number']) if x['loksabha_number'].isdigit() else 0,
            x['session_number'] or '0'
        ))
        
        # Questions by type
        question_types = Question.objects.values('question_type').annotate(
            count=Count('id')
        ).order_by('-count')
        
        # Questions with/without answers
        answered_questions = Question.objects.exclude(
            Q(answer_text='') | Q(answer_text__isnull=True)
        ).count()
        unanswered_questions = total_questions - answered_questions
        
        # Recent activity
        from django.utils import timezone
        from datetime import timedelta
        
        recent_questions = Question.objects.filter(
            last_scraped__gte=timezone.now() - timedelta(days=7)
        ).count()
        
        # Data richness statistics
        questions_with_pdf_files = Question.objects.exclude(pdf_files=[]).count()
        questions_with_ministers = Question.objects.exclude(minister_names=[]).count()
        questions_with_document_handle = Question.objects.exclude(document_handle='').count()
        questions_with_resource_id = Question.objects.exclude(api_resource_id='').count()
        
        # Language breakdown
        language_stats = Question.objects.exclude(language='').values('language').annotate(
            count=Count('id')
        ).order_by('-count')
        
        # Document type breakdown
        doc_type_stats = Question.objects.exclude(document_type='').values('document_type').annotate(
            count=Count('id')
        ).order_by('-count')
        
        return Response({
            'total_statistics': {
                'total_questions': total_questions,
                'total_members': total_members,
                'total_ministries': total_ministries,
                'answered_questions': answered_questions,
                'unanswered_questions': unanswered_questions,
                'recent_questions_scraped': recent_questions
            },
            'loksabha_breakdown': loksabha_stats,
            'session_breakdown': session_stats,
            'question_types': list(question_types),
            'answer_statistics': {
                'answered_percentage': round((answered_questions / max(total_questions, 1)) * 100, 2),
                'unanswered_percentage': round((unanswered_questions / max(total_questions, 1)) * 100, 2)
            },
            'data_richness': {
                'questions_with_pdf_files': questions_with_pdf_files,
                'questions_with_ministers': questions_with_ministers,
                'questions_with_document_handle': questions_with_document_handle,
                'questions_with_api_resource_id': questions_with_resource_id,
                'pdf_coverage_percentage': round((questions_with_pdf_files / max(total_questions, 1)) * 100, 2),
                'minister_coverage_percentage': round((questions_with_ministers / max(total_questions, 1)) * 100, 2)
            },
            'language_breakdown': list(language_stats),
            'document_type_breakdown': list(doc_type_stats)
        })


class CleanupStaleJobsView(APIView):
    """Manually cleanup stale jobs"""
    permission_classes = []
    
    @extend_schema(
        description="Manually cleanup jobs that are stuck in running/pending state",
        tags=['Scraper']
    )
    def post(self, request):
        """Cleanup stale jobs"""
        from datetime import timedelta
        
        # Allow custom threshold, default to 1 hour
        hours = request.data.get('stale_hours', 1)
        stale_threshold = timezone.now() - timedelta(hours=hours)
        
        stale_jobs = ScrapingJob.objects.filter(
            status__in=['pending', 'running'],
            last_activity__lt=stale_threshold
        )
        
        if not stale_jobs.exists():
            return Response({
                'message': 'No stale jobs found',
                'cleaned_count': 0
            })
        
        stale_count = stale_jobs.count()
        job_details = []
        
        for job in stale_jobs:
            job_details.append({
                'id': job.id,
                'name': job.name,
                'status': job.status,
                'last_activity': job.last_activity
            })
            
            job.status = 'failed'
            job.error_message = f"Manually marked as stale - no activity since {job.last_activity}"
            job.completed_at = timezone.now()
            job.save()
        
        return Response({
            'message': f'Cleaned up {stale_count} stale jobs',
            'cleaned_count': stale_count,
            'cleaned_jobs': job_details
        })


class JobDetailsView(APIView):
    """Get details of a specific scraping job"""
    permission_classes = []
    
    @extend_schema(
        description="Get detailed information about a specific scraping job by ID",
        tags=['Scraper']
    )
    def get(self, request, job_id):
        """Get job details by ID"""
        try:
            job = ScrapingJob.objects.get(id=job_id)
        except ScrapingJob.DoesNotExist:
            return Response({'error': 'Job not found'}, status=404)
        
        return Response({
            'job': {
                'id': job.id,
                'name': job.name,
                'description': job.description,
                'job_type': job.job_type,
                'status': job.status,
                'progress_percent': job.progress_percent,
                'questions_processed': job.questions_processed,
                'questions_created': job.questions_created,
                'questions_updated': job.questions_updated,
                'questions_failed': job.questions_failed,
                'total_expected': job.total_questions_expected,
                'batch_size': job.batch_size,
                'worker_count': job.worker_count,
                'created_at': job.created_at,
                'started_at': job.started_at,
                'completed_at': job.completed_at,
                'last_activity': job.last_activity,
                'error_message': job.error_message,
                'error_count': job.error_count,
                'duration_seconds': job.duration.total_seconds() if job.duration else None,
                'is_running': job.is_running,
                'target_loksabhas': [ls.number for ls in job.target_lok_sabhas.all()],
                'target_sessions': [f"{s.lok_sabha.number}th LS Session {s.session_number}" for s in job.target_sessions.all()]
            }
        }) 