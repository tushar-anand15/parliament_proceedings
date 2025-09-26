from django.shortcuts import render
from django.db.models import Q
from rest_framework import viewsets, status
from rest_framework.decorators import action, api_view
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema, OpenApiParameter
from drf_spectacular.types import OpenApiTypes
from .models import Question, LokSabha, Session, Member, Ministry
from .question_download_service import QuestionDownloadService


class QuestionViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing parliamentary questions.
    
    Provides CRUD operations for questions with advanced filtering and search capabilities.
    """
    queryset = Question.objects.all()
    # serializer_class = QuestionSerializer  # Will be added when we create serializers
    
    @extend_schema(
        description="List all parliamentary questions with optional filtering",
        parameters=[
            OpenApiParameter(
                name='lok_sabha',
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description='Filter by Lok Sabha number (e.g., 15, 16, 17)'
            ),
            OpenApiParameter(
                name='question_type',
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description='Filter by question type (Starred, Unstarred, Short Notice)'
            ),
            OpenApiParameter(
                name='search',
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description='Search in question title and content'
            ),
        ],
        tags=['Questions']
    )
    def list(self, request):
        """List parliamentary questions with filtering options"""
        try:
            # Get query parameters
            lok_sabha = request.query_params.get('lok_sabha')
            question_type = request.query_params.get('question_type')
            search = request.query_params.get('search')
            limit = int(request.query_params.get('limit', 50))
            
            # Start with base queryset
            queryset = Question.objects.all()
            total_count = queryset.count()
            
            # Apply filters
            if lok_sabha:
                queryset = queryset.filter(lok_sabha__number=lok_sabha)
            
            if question_type:
                queryset = queryset.filter(question_type__icontains=question_type)
            
            if search:
                queryset = queryset.filter(
                    Q(title__icontains=search) | 
                    Q(question_text__icontains=search)  # Fixed field name
                )
            
            # Apply limit
            queryset = queryset[:limit]
            
            # Debug: Print actual data
            print(f"DEBUG: Total questions in DB: {total_count}")
            print(f"DEBUG: Queryset count after filters: {queryset.count()}")
            print(f"DEBUG: Limit: {limit}")
            
            # Convert to list of dictionaries
            questions = []
            for q in queryset:
                # Get related data safely
                members_list = list(q.members.values_list('name', flat=True)) if q.members.exists() else []
                ministries_list = list(q.ministries.values_list('name', flat=True)) if q.ministries.exists() else []
                
                questions.append({
                    'id': q.id,
                    'question_id': q.question_id,
                    'question_number': q.question_number,
                    'title': q.title,
                    'question_type': q.question_type,
                    'lok_sabha': q.lok_sabha.number if q.lok_sabha else None,
                    'session': q.session.session_number if q.session else None,
                    'members': members_list,
                    'ministries': ministries_list,
                    'date': q.date.isoformat() if q.date else None,
                    'status': q.status,
                    'pdf_files': q.pdf_files,
                    'has_answer': q.has_answer
                })
            
            return Response({
                'questions': questions,
                'total_questions': len(questions),
                'total_in_database': total_count,
                'filters_applied': {
                    'lok_sabha': lok_sabha,
                    'question_type': question_type,
                    'search': search,
                    'limit': limit
                }
            })
            
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            print(f"Error in questions list API: {error_details}")
            
            return Response({
                'error': f'Failed to fetch questions: {str(e)}',
                'error_details': error_details,
                'questions': [],
                'total_questions': 0
            }, status=500)
    
    
    @extend_schema(
        description="Retrieve a specific parliamentary question",
        tags=['Questions']
    )
    def retrieve(self, request, pk=None):
        """Get details of a specific question"""
        try:
            question = Question.objects.get(pk=pk)
            return Response({
                'message': f'Question {pk} details - serialization to be implemented',
                'question_id': question.question_id,
                'title': question.title,
                'question_type': question.question_type,
                'status': question.status
            })
        except Question.DoesNotExist:
            return Response({'error': 'Question not found'}, status=404)
    
    @action(detail=False, methods=['post'])
    @extend_schema(
        description="Advanced search for parliamentary questions",
        tags=['Questions']
    )
    def search(self, request):
        """Advanced search endpoint for questions"""
        return Response({
            'message': 'Advanced search endpoint - implementation pending',
            'available_search_fields': [
                'title', 'subject', 'question_text', 'answer_text',
                'members', 'ministries', 'date_range'
            ]
        })


@api_view(['GET'])
@extend_schema(
    description="Get statistics about parliamentary questions",
    tags=['Questions']
)
def question_stats(request):
    """Get overall statistics about questions in the database"""
    try:
        total_questions = Question.objects.count()
        total_lok_sabhas = LokSabha.objects.count()
        total_sessions = Session.objects.count()
        total_members = Member.objects.count()
        total_ministries = Ministry.objects.count()
        
        return Response({
            'statistics': {
                'total_questions': total_questions,
                'total_lok_sabhas': total_lok_sabhas,
                'total_sessions': total_sessions,
                'total_members': total_members,
                'total_ministries': total_ministries
            },
            'last_updated': 'Real-time'
        })
    except Exception as e:
        return Response({
            'error': 'Failed to fetch statistics',
            'detail': str(e)
        }, status=500)


class QuestionCeleryTaskStatusView(APIView):
    """Get Celery task status for questions"""
    permission_classes = []
    
    @extend_schema(
        description="Get status of a Celery task for questions",
        tags=['Questions']
    )
    def get(self, request, task_id):
        """Get task status"""
        try:
            from celery.result import AsyncResult
            from .tasks import download_question_pdf_task, bulk_download_question_pdfs_task, process_download_queue_task
            
            # Get task result
            task_result = AsyncResult(task_id, app=download_question_pdf_task.app)
            
            response_data = {
                'task_id': task_id,
                'status': task_result.status,
                'ready': task_result.ready(),
                'successful': task_result.successful(),
                'failed': task_result.failed(),
            }
            
            if task_result.ready():
                if task_result.successful():
                    response_data['result'] = task_result.result
                else:
                    response_data['error'] = str(task_result.result)
            else:
                # Task is still running, get progress info
                if hasattr(task_result, 'info') and task_result.info:
                    response_data['info'] = task_result.info
            
            return Response(response_data)
            
        except Exception as e:
            return Response({
                'error': f'Failed to get task status: {str(e)}'
            }, status=500)


class QuestionBulkDownloadView(APIView):
    """Start bulk download of question PDFs using Celery"""
    permission_classes = []
    
    @extend_schema(
        description="Start bulk download of question PDFs",
        tags=['Questions']
    )
    def post(self, request):
        """Start bulk download"""
        try:
            question_ids = request.data.get('question_ids', [])
            use_celery = request.data.get('use_celery', True)
            
            if not question_ids:
                return Response({
                    'error': 'question_ids is required'
                }, status=400)
            
            # Get questions
            questions = Question.objects.filter(id__in=question_ids)
            
            if not questions.exists():
                return Response({
                    'error': 'No questions found with provided IDs'
                }, status=404)
            
            # Initialize service
            service = QuestionDownloadService()
            
            # Start bulk download
            result = service.bulk_download_questions(questions, use_celery=use_celery)
            
            return Response(result)
            
        except Exception as e:
            return Response({
                'error': f'Failed to start bulk download: {str(e)}'
            }, status=500)


class QuestionDownloadQueueView(APIView):
    """Process question download queue using Celery"""
    permission_classes = []
    
    @extend_schema(
        description="Process question download queue",
        tags=['Questions']
    )
    def post(self, request):
        """Process download queue"""
        try:
            max_items = request.data.get('max_items', 10)
            use_celery = request.data.get('use_celery', True)
            
            # Initialize service
            service = QuestionDownloadService()
            
            # Process queue
            result = service.process_download_queue(max_items, use_celery=use_celery)
            
            return Response(result)
            
        except Exception as e:
            return Response({
                'error': f'Failed to process download queue: {str(e)}'
            }, status=500)


class QuestionDownloadStatisticsView(APIView):
    """Get question download statistics using Celery"""
    permission_classes = []
    
    @extend_schema(
        description="Get question download statistics",
        tags=['Questions']
    )
    def get(self, request):
        """Get download statistics"""
        try:
            use_celery = request.query_params.get('use_celery', 'true').lower() == 'true'
            
            if use_celery:
                # Use Celery task
                from .tasks import get_download_statistics_task
                
                task = get_download_statistics_task.delay()
                
                return Response({
                    'task_id': task.id,
                    'status': 'started',
                    'message': 'Statistics calculation started via Celery. Use task status endpoint to get results.'
                })
            else:
                # Direct calculation
                service = QuestionDownloadService()
                stats = service.get_download_statistics()
                
                return Response({
                    'statistics': stats,
                    'calculated_at': 'real-time'
                })
            
        except Exception as e:
            return Response({
                'error': f'Failed to get download statistics: {str(e)}'
            }, status=500)
