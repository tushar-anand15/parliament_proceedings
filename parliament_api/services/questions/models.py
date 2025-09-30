from django.db import models
from django.contrib.auth.models import User
import json


class ParliamentInstitution(models.Model):
    """Model to store Parliament institution information (Lok Sabha, Rajya Sabha)"""
    
    INSTITUTION_TYPES = [
        ('lok_sabha', 'Lok Sabha'),
        ('rajya_sabha', 'Rajya Sabha'),
    ]
    
    name = models.CharField(max_length=50, choices=INSTITUTION_TYPES, unique=True)
    full_name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['name']
    
    def __str__(self):
        return self.full_name


class LokSabha(models.Model):
    """Model to store Lok Sabha information"""
    number = models.CharField(max_length=10, unique=True)  # "15", "16", "17"
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    is_current = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-number']
        verbose_name = "Lok Sabha"
        verbose_name_plural = "Lok Sabhas"

    def __str__(self):
        return f"{self.number}th Lok Sabha"


class Session(models.Model):
    """Model to store session information"""
    lok_sabha = models.ForeignKey(LokSabha, on_delete=models.CASCADE, related_name='sessions')
    session_number = models.CharField(max_length=10)
    session_period = models.JSONField(default=list, blank=True)  # Array of period strings
    dates = models.JSONField(default=list, blank=True)  # Array of session dates
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    is_current = models.BooleanField(default=False)
    raw_api_data = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['lok_sabha', 'session_number']
        ordering = ['-lok_sabha__number', '-session_number']

    def __str__(self):
        return f"{self.lok_sabha.number}th LS - Session {self.session_number}"


class Ministry(models.Model):
    """Model to store ministry information"""
    name = models.CharField(max_length=200, unique=True)
    full_name = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name_plural = "Ministries"

    def __str__(self):
        return self.name


class Member(models.Model):
    """Model to store MP information"""
    name = models.CharField(max_length=200)
    constituency = models.CharField(max_length=200, blank=True)
    party = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=100, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class QuestionMasterData(models.Model):
    """Model to store master questions metadata from sansad.in API"""
    
    QUESTION_TYPES = [
        ('STARRED', 'Starred Question'),
        ('UNSTARRED', 'Unstarred Question'),
        ('SHORT_NOTICE', 'Short Notice Question'),
    ]
    
    # Institution and Session Information
    parent_institution = models.ForeignKey(ParliamentInstitution, on_delete=models.CASCADE, related_name='question_master_data', null=True, blank=True)  # Will be populated after creation
    lok_sabha_number = models.CharField(max_length=10)  # lokNo - for Lok Sabha questions
    rajya_sabha_number = models.CharField(max_length=10, blank=True)  # For Rajya Sabha questions (future)
    session_number = models.CharField(max_length=10)  # sessionNo
    
    # Basic Information from API
    question_number = models.CharField(max_length=50)  # quesNo
    subjects = models.TextField()  # subjects
    members = models.JSONField(default=list)  # member array
    ministry = models.CharField(max_length=200)  # ministry
    question_type = models.CharField(max_length=20, choices=QUESTION_TYPES)  # type
    date = models.DateField(null=True, blank=True)  # date
    
    # PDF URLs
    questions_file_path = models.URLField(blank=True)  # questionsFilePath
    questions_file_path_hindi = models.URLField(blank=True)  # questionsFilePathHindi
    
    # Answer data (if available)
    question_text = models.TextField(blank=True, null=True)  # questionText
    answer_text = models.TextField(blank=True, null=True)  # answerText
    answer_text_hindi = models.TextField(blank=True, null=True)  # answerTextHindi
    
    # Supplementary questions
    supplementary_type = models.BooleanField(default=False)  # supplementaryType
    supplementary_questions = models.JSONField(default=list, blank=True)  # supplementaryQuestionResDtoList
    
    # Relationships to our internal models
    lok_sabha = models.ForeignKey(LokSabha, on_delete=models.CASCADE, related_name='master_questions', null=True, blank=True)
    session = models.ForeignKey(Session, on_delete=models.CASCADE, related_name='master_questions', null=True, blank=True)
    
    # Processing status
    is_processed = models.BooleanField(default=False)  # Whether we've created a Question from this
    processed_at = models.DateTimeField(null=True, blank=True)
    
    # Raw API data
    raw_api_data = models.JSONField(default=dict, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_fetched = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['parent_institution', 'question_number', 'lok_sabha_number', 'session_number', 'question_type']
        ordering = ['-date', '-question_number']
        indexes = [
            models.Index(fields=['parent_institution', 'lok_sabha_number', 'session_number']),
            models.Index(fields=['question_type']),
            models.Index(fields=['is_processed']),
            models.Index(fields=['date']),
        ]

    def __str__(self):
        return f"Q.{self.question_number} ({self.question_type}) - {self.subjects[:50]}"
    
    def get_pdf_url(self):
        """Get the primary PDF URL"""
        return self.questions_file_path or self.questions_file_path_hindi


class Question(models.Model):
    """Main model for parliamentary questions"""
    
    QUESTION_TYPES = [
        ('Starred', 'Starred Question'),
        ('Unstarred', 'Unstarred Question'),
        ('Short Notice', 'Short Notice Question'),
    ]
    
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('answered', 'Answered'),
        ('pending', 'Pending'),
        ('withdrawn', 'Withdrawn'),
    ]

    # Institution and Basic Information
    parent_institution = models.ForeignKey(ParliamentInstitution, on_delete=models.CASCADE, related_name='questions', null=True, blank=True)  # Will be populated after creation
    question_id = models.CharField(max_length=50, unique=True)  # Internal UUID
    api_resource_id = models.CharField(max_length=50, blank=True)  # API resourceId
    question_number = models.CharField(max_length=50)
    question_type = models.CharField(max_length=20, choices=QUESTION_TYPES)
    
    # Content
    title = models.TextField()
    subject = models.TextField(blank=True)
    question_text = models.TextField(blank=True, null=True)
    answer_text = models.TextField(blank=True, null=True)
    
    # API Metadata
    document_type = models.CharField(max_length=100, blank=True)  # e.g., "Part 1(Questions And Answers)"
    language = models.CharField(max_length=50, blank=True)  # e.g., "English", "Original"
    year = models.CharField(max_length=4, blank=True)
    document_handle = models.CharField(max_length=100, blank=True)  # e.g., "123456789/805951"
    pdf_files = models.JSONField(default=list, blank=True)  # Array of PDF URLs
    minister_names = models.JSONField(default=list, blank=True)  # Array of minister names
    
    # Additional metadata fields
    council_of_state_no = models.CharField(max_length=50, blank=True)
    committee_name = models.CharField(max_length=200, blank=True)
    assembly_no = models.CharField(max_length=50, blank=True)
    debate = models.CharField(max_length=200, blank=True)
    report_no = models.CharField(max_length=50, blank=True)
    youtube_url = models.URLField(blank=True)
    source = models.CharField(max_length=100, blank=True)
    
    # Timestamps
    date = models.DateField(null=True, blank=True)
    asked_date = models.DateField(null=True, blank=True)
    answered_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    
    # Relationships
    lok_sabha = models.ForeignKey(LokSabha, on_delete=models.CASCADE, related_name='questions')
    session = models.ForeignKey(Session, on_delete=models.CASCADE, related_name='questions', null=True, blank=True)
    members = models.ManyToManyField(Member, related_name='questions', blank=True)
    ministries = models.ManyToManyField(Ministry, related_name='questions', blank=True)
    
    # Link to master data
    master_data = models.OneToOneField(QuestionMasterData, on_delete=models.SET_NULL, null=True, blank=True, related_name='question')
    
    # Raw API data
    raw_api_data = models.JSONField(default=dict, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_scraped = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-date', '-question_number']
        indexes = [
            models.Index(fields=['question_id']),
            models.Index(fields=['lok_sabha', 'date']),
            models.Index(fields=['question_type']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f"Q.{self.question_number} ({self.question_type}) - {self.title[:50]}"

    def get_api_link(self):
        """Generate API link for the question"""
        if self.question_id:
            return f"https://sansad.in/getFile?source=questions&type=questions&id={self.question_id}"
        return None

    def get_members_list(self):
        """Get list of member names"""
        return list(self.members.values_list('name', flat=True))

    def get_ministries_list(self):
        """Get list of ministry names"""
        return list(self.ministries.values_list('name', flat=True))

    @property
    def has_answer(self):
        return bool(self.answer_text)

    @property
    def days_since_asked(self):
        if self.asked_date:
            from django.utils import timezone
            return (timezone.now().date() - self.asked_date).days
        return None


class QuestionFollowUp(models.Model):
    """Model for follow-up questions"""
    original_question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='follow_ups')
    follow_up_question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='original_questions')
    relationship_type = models.CharField(max_length=50, default='follow_up')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['original_question', 'follow_up_question']

    def __str__(self):
        return f"Follow-up: {self.follow_up_question.question_number} -> {self.original_question.question_number}"


class QuestionTag(models.Model):
    """Model for question tags/topics"""
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    color = models.CharField(max_length=7, default='#007bff')  # Hex color
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class QuestionTagging(models.Model):
    """Many-to-many relationship between questions and tags"""
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    tag = models.ForeignKey(QuestionTag, on_delete=models.CASCADE)
    confidence = models.FloatField(default=1.0)  # AI confidence if auto-tagged
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['question', 'tag']

    def __str__(self):
        return f"{self.question.question_number} - {self.tag.name}"
