from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from services.questions.models import Question
import os


class DocumentFile(models.Model):
    """Model to track PDF files for parliamentary documents"""
    
    STATUS_CHOICES = [
        ('pending', 'Download Pending'),
        ('downloading', 'Currently Downloading'),
        ('completed', 'Download Completed'),
        ('failed', 'Download Failed'),
        ('not_available', 'Not Available'),
    ]
    
    DOCUMENT_CATEGORIES = [
        ('parl_question', 'Parliamentary Question'),
        ('parl_debate', 'Parliamentary Debate'),
        ('parl_answer', 'Parliamentary Answer'),
        ('parl_appendix', 'Parliamentary Appendix'),
        ('parl_committee', 'Committee Report'),
        ('parl_bill', 'Bill Document'),
        ('other', 'Other Document'),
    ]
    
    FILE_TYPES = [
        ('question', 'Question Document'),
        ('answer', 'Answer Document'),
        ('combined', 'Combined Q&A Document'),
        ('debate', 'Debate Transcript'),
        ('appendix', 'Appendix'),
        ('committee_report', 'Committee Report'),
        ('bill', 'Bill Document'),
        ('other', 'Other'),
    ]

    # Document Category (primary categorization)
    document_category = models.CharField(max_length=20, choices=DOCUMENT_CATEGORIES, default='other')
    
    # Relationships (optional - depends on document type)
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='files', null=True, blank=True)
    
    # File Information
    file_type = models.CharField(max_length=20, choices=FILE_TYPES, default='question')
    original_url = models.URLField(max_length=500)
    file_name = models.CharField(max_length=255)
    file_path = models.FileField(upload_to='pdfs/', null=True, blank=True)
    file_size = models.BigIntegerField(null=True, blank=True)  # Size in bytes
    content_type = models.CharField(max_length=100, default='application/pdf')
    
    # Download Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    download_attempts = models.IntegerField(default=0)
    last_download_attempt = models.DateTimeField(null=True, blank=True)
    download_error = models.TextField(blank=True)
    
    # Google Cloud Storage fields
    gcs_bucket_name = models.CharField(max_length=100, blank=True)
    gcs_object_key = models.CharField(max_length=500, blank=True)
    gcs_uploaded_at = models.DateTimeField(null=True, blank=True)
    gcs_upload_status = models.CharField(max_length=20, default='pending', choices=[
        ('pending', 'Upload Pending'),
        ('uploading', 'Currently Uploading'),
        ('completed', 'Upload Completed'),
        ('failed', 'Upload Failed'),
    ])
    gcs_etag = models.CharField(max_length=100, blank=True)  # For integrity checking
    gcs_url = models.URLField(max_length=500, blank=True)  # gs:// URL
    
    # Metadata
    requested_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    download_priority = models.IntegerField(default=5)  # 1=highest, 10=lowest
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    downloaded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['document_category', 'file_type']),
            models.Index(fields=['question', 'file_type']),
            models.Index(fields=['download_priority', 'created_at']),
        ]

    def __str__(self):
        if self.question:
            return f"Q.{self.question.question_number} - {self.file_type} ({self.status})"
        else:
            return f"{self.document_category} - {self.file_type} ({self.status})"

    @property
    def is_downloaded(self):
        return self.status == 'completed' and (self.file_path or self.gcs_object_key)
    
    @property
    def is_in_gcs(self):
        return self.gcs_upload_status == 'completed' and self.gcs_object_key

    @property
    def file_size_mb(self):
        if self.file_size:
            return round(self.file_size / (1024 * 1024), 2)
        return None

    def get_absolute_path(self):
        """Get absolute file path if file exists"""
        if self.file_path:
            return self.file_path.path
        return None

    def get_download_url(self):
        """Get URL to download the file through our API"""
        if self.is_downloaded:
            return f"/api/files/{self.id}/download/"
        return None
    
    def get_gcs_presigned_url(self, expiration_minutes=60):
        """Get presigned URL for GCS file access"""
        if not self.is_in_gcs:
            return None
        
        try:
            from services.cloud_storage.gcs_service import GCSService
            gcs_service = GCSService()
            return gcs_service.generate_presigned_url(
                self.gcs_bucket_name,
                self.gcs_object_key,
                expiration_minutes
            )
        except Exception:
            return None

    def delete_file(self):
        """Delete the physical file from disk"""
        if self.file_path and os.path.exists(self.file_path.path):
            os.remove(self.file_path.path)
            self.file_path = None
            self.status = 'pending'
            self.save()

    def can_retry_download(self):
        """Check if download can be retried"""
        return self.status in ['failed', 'pending'] and self.download_attempts < 3


class DownloadQueue(models.Model):
    """Model to manage parallel download queue"""
    
    QUEUE_STATUS = [
        ('queued', 'Queued'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]

    document_file = models.ForeignKey(DocumentFile, on_delete=models.CASCADE, related_name='download_jobs')
    status = models.CharField(max_length=20, choices=QUEUE_STATUS, default='queued')
    priority = models.IntegerField(default=5)
    worker_id = models.CharField(max_length=50, blank=True)  # ID of worker processing this
    
    # Progress tracking
    progress_percent = models.IntegerField(default=0)
    bytes_downloaded = models.BigIntegerField(default=0)
    total_bytes = models.BigIntegerField(null=True, blank=True)
    
    # Error handling
    error_message = models.TextField(blank=True)
    retry_count = models.IntegerField(default=0)
    max_retries = models.IntegerField(default=3)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['priority', 'created_at']
        indexes = [
            models.Index(fields=['status', 'priority']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f"Download Job {self.id} - {self.document_file} ({self.status})"

    @property
    def is_processing(self):
        return self.status in ['queued', 'processing']

    @property
    def can_retry(self):
        return self.status == 'failed' and self.retry_count < self.max_retries

    def mark_started(self, worker_id):
        """Mark download as started by a worker"""
        self.status = 'processing'
        self.worker_id = worker_id
        self.started_at = timezone.now()
        self.save()

    def mark_completed(self):
        """Mark download as completed"""
        self.status = 'completed'
        self.progress_percent = 100
        self.completed_at = timezone.now()
        self.save()

    def mark_failed(self, error_message):
        """Mark download as failed"""
        self.status = 'failed'
        self.error_message = error_message
        self.retry_count += 1
        self.save()


class DownloadBatch(models.Model):
    """Model to track batch download requests"""
    
    BATCH_STATUS = [
        ('created', 'Created'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('partially_failed', 'Partially Failed'),
        ('failed', 'Failed'),
    ]

    # Batch Information
    name = models.CharField(max_length=200, blank=True)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=BATCH_STATUS, default='created')
    
    # Relationships
    questions = models.ManyToManyField(Question, related_name='download_batches')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    
    # Progress tracking
    total_files = models.IntegerField(default=0)
    completed_files = models.IntegerField(default=0)
    failed_files = models.IntegerField(default=0)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Batch {self.id}: {self.name or 'Unnamed'} ({self.status})"

    @property
    def progress_percent(self):
        if self.total_files > 0:
            return round((self.completed_files / self.total_files) * 100, 2)
        return 0

    def update_progress(self):
        """Update batch progress based on download jobs"""
        jobs = DownloadQueue.objects.filter(
            document_file__question__in=self.questions.all()
        )
        self.total_files = jobs.count()
        self.completed_files = jobs.filter(status='completed').count()
        self.failed_files = jobs.filter(status='failed').count()
        
        if self.total_files > 0:
            if self.completed_files == self.total_files:
                self.status = 'completed'
            elif self.failed_files > 0:
                self.status = 'partially_failed'
            else:
                self.status = 'processing'
        
        self.save()


class FileAccessLog(models.Model):
    """Model to track file access for analytics"""
    document_file = models.ForeignKey(DocumentFile, on_delete=models.CASCADE, related_name='access_logs')
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    access_type = models.CharField(max_length=50, default='download')  # download, view, etc.
    accessed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-accessed_at']
        indexes = [
            models.Index(fields=['document_file', 'accessed_at']),
            models.Index(fields=['user', 'accessed_at']),
        ]

    def __str__(self):
        user_str = self.user.username if self.user else self.ip_address
        return f"{self.document_file.file_name} - {user_str} ({self.accessed_at})"
