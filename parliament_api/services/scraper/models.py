from django.db import models
from django.contrib.auth.models import User
from services.questions.models import LokSabha, Session
from django.utils import timezone
import json


class ScrapingJob(models.Model):
    """Model to track scraping jobs for parliamentary data"""
    
    JOB_STATUS = [
        ('pending', 'Pending'),
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
        ('paused', 'Paused'),
    ]
    
    JOB_TYPES = [
        ('full_scrape', 'Full Scrape'),
        ('incremental', 'Incremental Update'),
        ('specific_session', 'Specific Session'),
        ('retry_failed', 'Retry Failed'),
        ('debates', 'Debate Scraping'),
    ]

    # Job Information
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    job_type = models.CharField(max_length=20, choices=JOB_TYPES, default='incremental')
    status = models.CharField(max_length=20, choices=JOB_STATUS, default='pending')
    
    # Target Configuration
    target_lok_sabhas = models.ManyToManyField(LokSabha, blank=True)
    target_sessions = models.ManyToManyField(Session, blank=True)
    
    # Progress Tracking
    total_questions_expected = models.IntegerField(default=0)
    questions_processed = models.IntegerField(default=0)
    questions_created = models.IntegerField(default=0)
    questions_updated = models.IntegerField(default=0)
    questions_failed = models.IntegerField(default=0)
    
    # Configuration
    batch_size = models.IntegerField(default=100)
    worker_count = models.IntegerField(default=5)
    max_retries = models.IntegerField(default=3)
    delay_between_requests = models.FloatField(default=0.5)  # seconds
    
    # Execution Details
    started_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    worker_id = models.CharField(max_length=50, blank=True)
    pid = models.IntegerField(null=True, blank=True)  # Process ID
    
    # Error Handling
    error_message = models.TextField(blank=True)
    error_count = models.IntegerField(default=0)
    last_error = models.DateTimeField(null=True, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    last_activity = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['job_type', 'status']),
            models.Index(fields=['started_at']),
        ]

    def __str__(self):
        return f"Scraping Job: {self.name} ({self.status})"

    @property
    def progress_percent(self):
        if self.total_questions_expected > 0:
            return round((self.questions_processed / self.total_questions_expected) * 100, 2)
        return 0

    @property
    def is_running(self):
        return self.status in ['pending', 'running', 'paused']

    @property
    def duration(self):
        if self.started_at:
            end_time = self.completed_at or timezone.now()
            return end_time - self.started_at
        return None

    def start_job(self, worker_id=None, pid=None):
        """Mark job as started"""
        self.status = 'running'
        self.started_at = timezone.now()
        if worker_id:
            self.worker_id = worker_id
        if pid:
            self.pid = pid
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
        self.error_count += 1
        self.last_error = timezone.now()
        self.save()

    def pause_job(self):
        """Pause the job"""
        if self.status == 'running':
            self.status = 'paused'
            self.save()

    def resume_job(self):
        """Resume a paused job"""
        if self.status == 'paused':
            self.status = 'running'
            self.save()

    def cancel_job(self):
        """Cancel the job"""
        if self.is_running:
            self.status = 'cancelled'
            self.completed_at = timezone.now()
            self.save()


class ScrapingSession(models.Model):
    """Model to track scraping progress for specific Lok Sabha sessions"""
    
    SESSION_STATUS = [
        ('not_started', 'Not Started'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('partially_completed', 'Partially Completed'),
    ]

    # Relationships
    scraping_job = models.ForeignKey(ScrapingJob, on_delete=models.CASCADE, related_name='sessions')
    lok_sabha = models.ForeignKey(LokSabha, on_delete=models.CASCADE)
    session = models.ForeignKey(Session, on_delete=models.CASCADE, null=True, blank=True)
    
    # Progress
    status = models.CharField(max_length=20, choices=SESSION_STATUS, default='not_started')
    total_questions = models.IntegerField(default=0)
    processed_questions = models.IntegerField(default=0)
    successful_questions = models.IntegerField(default=0)
    failed_questions = models.IntegerField(default=0)
    
    # API Pagination
    current_start_position = models.IntegerField(default=0)
    batch_size = models.IntegerField(default=100)
    last_question_id = models.CharField(max_length=50, blank=True)
    
    # Timestamps
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    last_update = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['scraping_job', 'lok_sabha', 'session']
        ordering = ['-started_at']

    def __str__(self):
        session_str = f" Session {self.session.session_number}" if self.session else ""
        return f"{self.lok_sabha.number}th LS{session_str} - {self.status}"

    @property
    def progress_percent(self):
        if self.total_questions > 0:
            return round((self.processed_questions / self.total_questions) * 100, 2)
        return 0

    def update_progress(self, processed=0, successful=0, failed=0):
        """Update progress counters"""
        self.processed_questions += processed
        self.successful_questions += successful
        self.failed_questions += failed
        self.save()


class ScrapingError(models.Model):
    """Model to track specific scraping errors"""
    
    ERROR_TYPES = [
        ('api_error', 'API Error'),
        ('parsing_error', 'Data Parsing Error'),
        ('database_error', 'Database Error'),
        ('network_error', 'Network Error'),
        ('timeout_error', 'Timeout Error'),
        ('rate_limit', 'Rate Limit Exceeded'),
        ('unknown', 'Unknown Error'),
    ]

    # Relationships
    scraping_job = models.ForeignKey(ScrapingJob, on_delete=models.CASCADE, related_name='errors')
    scraping_session = models.ForeignKey(ScrapingSession, on_delete=models.CASCADE, null=True, blank=True)
    
    # Error Details
    error_type = models.CharField(max_length=20, choices=ERROR_TYPES, default='unknown')
    error_message = models.TextField()
    stack_trace = models.TextField(blank=True)
    
    # Context
    api_endpoint = models.URLField(blank=True)
    request_data = models.JSONField(default=dict, blank=True)
    response_status = models.IntegerField(null=True, blank=True)
    question_id = models.CharField(max_length=50, blank=True)
    
    # Recovery
    is_resolved = models.BooleanField(default=False)
    retry_count = models.IntegerField(default=0)
    resolved_at = models.DateTimeField(null=True, blank=True)
    
    # Timestamp
    occurred_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-occurred_at']
        indexes = [
            models.Index(fields=['scraping_job', 'error_type']),
            models.Index(fields=['occurred_at']),
            models.Index(fields=['is_resolved']),
        ]

    def __str__(self):
        return f"{self.error_type}: {self.error_message[:50]}..."

    def mark_resolved(self):
        """Mark error as resolved"""
        self.is_resolved = True
        self.resolved_at = timezone.now()
        self.save()


class ScrapingConfig(models.Model):
    """Model to store scraping configuration and settings"""
    
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    
    # API Configuration
    api_base_url = models.URLField(default="https://eparlib.sansad.in/restv3")
    api_timeout = models.IntegerField(default=30)  # seconds
    max_retries = models.IntegerField(default=3)
    delay_between_requests = models.FloatField(default=0.5)
    
    # Scraping Parameters
    default_batch_size = models.IntegerField(default=100)
    default_workers = models.IntegerField(default=5)
    enable_parallel_processing = models.BooleanField(default=True)
    
    # Data Processing
    update_existing_questions = models.BooleanField(default=True)
    create_missing_members = models.BooleanField(default=True)
    create_missing_ministries = models.BooleanField(default=True)
    
    # Scheduling
    auto_scrape_enabled = models.BooleanField(default=False)
    auto_scrape_frequency = models.IntegerField(default=24)  # hours
    last_auto_scrape = models.DateTimeField(null=True, blank=True)
    
    # Flags
    is_active = models.BooleanField(default=True)
    is_default = models.BooleanField(default=False)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f"Config: {self.name}"

    def save(self, *args, **kwargs):
        # Ensure only one default config
        if self.is_default:
            ScrapingConfig.objects.filter(is_default=True).update(is_default=False)
        super().save(*args, **kwargs)

    @classmethod
    def get_default(cls):
        """Get the default scraping configuration"""
        try:
            return cls.objects.get(is_default=True)
        except cls.DoesNotExist:
            return cls.objects.filter(is_active=True).first()


class DataSource(models.Model):
    """Model to track different data sources"""
    
    SOURCE_TYPES = [
        ('api', 'API Endpoint'),
        ('file', 'File Upload'),
        ('manual', 'Manual Entry'),
        ('external', 'External Source'),
    ]

    name = models.CharField(max_length=100, unique=True)
    source_type = models.CharField(max_length=20, choices=SOURCE_TYPES, default='api')
    base_url = models.URLField(blank=True)
    description = models.TextField(blank=True)
    
    # Configuration
    auth_required = models.BooleanField(default=False)
    auth_type = models.CharField(max_length=50, blank=True)  # token, basic, oauth, etc.
    rate_limit = models.IntegerField(null=True, blank=True)  # requests per minute
    
    # Status
    is_active = models.BooleanField(default=True)
    last_accessed = models.DateTimeField(null=True, blank=True)
    last_success = models.DateTimeField(null=True, blank=True)
    error_count = models.IntegerField(default=0)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f"Data Source: {self.name} ({self.source_type})"

    def record_success(self):
        """Record successful access"""
        self.last_accessed = timezone.now()
        self.last_success = timezone.now()
        self.error_count = 0
        self.save()

    def record_error(self):
        """Record failed access"""
        self.last_accessed = timezone.now()
        self.error_count += 1
        self.save() 