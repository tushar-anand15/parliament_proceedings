from django.shortcuts import render
from django.utils import timezone
from rest_framework import viewsets, status, generics
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from drf_spectacular.utils import extend_schema, extend_schema_view
from .models import (
    AIAnalysisJob, DocumentSummary, MetadataExtraction, 
    TopicClassification, AIModelUsage, AIPromptTemplate
)
from services.questions.models import Question
from services.files.models import DocumentFile


@extend_schema_view(
    retrieve=extend_schema(operation_id='ai_analysis_jobs_detail')
)
class AIAnalysisJobViewSet(viewsets.ModelViewSet):
    """AI analysis job management"""
    queryset = AIAnalysisJob.objects.all()
    permission_classes = []
    
    @extend_schema(
        operation_id='ai_analysis_jobs_list',
        description="List AI analysis jobs",
        tags=['AI Service']
    )
    def list(self, request):
        """List AI analysis jobs"""
        jobs = AIAnalysisJob.objects.all().order_by('-created_at')[:20]
        return Response({
            'jobs': [
                {
                    'id': job.id,
                    'job_type': job.job_type,
                    'status': job.status,
                    'progress': job.progress,
                    'model_used': job.model_used,
                    'prompt_tokens': job.prompt_tokens,
                    'completion_tokens': job.completion_tokens,
                    'total_cost': float(job.total_cost) if job.total_cost else 0,
                    'created_at': job.created_at,
                    'completed_at': job.completed_at
                }
                for job in jobs
            ]
        })
    
    @extend_schema(
        description="Create new AI analysis job",
        tags=['AI Service']
    )
    def create(self, request):
        """Create new analysis job"""
        job_type = request.data.get('job_type', 'text_analysis')
        input_text = request.data.get('input_text', '')
        model_name = request.data.get('model', 'gpt-3.5-turbo')
        
        if not input_text:
            return Response({'error': 'Input text is required'}, status=400)
        
        job = AIAnalysisJob.objects.create(
            job_type=job_type,
            input_text=input_text,
            model_used=model_name,
            created_by=request.user,
            parameters={'custom_request': True}
        )
        
        return Response({
            'message': 'AI analysis job created',
            'job_id': job.id,
            'status': job.status
        }, status=201)


@extend_schema_view(
    retrieve=extend_schema(operation_id='ai_summaries_detail')
)
class DocumentSummaryViewSet(viewsets.ModelViewSet):
    """Document summary management"""
    queryset = DocumentSummary.objects.all()
    permission_classes = []
    
    @extend_schema(
        operation_id='ai_summaries_list',
        description="List document summaries",
        tags=['AI Service']
    )
    def list(self, request):
        """List document summaries"""
        summaries = DocumentSummary.objects.all().order_by('-created_at')[:20]
        return Response({
            'summaries': [
                {
                    'id': summary.id,
                    'summary_type': summary.summary_type,
                    'summary_text': summary.summary_text[:200] + '...' if len(summary.summary_text) > 200 else summary.summary_text,
                    'confidence_score': float(summary.confidence_score) if summary.confidence_score else 0,
                    'word_count': summary.word_count,
                    'created_at': summary.created_at,
                    'question_id': summary.question.id if summary.question else None
                }
                for summary in summaries
            ]
        })


@extend_schema_view(
    retrieve=extend_schema(operation_id='ai_metadata_extractions_detail')
)
class MetadataExtractionViewSet(viewsets.ModelViewSet):
    """Metadata extraction management"""
    queryset = MetadataExtraction.objects.all()
    permission_classes = []
    
    @extend_schema(
        operation_id='ai_metadata_extractions_list',
        description="List metadata extractions",
        tags=['AI Service']
    )
    def list(self, request):
        """List metadata extractions"""
        extractions = MetadataExtraction.objects.all().order_by('-created_at')[:20]
        return Response({
            'extractions': [
                {
                    'id': extraction.id,
                    'extraction_type': extraction.extraction_type,
                    'extracted_metadata': extraction.extracted_metadata,
                    'confidence_score': float(extraction.confidence_score) if extraction.confidence_score else 0,
                    'created_at': extraction.created_at,
                    'question_id': extraction.question.id if extraction.question else None
                }
                for extraction in extractions
            ]
        })


@extend_schema_view(
    retrieve=extend_schema(operation_id='ai_topic_classifications_detail')
)
class TopicClassificationViewSet(viewsets.ModelViewSet):
    """Topic classification management"""
    queryset = TopicClassification.objects.all()
    permission_classes = []
    
    @extend_schema(
        operation_id='ai_topic_classifications_list',
        description="List topic classifications",
        tags=['AI Service']
    )
    def list(self, request):
        """List topic classifications"""
        classifications = TopicClassification.objects.all().order_by('-created_at')[:20]
        return Response({
            'classifications': [
                {
                    'id': classification.id,
                    'primary_topic': classification.primary_topic,
                    'secondary_topics': classification.secondary_topics,
                    'confidence_scores': classification.confidence_scores,
                    'created_at': classification.created_at,
                    'question_id': classification.question.id if classification.question else None
                }
                for classification in classifications
            ]
        })


@extend_schema_view(
    retrieve=extend_schema(operation_id='ai_model_usage_detail')
)
class AIModelUsageViewSet(viewsets.ModelViewSet):
    """AI model usage tracking"""
    queryset = AIModelUsage.objects.all()
    permission_classes = []
    
    @extend_schema(
        operation_id='ai_model_usage_list',
        description="List AI model usage",
        tags=['AI Service']
    )
    def list(self, request):
        """List model usage records"""
        usage_records = AIModelUsage.objects.all().order_by('-timestamp')[:50]
        return Response({
            'usage_records': [
                {
                    'id': record.id,
                    'model_name': record.model_name,
                    'operation_type': record.operation_type,
                    'prompt_tokens': record.prompt_tokens,
                    'completion_tokens': record.completion_tokens,
                    'total_tokens': record.total_tokens,
                    'cost': float(record.cost) if record.cost else 0,
                    'timestamp': record.timestamp,
                    'user': record.user.username if record.user else None
                }
                for record in usage_records
            ]
        })


@extend_schema_view(
    retrieve=extend_schema(operation_id='ai_prompt_templates_detail')
)
class AIPromptTemplateViewSet(viewsets.ModelViewSet):
    """AI prompt template management"""
    queryset = AIPromptTemplate.objects.all()
    permission_classes = []
    
    @extend_schema(
        operation_id='ai_prompt_templates_list',
        description="List AI prompt templates",
        tags=['AI Service']
    )
    def list(self, request):
        """List prompt templates"""
        templates = AIPromptTemplate.objects.filter(is_active=True)
        return Response({
            'templates': [
                {
                    'id': template.id,
                    'name': template.name,
                    'description': template.description,
                    'template_type': template.template_type,
                    'template_text': template.template_text,
                    'default_model': template.default_model,
                    'usage_count': template.usage_count,
                    'created_at': template.created_at
                }
                for template in templates
            ]
        })


# Text Analysis Views
class AnalyzeTextView(APIView):
    """Analyze text content"""
    permission_classes = []
    
    @extend_schema(
        description="Analyze text using AI",
        tags=['AI Service']
    )
    def post(self, request):
        """Analyze text"""
        text = request.data.get('text', '')
        analysis_type = request.data.get('type', 'general')
        model = request.data.get('model', 'gpt-3.5-turbo')
        
        if not text:
            return Response({'error': 'Text is required'}, status=400)
        
        # Create analysis job
        job = AIAnalysisJob.objects.create(
            job_type='text_analysis',
            input_text=text,
            model_used=model,
            created_by=request.user,
            parameters={'analysis_type': analysis_type}
        )
        
        # Mock analysis result (in production, this would call actual AI service)
        mock_result = {
            'sentiment': 'neutral',
            'key_topics': ['parliament', 'government', 'policy'],
            'complexity_score': 0.7,
            'word_count': len(text.split()),
            'readability_score': 0.8
        }
        
        job.result = mock_result
        job.status = 'completed'
        job.completed_at = timezone.now()
        job.save()
        
        return Response({
            'job_id': job.id,
            'analysis': mock_result,
            'status': 'completed'
        })


class AnalyzeDocumentView(APIView):
    """Analyze document content"""
    permission_classes = []
    
    @extend_schema(
        description="Analyze document content using AI",
        tags=['AI Service']
    )
    def post(self, request):
        """Analyze document"""
        document_id = request.data.get('document_id')
        analysis_type = request.data.get('type', 'general')
        
        if not document_id:
            return Response({'error': 'Document ID is required'}, status=400)
        
        try:
            document = DocumentFile.objects.get(id=document_id)
        except DocumentFile.DoesNotExist:
            return Response({'error': 'Document not found'}, status=404)
        
        # Create analysis job
        job = AIAnalysisJob.objects.create(
            job_type='document_analysis',
            input_text=f"Document: {document.original_filename}",
            model_used='gpt-3.5-turbo',
            created_by=request.user,
            parameters={'document_id': document_id, 'analysis_type': analysis_type}
        )
        
        return Response({
            'message': 'Document analysis started',
            'job_id': job.id,
            'document': document.original_filename
        })


class BatchAnalysisView(APIView):
    """Batch analysis of multiple items"""
    permission_classes = []
    
    @extend_schema(
        description="Perform batch analysis on multiple items",
        tags=['AI Service']
    )
    def post(self, request):
        """Batch analysis"""
        items = request.data.get('items', [])
        analysis_type = request.data.get('type', 'general')
        
        if not items:
            return Response({'error': 'Items list is required'}, status=400)
        
        job_ids = []
        for item in items:
            job = AIAnalysisJob.objects.create(
                job_type='batch_analysis',
                input_text=item.get('text', ''),
                model_used='gpt-3.5-turbo',
                created_by=request.user,
                parameters={'analysis_type': analysis_type, 'batch_id': timezone.now().timestamp()}
            )
            job_ids.append(job.id)
        
        return Response({
            'message': f'Batch analysis started for {len(items)} items',
            'job_ids': job_ids
        })


# Summarization Views
class SummarizeTextView(APIView):
    """Summarize text content"""
    permission_classes = []
    
    @extend_schema(
        description="Summarize text using AI",
        tags=['AI Service']
    )
    def post(self, request):
        """Summarize text"""
        text = request.data.get('text', '')
        summary_type = request.data.get('type', 'extractive')
        max_length = request.data.get('max_length', 150)
        
        if not text:
            return Response({'error': 'Text is required'}, status=400)
        
        # Create summary
        summary = DocumentSummary.objects.create(
            summary_type=summary_type,
            summary_text=f"Mock summary of the provided text (length: {max_length} words max)",
            confidence_score=0.85,
            word_count=max_length,
            created_by=request.user
        )
        
        return Response({
            'summary_id': summary.id,
            'summary': summary.summary_text,
            'confidence_score': float(summary.confidence_score),
            'word_count': summary.word_count
        })


class SummarizeQuestionView(APIView):
    """Summarize parliamentary question"""
    permission_classes = []
    
    @extend_schema(
        description="Summarize a parliamentary question",
        tags=['AI Service']
    )
    def post(self, request):
        """Summarize question"""
        question_id = request.data.get('question_id')
        summary_type = request.data.get('type', 'extractive')
        
        if not question_id:
            return Response({'error': 'Question ID is required'}, status=400)
        
        try:
            question = Question.objects.get(id=question_id)
        except Question.DoesNotExist:
            return Response({'error': 'Question not found'}, status=404)
        
        # Create summary
        summary = DocumentSummary.objects.create(
            question=question,
            summary_type=summary_type,
            summary_text=f"Summary of question: {question.question_text[:100]}...",
            confidence_score=0.90,
            word_count=50,
            created_by=request.user
        )
        
        return Response({
            'summary_id': summary.id,
            'summary': summary.summary_text,
            'question_id': question.id,
            'confidence_score': float(summary.confidence_score)
        })


class SummarizeMultipleView(APIView):
    """Summarize multiple documents or questions"""
    permission_classes = []
    
    @extend_schema(
        description="Summarize multiple items",
        tags=['AI Service']
    )
    def post(self, request):
        """Summarize multiple items"""
        item_ids = request.data.get('item_ids', [])
        item_type = request.data.get('item_type', 'question')
        
        if not item_ids:
            return Response({'error': 'Item IDs are required'}, status=400)
        
        summaries = []
        for item_id in item_ids:
            summary = DocumentSummary.objects.create(
                summary_type='batch',
                summary_text=f"Batch summary for {item_type} {item_id}",
                confidence_score=0.80,
                word_count=100,
                created_by=request.user
            )
            summaries.append({
                'id': summary.id,
                'item_id': item_id,
                'summary': summary.summary_text
            })
        
        return Response({
            'message': f'Created summaries for {len(item_ids)} items',
            'summaries': summaries
        })


# Topic Classification Views
class ClassifyTopicView(APIView):
    """Classify text topic"""
    permission_classes = []
    
    @extend_schema(
        description="Classify topic of text",
        tags=['AI Service']
    )
    def post(self, request):
        """Classify topic"""
        text = request.data.get('text', '')
        
        if not text:
            return Response({'error': 'Text is required'}, status=400)
        
        # Mock classification
        classification = TopicClassification.objects.create(
            primary_topic='Government Policy',
            secondary_topics=['Healthcare', 'Education', 'Finance'],
            confidence_scores={'Government Policy': 0.85, 'Healthcare': 0.60},
            created_by=request.user
        )
        
        return Response({
            'classification_id': classification.id,
            'primary_topic': classification.primary_topic,
            'secondary_topics': classification.secondary_topics,
            'confidence_scores': classification.confidence_scores
        })


class ClassifyQuestionView(APIView):
    """Classify parliamentary question topic"""
    permission_classes = []
    
    @extend_schema(
        description="Classify topic of a parliamentary question",
        tags=['AI Service']
    )
    def post(self, request):
        """Classify question topic"""
        question_id = request.data.get('question_id')
        
        if not question_id:
            return Response({'error': 'Question ID is required'}, status=400)
        
        try:
            question = Question.objects.get(id=question_id)
        except Question.DoesNotExist:
            return Response({'error': 'Question not found'}, status=404)
        
        classification = TopicClassification.objects.create(
            question=question,
            primary_topic='Parliamentary Procedure',
            secondary_topics=['Budget', 'Policy'],
            confidence_scores={'Parliamentary Procedure': 0.90},
            created_by=request.user
        )
        
        return Response({
            'classification_id': classification.id,
            'question_id': question.id,
            'primary_topic': classification.primary_topic,
            'secondary_topics': classification.secondary_topics
        })


class BatchClassifyView(APIView):
    """Batch topic classification"""
    permission_classes = []
    
    @extend_schema(
        description="Classify topics for multiple items",
        tags=['AI Service']
    )
    def post(self, request):
        """Batch classify"""
        items = request.data.get('items', [])
        
        if not items:
            return Response({'error': 'Items are required'}, status=400)
        
        classifications = []
        for item in items:
            classification = TopicClassification.objects.create(
                primary_topic='Batch Classification Topic',
                secondary_topics=['General'],
                confidence_scores={'Batch Classification Topic': 0.75},
                created_by=request.user
            )
            classifications.append({
                'id': classification.id,
                'primary_topic': classification.primary_topic
            })
        
        return Response({
            'message': f'Classified {len(items)} items',
            'classifications': classifications
        })


# Question Processing Views
class ProcessQuestionView(APIView):
    """Process parliamentary question with AI"""
    permission_classes = []
    
    @extend_schema(
        description="Process a parliamentary question with AI",
        tags=['AI Service']
    )
    def post(self, request):
        """Process question"""
        question_id = request.data.get('question_id')
        processing_types = request.data.get('types', ['summary', 'classification', 'keywords'])
        
        if not question_id:
            return Response({'error': 'Question ID is required'}, status=400)
        
        try:
            question = Question.objects.get(id=question_id)
        except Question.DoesNotExist:
            return Response({'error': 'Question not found'}, status=404)
        
        results = {}
        
        # Create processing jobs based on requested types
        if 'summary' in processing_types:
            summary = DocumentSummary.objects.create(
                question=question,
                summary_type='ai_generated',
                summary_text=f"AI-generated summary of question {question.id}",
                confidence_score=0.88,
                word_count=75,
                created_by=request.user
            )
            results['summary'] = {
                'id': summary.id,
                'text': summary.summary_text
            }
        
        if 'classification' in processing_types:
            classification = TopicClassification.objects.create(
                question=question,
                primary_topic='Parliamentary Affairs',
                secondary_topics=['Government', 'Policy'],
                confidence_scores={'Parliamentary Affairs': 0.92},
                created_by=request.user
            )
            results['classification'] = {
                'id': classification.id,
                'primary_topic': classification.primary_topic
            }
        
        if 'keywords' in processing_types:
            metadata = MetadataExtraction.objects.create(
                question=question,
                extraction_type='keywords',
                extracted_metadata={'keywords': ['parliament', 'government', 'policy', 'minister']},
                confidence_score=0.85,
                created_by=request.user
            )
            results['keywords'] = {
                'id': metadata.id,
                'keywords': metadata.extracted_metadata.get('keywords', [])
            }
        
        return Response({
            'message': 'Question processed successfully',
            'question_id': question.id,
            'results': results
        })


class ExtractKeywordsView(APIView):
    """Extract keywords from text"""
    permission_classes = []
    
    @extend_schema(
        description="Extract keywords from text",
        tags=['AI Service']
    )
    def post(self, request):
        """Extract keywords"""
        text = request.data.get('text', '')
        max_keywords = request.data.get('max_keywords', 10)
        
        if not text:
            return Response({'error': 'Text is required'}, status=400)
        
        # Mock keyword extraction
        keywords = ['parliament', 'government', 'policy', 'minister', 'bill', 'law'][:max_keywords]
        
        metadata = MetadataExtraction.objects.create(
            extraction_type='keywords',
            extracted_metadata={'keywords': keywords, 'text_length': len(text)},
            confidence_score=0.80,
            created_by=request.user
        )
        
        return Response({
            'extraction_id': metadata.id,
            'keywords': keywords,
            'confidence_score': float(metadata.confidence_score)
        })


class ExtractEntitiesView(APIView):
    """Extract named entities from text"""
    permission_classes = []
    
    @extend_schema(
        description="Extract named entities from text",
        tags=['AI Service']
    )
    def post(self, request):
        """Extract entities"""
        text = request.data.get('text', '')
        
        if not text:
            return Response({'error': 'Text is required'}, status=400)
        
        # Mock entity extraction
        entities = {
            'PERSON': ['Minister Singh', 'MP Kumar'],
            'ORG': ['Parliament', 'Ministry of Health'],
            'GPE': ['India', 'Delhi'],
            'DATE': ['2024', 'January']
        }
        
        metadata = MetadataExtraction.objects.create(
            extraction_type='entities',
            extracted_metadata={'entities': entities},
            confidence_score=0.88,
            created_by=request.user
        )
        
        return Response({
            'extraction_id': metadata.id,
            'entities': entities,
            'confidence_score': float(metadata.confidence_score)
        })


# AI Models and Configuration Views
class AIModelsView(APIView):
    """List available AI models"""
    permission_classes = []
    
    @extend_schema(
        description="List available AI models",
        tags=['AI Service']
    )
    def get(self, request):
        """List AI models"""
        models = [
            {
                'name': 'gpt-3.5-turbo',
                'type': 'language_model',
                'description': 'Fast and efficient language model',
                'cost_per_token': 0.0000015,
                'max_tokens': 4096,
                'available': True
            },
            {
                'name': 'gpt-4',
                'type': 'language_model',
                'description': 'Advanced reasoning and analysis',
                'cost_per_token': 0.00003,
                'max_tokens': 8192,
                'available': True
            },
            {
                'name': 'text-embedding-ada-002',
                'type': 'embedding_model',
                'description': 'Text embeddings for similarity',
                'cost_per_token': 0.0000001,
                'max_tokens': 8191,
                'available': True
            }
        ]
        
        return Response({
            'models': models,
            'total_models': len(models)
        })


class TestModelView(APIView):
    """Test AI model functionality"""
    permission_classes = []
    
    @extend_schema(
        description="Test AI model with sample input",
        tags=['AI Service']
    )
    def post(self, request):
        """Test model"""
        model_name = request.data.get('model', 'gpt-3.5-turbo')
        test_input = request.data.get('input', 'Hello, how are you?')
        
        # Mock model test
        test_result = {
            'model': model_name,
            'input': test_input,
            'output': f'Test response from {model_name}',
            'latency_ms': 150,
            'tokens_used': 25,
            'success': True
        }
        
        # Track usage
        AIModelUsage.objects.create(
            model_name=model_name,
            operation_type='test',
            prompt_tokens=len(test_input.split()),
            completion_tokens=10,
            total_tokens=len(test_input.split()) + 10,
            cost=0.001,
            user=request.user
        )
        
        return Response(test_result)


class ModelStatusView(APIView):
    """Get AI model status"""
    permission_classes = []
    
    @extend_schema(
        description="Get status of AI models",
        tags=['AI Service']
    )
    def get(self, request):
        """Get model status"""
        return Response({
            'models_available': 3,
            'models_healthy': 3,
            'average_response_time': 145,
            'total_requests_today': 127,
            'error_rate': 0.02,
            'last_health_check': timezone.now()
        })


# Job Management Views
class JobStatusView(APIView):
    """Get job status"""
    permission_classes = []
    
    @extend_schema(
        description="Get status of AI jobs",
        tags=['AI Service']
    )
    def get(self, request):
        """Get job status"""
        from django.db.models import Count
        
        status_counts = AIAnalysisJob.objects.values('status').annotate(
            count=Count('id')
        )
        
        return Response({
            'job_status': {
                item['status']: item['count']
                for item in status_counts
            },
            'total_jobs': AIAnalysisJob.objects.count(),
            'jobs_today': AIAnalysisJob.objects.filter(
                created_at__date=timezone.now().date()
            ).count()
        })


class JobQueueView(APIView):
    """Get job queue"""
    permission_classes = []
    
    @extend_schema(
        description="Get AI job queue",
        tags=['AI Service']
    )
    def get(self, request):
        """Get job queue"""
        pending_jobs = AIAnalysisJob.objects.filter(status='pending')[:10]
        
        return Response({
            'pending_jobs': [
                {
                    'id': job.id,
                    'job_type': job.job_type,
                    'created_at': job.created_at,
                    'priority': 'normal'  # Could be added to model
                }
                for job in pending_jobs
            ],
            'queue_length': pending_jobs.count()
        })


class JobResultView(APIView):
    """Get job result"""
    permission_classes = []
    
    @extend_schema(
        description="Get result of AI job",
        tags=['AI Service']
    )
    def get(self, request, job_id):
        """Get job result"""
        try:
            job = AIAnalysisJob.objects.get(id=job_id)
        except AIAnalysisJob.DoesNotExist:
            return Response({'error': 'Job not found'}, status=404)
        
        return Response({
            'job': {
                'id': job.id,
                'job_type': job.job_type,
                'status': job.status,
                'result': job.result,
                'model_used': job.model_used,
                'created_at': job.created_at,
                'completed_at': job.completed_at,
                'total_cost': float(job.total_cost) if job.total_cost else 0
            }
        })


class CancelJobView(APIView):
    """Cancel AI job"""
    permission_classes = []
    
    @extend_schema(
        description="Cancel AI job",
        tags=['AI Service']
    )
    def post(self, request, job_id):
        """Cancel job"""
        try:
            job = AIAnalysisJob.objects.get(id=job_id)
        except AIAnalysisJob.DoesNotExist:
            return Response({'error': 'Job not found'}, status=404)
        
        if job.status in ['completed', 'failed', 'cancelled']:
            return Response({'error': 'Cannot cancel completed job'}, status=400)
        
        job.status = 'cancelled'
        job.completed_at = timezone.now()
        job.save()
        
        return Response({
            'message': 'Job cancelled successfully',
            'job_id': job.id
        })


# Statistics and Monitoring Views
class AIStatsView(APIView):
    """Get AI service statistics"""
    permission_classes = []
    
    @extend_schema(
        description="Get AI service statistics",
        tags=['AI Service']
    )
    def get(self, request):
        """Get AI stats"""
        from django.db.models import Sum, Count, Avg
        
        # Job statistics
        job_stats = AIAnalysisJob.objects.aggregate(
            total_jobs=Count('id'),
            avg_completion_time=Avg('completion_time'),
            total_tokens=Sum('prompt_tokens') + Sum('completion_tokens')
        )
        
        # Usage statistics
        usage_stats = AIModelUsage.objects.aggregate(
            total_cost=Sum('cost'),
            total_tokens=Sum('total_tokens')
        )
        
        return Response({
            'jobs': {
                'total': job_stats['total_jobs'] or 0,
                'average_completion_time': job_stats['avg_completion_time'] or 0,
                'total_tokens_processed': job_stats['total_tokens'] or 0
            },
            'usage': {
                'total_cost': float(usage_stats['total_cost'] or 0),
                'total_tokens': usage_stats['total_tokens'] or 0
            },
            'summaries_created': DocumentSummary.objects.count(),
            'classifications_created': TopicClassification.objects.count(),
            'metadata_extractions': MetadataExtraction.objects.count()
        })


class UsageStatsView(APIView):
    """Get usage statistics"""
    permission_classes = []
    
    @extend_schema(
        description="Get AI service usage statistics",
        tags=['AI Service']
    )
    def get(self, request):
        """Get usage stats"""
        from django.db.models import Sum, Count
        from datetime import timedelta
        
        # Today's usage
        today = timezone.now().date()
        today_usage = AIModelUsage.objects.filter(timestamp__date=today).aggregate(
            tokens=Sum('total_tokens'),
            cost=Sum('cost'),
            requests=Count('id')
        )
        
        # This week's usage
        week_ago = timezone.now() - timedelta(days=7)
        week_usage = AIModelUsage.objects.filter(timestamp__gte=week_ago).aggregate(
            tokens=Sum('total_tokens'),
            cost=Sum('cost'),
            requests=Count('id')
        )
        
        return Response({
            'today': {
                'total_tokens': today_usage['tokens'] or 0,
                'total_cost': float(today_usage['cost'] or 0),
                'total_requests': today_usage['requests'] or 0
            },
            'this_week': {
                'total_tokens': week_usage['tokens'] or 0,
                'total_cost': float(week_usage['cost'] or 0),
                'total_requests': week_usage['requests'] or 0
            },
            'top_models': [
                {'model': 'gpt-3.5-turbo', 'usage_count': 45},
                {'model': 'gpt-4', 'usage_count': 12},
                {'model': 'text-embedding-ada-002', 'usage_count': 8}
            ]
        })


class CostAnalysisView(APIView):
    """Get cost analysis"""
    permission_classes = []
    
    @extend_schema(
        description="Get AI service cost analysis",
        tags=['AI Service']
    )
    def get(self, request):
        """Get cost analysis"""
        from django.db.models import Sum
        from datetime import timedelta
        
        # Cost by model
        cost_by_model = AIModelUsage.objects.values('model_name').annotate(
            total_cost=Sum('cost')
        ).order_by('-total_cost')
        
        # Monthly trend (simplified)
        monthly_cost = AIModelUsage.objects.filter(
            timestamp__gte=timezone.now() - timedelta(days=30)
        ).aggregate(total=Sum('cost'))
        
        return Response({
            'total_monthly_cost': float(monthly_cost['total'] or 0),
            'cost_by_model': [
                {
                    'model': item['model_name'],
                    'cost': float(item['total_cost'] or 0)
                }
                for item in cost_by_model
            ],
            'average_cost_per_request': 0.015,  # Mock value
            'projected_monthly_cost': float(monthly_cost['total'] or 0) * 1.2,
            'cost_trends': {
                'increasing': True,
                'trend_percentage': 15.5
            }
        })
