from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

# Create a router for viewsets
router = DefaultRouter()
router.register(r'analysis-jobs', views.AIAnalysisJobViewSet, basename='ai-analysis-job')
router.register(r'summaries', views.DocumentSummaryViewSet, basename='document-summary')
router.register(r'metadata-extractions', views.MetadataExtractionViewSet, basename='metadata-extraction')
router.register(r'topic-classifications', views.TopicClassificationViewSet, basename='topic-classification')
router.register(r'model-usage', views.AIModelUsageViewSet, basename='ai-model-usage')
router.register(r'prompt-templates', views.AIPromptTemplateViewSet, basename='ai-prompt-template')

app_name = 'ai_service'

urlpatterns = [
    # Text analysis
    path('analyze/text/', views.AnalyzeTextView.as_view(), name='analyze-text'),
    path('analyze/document/', views.AnalyzeDocumentView.as_view(), name='analyze-document'),
    path('analyze/batch/', views.BatchAnalysisView.as_view(), name='batch-analysis'),
    
    # Summarization
    path('summarize/text/', views.SummarizeTextView.as_view(), name='summarize-text'),
    path('summarize/question/', views.SummarizeQuestionView.as_view(), name='summarize-question'),
    path('summarize/multiple/', views.SummarizeMultipleView.as_view(), name='summarize-multiple'),
    
    # Topic classification
    path('classify/topic/', views.ClassifyTopicView.as_view(), name='classify-topic'),
    path('classify/question/', views.ClassifyQuestionView.as_view(), name='classify-question'),
    path('classify/batch/', views.BatchClassifyView.as_view(), name='batch-classify'),
    
    # Question processing
    path('process/question/', views.ProcessQuestionView.as_view(), name='process-question'),
    path('extract/keywords/', views.ExtractKeywordsView.as_view(), name='extract-keywords'),
    path('extract/entities/', views.ExtractEntitiesView.as_view(), name='extract-entities'),
    
    # AI models and configuration
    path('models/', views.AIModelsView.as_view(), name='ai-models'),
    path('models/test/', views.TestModelView.as_view(), name='test-model'),
    path('models/status/', views.ModelStatusView.as_view(), name='model-status'),
    
    # Analysis status and monitoring
    path('jobs/status/', views.JobStatusView.as_view(), name='job-status'),
    path('jobs/queue/', views.JobQueueView.as_view(), name='job-queue'),
    path('jobs/<int:job_id>/result/', views.JobResultView.as_view(), name='job-result'),
    path('jobs/<int:job_id>/cancel/', views.CancelJobView.as_view(), name='cancel-job'),
    
    # Statistics and monitoring
    path('stats/', views.AIStatsView.as_view(), name='ai-stats'),
    path('usage/', views.UsageStatsView.as_view(), name='usage-stats'),
    path('costs/', views.CostAnalysisView.as_view(), name='cost-analysis'),
    
    # Router URLs
    path('', include(router.urls)),
] 