from django.shortcuts import render
from django.db.models import Q
from rest_framework import viewsets, status
from rest_framework.decorators import action, api_view
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from drf_spectacular.utils import extend_schema, OpenApiParameter
from drf_spectacular.types import OpenApiTypes
from .models import Question, QuestionMasterData, LokSabha, Session, Member, Ministry
from .question_download_service import QuestionDownloadService
from .master_data_service import QuestionMasterDataService
from .rs_master_data_service import RajyaSabhaMasterDataService
from .fast_stats_view import FastDownloadStatsView
import logging

logger = logging.getLogger(__name__)


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
                'status': 'success',
                'data': {
                    'questions': questions,
                    'pagination': {
                        'total': total_count,
                        'limit': limit,
                        'returned': len(questions)
                    },
                    'filters_applied': {
                        'lok_sabha': lok_sabha,
                        'question_type': question_type,
                        'search': search
                    }
                },
                'message': f'Retrieved {len(questions)} LS questions'
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
    permission_classes = [IsAuthenticated]
    
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
    permission_classes = [IsAuthenticated]
    
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
    permission_classes = [IsAuthenticated]
    
    @extend_schema(
        description="Process question download queue",
        tags=['Questions']
    )
    def post(self, request):
        """Process download queue"""
        try:
            max_items = request.data.get('max_items', 10)
            use_celery = request.data.get('use_celery', True)
            
            if use_celery:
                # Use Celery task
                from .tasks import process_download_queue_task
                
                task = process_download_queue_task.delay(max_items)
                
                return Response({
                    'task_id': task.id,
                    'status': 'started',
                    'message': f'Queue processing started via Celery for {max_items} items. Use task status endpoint to get results.'
                })
            else:
                # Direct processing
                service = QuestionDownloadService()
                result = service.process_download_queue(max_items, use_celery=False)
                
                return Response({
                    'status': 'completed',
                    'result': result
                })
            
        except Exception as e:
            return Response({
                'error': f'Failed to process download queue: {str(e)}'
            }, status=500)


class QuestionDownloadStatisticsView(APIView):
    """Get question download statistics using Celery"""
    permission_classes = [IsAuthenticated]
    
    @extend_schema(
        description="Get question download statistics including master data stats",
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
                download_service = QuestionDownloadService()
                download_stats = download_service.get_download_statistics()
                
                master_service = QuestionMasterDataService()
                master_stats = master_service.get_master_data_statistics()
                
                return Response({
                    'download_statistics': download_stats,
                    'master_data_statistics': master_stats,
                    'calculated_at': 'real-time'
                })
            
        except Exception as e:
            return Response({
                'error': f'Failed to get download statistics: {str(e)}'
            }, status=500)


class QuestionPopulateView(APIView):
    """Populate questions from external sansad.in API"""
    permission_classes = [IsAuthenticated]
    
    @extend_schema(
        description="Populate questions from external API and test download flow",
        tags=['Questions']
    )
    def post(self, request):
        """Populate questions from external API"""
        try:
            import requests
            import uuid
            from django.utils import timezone
            
            loksabha_no = request.data.get('loksabha_no', '18')
            session_no = request.data.get('session_no', '5')
            page_size = request.data.get('page_size', 10)
            test_download = request.data.get('test_download', True)
            
            # Fetch from external API
            external_url = f"https://sansad.in/api_ls/question/qetFilteredQuestionsAns?loksabhaNo={loksabha_no}&sessionNumber={session_no}&pageNo=1&locale=en&pageSize={page_size}"
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36',
                'Accept': 'application/json, text/plain, */*',
                'Referer': 'https://sansad.in/ls/questions/questions-and-answers'
            }
            
            response = requests.get(external_url, headers=headers, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            if not data or not isinstance(data, list) or not data[0].get('listOfQuestions'):
                return Response({
                    'error': 'Invalid response from external API'
                }, status=400)
            
            questions_data = data[0]['listOfQuestions']
            total_available = data[0].get('totalRecordSize', len(questions_data))
            
            # Get or create LokSabha and Session
            lok_sabha, _ = LokSabha.objects.get_or_create(
                number=loksabha_no,
                defaults={'is_current': loksabha_no == '18'}
            )
            
            session, _ = Session.objects.get_or_create(
                lok_sabha=lok_sabha,
                session_number=session_no,
                defaults={'is_current': session_no == '5'}
            )
            
            # Save questions to database
            created_count = 0
            updated_count = 0
            
            for q_data in questions_data:
                question_data = {
                    'question_id': str(uuid.uuid4()),
                    'question_number': str(q_data.get('quesNo', '')),
                    'question_type': q_data.get('type', 'STARRED'),
                    'title': q_data.get('subjects', ''),
                    'subject': q_data.get('subjects', ''),
                    'lok_sabha': lok_sabha,
                    'session': session,
                    'pdf_files': [q_data.get('questionsFilePath', '')],
                    'minister_names': [q_data.get('ministry', '')],
                    'raw_api_data': q_data,
                    'last_scraped': timezone.now()
                }
                
                # Create or update question
                question, created = Question.objects.get_or_create(
                    question_number=question_data['question_number'],
                    lok_sabha=lok_sabha,
                    session=session,
                    defaults=question_data
                )
                
                if created:
                    created_count += 1
                else:
                    # Update existing
                    for key, value in question_data.items():
                        if key not in ['question_number', 'lok_sabha', 'session']:
                            setattr(question, key, value)
                    question.save()
                    updated_count += 1
            
            result = {
                'status': 'SUCCESS',
                'loksabha_no': loksabha_no,
                'session_no': session_no,
                'total_available': total_available,
                'fetched': len(questions_data),
                'created': created_count,
                'updated': updated_count,
                'message': f'Successfully populated {created_count} new and {updated_count} updated questions'
            }
            
            # Test download flow if requested
            if test_download and created_count > 0:
                # Get the first created question and test download
                test_question = Question.objects.filter(
                    lok_sabha=lok_sabha,
                    session=session
                ).exclude(pdf_files__exact=[]).first()
                
                if test_question and test_question.pdf_files:
                    try:
                        service = QuestionDownloadService()
                        pdf_url = test_question.pdf_files[0]
                        
                        # Test the download with GCS integration
                        download_success = service.download_question_pdf(test_question, pdf_url)
                        
                        result['test_download'] = {
                            'attempted': True,
                            'success': download_success,
                            'question_number': test_question.question_number,
                            'pdf_url': pdf_url
                        }
                        
                        if download_success:
                            # Check if file was uploaded to GCS
                            from services.files.models import DocumentFile
                            doc_file = DocumentFile.objects.filter(question=test_question).first()
                            if doc_file:
                                result['test_download']['gcs_status'] = doc_file.gcs_upload_status
                                result['test_download']['gcs_bucket'] = doc_file.gcs_bucket_name
                                result['test_download']['gcs_object'] = doc_file.gcs_object_key
                        
                    except Exception as download_error:
                        result['test_download'] = {
                            'attempted': True,
                            'success': False,
                            'error': str(download_error)
                        }
            
            return Response(result)
            
        except Exception as e:
            return Response({
                'error': f'Failed to populate questions: {str(e)}'
            }, status=500)


class QuestionMasterDataView(APIView):
    """Manage master questions data from sansad.in API"""
    permission_classes = [IsAuthenticated]
    
    @extend_schema(
        description="Fetch Lok Sabha sessions metadata",
        tags=['Questions Master Data']
    )
    def get(self, request):
        """Get master data statistics"""
        try:
            service = QuestionMasterDataService()
            stats = service.get_master_data_statistics()
            
            return Response({
                'status': 'SUCCESS',
                'statistics': stats
            })
            
        except Exception as e:
            return Response({
                'error': f'Failed to get master data statistics: {str(e)}'
            }, status=500)
    
    @extend_schema(
        description="Fetch and store Lok Sabha sessions metadata",
        tags=['Questions Master Data']
    )
    def post(self, request):
        """Fetch Lok Sabha sessions from API"""
        try:
            action = request.data.get('action', 'fetch_sessions')
            service = QuestionMasterDataService()
            
            if action == 'fetch_sessions':
                result = service.fetch_lok_sabha_sessions()
                return Response(result)
            
            elif action == 'fetch_questions_count':
                result = service.fetch_questions_count_by_lok_sabha()
                return Response(result)
            
            elif action == 'fetch_questions':
                lok_sabha_number = request.data.get('lok_sabha_number', '18')
                session_number = request.data.get('session_number', '5')
                page_size = request.data.get('page_size', 10000)
                
                result = service.fetch_questions_for_session(
                    lok_sabha_number, session_number, page_size
                )
                return Response(result)
            
            elif action == 'initialize_master_data':
                force_update = request.data.get('force_update', False)
                
                result = service.initialize_master_data(force_update)
                return Response(result)
            
            elif action == 'fetch_all_questions':
                lok_sabha_numbers = request.data.get('lok_sabha_numbers')
                max_sessions_per_lok_sabha = request.data.get('max_sessions_per_lok_sabha')
                
                result = service.fetch_all_questions(
                    lok_sabha_numbers, max_sessions_per_lok_sabha
                )
                return Response(result)
            
            else:
                return Response({
                    'error': 'Invalid action. Supported actions: fetch_sessions, fetch_questions_count, fetch_questions, initialize_master_data, fetch_all_questions'
                }, status=400)
            
        except Exception as e:
            return Response({
                'error': f'Failed to execute action {action}: {str(e)}'
            }, status=500)


class QuestionMasterDataBulkDownloadView(APIView):
    """Start bulk download from master data"""
    permission_classes = [IsAuthenticated]
    
    @extend_schema(
        description="Start bulk download of question PDFs from master data",
        tags=['Questions Master Data']
    )
    def post(self, request):
        """Start bulk download from master data"""
        try:
            lok_sabha_number = request.data.get('lok_sabha_number')
            session_number = request.data.get('session_number')
            question_type = request.data.get('question_type')
            limit = request.data.get('limit')
            use_celery = request.data.get('use_celery', True)
            pending_only = request.data.get('pending_only', True)  # Default to pending only
            
            # Get master data service
            master_service = QuestionMasterDataService()
            
            # Get questions for download
            master_data_list = master_service.get_questions_for_download(
                lok_sabha_number=lok_sabha_number,
                session_number=session_number,
                question_type=question_type,
                limit=limit,
                pending_only=pending_only
            )
            
            if not master_data_list:
                return Response({
                    'error': 'No questions found matching the criteria'
                }, status=404)
            
            # Initialize download service
            download_service = QuestionDownloadService()
            
            # Start bulk download
            result = download_service.bulk_download_questions_from_master_data(
                master_data_list, use_celery=use_celery
            )
            
            return Response(result)
            
        except Exception as e:
            return Response({
                'error': f'Failed to start bulk download from master data: {str(e)}'
            }, status=500)


class QuestionMasterDataListView(APIView):
    """List master questions data with filtering"""
    permission_classes = [IsAuthenticated]
    
    @extend_schema(
        description="List master questions data with filtering options",
        parameters=[
            OpenApiParameter(
                name='lok_sabha_number',
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description='Filter by Lok Sabha number (e.g., 18)'
            ),
            OpenApiParameter(
                name='session_number',
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description='Filter by session number (e.g., 5)'
            ),
            OpenApiParameter(
                name='question_type',
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description='Filter by question type (STARRED, UNSTARRED)'
            ),
            OpenApiParameter(
                name='is_processed',
                type=OpenApiTypes.BOOL,
                location=OpenApiParameter.QUERY,
                description='Filter by processing status'
            ),
            OpenApiParameter(
                name='limit',
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                description='Limit number of results (default: 50)'
            ),
        ],
        tags=['Questions Master Data']
    )
    def get(self, request):
        """List master questions data"""
        try:
            # Get query parameters
            lok_sabha_number = request.query_params.get('lok_sabha_number')
            session_number = request.query_params.get('session_number')
            question_type = request.query_params.get('question_type')
            is_processed = request.query_params.get('is_processed')
            limit = int(request.query_params.get('limit', 50))
            
            # Build queryset
            queryset = QuestionMasterData.objects.all()
            
            if lok_sabha_number:
                queryset = queryset.filter(lok_sabha_number=lok_sabha_number)
            
            if session_number:
                queryset = queryset.filter(session_number=session_number)
            
            if question_type:
                queryset = queryset.filter(question_type=question_type)
            
            if is_processed is not None:
                is_processed_bool = is_processed.lower() == 'true'
                queryset = queryset.filter(is_processed=is_processed_bool)
            
            # Apply ordering and limit
            queryset = queryset.order_by('-date', '-question_number')[:limit]
            
            # Convert to list
            master_data_list = []
            for md in queryset:
                master_data_list.append({
                    'id': md.id,
                    'question_number': md.question_number,
                    'subjects': md.subjects,
                    'lok_sabha_number': md.lok_sabha_number,
                    'session_number': md.session_number,
                    'question_type': md.question_type,
                    'members': md.members,
                    'ministry': md.ministry,
                    'date': md.date.isoformat() if md.date else None,
                    'has_pdf_url': bool(md.get_pdf_url()),
                    'pdf_url': md.get_pdf_url(),
                    'is_processed': md.is_processed,
                    'processed_at': md.processed_at.isoformat() if md.processed_at else None,
                    'last_fetched': md.last_fetched.isoformat() if md.last_fetched else None
                })
            
            return Response({
                'master_data': master_data_list,
                'total_returned': len(master_data_list),
                'filters_applied': {
                    'lok_sabha_number': lok_sabha_number,
                    'session_number': session_number,
                    'question_type': question_type,
                    'is_processed': is_processed,
                    'limit': limit
                }
            })
            
        except Exception as e:
            return Response({
                'error': f'Failed to list master data: {str(e)}'
            }, status=500)


class QuestionSessionTestView(APIView):
    """Session-based question testing endpoints"""
    permission_classes = [IsAuthenticated]
    
    @extend_schema(
        description="Get available sessions for testing",
        tags=['Questions Testing']
    )
    def get(self, request):
        """List all available sessions with question counts"""
        try:
            service = QuestionMasterDataService()
            sessions = service.list_available_sessions()
            
            return Response({
                'status': 'SUCCESS',
                'total_sessions': len(sessions),
                'sessions': sessions,
                'message': f'Found {len(sessions)} sessions with question data'
            })
            
        except Exception as e:
            return Response({
                'error': f'Failed to list available sessions: {str(e)}'
            }, status=500)
    
    @extend_schema(
        description="Test random questions from a specific session",
        tags=['Questions Testing']
    )
    def post(self, request):
        """Test random questions from a session"""
        try:
            lok_sabha_number = request.data.get('lok_sabha_number', '18')
            session_number = request.data.get('session_number', '5')
            question_count = request.data.get('question_count', 20)
            download_pdfs = request.data.get('download_pdfs', True)
            use_celery = request.data.get('use_celery', True)
            
            # Get master data service
            master_service = QuestionMasterDataService()
            
            # Get session summary first
            session_summary = master_service.get_session_summary(lok_sabha_number, session_number)
            
            # Get random questions directly from database
            random_questions = QuestionMasterData.objects.filter(
                lok_sabha_number=lok_sabha_number,
                session_number=session_number
            ).exclude(questions_file_path='').order_by('?')[:question_count]
            
            if not random_questions:
                return Response({
                    'error': f'No questions with PDF URLs found for LS{lok_sabha_number} Session{session_number}',
                    'session_summary': session_summary
                }, status=404)
            
            result = {
                'status': 'SUCCESS',
                'session_summary': session_summary,
                'selected_questions': len(random_questions),
                'questions': []
            }
            
            # Add question details
            for q in random_questions:
                result['questions'].append({
                    'id': q.id,
                    'question_number': q.question_number,
                    'subjects': q.subjects,
                    'question_type': q.question_type,
                    'ministry': q.ministry,
                    'members': q.members,
                    'pdf_url': q.get_pdf_url(),
                    'date': q.date.isoformat() if q.date else None
                })
            
            # If download requested, start bulk download
            if download_pdfs:
                download_service = QuestionDownloadService()
                
                # Convert to actual QuestionMasterData objects for download
                master_data_objects = list(random_questions)
                
                download_result = download_service.bulk_download_questions_from_master_data(
                    master_data_objects, use_celery=use_celery
                )
                
                result['download_result'] = download_result
            
            return Response(result)
            
        except ValueError as e:
            return Response({
                'error': str(e)
            }, status=404)
        except Exception as e:
            return Response({
                'error': f'Failed to test session questions: {str(e)}'
            }, status=500)


class QuestionSessionSummaryView(APIView):
    """Get detailed summary for a specific session"""
    permission_classes = [IsAuthenticated]
    
    @extend_schema(
        description="Get detailed summary for a specific session",
        parameters=[
            OpenApiParameter(
                name='lok_sabha_number',
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description='Lok Sabha number (e.g., 18)',
                required=True
            ),
            OpenApiParameter(
                name='session_number',
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description='Session number (e.g., 5)',
                required=True
            ),
        ],
        tags=['Questions Testing']
    )
    def get(self, request):
        """Get session summary"""
        try:
            lok_sabha_number = request.query_params.get('lok_sabha_number')
            session_number = request.query_params.get('session_number')
            
            if not lok_sabha_number or not session_number:
                return Response({
                    'error': 'Both lok_sabha_number and session_number are required'
                }, status=400)
            
            service = QuestionMasterDataService()
            summary = service.get_session_summary(lok_sabha_number, session_number)
            
            return Response({
                'status': 'SUCCESS',
                'summary': summary
            })
            
        except ValueError as e:
            return Response({
                'error': str(e)
            }, status=404)
        except Exception as e:
            return Response({
                'error': f'Failed to get session summary: {str(e)}'
            }, status=500)


# ============================================================================
# RAJYA SABHA VIEWS (Integrated into existing views.py)
# ============================================================================

class RSQuestionMasterDataView(APIView):
    """Rajya Sabha Question Master Data endpoints"""
    permission_classes = [IsAuthenticated]
    
    @extend_schema(
        description="Get Rajya Sabha question master data statistics and overview",
        tags=['RS Questions']
    )
    def get(self, request):
        """Get RS question master data overview"""
        try:
            rs_service = RajyaSabhaMasterDataService()
            stats = rs_service.get_rs_statistics()
            
            return Response({
                'status': 'success',
                'data': stats,
                'message': 'RS question master data retrieved successfully'
            })
            
        except Exception as e:
            logger.error(f"Failed to get RS master data: {str(e)}")
            return Response({
                'status': 'error',
                'message': f'Failed to get RS master data: {str(e)}'
            }, status=500)


class RSQuestionStatisticsView(APIView):
    """Get RS question statistics"""
    permission_classes = [IsAuthenticated]
    
    @extend_schema(
        description="Get detailed statistics about RS questions",
        tags=['RS Questions']
    )
    def get(self, request):
        """Get RS question statistics"""
        try:
            from .models import ParliamentInstitution
            from django.db.models import Count, Q
            
            rs_service = RajyaSabhaMasterDataService()
            stats = rs_service.get_rs_statistics()
            
            # Add additional statistics
            rs_institution = ParliamentInstitution.objects.get(name='rajya_sabha')
            
            # Session-wise breakdown
            session_stats = QuestionMasterData.objects.filter(
                parent_institution=rs_institution
            ).values('session_number').annotate(
                total=Count('id'),
                with_pdf=Count('id', filter=Q(questions_file_path__gt='')),
                processed=Count('id', filter=Q(is_processed=True)),
                starred=Count('id', filter=Q(question_type='STARRED')),
                unstarred=Count('id', filter=Q(question_type='UNSTARRED'))
            ).order_by('-session_number')[:20]  # Top 20 recent sessions
            
            # Ministry-wise breakdown
            ministry_stats = QuestionMasterData.objects.filter(
                parent_institution=rs_institution
            ).exclude(ministry='').values('ministry').annotate(
                total=Count('id')
            ).order_by('-total')[:15]  # Top 15 ministries
            
            stats.update({
                'session_breakdown': list(session_stats),
                'ministry_breakdown': list(ministry_stats)
            })
            
            return Response({
                'status': 'success',
                'data': stats,
                'message': 'RS question statistics retrieved successfully'
            })
            
        except ParliamentInstitution.DoesNotExist:
            return Response({
                'status': 'error',
                'message': 'Rajya Sabha institution not found'
            }, status=404)
        except Exception as e:
            logger.error(f"Failed to get RS statistics: {str(e)}")
            return Response({
                'status': 'error',
                'message': f'Failed to get RS statistics: {str(e)}'
            }, status=500)


class RSQuestionMasterDataListView(APIView):
    """List Rajya Sabha question master data with filtering"""
    permission_classes = [IsAuthenticated]
    
    @extend_schema(
        description="List RS question master data with filtering options",
        tags=['RS Questions']
    )
    def get(self, request):
        """List RS question master data"""
        try:
            from .models import ParliamentInstitution
            
            # Get query parameters
            session_number = request.GET.get('session_number')
            question_type = request.GET.get('question_type')
            ministry = request.GET.get('ministry')
            has_pdf = request.GET.get('has_pdf')
            limit = int(request.GET.get('limit', 100))
            offset = int(request.GET.get('offset', 0))
            
            # Get RS institution
            rs_institution = ParliamentInstitution.objects.get(name='rajya_sabha')
            
            # Build queryset
            queryset = QuestionMasterData.objects.filter(parent_institution=rs_institution)
            
            if session_number:
                queryset = queryset.filter(session_number=session_number)
            
            if question_type:
                queryset = queryset.filter(question_type=question_type)
            
            if ministry:
                queryset = queryset.filter(ministry__icontains=ministry)
            
            if has_pdf == 'true':
                queryset = queryset.exclude(questions_file_path='')
            elif has_pdf == 'false':
                queryset = queryset.filter(questions_file_path='')
            
            # Get total count
            total_count = queryset.count()
            
            # Apply pagination
            questions = queryset.order_by('-date', '-question_number')[offset:offset+limit]
            
            # Serialize data
            questions_data = []
            for q in questions:
                questions_data.append({
                    'id': q.id,
                    'question_number': q.question_number,
                    'subjects': q.subjects,
                    'question_type': q.question_type,
                    'ministry': q.ministry,
                    'session_number': q.session_number,
                    'date': q.date.isoformat() if q.date else None,
                    'has_pdf': bool(q.questions_file_path),
                    'pdf_url': q.questions_file_path,
                    'pdf_url_hindi': q.questions_file_path_hindi,
                    'is_processed': q.is_processed,
                    'members': q.members,
                    'created_at': q.created_at.isoformat(),
                    'last_fetched': q.last_fetched.isoformat()
                })
            
            return Response({
                'status': 'success',
                'data': {
                    'questions': questions_data,
                    'pagination': {
                        'total': total_count,
                        'limit': limit,
                        'offset': offset,
                        'has_next': offset + limit < total_count,
                        'has_previous': offset > 0
                    }
                },
                'message': f'Retrieved {len(questions_data)} RS questions'
            })
            
        except ParliamentInstitution.DoesNotExist:
            return Response({
                'status': 'error',
                'message': 'Rajya Sabha institution not found. Please initialize RS data first.'
            }, status=404)
        except Exception as e:
            logger.error(f"Failed to list RS questions: {str(e)}")
            return Response({
                'status': 'error',
                'message': f'Failed to list RS questions: {str(e)}'
            }, status=500)


class RSQuestionScrapingView(APIView):
    """Start RS question scraping"""
    permission_classes = [IsAuthenticated]
    
    @extend_schema(
        description="Start scraping RS questions for a specific session",
        tags=['RS Questions']
    )
    def post(self, request):
        """Start RS question scraping"""
        try:
            from .tasks import scrape_rs_questions_task
            
            session_number = request.data.get('session_number', '268')  # Default to current session
            download_pdfs = request.data.get('download_pdfs', True)
            
            # Start scraping task
            task = scrape_rs_questions_task.delay(
                session_no=session_number,
                download_pdfs=download_pdfs
            )
            
            return Response({
                'status': 'success',
                'data': {
                    'task_id': task.id,
                    'session_number': session_number,
                    'download_pdfs': download_pdfs
                },
                'message': f'Started RS question scraping for session {session_number}'
            })
            
        except Exception as e:
            logger.error(f"Failed to start RS scraping: {str(e)}")
            return Response({
                'status': 'error',
                'message': f'Failed to start RS scraping: {str(e)}'
            }, status=500)


class RSQuestionBulkDownloadView(APIView):
    """Bulk download RS question PDFs"""
    permission_classes = [IsAuthenticated]
    
    @extend_schema(
        description="Queue multiple RS questions for PDF download",
        tags=['RS Questions']
    )
    def post(self, request):
        """Queue RS questions for bulk PDF download"""
        try:
            from .models import ParliamentInstitution
            from .tasks import bulk_download_rs_question_pdfs_task
            
            master_data_ids = request.data.get('master_data_ids', [])
            session_number = request.data.get('session_number')
            download_all_session = request.data.get('download_all_session', False)
            limit = request.data.get('limit')  # NEW: Support limit parameter
            pending_only = request.data.get('pending_only', True)  # NEW: Support pending_only parameter
            
            # NEW: Support limit and pending_only parameters (for batch download script)
            if limit is not None and not master_data_ids and not download_all_session:
                # Query RS questions with limit and pending_only
                rs_institution = ParliamentInstitution.objects.get(name='rajya_sabha')
                queryset = QuestionMasterData.objects.filter(
                    parent_institution=rs_institution
                ).exclude(questions_file_path='')
                
                if pending_only:
                    queryset = queryset.filter(pdf_downloaded=False)
                
                if session_number:
                    queryset = queryset.filter(session_number=session_number)
                
                # Use random ordering to avoid duplicate scheduling
                queryset = queryset.order_by('?')[:limit]
                
                master_data_ids = list(queryset.values_list('id', flat=True))
                
                logger.info(f"RS bulk download with limit={limit}, pending_only={pending_only}: found {len(master_data_ids)} questions")
            
            elif download_all_session and session_number:
                # Download all questions for a specific session that haven't been downloaded yet
                rs_institution = ParliamentInstitution.objects.get(name='rajya_sabha')
                session_questions = QuestionMasterData.objects.filter(
                    parent_institution=rs_institution,
                    session_number=session_number,
                    pdf_downloaded=False  # FIXED: Check if PDF downloaded, not if metadata processed
                ).exclude(questions_file_path='')
                
                master_data_ids = list(session_questions.values_list('id', flat=True))
                
            elif not master_data_ids:
                return Response({
                    'status': 'error',
                    'message': 'No master_data_ids provided and no query parameters specified'
                }, status=400)
            
            if not master_data_ids:
                return Response({
                    'status': 'error',
                    'message': 'No RS questions found for download'
                }, status=404)
            
            # Start bulk download task
            task = bulk_download_rs_question_pdfs_task.delay(master_data_ids)
            
            return Response({
                'status': 'success',
                'data': {
                    'task_id': task.id,
                    'questions_queued': len(master_data_ids),
                    'session_number': session_number if session_number else None
                },
                'message': f'Queued {len(master_data_ids)} RS questions for bulk download'
            })
            
        except ParliamentInstitution.DoesNotExist:
            return Response({
                'status': 'error',
                'message': 'Rajya Sabha institution not found'
            }, status=404)
        except Exception as e:
            logger.error(f"Failed to queue RS bulk download: {str(e)}")
            return Response({
                'status': 'error',
                'message': f'Failed to queue bulk download: {str(e)}'
            }, status=500)


class RSQuestionInitializeView(APIView):
    """Initialize RS master data"""
    permission_classes = [IsAuthenticated]
    
    @extend_schema(
        description="Initialize Rajya Sabha master data (sessions and questions)",
        tags=['RS Questions']
    )
    def post(self, request):
        """Initialize RS master data"""
        try:
            from .tasks import initialize_rs_master_data_task
            
            force_update = request.data.get('force_update', False)
            
            # Start initialization task
            task = initialize_rs_master_data_task.delay(force_update=force_update)
            
            return Response({
                'status': 'success',
                'data': {
                    'task_id': task.id,
                    'force_update': force_update
                },
                'message': 'Started RS master data initialization'
            })
            
        except Exception as e:
            logger.error(f"Failed to start RS initialization: {str(e)}")
            return Response({
                'status': 'error',
                'message': f'Failed to start RS initialization: {str(e)}'
            }, status=500)


class RSQuestionTaskStatusView(APIView):
    """Check RS task status"""
    permission_classes = [IsAuthenticated]
    
    @extend_schema(
        description="Check status of RS question Celery tasks",
        tags=['RS Questions']
    )
    def get(self, request, task_id):
        """Get task status"""
        try:
            from celery.result import AsyncResult
            
            task_result = AsyncResult(task_id)
            
            if task_result.state == 'PENDING':
                response = {
                    'state': task_result.state,
                    'status': 'Task is waiting to be processed'
                }
            elif task_result.state == 'PROGRESS':
                response = {
                    'state': task_result.state,
                    'status': task_result.info.get('status', ''),
                    'progress': task_result.info.get('progress', 0),
                    'details': task_result.info
                }
            elif task_result.state == 'SUCCESS':
                response = {
                    'state': task_result.state,
                    'status': 'Task completed successfully',
                    'result': task_result.result
                }
            else:  # FAILURE
                response = {
                    'state': task_result.state,
                    'status': 'Task failed',
                    'error': str(task_result.info)
                }
            
            return Response({
                'status': 'success',
                'data': response
            })
            
        except Exception as e:
            logger.error(f"Failed to get task status: {str(e)}")
            return Response({
                'status': 'error',
                'message': f'Failed to get task status: {str(e)}'
            }, status=500)
