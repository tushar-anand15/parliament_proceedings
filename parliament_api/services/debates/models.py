from django.db import models
from django.contrib.auth.models import User
from services.questions.models import LokSabha, Session, ParliamentInstitution
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
    
    DEBATE_CATEGORIES = [
        ('uncorrected', 'Uncorrected Proceedings'),
        ('corrected', 'Corrected Proceedings'),
        ('synopsis', 'Synopsis'),
        ('text_of_debate', 'Text of Debate'),
        ('verbatim', 'Verbatim Debates (RS)'),
        ('official_qa', 'Official Q&A (RS)'),
        ('official_other', 'Official Other (RS)'),
        ('official', 'Official Debates (RS)'),
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
    
    # Institution and Session Information
    parent_institution = models.ForeignKey(ParliamentInstitution, on_delete=models.CASCADE, related_name='debates', null=True, blank=True)  # Will be populated after creation
    lok_sabha = models.ForeignKey(LokSabha, on_delete=models.CASCADE, related_name='debates')
    session = models.ForeignKey(Session, on_delete=models.CASCADE, related_name='debates')
    
    # Debate Information
    debate_date = models.DateField()
    debate_type = models.CharField(max_length=20, choices=DEBATE_TYPES, default='text_of_debate')
    debate_category = models.CharField(max_length=20, choices=DEBATE_CATEGORIES, default='uncorrected', help_text='Whether this is corrected or uncorrected proceedings')
    language = models.CharField(max_length=50, default='en')
    time_slot = models.CharField(max_length=100, blank=True, null=True, help_text='Time slot for RS verbatim debates (e.g., "11:00-12:00 Noon") or Question number for RS official debates')
    
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
    
    # Metadata hash for duplicate detection
    metadata_hash = models.CharField(max_length=64, blank=True, default='', db_index=True, help_text='Hash of metadata for duplicate detection')
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_scraped = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        unique_together = ['parent_institution', 'debate_date', 'debate_category', 'language', 'time_slot']
        ordering = ['-debate_date']
        indexes = [
            models.Index(fields=['parent_institution', 'debate_date']),
            models.Index(fields=['status']),
            models.Index(fields=['debate_date']),
            models.Index(fields=['debate_category']),
            models.Index(fields=['time_slot']),
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


class DebateMasterData(models.Model):
    """Master data for parliamentary debates - stores comprehensive session metadata"""
    
    # Institution and Session identification
    parent_institution = models.ForeignKey(ParliamentInstitution, on_delete=models.CASCADE, related_name='debate_master_data', null=True, blank=True)  # Will be populated after creation
    lok_sabha_number = models.CharField(max_length=10)
    rajya_sabha_number = models.CharField(max_length=10, blank=True)  # For Rajya Sabha debates (future)
    session_number = models.CharField(max_length=10)
    
    # Foreign key relationships
    lok_sabha = models.ForeignKey(LokSabha, on_delete=models.CASCADE, related_name='debate_master_data')
    session = models.ForeignKey(Session, on_delete=models.CASCADE, related_name='debate_master_data')
    
    # Session metadata
    available_dates = models.JSONField(default=list, help_text='List of all available debate dates for this session')
    session_period = models.JSONField(default=list, blank=True, help_text='Session period information from API')
    date_range_start = models.DateField(null=True, blank=True, help_text='First available debate date')
    date_range_end = models.DateField(null=True, blank=True, help_text='Last available debate date')
    
    # Statistics
    total_debate_days = models.IntegerField(default=0, help_text='Total number of days with debates')
    debates_discovered = models.IntegerField(default=0, help_text='Number of debates discovered for this session')
    debates_downloaded = models.IntegerField(default=0, help_text='Number of debates successfully downloaded')
    
    # API source information
    api_source = models.CharField(max_length=100, default='sansad.in', help_text='Primary API source used to fetch this data')
    fallback_api_sources = models.JSONField(default=list, help_text='List of fallback API sources used')
    debate_category = models.CharField(max_length=50, default='corrected', help_text='Debate category: corrected, uncorrected, verbatim, official')
    
    # Data completeness
    is_complete = models.BooleanField(default=False, help_text='Whether all available debates for this session have been discovered')
    last_discovery_attempt = models.DateTimeField(null=True, blank=True, help_text='Last time we attempted to discover debates')
    discovery_success = models.BooleanField(default=False, help_text='Whether the last discovery attempt was successful')
    
    # Raw API data
    raw_api_data = models.JSONField(default=dict, blank=True, help_text='Raw response from the API')
    
    # Metadata hash for duplicate detection
    metadata_hash = models.CharField(max_length=64, blank=True, default='', db_index=True, help_text='Hash of metadata for duplicate detection')
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_fetched = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['parent_institution', 'lok_sabha_number', 'session_number', 'debate_category']
        ordering = ['-lok_sabha_number', '-session_number']
        indexes = [
            models.Index(fields=['parent_institution', 'lok_sabha_number', 'session_number']),
            models.Index(fields=['lok_sabha', 'session']),
            models.Index(fields=['is_complete']),
            models.Index(fields=['last_fetched']),
        ]
    
    def __str__(self):
        return f"Debate Master Data: LS{self.lok_sabha_number} Session {self.session_number}"
    
    @property
    def is_stale(self):
        """Check if master data is older than 7 days"""
        from django.utils import timezone
        from datetime import timedelta
        return self.last_fetched < timezone.now() - timedelta(days=7)
    
    @property
    def date_count(self):
        """Number of available dates"""
        return len(self.available_dates)
    
    @property
    def completion_percentage(self):
        """Percentage of debates downloaded vs discovered"""
        if self.debates_discovered == 0:
            return 0
        return round((self.debates_downloaded / self.debates_discovered) * 100, 2)
    
    def get_dates_for_period(self, start_date=None, end_date=None):
        """Get filtered dates for a specific period"""
        from datetime import datetime
        
        filtered_dates = []
        for date_str in self.available_dates:
            try:
                # Parse DD/MM/YYYY format
                date_obj = datetime.strptime(date_str, '%d/%m/%Y').date()
                
                # Apply filters
                if start_date and date_obj < start_date:
                    continue
                if end_date and date_obj > end_date:
                    continue
                    
                filtered_dates.append(date_str)
            except ValueError:
                continue
        
        return filtered_dates
    
    def update_statistics(self):
        """Update statistics based on current debate records"""
        debates_qs = Debate.objects.filter(
            lok_sabha__number=self.lok_sabha_number,
            session__session_number=self.session_number
        )
        
        self.debates_discovered = debates_qs.count()
        self.debates_downloaded = debates_qs.filter(status='completed').count()
        self.save()


class SessionDateCache(models.Model):
    """Cache for available session dates from the API (legacy - kept for backward compatibility)"""
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
