from django.shortcuts import render
from rest_framework import viewsets, status
from rest_framework.decorators import action, api_view
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, OpenApiParameter
from drf_spectacular.types import OpenApiTypes
from .models import Question, LokSabha, Session, Member, Ministry


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
        # This is a placeholder - actual filtering logic will be implemented
        return Response({
            'message': 'Questions endpoint - filtering logic to be implemented',
            'total_questions': Question.objects.count(),
            'available_filters': {
                'lok_sabha': ['15', '16', '17'],
                'question_type': ['Starred', 'Unstarred', 'Short Notice'],
                'search': 'Full text search in title and content'
            }
        })
    
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
