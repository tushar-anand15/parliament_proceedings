from django.db import models
from django.contrib.auth.models import User
from services.questions.models import LokSabha, Session
from services.files.models import DocumentFile
import json


class Debate(models.Model):
    """Model to store parliamentary debate information"""
    
    DEBATE_TYPES = [
        ('text_of_debate', 'Text of Debate'),
        ('synopsis', 'Synopsis of Debate'),
        ('uncorrected', 'Uncorrected Debate'),
        ('corrected', 'Corrected Debate'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Pending Download'),
        ('downloading', 'Downloading'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('not_available', 'Not Available'),
    ]
    
    # Identification
    debate_id = models.CharField(max_length=50, unique=True)  # Internal UUID
    
    # Session Information
    lok_sabha = models.ForeignKey(LokSabha, on_delete=models.CASCADE, related_name='debates')
    session = models.ForeignKey(Session, on_delete=models.CASCADE, related_name='debates')
    
    # Debate Information
    debate_date = models.DateField()
    debate_type = models.CharField(max_length=20, choices=DEBATE_TYPES, default='text_of_debate')
    language = models.CharField(max_length=50, default='en')
    
    # PDF Information
    pdf_url = models.URLField(max_length=500, blank=True)
    pdf_file = models.ForeignKey(DocumentFile, on_delete=models.SET_NULL, null=True, blank=True, related_name='debate')
    
    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    download_attempts = models.IntegerField(default=0)
    last_download_attempt = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True)
    
    # Metadata
    page_count = models.IntegerField(null=True, blank=True)
    file_size = models.BigIntegerField(null=True, blank=True)  # Size in bytes
    
    # API Response Data
    raw_api_data = models.JSONField(default=dict, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_scraped = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        unique_together = ['lok_sabha', 'session', 'debate_date', 'debate_type', 'language']
        ordering = ['-debate_date']
        indexes = [
            models.Index(fields=['lok_sabha', 'session', 'debate_date']),
            models.Index(fields=['status']),
            models.Index(fields=['debate_date']),
        ]
    
    def __str__(self):
        return f"{self.lok_sabha.number}th LS - Session {self.session.session_number} - {self.debate_date}"
    
    @property
    def is_downloaded(self):
        return self.status == 'completed' and self.pdf_file
    
    @property
    def file_size_mb(self):
        if self.file_size:
            return round(self.file_size / (1024 * 1024), 2)
        return None
    
    def get_pdf_filename(self):
        """Generate consistent filename for PDF"""
        date_str = self.debate_date.strftime('%Y%m%d')
        return f"debate_{self.lok_sabha.number}_{self.session.session_number}_{date_str}_{self.language}.pdf"


class DebateSpeech(models.Model):
    """Model to store individual speeches within a debate (future enhancement)"""
    
    debate = models.ForeignKey(Debate, on_delete=models.CASCADE, related_name='speeches')
    speaker_name = models.CharField(max_length=200)
    speaker_designation = models.CharField(max_length=200, blank=True)
    speech_text = models.TextField()
    speech_order = models.IntegerField()
    start_page = models.IntegerField(null=True, blank=True)
    end_page = models.IntegerField(null=True, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['debate', 'speech_order']
        indexes = [
            models.Index(fields=['debate', 'speech_order']),
            models.Index(fields=['speaker_name']),
        ]
    
    def __str__(self):
        return f"{self.speaker_name} - {self.debate.debate_date}"


class DebateTag(models.Model):
    """Model for debate tags/topics"""
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['name']
    
    def __str__(self):
        return self.name


class DebateTagging(models.Model):
    """Many-to-many relationship between debates and tags"""
    debate = models.ForeignKey(Debate, on_delete=models.CASCADE)
    tag = models.ForeignKey(DebateTag, on_delete=models.CASCADE)
    confidence = models.FloatField(default=1.0)  # AI confidence if auto-tagged
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ['debate', 'tag']
    
    def __str__(self):
        return f"{self.debate} - {self.tag.name}"


class SessionDateCache(models.Model):
    """Cache for available session dates from the API"""
    lok_sabha = models.ForeignKey(LokSabha, on_delete=models.CASCADE, related_name='date_cache')
    session = models.ForeignKey(Session, on_delete=models.CASCADE, related_name='date_cache')
    
    # Cache data
    available_dates = models.JSONField(default=list)  # List of date strings
    session_period = models.JSONField(default=list, blank=True)  # Session period info
    api_source = models.CharField(max_length=100, default='sansad.in', help_text='API source used to fetch this data')
    
    # Cache management
    last_updated = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ['lok_sabha', 'session']
        indexes = [
            models.Index(fields=['lok_sabha', 'session']),
            models.Index(fields=['last_updated']),
        ]
    
    def __str__(self):
        return f"Date cache for {self.lok_sabha.number}th LS Session {self.session.session_number}"
    
    @property
    def is_stale(self):
        """Check if cache is older than 10 days"""
        from django.utils import timezone
        from datetime import timedelta
        return self.last_updated < timezone.now() - timedelta(days=10)
    
    @property
    def date_count(self):
        """Number of cached dates"""
        return len(self.available_dates)
