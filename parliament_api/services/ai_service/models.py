from django.db import models
from django.contrib.auth.models import User
from services.questions.models import Question
from django.utils import timezone
import json


class AIAnalysisJob(models.Model):
    """Model to track AI analysis jobs"""
    
    JOB_STATUS = [
        ('pending', 'Pending'),
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]
    
    JOB_TYPES = [
        ('summary', 'Document Summary'),
        ('metadata_extraction', 'Metadata Extraction'),
        ('topic_classification', 'Topic Classification'),
        ('sentiment_analysis', 'Sentiment Analysis'),
        ('entity_extraction', 'Entity Extraction'),
        ('full_analysis', 'Full Analysis'),
    ]

    # Job Information
    name = models.CharField(max_length=200)
    job_type = models.CharField(max_length=30, choices=JOB_TYPES, default='summary')
    status = models.CharField(max_length=20, choices=JOB_STATUS, default='pending')
    
    # Target Questions
    questions = models.ManyToManyField(Question, related_name='ai_jobs', blank=True)
    
    # Configuration
    ai_model = models.CharField(max_length=100, default='gpt-3.5-turbo')
    batch_size = models.IntegerField(default=10)
    max_tokens = models.IntegerField(default=1000)
    temperature = models.FloatField(default=0.3)
    
    # Progress Tracking
    total_questions = models.IntegerField(default=0)
    processed_questions = models.IntegerField(default=0)
    successful_analyses = models.IntegerField(default=0)
    failed_analyses = models.IntegerField(default=0)
    
    # Cost Tracking
    total_tokens_used = models.BigIntegerField(default=0)
    estimated_cost = models.DecimalField(max_digits=10, decimal_places=4, default=0)
    
    # Execution Details
    started_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    error_message = models.TextField(blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['job_type', 'status']),
        ]

    def __str__(self):
        return f"AI Job: {self.name} ({self.job_type}) - {self.status}"

    @property
    def progress_percent(self):
        if self.total_questions > 0:
            return round((self.processed_questions / self.total_questions) * 100, 2)
        return 0

    @property
    def duration(self):
        if self.started_at:
            end_time = self.completed_at or timezone.now()
            return end_time - self.started_at
        return None

    def start_job(self):
        """Mark job as started"""
        self.status = 'running'
        self.started_at = timezone.now()
        self.save()

    def complete_job(self):
        """Mark job as completed"""
        self.status = 'completed'
        self.completed_at = timezone.now()
        self.save()

    def fail_job(self, error_message):
        """Mark job as failed"""
        self.status = 'failed'
        self.error_message = error_message
        self.save()


class DocumentSummary(models.Model):
    """Model to store AI-generated document summaries"""
    
    SUMMARY_TYPES = [
        ('brief', 'Brief Summary'),
        ('detailed', 'Detailed Summary'),
        ('executive', 'Executive Summary'),
        ('technical', 'Technical Summary'),
    ]

    # Relationships
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='summaries')
    analysis_job = models.ForeignKey(AIAnalysisJob, on_delete=models.SET_NULL, null=True, blank=True)
    
    # Summary Content
    summary_type = models.CharField(max_length=20, choices=SUMMARY_TYPES, default='brief')
    summary_text = models.TextField()
    key_points = models.JSONField(default=list, blank=True)  # List of key points
    word_count = models.IntegerField(default=0)
    
    # AI Model Information
    ai_model = models.CharField(max_length=100, default='gpt-3.5-turbo')
    prompt_used = models.TextField(blank=True)
    tokens_used = models.IntegerField(default=0)
    processing_time = models.FloatField(default=0)  # seconds
    
    # Quality Metrics
    confidence_score = models.FloatField(null=True, blank=True)
    human_reviewed = models.BooleanField(default=False)
    human_rating = models.IntegerField(null=True, blank=True)  # 1-5 scale
    feedback = models.TextField(blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['question', 'summary_type']
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['question', 'summary_type']),
            models.Index(fields=['human_reviewed']),
        ]

    def __str__(self):
        return f"Summary ({self.summary_type}) - Q.{self.question.question_number}"

    @property
    def is_recent(self):
        """Check if summary is recent (within 30 days)"""
        return (timezone.now() - self.created_at).days <= 30


class MetadataExtraction(models.Model):
    """Model to store AI-extracted metadata from questions"""
    
    # Relationships
    question = models.OneToOneField(Question, on_delete=models.CASCADE, related_name='ai_metadata')
    analysis_job = models.ForeignKey(AIAnalysisJob, on_delete=models.SET_NULL, null=True, blank=True)
    
    # Extracted Entities
    people = models.JSONField(default=list, blank=True)  # Names of people mentioned
    organizations = models.JSONField(default=list, blank=True)  # Organizations mentioned
    locations = models.JSONField(default=list, blank=True)  # Places mentioned
    dates_mentioned = models.JSONField(default=list, blank=True)  # Dates in content
    amounts = models.JSONField(default=list, blank=True)  # Money/numerical amounts
    
    # Topics and Classifications
    primary_topics = models.JSONField(default=list, blank=True)  # Main topics
    secondary_topics = models.JSONField(default=list, blank=True)  # Related topics
    policy_areas = models.JSONField(default=list, blank=True)  # Policy domains
    urgency_level = models.CharField(max_length=20, blank=True)  # urgent, normal, low
    
    # Content Analysis
    sentiment = models.CharField(max_length=20, blank=True)  # positive, negative, neutral
    sentiment_score = models.FloatField(null=True, blank=True)  # -1 to 1
    complexity_score = models.FloatField(null=True, blank=True)  # 1-10 scale
    readability_score = models.FloatField(null=True, blank=True)  # Grade level
    
    # Question Analysis
    question_intent = models.CharField(max_length=50, blank=True)  # seeking_info, complaint, etc.
    requires_action = models.BooleanField(null=True, blank=True)
    follow_up_needed = models.BooleanField(null=True, blank=True)
    
    # AI Processing Details
    ai_model = models.CharField(max_length=100, default='gpt-3.5-turbo')
    confidence_scores = models.JSONField(default=dict, blank=True)  # Per-field confidence
    processing_notes = models.TextField(blank=True)
    
    # Quality Control
    human_verified = models.BooleanField(default=False)
    verification_notes = models.TextField(blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['urgency_level']),
            models.Index(fields=['sentiment']),
            models.Index(fields=['human_verified']),
        ]

    def __str__(self):
        return f"AI Metadata - Q.{self.question.question_number}"

    def get_all_entities(self):
        """Get all extracted entities in a single list"""
        entities = []
        entities.extend(self.people)
        entities.extend(self.organizations)
        entities.extend(self.locations)
        return list(set(entities))  # Remove duplicates

    def get_confidence_summary(self):
        """Get average confidence score"""
        if self.confidence_scores:
            scores = [score for score in self.confidence_scores.values() if isinstance(score, (int, float))]
            return sum(scores) / len(scores) if scores else 0
        return 0


class TopicClassification(models.Model):
    """Model to store topic classifications for questions"""
    
    CLASSIFICATION_TYPES = [
        ('automatic', 'Automatic Classification'),
        ('manual', 'Manual Classification'),
        ('hybrid', 'Human-AI Hybrid'),
    ]

    # Relationships
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='topic_classifications')
    analysis_job = models.ForeignKey(AIAnalysisJob, on_delete=models.SET_NULL, null=True, blank=True)
    
    # Classification Details
    topic_name = models.CharField(max_length=200)
    topic_category = models.CharField(max_length=100, blank=True)  # broad category
    confidence_score = models.FloatField(default=0.0)  # 0-1 scale
    classification_type = models.CharField(max_length=20, choices=CLASSIFICATION_TYPES, default='automatic')
    
    # Hierarchy
    parent_topic = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True)
    level = models.IntegerField(default=1)  # 1=main topic, 2=subtopic, etc.
    
    # Source Information
    keywords_matched = models.JSONField(default=list, blank=True)
    ai_reasoning = models.TextField(blank=True)
    
    # Validation
    human_validated = models.BooleanField(default=False)
    validation_notes = models.TextField(blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['question', 'topic_name']
        ordering = ['-confidence_score']
        indexes = [
            models.Index(fields=['topic_category']),
            models.Index(fields=['confidence_score']),
            models.Index(fields=['classification_type']),
        ]

    def __str__(self):
        return f"{self.topic_name} - Q.{self.question.question_number} ({self.confidence_score:.2f})"


class AIModelUsage(models.Model):
    """Model to track AI model usage and costs"""
    
    # Model Information
    model_name = models.CharField(max_length=100)
    model_version = models.CharField(max_length=50, blank=True)
    provider = models.CharField(max_length=50, default='openai')  # openai, anthropic, etc.
    
    # Usage Details
    operation_type = models.CharField(max_length=50)  # summary, classification, etc.
    input_tokens = models.IntegerField(default=0)
    output_tokens = models.IntegerField(default=0)
    total_tokens = models.IntegerField(default=0)
    
    # Cost Information
    cost_per_input_token = models.DecimalField(max_digits=10, decimal_places=8, default=0)
    cost_per_output_token = models.DecimalField(max_digits=10, decimal_places=8, default=0)
    total_cost = models.DecimalField(max_digits=10, decimal_places=4, default=0)
    
    # Performance Metrics
    response_time = models.FloatField(default=0)  # seconds
    success = models.BooleanField(default=True)
    error_message = models.TextField(blank=True)
    
    # Context
    question = models.ForeignKey(Question, on_delete=models.SET_NULL, null=True, blank=True)
    analysis_job = models.ForeignKey(AIAnalysisJob, on_delete=models.SET_NULL, null=True, blank=True)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    
    # Timestamp
    used_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-used_at']
        indexes = [
            models.Index(fields=['model_name', 'used_at']),
            models.Index(fields=['operation_type']),
            models.Index(fields=['success']),
        ]

    def __str__(self):
        return f"{self.model_name} - {self.operation_type} ({self.total_tokens} tokens)"

    def calculate_cost(self):
        """Calculate and update the total cost"""
        input_cost = self.input_tokens * self.cost_per_input_token
        output_cost = self.output_tokens * self.cost_per_output_token
        self.total_cost = input_cost + output_cost
        return self.total_cost


class AIPromptTemplate(models.Model):
    """Model to store and manage AI prompt templates"""
    
    TEMPLATE_TYPES = [
        ('summary', 'Summary Generation'),
        ('classification', 'Topic Classification'),
        ('extraction', 'Entity Extraction'),
        ('analysis', 'General Analysis'),
    ]

    # Template Information
    name = models.CharField(max_length=200, unique=True)
    description = models.TextField(blank=True)
    template_type = models.CharField(max_length=20, choices=TEMPLATE_TYPES)
    
    # Template Content
    prompt_template = models.TextField()
    system_message = models.TextField(blank=True)
    variables = models.JSONField(default=list, blank=True)  # List of variables in template
    
    # Configuration
    recommended_model = models.CharField(max_length=100, blank=True)
    max_tokens = models.IntegerField(default=1000)
    temperature = models.FloatField(default=0.3)
    
    # Status
    is_active = models.BooleanField(default=True)
    is_default = models.BooleanField(default=False)
    usage_count = models.IntegerField(default=0)
    
    # Version Control
    version = models.CharField(max_length=20, default='1.0')
    parent_template = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['template_type', 'name']
        indexes = [
            models.Index(fields=['template_type', 'is_active']),
            models.Index(fields=['is_default']),
        ]

    def __str__(self):
        return f"Prompt: {self.name} ({self.template_type})"

    def render_prompt(self, **kwargs):
        """Render the prompt template with provided variables"""
        try:
            return self.prompt_template.format(**kwargs)
        except KeyError as e:
            raise ValueError(f"Missing variable for prompt template: {e}")

    def increment_usage(self):
        """Increment the usage counter"""
        self.usage_count += 1
        self.save(update_fields=['usage_count'])
