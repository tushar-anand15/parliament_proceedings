"""
Production-Grade Data Explorer Views
Optimized for high performance with large datasets
"""
from django.db.models import Q, Count, Prefetch, F, Min, Max
from django.core.cache import cache
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from drf_spectacular.utils import extend_schema, OpenApiParameter
from drf_spectacular.types import OpenApiTypes
import logging
from datetime import datetime

from services.questions.models import QuestionMasterData, ParliamentInstitution
from services.debates.models import Debate, DebateMasterData
from .serializers import (
    LSQuestionExplorerSerializer,
    RSQuestionExplorerSerializer,
    LSDebateExplorerSerializer,
    RSDebateExplorerSerializer,
    QuestionDetailSerializer,
    DebateDetailSerializer,
    DebateMasterDataSerializer
)

logger = logging.getLogger(__name__)


class BasePaginatedExplorerView(APIView):
    """
    Base class for paginated explorer views
    Implements efficient pagination with count caching
    """
    permission_classes = [IsAuthenticated]
    
    def paginate_queryset(self, queryset, request, cache_key_prefix=''):
        """
        Efficient pagination with count caching
        Returns: (paginated_queryset, pagination_meta)
        """
        # Get pagination parameters
        limit = min(int(request.query_params.get('limit', 100)), 500)  # Max 500
        offset = int(request.query_params.get('offset', 0))
        
        # Try to get total count from cache (with graceful fallback)
        total_count = None
        cache_key = f"{cache_key_prefix}_count"
        
        try:
            total_count = cache.get(cache_key)
        except Exception as e:
            logger.warning(f"Cache get failed: {e}. Continuing without cache.")
        
        if total_count is None:
            total_count = queryset.count()
            # Try to cache for 5 minutes (gracefully fail if cache unavailable)
            try:
                cache.set(cache_key, total_count, 300)
            except Exception as e:
                logger.warning(f"Cache set failed: {e}. Continuing without cache.")
        
        # Get paginated results
        paginated = queryset[offset:offset + limit]
        
        pagination_meta = {
            'total': total_count,
            'limit': limit,
            'offset': offset,
            'returned': len(paginated),
            'has_next': (offset + limit) < total_count,
            'has_previous': offset > 0,
            'next_offset': offset + limit if (offset + limit) < total_count else None,
            'previous_offset': max(0, offset - limit) if offset > 0 else None
        }
        
        return paginated, pagination_meta
    
    def parse_date(self, date_str):
        """Parse date string to date object"""
        if not date_str:
            return None
        try:
            return datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            return None
    
    def build_search_query(self, search_term, fields):
        """Build Q object for search across multiple fields"""
        if not search_term:
            return Q()
        
        query = Q()
        for field in fields:
            query |= Q(**{f"{field}__icontains": search_term})
        return query


class LSQuestionExplorerView(BasePaginatedExplorerView):
    """
    High-performance Lok Sabha Questions Explorer
    Supports advanced filtering, sorting, search, and pagination
    """
    
    @extend_schema(
        description="""
        Explore Lok Sabha Questions with advanced filtering and sorting.
        
        **Performance Features:**
        - Optimized database queries with proper indexing
        - Count caching for fast pagination
        - Efficient serialization
        - Support for up to 500 records per page
        
        **Filtering:**
        - lok_sabha: Lok Sabha number (e.g., "18")
        - session: Session number (e.g., "5")
        - question_type: STARRED, UNSTARRED, SHORT_NOTICE
        - ministry: Filter by ministry (partial match)
        - has_pdf: true/false
        - has_answer: true/false
        - is_processed: true/false
        - pdf_downloaded: true/false
        - date_from: Start date (YYYY-MM-DD)
        - date_to: End date (YYYY-MM-DD)
        - search: Search in subjects and ministry
        
        **Sorting:**
        - sort_by: date, question_number, ministry, question_type, created_at
        - order: asc/desc (default: desc)
        
        **Pagination:**
        - limit: Records per page (default: 100, max: 500)
        - offset: Starting position (default: 0)
        """,
        parameters=[
            OpenApiParameter('lok_sabha', OpenApiTypes.STR, description='Lok Sabha number'),
            OpenApiParameter('session', OpenApiTypes.STR, description='Session number'),
            OpenApiParameter('question_type', OpenApiTypes.STR, description='Question type'),
            OpenApiParameter('ministry', OpenApiTypes.STR, description='Ministry filter'),
            OpenApiParameter('has_pdf', OpenApiTypes.BOOL, description='Has PDF'),
            OpenApiParameter('has_answer', OpenApiTypes.BOOL, description='Has answer'),
            OpenApiParameter('is_processed', OpenApiTypes.BOOL, description='Is processed'),
            OpenApiParameter('pdf_downloaded', OpenApiTypes.BOOL, description='PDF downloaded'),
            OpenApiParameter('date_from', OpenApiTypes.DATE, description='Start date'),
            OpenApiParameter('date_to', OpenApiTypes.DATE, description='End date'),
            OpenApiParameter('search', OpenApiTypes.STR, description='Search term'),
            OpenApiParameter('sort_by', OpenApiTypes.STR, description='Sort field'),
            OpenApiParameter('order', OpenApiTypes.STR, description='Sort order (asc/desc)'),
            OpenApiParameter('limit', OpenApiTypes.INT, description='Records per page'),
            OpenApiParameter('offset', OpenApiTypes.INT, description='Offset'),
        ],
        tags=['Data Explorer']
    )
    def get(self, request):
        """Get Lok Sabha questions with filters"""
        try:
            # Get LS institution
            ls_institution = ParliamentInstitution.objects.get(name='lok_sabha')
            
            # Base queryset with institution filter
            queryset = QuestionMasterData.objects.filter(
                parent_institution=ls_institution
            ).select_related('lok_sabha', 'session')
            
            # Build filter parameters
            filters = Q()
            
            # Lok Sabha and Session filters
            lok_sabha = request.query_params.get('lok_sabha')
            if lok_sabha:
                filters &= Q(lok_sabha_number=lok_sabha)
            
            session = request.query_params.get('session')
            if session:
                filters &= Q(session_number=session)
            
            # Question type filter
            question_type = request.query_params.get('question_type')
            if question_type:
                filters &= Q(question_type=question_type)
            
            # Ministry filter
            ministry = request.query_params.get('ministry')
            if ministry:
                filters &= Q(ministry__icontains=ministry)
            
            # Boolean filters
            has_pdf = request.query_params.get('has_pdf')
            if has_pdf == 'true':
                filters &= (Q(questions_file_path__isnull=False) & ~Q(questions_file_path='')) | \
                          (Q(questions_file_path_hindi__isnull=False) & ~Q(questions_file_path_hindi=''))
            elif has_pdf == 'false':
                filters &= (Q(questions_file_path='') | Q(questions_file_path__isnull=True)) & \
                          (Q(questions_file_path_hindi='') | Q(questions_file_path_hindi__isnull=True))
            
            has_answer = request.query_params.get('has_answer')
            if has_answer == 'true':
                filters &= Q(answer_text__isnull=False) & ~Q(answer_text='')
            elif has_answer == 'false':
                filters &= Q(answer_text='') | Q(answer_text__isnull=True)
            
            is_processed = request.query_params.get('is_processed')
            if is_processed is not None:
                filters &= Q(is_processed=(is_processed == 'true'))
            
            pdf_downloaded = request.query_params.get('pdf_downloaded')
            if pdf_downloaded is not None:
                filters &= Q(pdf_downloaded=(pdf_downloaded == 'true'))
            
            # Date range filters
            date_from = self.parse_date(request.query_params.get('date_from'))
            if date_from:
                filters &= Q(date__gte=date_from)
            
            date_to = self.parse_date(request.query_params.get('date_to'))
            if date_to:
                filters &= Q(date__lte=date_to)
            
            # Search filter
            search = request.query_params.get('search')
            if search:
                search_query = self.build_search_query(
                    search,
                    ['subjects', 'ministry', 'question_number']
                )
                filters &= search_query
            
            # Apply all filters
            queryset = queryset.filter(filters)
            
            # Sorting
            sort_by = request.query_params.get('sort_by', 'date')
            order = request.query_params.get('order', 'desc')
            
            # Map sort fields to model fields
            sort_field_map = {
                'date': 'date',
                'question_number': 'question_number',
                'ministry': 'ministry',
                'question_type': 'question_type',
                'created_at': 'created_at',
                'updated_at': 'updated_at'
            }
            
            sort_field = sort_field_map.get(sort_by, 'date')
            if order == 'asc':
                queryset = queryset.order_by(sort_field, 'question_number')
            else:
                queryset = queryset.order_by(f'-{sort_field}', '-question_number')
            
            # Build cache key based on filters
            cache_key = f"ls_questions_explorer_{lok_sabha}_{session}_{question_type}"
            
            # Paginate
            paginated_qs, pagination_meta = self.paginate_queryset(
                queryset, request, cache_key
            )
            
            # Serialize
            serializer = LSQuestionExplorerSerializer(paginated_qs, many=True)
            
            return Response({
                'status': 'success',
                'data': {
                    'questions': serializer.data,
                    'pagination': pagination_meta
                },
                'applied_filters': {
                    'lok_sabha': lok_sabha,
                    'session': session,
                    'question_type': question_type,
                    'ministry': ministry,
                    'has_pdf': has_pdf,
                    'has_answer': has_answer,
                    'is_processed': is_processed,
                    'pdf_downloaded': pdf_downloaded,
                    'date_from': str(date_from) if date_from else None,
                    'date_to': str(date_to) if date_to else None,
                    'search': search,
                    'sort_by': sort_by,
                    'order': order
                }
            })
            
        except ParliamentInstitution.DoesNotExist:
            return Response({
                'status': 'error',
                'error': 'Lok Sabha institution not found'
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Error in LS Question Explorer: {str(e)}", exc_info=True)
            return Response({
                'status': 'error',
                'error': f'Failed to fetch questions: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class RSQuestionExplorerView(BasePaginatedExplorerView):
    """
    High-performance Rajya Sabha Questions Explorer
    Supports advanced filtering, sorting, search, and pagination
    """
    
    @extend_schema(
        description="""
        Explore Rajya Sabha Questions with advanced filtering and sorting.
        
        **Filtering:**
        - session: Session number (e.g., "268")
        - question_type: STARRED, UNSTARRED, SHORT_NOTICE
        - ministry: Filter by ministry (partial match)
        - has_pdf: true/false
        - has_answer: true/false
        - is_processed: true/false
        - pdf_downloaded: true/false
        - date_from: Start date (YYYY-MM-DD)
        - date_to: End date (YYYY-MM-DD)
        - search: Search in subjects and ministry
        
        **Sorting:**
        - sort_by: date, question_number, ministry, question_type, created_at
        - order: asc/desc (default: desc)
        
        **Pagination:**
        - limit: Records per page (default: 100, max: 500)
        - offset: Starting position (default: 0)
        """,
        parameters=[
            OpenApiParameter('session', OpenApiTypes.STR, description='Session number'),
            OpenApiParameter('question_type', OpenApiTypes.STR, description='Question type'),
            OpenApiParameter('ministry', OpenApiTypes.STR, description='Ministry filter'),
            OpenApiParameter('has_pdf', OpenApiTypes.BOOL, description='Has PDF'),
            OpenApiParameter('has_answer', OpenApiTypes.BOOL, description='Has answer'),
            OpenApiParameter('is_processed', OpenApiTypes.BOOL, description='Is processed'),
            OpenApiParameter('pdf_downloaded', OpenApiTypes.BOOL, description='PDF downloaded'),
            OpenApiParameter('date_from', OpenApiTypes.DATE, description='Start date'),
            OpenApiParameter('date_to', OpenApiTypes.DATE, description='End date'),
            OpenApiParameter('search', OpenApiTypes.STR, description='Search term'),
            OpenApiParameter('sort_by', OpenApiTypes.STR, description='Sort field'),
            OpenApiParameter('order', OpenApiTypes.STR, description='Sort order (asc/desc)'),
            OpenApiParameter('limit', OpenApiTypes.INT, description='Records per page'),
            OpenApiParameter('offset', OpenApiTypes.INT, description='Offset'),
        ],
        tags=['Data Explorer']
    )
    def get(self, request):
        """Get Rajya Sabha questions with filters"""
        try:
            # Get RS institution
            rs_institution = ParliamentInstitution.objects.get(name='rajya_sabha')
            
            # Base queryset with institution filter
            queryset = QuestionMasterData.objects.filter(
                parent_institution=rs_institution
            ).select_related('lok_sabha', 'session')
            
            # Build filter parameters
            filters = Q()
            
            # Session filter
            session = request.query_params.get('session')
            if session:
                filters &= Q(session_number=session)
            
            # Question type filter
            question_type = request.query_params.get('question_type')
            if question_type:
                filters &= Q(question_type=question_type)
            
            # Ministry filter
            ministry = request.query_params.get('ministry')
            if ministry:
                filters &= Q(ministry__icontains=ministry)
            
            # Boolean filters
            has_pdf = request.query_params.get('has_pdf')
            if has_pdf == 'true':
                filters &= (Q(questions_file_path__isnull=False) & ~Q(questions_file_path='')) | \
                          (Q(questions_file_path_hindi__isnull=False) & ~Q(questions_file_path_hindi=''))
            elif has_pdf == 'false':
                filters &= (Q(questions_file_path='') | Q(questions_file_path__isnull=True)) & \
                          (Q(questions_file_path_hindi='') | Q(questions_file_path_hindi__isnull=True))
            
            has_answer = request.query_params.get('has_answer')
            if has_answer == 'true':
                filters &= Q(answer_text__isnull=False) & ~Q(answer_text='')
            elif has_answer == 'false':
                filters &= Q(answer_text='') | Q(answer_text__isnull=True)
            
            is_processed = request.query_params.get('is_processed')
            if is_processed is not None:
                filters &= Q(is_processed=(is_processed == 'true'))
            
            pdf_downloaded = request.query_params.get('pdf_downloaded')
            if pdf_downloaded is not None:
                filters &= Q(pdf_downloaded=(pdf_downloaded == 'true'))
            
            # Date range filters
            date_from = self.parse_date(request.query_params.get('date_from'))
            if date_from:
                filters &= Q(date__gte=date_from)
            
            date_to = self.parse_date(request.query_params.get('date_to'))
            if date_to:
                filters &= Q(date__lte=date_to)
            
            # Search filter
            search = request.query_params.get('search')
            if search:
                search_query = self.build_search_query(
                    search,
                    ['subjects', 'ministry', 'question_number']
                )
                filters &= search_query
            
            # Apply all filters
            queryset = queryset.filter(filters)
            
            # Sorting
            sort_by = request.query_params.get('sort_by', 'date')
            order = request.query_params.get('order', 'desc')
            
            # Map sort fields to model fields
            sort_field_map = {
                'date': 'date',
                'question_number': 'question_number',
                'ministry': 'ministry',
                'question_type': 'question_type',
                'created_at': 'created_at',
                'updated_at': 'updated_at'
            }
            
            sort_field = sort_field_map.get(sort_by, 'date')
            if order == 'asc':
                queryset = queryset.order_by(sort_field, 'question_number')
            else:
                queryset = queryset.order_by(f'-{sort_field}', '-question_number')
            
            # Build cache key based on filters
            cache_key = f"rs_questions_explorer_{session}_{question_type}"
            
            # Paginate
            paginated_qs, pagination_meta = self.paginate_queryset(
                queryset, request, cache_key
            )
            
            # Serialize
            serializer = RSQuestionExplorerSerializer(paginated_qs, many=True)
            
            return Response({
                'status': 'success',
                'data': {
                    'questions': serializer.data,
                    'pagination': pagination_meta
                },
                'applied_filters': {
                    'session': session,
                    'question_type': question_type,
                    'ministry': ministry,
                    'has_pdf': has_pdf,
                    'has_answer': has_answer,
                    'is_processed': is_processed,
                    'pdf_downloaded': pdf_downloaded,
                    'date_from': str(date_from) if date_from else None,
                    'date_to': str(date_to) if date_to else None,
                    'search': search,
                    'sort_by': sort_by,
                    'order': order
                }
            })
            
        except ParliamentInstitution.DoesNotExist:
            return Response({
                'status': 'error',
                'error': 'Rajya Sabha institution not found'
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Error in RS Question Explorer: {str(e)}", exc_info=True)
            return Response({
                'status': 'error',
                'error': f'Failed to fetch questions: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class LSDebateExplorerView(BasePaginatedExplorerView):
    """
    High-performance Lok Sabha Debates Explorer
    Shows individual debate days with metadata
    """
    
    @extend_schema(
        description="""
        Explore Lok Sabha Debates (individual debate days) with filtering and sorting.
        
        **Note**: Run 'populate_debates_from_master' management command first to create
        individual debate records from session-level master data.
        
        **Filtering:**
        - lok_sabha: Lok Sabha number (e.g., "18")
        - session: Session number (e.g., "5")
        - debate_category: corrected, uncorrected
        - status: pending, completed, failed, not_available
        - date_from: Start date (YYYY-MM-DD)
        - date_to: End date (YYYY-MM-DD)
        
        **Sorting:**
        - sort_by: debate_date, created_at, updated_at, status
        - order: asc/desc (default: desc)
        
        **Pagination:**
        - limit: Records per page (default: 100, max: 500)
        - offset: Starting position (default: 0)
        """,
        parameters=[
            OpenApiParameter('lok_sabha', OpenApiTypes.STR, description='Lok Sabha number'),
            OpenApiParameter('session', OpenApiTypes.STR, description='Session number'),
            OpenApiParameter('debate_category', OpenApiTypes.STR, description='Debate category'),
            OpenApiParameter('status', OpenApiTypes.STR, description='Status filter'),
            OpenApiParameter('date_from', OpenApiTypes.DATE, description='Start date'),
            OpenApiParameter('date_to', OpenApiTypes.DATE, description='End date'),
            OpenApiParameter('sort_by', OpenApiTypes.STR, description='Sort field'),
            OpenApiParameter('order', OpenApiTypes.STR, description='Sort order (asc/desc)'),
            OpenApiParameter('limit', OpenApiTypes.INT, description='Records per page'),
            OpenApiParameter('offset', OpenApiTypes.INT, description='Offset'),
        ],
        tags=['Data Explorer']
    )
    def get(self, request):
        """Get Lok Sabha debate records"""
        try:
            # Get LS institution
            ls_institution = ParliamentInstitution.objects.get(name='lok_sabha')
            
            # Base queryset with institution filter and optimizations
            queryset = Debate.objects.filter(
                parent_institution=ls_institution
            ).select_related('lok_sabha', 'session', 'pdf_file')
            
            # Build filter parameters
            filters = Q()
            
            # Lok Sabha and Session filters
            lok_sabha = request.query_params.get('lok_sabha')
            if lok_sabha:
                filters &= Q(lok_sabha__number=lok_sabha)
            
            session = request.query_params.get('session')
            if session:
                filters &= Q(session__session_number=session)
            
            # Debate category filter
            debate_category = request.query_params.get('debate_category')
            if debate_category:
                filters &= Q(debate_category=debate_category)
            
            # Status filter
            status_filter = request.query_params.get('status')
            if status_filter:
                filters &= Q(status=status_filter)
            
            # Date range filters
            date_from = self.parse_date(request.query_params.get('date_from'))
            if date_from:
                filters &= Q(debate_date__gte=date_from)
            
            date_to = self.parse_date(request.query_params.get('date_to'))
            if date_to:
                filters &= Q(debate_date__lte=date_to)
            
            # Apply all filters
            queryset = queryset.filter(filters)
            
            # Sorting
            sort_by = request.query_params.get('sort_by', 'debate_date')
            order = request.query_params.get('order', 'desc')
            
            # Map sort fields to model fields
            sort_field_map = {
                'debate_date': 'debate_date',
                'created_at': 'created_at',
                'updated_at': 'updated_at',
                'status': 'status'
            }
            
            sort_field = sort_field_map.get(sort_by, 'debate_date')
            if order == 'asc':
                queryset = queryset.order_by(sort_field, 'id')
            else:
                queryset = queryset.order_by(f'-{sort_field}', '-id')
            
            # Build cache key based on filters
            cache_key = f"ls_debates_explorer_{lok_sabha}_{session}_{debate_category}"
            
            # Paginate
            paginated_qs, pagination_meta = self.paginate_queryset(
                queryset, request, cache_key
            )
            
            # Serialize
            serializer = LSDebateExplorerSerializer(paginated_qs, many=True)
            
            return Response({
                'status': 'success',
                'data': {
                    'debates': serializer.data,
                    'pagination': pagination_meta
                },
                'applied_filters': {
                    'lok_sabha': lok_sabha,
                    'session': session,
                    'debate_category': debate_category,
                    'status': status_filter,
                    'date_from': str(date_from) if date_from else None,
                    'date_to': str(date_to) if date_to else None,
                    'sort_by': sort_by,
                    'order': order
                }
            })
            
        except ParliamentInstitution.DoesNotExist:
            return Response({
                'status': 'error',
                'error': 'Lok Sabha institution not found'
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Error in LS Debate Explorer: {str(e)}", exc_info=True)
            return Response({
                'status': 'error',
                'error': f'Failed to fetch debates: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class RSDebateExplorerView(BasePaginatedExplorerView):
    """
    High-performance Rajya Sabha Debates Explorer
    Shows individual debate days with metadata
    """
    
    @extend_schema(
        description="""
        Explore Rajya Sabha Debates (individual debate days) with filtering and sorting.
        
        **Note**: Run 'populate_debates_from_master' management command first to create
        individual debate records from session-level master data.
        
        **Filtering:**
        - session: Session number
        - debate_category: verbatim, official_qa, official_other, official, corrected
        - status: pending, completed, failed, not_available
        - date_from: Start date (YYYY-MM-DD)
        - date_to: End date (YYYY-MM-DD)
        
        **Sorting:**
        - sort_by: debate_date, created_at, updated_at, status
        - order: asc/desc (default: desc)
        
        **Pagination:**
        - limit: Records per page (default: 100, max: 500)
        - offset: Starting position (default: 0)
        """,
        parameters=[
            OpenApiParameter('session', OpenApiTypes.STR, description='Session number'),
            OpenApiParameter('debate_category', OpenApiTypes.STR, description='Debate category'),
            OpenApiParameter('status', OpenApiTypes.STR, description='Status filter'),
            OpenApiParameter('date_from', OpenApiTypes.DATE, description='Start date'),
            OpenApiParameter('date_to', OpenApiTypes.DATE, description='End date'),
            OpenApiParameter('sort_by', OpenApiTypes.STR, description='Sort field'),
            OpenApiParameter('order', OpenApiTypes.STR, description='Sort order (asc/desc)'),
            OpenApiParameter('limit', OpenApiTypes.INT, description='Records per page'),
            OpenApiParameter('offset', OpenApiTypes.INT, description='Offset'),
        ],
        tags=['Data Explorer']
    )
    def get(self, request):
        """Get Rajya Sabha debate records"""
        try:
            # Get RS institution
            rs_institution = ParliamentInstitution.objects.get(name='rajya_sabha')
            
            # Base queryset with institution filter and optimizations
            queryset = Debate.objects.filter(
                parent_institution=rs_institution
            ).select_related('lok_sabha', 'session', 'pdf_file')
            
            # Build filter parameters
            filters = Q()
            
            # Session filter
            session = request.query_params.get('session')
            if session:
                filters &= Q(session__session_number=session)
            
            # Debate category filter
            debate_category = request.query_params.get('debate_category')
            if debate_category:
                filters &= Q(debate_category=debate_category)
            
            # Status filter
            status_filter = request.query_params.get('status')
            if status_filter:
                filters &= Q(status=status_filter)
            
            # Date range filters
            date_from = self.parse_date(request.query_params.get('date_from'))
            if date_from:
                filters &= Q(debate_date__gte=date_from)
            
            date_to = self.parse_date(request.query_params.get('date_to'))
            if date_to:
                filters &= Q(debate_date__lte=date_to)
            
            # Apply all filters
            queryset = queryset.filter(filters)
            
            # Sorting
            sort_by = request.query_params.get('sort_by', 'debate_date')
            order = request.query_params.get('order', 'desc')
            
            # Map sort fields to model fields
            sort_field_map = {
                'debate_date': 'debate_date',
                'created_at': 'created_at',
                'updated_at': 'updated_at',
                'status': 'status'
            }
            
            sort_field = sort_field_map.get(sort_by, 'debate_date')
            if order == 'asc':
                queryset = queryset.order_by(sort_field, 'id')
            else:
                queryset = queryset.order_by(f'-{sort_field}', '-id')
            
            # Build cache key based on filters
            cache_key = f"rs_debates_explorer_{session}_{debate_category}"
            
            # Paginate
            paginated_qs, pagination_meta = self.paginate_queryset(
                queryset, request, cache_key
            )
            
            # Serialize
            serializer = RSDebateExplorerSerializer(paginated_qs, many=True)
            
            return Response({
                'status': 'success',
                'data': {
                    'debates': serializer.data,
                    'pagination': pagination_meta
                },
                'applied_filters': {
                    'session': session,
                    'debate_category': debate_category,
                    'status': status_filter,
                    'date_from': str(date_from) if date_from else None,
                    'date_to': str(date_to) if date_to else None,
                    'sort_by': sort_by,
                    'order': order
                }
            })
            
        except ParliamentInstitution.DoesNotExist:
            return Response({
                'status': 'error',
                'error': 'Rajya Sabha institution not found'
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Error in RS Debate Explorer: {str(e)}", exc_info=True)
            return Response({
                'status': 'error',
                'error': f'Failed to fetch debates: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class QuestionMetadataView(APIView):
    """
    Get available filter options for Questions
    Returns unique values for dropdowns and filters
    """
    permission_classes = [IsAuthenticated]
    
    @extend_schema(
        description="Get available filter metadata for Questions (LS and RS)",
        parameters=[
            OpenApiParameter('institution', OpenApiTypes.STR, description='lok_sabha or rajya_sabha'),
        ],
        tags=['Data Explorer']
    )
    def get(self, request):
        """Get metadata for question filters"""
        try:
            institution = request.query_params.get('institution', 'lok_sabha')
            
            # Get institution
            institution_obj = ParliamentInstitution.objects.get(name=institution)
            
            # Get unique values from database
            queryset = QuestionMasterData.objects.filter(parent_institution=institution_obj)
            
            # Cache key
            cache_key = f"question_metadata_{institution}"
            cached_data = None
            
            # Try to get from cache (gracefully fail if cache unavailable)
            try:
                cached_data = cache.get(cache_key)
            except Exception as e:
                logger.warning(f"Cache get failed: {e}. Continuing without cache.")
            
            if cached_data:
                return Response(cached_data)
            
            # Get unique Lok Sabhas/Sessions
            if institution == 'lok_sabha':
                lok_sabhas = queryset.values('lok_sabha_number').distinct().order_by('-lok_sabha_number')
                lok_sabha_list = [ls['lok_sabha_number'] for ls in lok_sabhas if ls['lok_sabha_number']]
            else:
                lok_sabha_list = []
            
            sessions = queryset.values('session_number').distinct().order_by('-session_number')
            session_list = [s['session_number'] for s in sessions if s['session_number']]
            
            # Get unique ministries (top 50 by count)
            ministries = queryset.values('ministry').annotate(
                count=Count('id')
            ).order_by('-count')[:50]
            ministry_list = [m['ministry'] for m in ministries if m['ministry']]
            
            # Get question types
            question_types = [choice[0] for choice in QuestionMasterData.QUESTION_TYPES]
            
            # Get date range
            date_range = queryset.aggregate(
                min_date=Min('date'),
                max_date=Max('date')
            )
            
            # Statistics
            stats = {
                'total_questions': queryset.count(),
                'with_pdf': queryset.filter(
                    Q(questions_file_path__isnull=False) & ~Q(questions_file_path='')
                ).count(),
                'with_answer': queryset.filter(
                    Q(answer_text__isnull=False) & ~Q(answer_text='')
                ).count(),
                'processed': queryset.filter(is_processed=True).count(),
                'pdf_downloaded': queryset.filter(pdf_downloaded=True).count()
            }
            
            response_data = {
                'status': 'success',
                'institution': institution,
                'metadata': {
                    'lok_sabhas': lok_sabha_list if institution == 'lok_sabha' else None,
                    'sessions': session_list,
                    'ministries': ministry_list,
                    'question_types': question_types,
                    'date_range': {
                        'min': str(date_range['min_date']) if date_range['min_date'] else None,
                        'max': str(date_range['max_date']) if date_range['max_date'] else None
                    }
                },
                'statistics': stats
            }
            
            # Try to cache for 1 hour (gracefully fail if cache unavailable)
            try:
                cache.set(cache_key, response_data, 3600)
            except Exception as e:
                logger.warning(f"Cache set failed: {e}. Continuing without cache.")
            
            return Response(response_data)
            
        except ParliamentInstitution.DoesNotExist:
            return Response({
                'status': 'error',
                'error': 'Institution not found'
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Error in Question Metadata: {str(e)}", exc_info=True)
            return Response({
                'status': 'error',
                'error': f'Failed to fetch metadata: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class DebateMetadataView(APIView):
    """
    Get available filter options for Debates
    Returns unique values for dropdowns and filters
    """
    permission_classes = [IsAuthenticated]
    
    @extend_schema(
        description="Get available filter metadata for Debates (LS and RS)",
        parameters=[
            OpenApiParameter('institution', OpenApiTypes.STR, description='lok_sabha or rajya_sabha'),
        ],
        tags=['Data Explorer']
    )
    def get(self, request):
        """Get metadata for debate filters"""
        try:
            institution = request.query_params.get('institution', 'lok_sabha')
            
            # Get institution
            institution_obj = ParliamentInstitution.objects.get(name=institution)
            
            # Get unique values from Debate table
            queryset = Debate.objects.filter(parent_institution=institution_obj)
            
            # Cache key
            cache_key = f"debate_metadata_{institution}"
            cached_data = None
            
            # Try to get from cache (gracefully fail if cache unavailable)
            try:
                cached_data = cache.get(cache_key)
            except Exception as e:
                logger.warning(f"Cache get failed: {e}. Continuing without cache.")
            
            if cached_data:
                return Response(cached_data)
            
            # Get unique Lok Sabhas/Sessions
            if institution == 'lok_sabha':
                lok_sabhas = queryset.values('lok_sabha__number').distinct().order_by('-lok_sabha__number')
                lok_sabha_list = [ls['lok_sabha__number'] for ls in lok_sabhas if ls['lok_sabha__number']]
            else:
                lok_sabha_list = []
            
            sessions = queryset.values('session__session_number').distinct().order_by('-session__session_number')
            session_list = [s['session__session_number'] for s in sessions if s['session__session_number']]
            
            # Get debate categories
            debate_categories = queryset.values('debate_category').distinct().order_by('debate_category')
            category_list = [dc['debate_category'] for dc in debate_categories if dc['debate_category']]
            
            # Get statuses
            status_list = [choice[0] for choice in Debate.STATUS_CHOICES]
            
            # Get date range
            date_range = queryset.aggregate(
                min_date=Min('debate_date'),
                max_date=Max('debate_date')
            )
            
            # Statistics
            stats = {
                'total_debates': queryset.count(),
                'completed': queryset.filter(status='completed').count(),
                'pending': queryset.filter(status='pending').count(),
                'failed': queryset.filter(status='failed').count(),
                'not_available': queryset.filter(status='not_available').count()
            }
            
            response_data = {
                'status': 'success',
                'institution': institution,
                'metadata': {
                    'lok_sabhas': lok_sabha_list if institution == 'lok_sabha' else None,
                    'sessions': session_list,
                    'debate_categories': category_list,
                    'statuses': status_list,
                    'date_range': {
                        'min': str(date_range['min_date']) if date_range['min_date'] else None,
                        'max': str(date_range['max_date']) if date_range['max_date'] else None
                    }
                },
                'statistics': stats
            }
            
            # Try to cache for 1 hour (gracefully fail if cache unavailable)
            try:
                cache.set(cache_key, response_data, 3600)
            except Exception as e:
                logger.warning(f"Cache set failed: {e}. Continuing without cache.")
            
            return Response(response_data)
            
        except ParliamentInstitution.DoesNotExist:
            return Response({
                'status': 'error',
                'error': 'Institution not found'
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Error in Debate Metadata: {str(e)}", exc_info=True)
            return Response({
                'status': 'error',
                'error': f'Failed to fetch metadata: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class QuestionDetailView(APIView):
    """Get detailed information about a specific question"""
    permission_classes = [IsAuthenticated]
    
    @extend_schema(
        description="Get detailed information about a specific question by ID",
        tags=['Data Explorer']
    )
    def get(self, request, pk):
        """Get question details"""
        try:
            question = QuestionMasterData.objects.select_related(
                'lok_sabha', 'session', 'parent_institution'
            ).get(pk=pk)
            
            serializer = QuestionDetailSerializer(question)
            
            return Response({
                'status': 'success',
                'data': serializer.data
            })
            
        except QuestionMasterData.DoesNotExist:
            return Response({
                'status': 'error',
                'error': 'Question not found'
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Error fetching question detail: {str(e)}", exc_info=True)
            return Response({
                'status': 'error',
                'error': f'Failed to fetch question: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class DebateDetailView(APIView):
    """Get detailed information about a specific debate"""
    permission_classes = [IsAuthenticated]
    
    @extend_schema(
        description="Get detailed information about a specific debate by ID",
        tags=['Data Explorer']
    )
    def get(self, request, pk):
        """Get debate details"""
        try:
            debate = Debate.objects.select_related(
                'lok_sabha', 'session', 'parent_institution', 'pdf_file'
            ).get(pk=pk)
            
            serializer = DebateDetailSerializer(debate)
            
            return Response({
                'status': 'success',
                'data': serializer.data
            })
            
        except Debate.DoesNotExist:
            return Response({
                'status': 'error',
                'error': 'Debate not found'
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Error fetching debate detail: {str(e)}", exc_info=True)
            return Response({
                'status': 'error',
                'error': f'Failed to fetch debate: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
