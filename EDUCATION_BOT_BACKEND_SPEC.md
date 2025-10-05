# Education-Bot Backend Specification
## Production-Grade Django Backend Architecture

**Based on**: Parliament API proven patterns and infrastructure  
**Date**: October 4, 2025  
**Version**: 1.0

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Technology Stack](#technology-stack)
3. [Project Structure](#project-structure)
4. [Database Architecture](#database-architecture)
5. [Service Layer Organization](#service-layer-organization)
6. [API Design](#api-design)
7. [Cloud Storage & File Management](#cloud-storage--file-management)
8. [AI/LLM Integration](#aillm-integration)
9. [Task Queue & Background Jobs](#task-queue--background-jobs)
10. [Authentication & Authorization](#authentication--authorization)
11. [Environment Configuration](#environment-configuration)
12. [Deployment & Startup](#deployment--startup)
13. [Management Commands](#management-commands)
14. [Testing Strategy](#testing-strategy)
15. [Phase 1 Implementation Plan](#phase-1-implementation-plan)

---

## Executive Summary

The Education-Bot backend will be built using the **exact same architectural patterns** as the parliament_api, providing a production-ready foundation for:

- **Course Builder Flow** (Admin/Educator): Create courses, upload syllabus materials, generate AI-powered slides
- **Course Player Flow** (Student): Watch lectures, interact with content, track progress (Phase 2+)

### Key Design Principles (Inherited from Parliament API)

✅ **Service-Oriented Architecture**: Each domain (courses, lectures, slides, AI) is a separate Django app  
✅ **Cloud-Native Storage**: GCS for all uploaded files (syllabus PDFs, generated slides, audio)  
✅ **Async Task Processing**: Celery + Redis for long-running operations (slide generation, TTS)  
✅ **Production-Ready Infrastructure**: PostgreSQL, comprehensive logging, error handling  
✅ **API-First Design**: DRF with drf-spectacular for auto-generated OpenAPI docs  
✅ **Scalable File Management**: Upload → GCS → Presigned URLs pattern  

---

## Technology Stack

### Core Framework
```
Django 5.2.3
djangorestframework 3.15.2
drf-spectacular 0.28.0 (OpenAPI/Swagger docs)
```

### Database & Caching
```
PostgreSQL (via psycopg[binary] 3.2.3)
Redis 5.2.1
```

### Task Queue
```
Celery 5.4.0
Flower 2.0.1 (monitoring UI)
```

### Cloud Storage
```
google-cloud-storage 2.10.0
google-auth 2.23.4
```

### AI/LLM Integration (NEW)
```
openai 1.54.0  # GPT-4 for slide generation
pinecone-client 5.0.0  # Vector DB for RAG
tiktoken 0.8.0  # Token counting
langchain 0.3.0  # Optional: For advanced RAG pipelines
PyPDF2 3.0.1  # PDF text extraction for syllabus
```

### Production Server
```
gunicorn 23.0.0
```

### Additional Dependencies
```
python-dotenv 1.0.0
requests 2.32.3
python-dateutil 2.9.0.post0
Pillow 11.0.0
django-cors-headers 4.6.0
djangorestframework-simplejwt 5.3.0 (if using JWT instead of Token auth)
```

---

## Project Structure

```
education_bot/                          # Project root
├── env/                                # Virtual environment
├── education_api/                      # Main Django project
│   ├── manage.py
│   ├── .env                           # Environment variables
│   ├── requirements.txt
│   ├── education-bot-gcs-key.json    # GCS service account key
│   │
│   ├── education_api/                 # Django settings module
│   │   ├── __init__.py
│   │   ├── settings.py               # Main settings (mirrors parliament_api pattern)
│   │   ├── celery.py                 # Celery app configuration
│   │   ├── urls.py                   # Root URL configuration
│   │   ├── wsgi.py
│   │   └── asgi.py
│   │
│   ├── services/                      # Service layer (Django apps)
│   │   ├── __init__.py
│   │   │
│   │   ├── user_auth/                # User authentication & profiles
│   │   │   ├── models.py             # UserProfile, APIKey, UserSession
│   │   │   ├── views.py
│   │   │   ├── urls.py
│   │   │   ├── admin.py
│   │   │   └── management/commands/
│   │   │       └── setup_admin.py
│   │   │
│   │   ├── cloud_storage/            # GCS integration (reuse exact code)
│   │   │   ├── gcs_service.py        # GCSService class
│   │   │   └── apps.py
│   │   │
│   │   ├── courses/                  # Course management
│   │   │   ├── models.py             # Course, Week, LearningObjective
│   │   │   ├── views.py              # Course CRUD APIs
│   │   │   ├── urls.py
│   │   │   ├── course_service.py     # Business logic
│   │   │   ├── tasks.py              # Celery tasks
│   │   │   ├── admin.py
│   │   │   └── management/commands/
│   │   │       └── initialize_sample_courses.py
│   │   │
│   │   ├── lectures/                 # Lecture management
│   │   │   ├── models.py             # Lecture, Slide
│   │   │   ├── views.py              # Lecture CRUD, slide generation APIs
│   │   │   ├── urls.py
│   │   │   ├── lecture_service.py
│   │   │   ├── tasks.py
│   │   │   └── admin.py
│   │   │
│   │   ├── ai_service/               # LLM & RAG integration
│   │   │   ├── models.py             # AITaskLog, GenerationHistory
│   │   │   ├── views.py              # AI generation status endpoints
│   │   │   ├── urls.py
│   │   │   ├── slide_generator_service.py  # Core slide generation
│   │   │   ├── rag_service.py        # Syllabus RAG pipeline
│   │   │   ├── llm_client.py         # OpenAI API wrapper
│   │   │   ├── prompts.py            # LLM prompt templates
│   │   │   ├── tasks.py              # Async AI generation tasks
│   │   │   └── admin.py
│   │   │
│   │   ├── files/                    # File uploads & management
│   │   │   ├── models.py             # SyllabusFile, DocumentFile
│   │   │   ├── views.py              # File upload/download APIs
│   │   │   ├── urls.py
│   │   │   ├── file_upload_service.py
│   │   │   ├── tasks.py              # Async file processing
│   │   │   └── admin.py
│   │   │
│   │   └── students/                 # Student domain (Phase 2)
│   │       ├── models.py             # StudentProfile, Enrollment, Progress
│   │       ├── views.py
│   │       ├── urls.py
│   │       └── admin.py
│   │
│   ├── media/                        # Local file storage (temp)
│   │   ├── syllabus/
│   │   ├── slides/
│   │   └── audio/
│   │
│   └── logs/                         # Application logs
│       ├── education.log
│       ├── celery.log
│       └── ai_service.log
│
├── startup.sh                        # Production startup script (adapted from parliament_api)
├── .env.example
└── README.md
```

---

## Database Architecture

### Core Models (Phase 1)

#### 1. User Authentication (`services/user_auth/models.py`)

```python
# Reuse exact UserProfile, APIKey models from parliament_api

class UserProfile(models.Model):
    """Extended user profile for educators and admins"""
    
    USER_TYPES = [
        ('admin', 'Administrator'),
        ('educator', 'Educator/Teacher'),
        ('student', 'Student'),  # Phase 2
    ]
    
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    user_type = models.CharField(max_length=20, choices=USER_TYPES, default='educator')
    organization = models.CharField(max_length=200, blank=True)
    
    # API usage tracking
    api_calls_today = models.IntegerField(default=0)
    daily_api_limit = models.IntegerField(default=1000)
    
    # Feature access (for different tiers)
    max_courses = models.IntegerField(default=10)
    max_ai_generations_per_month = models.IntegerField(default=100)
    
    # Metadata
    is_verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.user.username} ({self.user_type})"
```

#### 2. Course Management (`services/courses/models.py`)

```python
class Course(models.Model):
    """Top-level course entity"""
    
    GRADE_LEVELS = [
        ('elementary', 'Elementary School'),
        ('middle', 'Middle School'),
        ('high', 'High School'),
        ('undergraduate', 'Undergraduate'),
        ('graduate', 'Graduate'),
        ('professional', 'Professional Development'),
    ]
    
    SUBJECTS = [
        ('mathematics', 'Mathematics'),
        ('science', 'Science'),
        ('history', 'History'),
        ('english', 'English/Literature'),
        ('computer_science', 'Computer Science'),
        ('other', 'Other'),
    ]
    
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('published', 'Published'),
        ('archived', 'Archived'),
    ]
    
    # Basic Information
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=200)
    description = models.TextField()
    subject = models.CharField(max_length=50, choices=SUBJECTS)
    grade_level = models.CharField(max_length=50, choices=GRADE_LEVELS)
    
    # Course Structure
    total_weeks = models.IntegerField(default=12, help_text='Total number of weeks in course')
    lectures_per_week = models.IntegerField(default=3, help_text='Target lectures per week')
    
    # Ownership & Status
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='courses')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    
    # Syllabus files (JSON array of file references)
    syllabus_files = models.JSONField(default=list, blank=True, help_text='Array of syllabus file IDs')
    
    # Metadata
    thumbnail_url = models.URLField(blank=True)
    tags = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    published_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['created_by', 'status']),
            models.Index(fields=['subject', 'grade_level']),
            models.Index(fields=['status', '-created_at']),
        ]
    
    def __str__(self):
        return f"{self.title} ({self.grade_level})"
    
    @property
    def is_published(self):
        return self.status == 'published'
    
    @property
    def total_lectures(self):
        return self.total_weeks * self.lectures_per_week
    
    def get_progress(self):
        """Calculate course completion progress"""
        total_lectures = self.lectures.count()
        completed_lectures = self.lectures.filter(status='published').count()
        return (completed_lectures / max(total_lectures, 1)) * 100


class Week(models.Model):
    """Course week/module"""
    
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='weeks')
    week_number = models.IntegerField()
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    
    # Learning objectives
    learning_objectives = models.JSONField(default=list, blank=True)
    
    # Order & visibility
    order = models.IntegerField(default=0)
    is_visible = models.BooleanField(default=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['course', 'week_number']
        ordering = ['course', 'week_number']
        indexes = [
            models.Index(fields=['course', 'week_number']),
        ]
    
    def __str__(self):
        return f"{self.course.title} - Week {self.week_number}: {self.title}"
```

#### 3. Lecture & Slides (`services/lectures/models.py`)

```python
class Lecture(models.Model):
    """Individual lecture within a week"""
    
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('generating', 'Generating Slides'),
        ('ready', 'Ready for Review'),
        ('published', 'Published'),
        ('failed', 'Generation Failed'),
    ]
    
    # Relationships
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    week = models.ForeignKey(Week, on_delete=models.CASCADE, related_name='lectures')
    
    # Basic Information
    lecture_number = models.IntegerField(help_text='Lecture number within the week')
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    
    # Input: Educator-provided content
    lecture_notes = models.TextField(help_text='Educator-provided lecture notes (markdown supported)')
    target_duration_minutes = models.IntegerField(default=30, help_text='Target lecture duration')
    target_slide_count = models.IntegerField(default=13, help_text='Target number of slides')
    
    # Generation Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    generation_task_id = models.CharField(max_length=100, blank=True, help_text='Celery task ID for async generation')
    
    # Generation Metadata
    generated_at = models.DateTimeField(null=True, blank=True)
    generation_error = models.TextField(blank=True)
    generation_metadata = models.JSONField(default=dict, blank=True, help_text='LLM model, prompt version, tokens used')
    
    # Order & visibility
    order = models.IntegerField(default=0)
    is_visible = models.BooleanField(default=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    published_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        unique_together = ['week', 'lecture_number']
        ordering = ['week', 'lecture_number']
        indexes = [
            models.Index(fields=['week', 'lecture_number']),
            models.Index(fields=['status']),
            models.Index(fields=['generation_task_id']),
        ]
    
    def __str__(self):
        return f"{self.week.course.title} - {self.week.week_number}.{self.lecture_number}: {self.title}"
    
    @property
    def full_lecture_number(self):
        return f"{self.week.week_number}.{self.lecture_number}"
    
    @property
    def is_generated(self):
        return self.status in ['ready', 'published']


class Slide(models.Model):
    """Individual slide within a lecture"""
    
    SLIDE_TYPES = [
        ('title', 'Title Slide'),
        ('objectives', 'Learning Objectives'),
        ('content', 'Content Slide'),
        ('example', 'Example/Case Study'),
        ('summary', 'Summary'),
        ('next', 'Next Lecture Preview'),
    ]
    
    # Relationships
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    lecture = models.ForeignKey(Lecture, on_delete=models.CASCADE, related_name='slides')
    
    # Slide Information
    slide_number = models.IntegerField(help_text='Order within lecture (1-based)')
    slide_type = models.CharField(max_length=20, choices=SLIDE_TYPES, default='content')
    
    # Content
    title = models.CharField(max_length=200)
    content = models.TextField(help_text='Bullet points or main content (markdown supported)')
    notes = models.TextField(blank=True, help_text='Speaker notes / additional context')
    
    # Narration (for TTS - Phase 2)
    narration_script = models.TextField(help_text='15-20 second voice narration script')
    narration_audio_url = models.URLField(blank=True, help_text='GCS URL for generated audio (Phase 2)')
    narration_duration_ms = models.IntegerField(null=True, blank=True, help_text='Audio duration in milliseconds')
    
    # Visual elements
    visual_hint = models.TextField(blank=True, help_text='Suggestion for diagram/image')
    image_url = models.URLField(blank=True, help_text='Optional image URL')
    background_color = models.CharField(max_length=7, default='#FFFFFF')
    
    # Generation metadata
    generation_metadata = models.JSONField(default=dict, blank=True, help_text='LLM metadata for this slide')
    
    # Order & visibility
    order = models.IntegerField(default=0)
    is_visible = models.BooleanField(default=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['lecture', 'slide_number']
        ordering = ['lecture', 'slide_number']
        indexes = [
            models.Index(fields=['lecture', 'slide_number']),
        ]
    
    def __str__(self):
        return f"{self.lecture.title} - Slide {self.slide_number}: {self.title}"
```

#### 4. Files & Storage (`services/files/models.py`)

```python
# Adapt DocumentFile model from parliament_api

class SyllabusFile(models.Model):
    """Syllabus PDF/document uploaded by educator"""
    
    STATUS_CHOICES = [
        ('uploading', 'Uploading'),
        ('processing', 'Processing/Extracting Text'),
        ('completed', 'Ready'),
        ('failed', 'Processing Failed'),
    ]
    
    # Relationships
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    course = models.ForeignKey('courses.Course', on_delete=models.CASCADE, related_name='syllabus_files')
    uploaded_by = models.ForeignKey(User, on_delete=models.CASCADE)
    
    # File Information
    file_name = models.CharField(max_length=255)
    file_size = models.BigIntegerField(help_text='File size in bytes')
    content_type = models.CharField(max_length=100, default='application/pdf')
    
    # GCS Storage
    gcs_bucket_name = models.CharField(max_length=100)
    gcs_object_key = models.CharField(max_length=500)
    gcs_url = models.URLField(max_length=500)
    gcs_uploaded_at = models.DateTimeField(auto_now_add=True)
    
    # Text Extraction (for RAG)
    extracted_text = models.TextField(blank=True, help_text='Extracted text content for RAG')
    extraction_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='uploading')
    extraction_error = models.TextField(blank=True)
    
    # Vector DB Indexing
    vector_indexed = models.BooleanField(default=False)
    vector_index_id = models.CharField(max_length=100, blank=True, help_text='Pinecone namespace/ID')
    chunk_count = models.IntegerField(default=0, help_text='Number of text chunks created')
    
    # Metadata
    page_count = models.IntegerField(null=True, blank=True)
    title = models.CharField(max_length=200, blank=True)
    description = models.TextField(blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['course', 'extraction_status']),
            models.Index(fields=['vector_indexed']),
        ]
    
    def __str__(self):
        return f"{self.course.title} - {self.file_name}"
    
    @property
    def is_ready_for_rag(self):
        return self.extraction_status == 'completed' and self.vector_indexed
    
    def get_presigned_url(self, expiration_minutes=60):
        """Get presigned URL for file download"""
        from services.cloud_storage.gcs_service import GCSService
        gcs_service = GCSService()
        return gcs_service.generate_presigned_url(
            self.gcs_bucket_name,
            self.gcs_object_key,
            expiration_minutes
        )
```

#### 5. AI Service (`services/ai_service/models.py`)

```python
class AITaskLog(models.Model):
    """Track all AI generation tasks for monitoring and cost tracking"""
    
    TASK_TYPES = [
        ('slide_generation', 'Slide Generation'),
        ('slide_regeneration', 'Single Slide Regeneration'),
        ('syllabus_processing', 'Syllabus Text Extraction'),
        ('vector_indexing', 'Vector DB Indexing'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('running', 'Running'),
        ('success', 'Success'),
        ('failed', 'Failed'),
    ]
    
    # Task Information
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    task_type = models.CharField(max_length=50, choices=TASK_TYPES)
    celery_task_id = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    
    # Related Entities
    lecture = models.ForeignKey('lectures.Lecture', on_delete=models.CASCADE, null=True, blank=True, related_name='ai_tasks')
    course = models.ForeignKey('courses.Course', on_delete=models.CASCADE, null=True, blank=True, related_name='ai_tasks')
    initiated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    
    # LLM Usage Tracking
    model_name = models.CharField(max_length=50, default='gpt-4-turbo')
    prompt_tokens = models.IntegerField(default=0)
    completion_tokens = models.IntegerField(default=0)
    total_tokens = models.IntegerField(default=0)
    estimated_cost_usd = models.DecimalField(max_digits=10, decimal_places=4, default=0)
    
    # Performance Metrics
    duration_seconds = models.FloatField(null=True, blank=True)
    
    # Error Handling
    error_message = models.TextField(blank=True)
    error_traceback = models.TextField(blank=True)
    retry_count = models.IntegerField(default=0)
    
    # Timestamps
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-started_at']
        indexes = [
            models.Index(fields=['status', '-started_at']),
            models.Index(fields=['lecture']),
            models.Index(fields=['celery_task_id']),
        ]
    
    def __str__(self):
        return f"{self.task_type} - {self.status} ({self.started_at})"


class GenerationHistory(models.Model):
    """Track history of slide generations for a lecture (for comparison/rollback)"""
    
    lecture = models.ForeignKey('lectures.Lecture', on_delete=models.CASCADE, related_name='generation_history')
    version = models.IntegerField(help_text='Version number (incremental)')
    
    # Generation inputs
    lecture_notes_snapshot = models.TextField(help_text='Lecture notes at time of generation')
    target_slide_count = models.IntegerField()
    
    # Generated output (JSON snapshot)
    slides_json = models.JSONField(help_text='Full JSON of generated slides')
    
    # Metadata
    model_name = models.CharField(max_length=50)
    prompt_version = models.CharField(max_length=20)
    total_tokens = models.IntegerField()
    
    # Timestamps
    generated_at = models.DateTimeField(auto_now_add=True)
    generated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    
    class Meta:
        unique_together = ['lecture', 'version']
        ordering = ['lecture', '-version']
    
    def __str__(self):
        return f"{self.lecture.title} - v{self.version}"
```

---

## Service Layer Organization

Each domain is a separate Django app following the parliament_api pattern:

### 1. **User Authentication Service** (`services/user_auth/`)

**Purpose**: User registration, login, profile management, API key generation

**Key Components**:
- `models.py`: UserProfile, APIKey, UserSession
- `views.py`: RegisterView, LoginView, LogoutView, ProfileView
- `urls.py`: `/api/auth/` endpoints

**Reuse**: Copy entire structure from parliament_api

---

### 2. **Cloud Storage Service** (`services/cloud_storage/`)

**Purpose**: GCS integration for all file uploads

**Key Components**:
- `gcs_service.py`: **EXACT copy from parliament_api**

**GCS Buckets**:
- `education-bot-syllabus-prod`: Syllabus PDFs
- `education-bot-slides-prod`: Generated slide assets (images, audio)
- `education-bot-media-prod`: User-uploaded media

**Configuration** (`.env`):
```bash
GCS_PROJECT_ID=education-bot-project
GCS_CREDENTIALS_PATH=/path/to/education-bot-gcs-key.json
GCS_SYLLABUS_BUCKET=education-bot-syllabus-prod
GCS_SLIDES_BUCKET=education-bot-slides-prod
GCS_PRESIGNED_URL_EXPIRATION=3600
GCS_AUTO_DELETE_LOCAL=true
GCS_REGION=asia-south1
```

---

### 3. **Course Service** (`services/courses/`)

**Purpose**: Course creation, week management, metadata

**Key Files**:

**`course_service.py`**:
```python
class CourseService:
    """Business logic for course management"""
    
    def __init__(self):
        self.gcs_service = GCSService()
        self.logger = logging.getLogger(__name__)
    
    def create_course(self, user, course_data):
        """Create new course with default week structure"""
        course = Course.objects.create(
            created_by=user,
            title=course_data['title'],
            description=course_data['description'],
            subject=course_data['subject'],
            grade_level=course_data['grade_level'],
            total_weeks=course_data.get('total_weeks', 12),
            lectures_per_week=course_data.get('lectures_per_week', 3)
        )
        
        # Auto-create weeks
        for week_num in range(1, course.total_weeks + 1):
            Week.objects.create(
                course=course,
                week_number=week_num,
                title=f"Week {week_num}",
                description=""
            )
        
        return course
    
    def get_course_statistics(self, course_id):
        """Get comprehensive course stats"""
        course = Course.objects.get(id=course_id)
        
        total_lectures = Lecture.objects.filter(week__course=course).count()
        published_lectures = Lecture.objects.filter(
            week__course=course,
            status='published'
        ).count()
        total_slides = Slide.objects.filter(lecture__week__course=course).count()
        
        return {
            'course_id': str(course.id),
            'title': course.title,
            'total_weeks': course.total_weeks,
            'total_lectures': total_lectures,
            'published_lectures': published_lectures,
            'total_slides': total_slides,
            'completion_percent': (published_lectures / max(total_lectures, 1)) * 100,
            'status': course.status
        }
```

**`views.py`** (APIView pattern from parliament_api):
```python
class CourseListCreateView(APIView):
    """List all courses or create new course"""
    permission_classes = [IsAuthenticated]
    
    @extend_schema(
        description="List all courses for authenticated user",
        tags=['Courses']
    )
    def get(self, request):
        courses = Course.objects.filter(created_by=request.user)
        return Response({
            'courses': [
                {
                    'id': str(course.id),
                    'title': course.title,
                    'subject': course.subject,
                    'grade_level': course.grade_level,
                    'status': course.status,
                    'total_weeks': course.total_weeks,
                    'created_at': course.created_at.isoformat()
                }
                for course in courses
            ],
            'total': courses.count()
        })
    
    @extend_schema(
        description="Create new course",
        tags=['Courses']
    )
    def post(self, request):
        try:
            service = CourseService()
            course = service.create_course(request.user, request.data)
            
            return Response({
                'status': 'success',
                'course_id': str(course.id),
                'message': f'Course "{course.title}" created successfully'
            }, status=201)
        except Exception as e:
            return Response({
                'error': str(e)
            }, status=400)


class CourseDetailView(APIView):
    """Retrieve, update, or delete a course"""
    permission_classes = [IsAuthenticated]
    
    @extend_schema(
        description="Get course details with weeks and lectures",
        tags=['Courses']
    )
    def get(self, request, course_id):
        try:
            course = Course.objects.get(id=course_id, created_by=request.user)
            weeks = course.weeks.all().prefetch_related('lectures')
            
            return Response({
                'course': {
                    'id': str(course.id),
                    'title': course.title,
                    'description': course.description,
                    'subject': course.subject,
                    'grade_level': course.grade_level,
                    'total_weeks': course.total_weeks,
                    'lectures_per_week': course.lectures_per_week,
                    'status': course.status,
                    'weeks': [
                        {
                            'week_number': week.week_number,
                            'title': week.title,
                            'lectures': [
                                {
                                    'id': str(lecture.id),
                                    'lecture_number': lecture.lecture_number,
                                    'title': lecture.title,
                                    'status': lecture.status
                                }
                                for lecture in week.lectures.all()
                            ]
                        }
                        for week in weeks
                    ]
                }
            })
        except Course.DoesNotExist:
            return Response({'error': 'Course not found'}, status=404)
```

**`tasks.py`** (Celery tasks):
```python
@shared_task(bind=True, name='courses.publish_course')
def publish_course_task(self, course_id):
    """Publish course after validation"""
    try:
        course = Course.objects.get(id=course_id)
        
        # Validation checks
        total_lectures = Lecture.objects.filter(week__course=course).count()
        ready_lectures = Lecture.objects.filter(
            week__course=course,
            status='published'
        ).count()
        
        if ready_lectures < total_lectures * 0.8:  # At least 80% lectures ready
            return {
                'status': 'FAILED',
                'error': f'Only {ready_lectures}/{total_lectures} lectures are published'
            }
        
        course.status = 'published'
        course.published_at = timezone.now()
        course.save()
        
        return {
            'status': 'SUCCESS',
            'course_id': str(course.id),
            'published_at': course.published_at.isoformat()
        }
    except Exception as e:
        return {'status': 'FAILED', 'error': str(e)}
```

---

### 4. **Lecture Service** (`services/lectures/`)

**Purpose**: Lecture CRUD, trigger slide generation

**Key Files**:

**`lecture_service.py`**:
```python
class LectureService:
    """Business logic for lecture management"""
    
    def create_lecture(self, week_id, lecture_data):
        """Create new lecture"""
        week = Week.objects.get(id=week_id)
        
        lecture = Lecture.objects.create(
            week=week,
            lecture_number=lecture_data['lecture_number'],
            title=lecture_data['title'],
            description=lecture_data.get('description', ''),
            lecture_notes=lecture_data['lecture_notes'],
            target_slide_count=lecture_data.get('target_slide_count', 13),
            target_duration_minutes=lecture_data.get('target_duration_minutes', 30)
        )
        
        return lecture
    
    def get_lecture_with_slides(self, lecture_id):
        """Get lecture with all slides"""
        lecture = Lecture.objects.select_related('week__course').get(id=lecture_id)
        slides = lecture.slides.all().order_by('slide_number')
        
        return {
            'lecture': {
                'id': str(lecture.id),
                'title': lecture.title,
                'week': lecture.week.week_number,
                'lecture_number': lecture.lecture_number,
                'status': lecture.status,
                'lecture_notes': lecture.lecture_notes,
                'generated_at': lecture.generated_at.isoformat() if lecture.generated_at else None,
                'total_slides': slides.count()
            },
            'slides': [
                {
                    'id': str(slide.id),
                    'slide_number': slide.slide_number,
                    'slide_type': slide.slide_type,
                    'title': slide.title,
                    'content': slide.content,
                    'narration_script': slide.narration_script,
                    'visual_hint': slide.visual_hint,
                    'image_url': slide.image_url
                }
                for slide in slides
            ]
        }
```

**`views.py`**:
```python
class LectureGenerateSlidesView(APIView):
    """Trigger async slide generation for a lecture"""
    permission_classes = [IsAuthenticated]
    
    @extend_schema(
        description="Generate slides for lecture using AI (async)",
        tags=['Lectures']
    )
    def post(self, request, lecture_id):
        try:
            lecture = Lecture.objects.get(id=lecture_id)
            
            # Validate lecture has notes
            if not lecture.lecture_notes.strip():
                return Response({
                    'error': 'Lecture notes are required to generate slides'
                }, status=400)
            
            # Trigger async task
            from services.ai_service.tasks import generate_slides_task
            task = generate_slides_task.delay(str(lecture_id))
            
            # Update lecture status
            lecture.status = 'generating'
            lecture.generation_task_id = task.id
            lecture.save()
            
            return Response({
                'status': 'success',
                'task_id': task.id,
                'lecture_id': str(lecture_id),
                'message': 'Slide generation started. Poll /api/lectures/{id}/status for progress'
            })
        except Lecture.DoesNotExist:
            return Response({'error': 'Lecture not found'}, status=404)


class LectureGenerationStatusView(APIView):
    """Check slide generation status"""
    permission_classes = [IsAuthenticated]
    
    @extend_schema(
        description="Get slide generation status for a lecture",
        tags=['Lectures']
    )
    def get(self, request, lecture_id):
        try:
            from celery.result import AsyncResult
            
            lecture = Lecture.objects.get(id=lecture_id)
            
            if not lecture.generation_task_id:
                return Response({
                    'status': 'not_started',
                    'lecture_status': lecture.status
                })
            
            task = AsyncResult(lecture.generation_task_id)
            
            response = {
                'task_id': lecture.generation_task_id,
                'task_state': task.state,
                'lecture_status': lecture.status
            }
            
            if task.state == 'SUCCESS':
                response['result'] = task.result
                response['slides_generated'] = lecture.slides.count()
            elif task.state == 'FAILURE':
                response['error'] = str(task.result)
            elif task.state == 'PROGRESS':
                response['progress'] = task.info
            
            return Response(response)
        except Lecture.DoesNotExist:
            return Response({'error': 'Lecture not found'}, status=404)
```

---

### 5. **AI Service** (`services/ai_service/`)

**Purpose**: Core AI/LLM integration for slide generation and RAG

This is the **NEW** service specific to Education-Bot.

#### `llm_client.py` (OpenAI API wrapper)

```python
import openai
import tiktoken
from django.conf import settings
import logging

logger = logging.getLogger(__name__)


class LLMClient:
    """OpenAI API client wrapper"""
    
    def __init__(self):
        openai.api_key = settings.OPENAI_API_KEY
        self.model = settings.AI_MODEL_NAME  # gpt-4-turbo or gpt-4o
        self.encoding = tiktoken.encoding_for_model(self.model)
    
    def count_tokens(self, text: str) -> int:
        """Count tokens in text"""
        return len(self.encoding.encode(text))
    
    def generate_completion(self, messages, temperature=0.7, max_tokens=3000):
        """
        Generate LLM completion
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            temperature: Creativity (0.0-1.0)
            max_tokens: Max completion tokens
        
        Returns:
            Dict with completion text, token usage, and metadata
        """
        try:
            response = openai.ChatCompletion.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format={"type": "json_object"}  # Force JSON output
            )
            
            result = {
                'content': response.choices[0].message.content,
                'model': response.model,
                'prompt_tokens': response.usage.prompt_tokens,
                'completion_tokens': response.usage.completion_tokens,
                'total_tokens': response.usage.total_tokens,
                'finish_reason': response.choices[0].finish_reason
            }
            
            logger.info(f"LLM completion: {result['total_tokens']} tokens")
            return result
            
        except Exception as e:
            logger.error(f"LLM API error: {e}")
            raise
    
    def estimate_cost(self, prompt_tokens, completion_tokens):
        """
        Estimate cost based on token usage
        
        GPT-4-turbo pricing (as of 2025):
        - Input: $0.01 per 1K tokens
        - Output: $0.03 per 1K tokens
        """
        input_cost = (prompt_tokens / 1000) * 0.01
        output_cost = (completion_tokens / 1000) * 0.03
        return input_cost + output_cost
```

#### `rag_service.py` (RAG pipeline for syllabus context)

```python
import PyPDF2
from pinecone import Pinecone
from openai import OpenAI
from django.conf import settings
import logging

logger = logging.getLogger(__name__)


class RAGService:
    """Retrieval-Augmented Generation service for syllabus context"""
    
    def __init__(self):
        self.openai_client = OpenAI(api_key=settings.OPENAI_API_KEY)
        self.pinecone_client = Pinecone(api_key=settings.PINECONE_API_KEY)
        self.index = self.pinecone_client.Index(settings.PINECONE_INDEX_NAME)
        self.embedding_model = settings.EMBEDDING_MODEL  # text-embedding-3-large
    
    def extract_text_from_pdf(self, pdf_file_path):
        """Extract text from PDF file"""
        try:
            with open(pdf_file_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                text = ""
                
                for page in pdf_reader.pages:
                    text += page.extract_text() + "\n"
                
                return {
                    'text': text,
                    'page_count': len(pdf_reader.pages),
                    'success': True
                }
        except Exception as e:
            logger.error(f"PDF extraction error: {e}")
            return {
                'text': '',
                'page_count': 0,
                'success': False,
                'error': str(e)
            }
    
    def chunk_text(self, text, chunk_size=500, overlap=50):
        """
        Split text into overlapping chunks
        
        Args:
            text: Full text to chunk
            chunk_size: Words per chunk
            overlap: Overlapping words between chunks
        """
        words = text.split()
        chunks = []
        
        for i in range(0, len(words), chunk_size - overlap):
            chunk = " ".join(words[i:i + chunk_size])
            chunks.append(chunk)
        
        return chunks
    
    def generate_embeddings(self, texts):
        """Generate embeddings for text chunks"""
        try:
            response = self.openai_client.embeddings.create(
                model=self.embedding_model,
                input=texts
            )
            
            embeddings = [item.embedding for item in response.data]
            return embeddings
        except Exception as e:
            logger.error(f"Embedding generation error: {e}")
            raise
    
    def index_syllabus(self, syllabus_file):
        """
        Extract, chunk, embed, and index syllabus PDF
        
        Args:
            syllabus_file: SyllabusFile model instance
        """
        from services.files.models import SyllabusFile
        
        try:
            # Update status
            syllabus_file.extraction_status = 'processing'
            syllabus_file.save()
            
            # Extract text
            extraction_result = self.extract_text_from_pdf(syllabus_file.local_file_path)
            
            if not extraction_result['success']:
                syllabus_file.extraction_status = 'failed'
                syllabus_file.extraction_error = extraction_result['error']
                syllabus_file.save()
                return False
            
            text = extraction_result['text']
            syllabus_file.extracted_text = text
            syllabus_file.page_count = extraction_result['page_count']
            
            # Chunk text
            chunks = self.chunk_text(text)
            
            # Generate embeddings
            embeddings = self.generate_embeddings(chunks)
            
            # Prepare vectors for Pinecone
            namespace = f"course_{syllabus_file.course.id}"
            vectors = []
            
            for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
                vector_id = f"syllabus_{syllabus_file.id}_chunk_{i}"
                vectors.append({
                    "id": vector_id,
                    "values": embedding,
                    "metadata": {
                        "course_id": str(syllabus_file.course.id),
                        "syllabus_file_id": str(syllabus_file.id),
                        "chunk_index": i,
                        "text": chunk[:1000]  # Store first 1000 chars in metadata
                    }
                })
            
            # Upsert to Pinecone
            self.index.upsert(vectors=vectors, namespace=namespace)
            
            # Update syllabus file
            syllabus_file.extraction_status = 'completed'
            syllabus_file.vector_indexed = True
            syllabus_file.vector_index_id = namespace
            syllabus_file.chunk_count = len(chunks)
            syllabus_file.save()
            
            logger.info(f"Indexed {len(chunks)} chunks for syllabus {syllabus_file.id}")
            return True
            
        except Exception as e:
            logger.error(f"Syllabus indexing error: {e}")
            syllabus_file.extraction_status = 'failed'
            syllabus_file.extraction_error = str(e)
            syllabus_file.save()
            return False
    
    def retrieve_context(self, lecture_notes, course_id, top_k=5):
        """
        Retrieve relevant syllabus chunks for lecture notes
        
        Args:
            lecture_notes: Educator's lecture notes
            course_id: Course UUID
            top_k: Number of top chunks to retrieve
        
        Returns:
            String of concatenated relevant chunks
        """
        try:
            # Generate embedding for lecture notes
            query_embedding = self.generate_embeddings([lecture_notes[:1000]])[0]
            
            # Query Pinecone
            namespace = f"course_{course_id}"
            results = self.index.query(
                vector=query_embedding,
                top_k=top_k,
                namespace=namespace,
                include_metadata=True
            )
            
            # Concatenate relevant chunks
            context_chunks = []
            for match in results.matches:
                if match.score > 0.7:  # Relevance threshold
                    context_chunks.append(match.metadata['text'])
            
            context = "\n\n".join(context_chunks)
            logger.info(f"Retrieved {len(context_chunks)} relevant chunks (threshold: 0.7)")
            
            return context
            
        except Exception as e:
            logger.error(f"Context retrieval error: {e}")
            return ""
```

#### `slide_generator_service.py` (Core slide generation logic)

```python
from .llm_client import LLMClient
from .rag_service import RAGService
from .prompts import SLIDE_GENERATION_SYSTEM_PROMPT, SLIDE_GENERATION_USER_PROMPT
from services.lectures.models import Lecture, Slide
from services.ai_service.models import AITaskLog
from django.utils import timezone
import json
import logging

logger = logging.getLogger(__name__)


class SlideGeneratorService:
    """Core service for AI-powered slide generation"""
    
    def __init__(self):
        self.llm_client = LLMClient()
        self.rag_service = RAGService()
    
    def generate_slides(self, lecture_id: str):
        """
        Main slide generation pipeline
        
        Steps:
        1. Get lecture and course context
        2. Retrieve relevant syllabus chunks (RAG)
        3. Build LLM prompt with context
        4. Call LLM to generate slides
        5. Parse and save slides to database
        6. Log task and token usage
        """
        # Create task log
        task_log = AITaskLog.objects.create(
            task_type='slide_generation',
            lecture_id=lecture_id,
            status='running'
        )
        
        try:
            # 1. Get lecture
            lecture = Lecture.objects.select_related('week__course').get(id=lecture_id)
            course = lecture.week.course
            
            lecture.status = 'generating'
            lecture.save()
            
            # 2. Retrieve RAG context from syllabus
            logger.info(f"Retrieving syllabus context for lecture {lecture.title}")
            rag_context = self.rag_service.retrieve_context(
                lecture.lecture_notes,
                str(course.id),
                top_k=5
            )
            
            # 3. Build prompt
            messages = [
                {
                    "role": "system",
                    "content": SLIDE_GENERATION_SYSTEM_PROMPT
                },
                {
                    "role": "user",
                    "content": SLIDE_GENERATION_USER_PROMPT.format(
                        course_title=course.title,
                        grade_level=course.grade_level,
                        lecture_title=lecture.title,
                        lecture_notes=lecture.lecture_notes,
                        rag_context=rag_context,
                        target_slide_count=lecture.target_slide_count
                    )
                }
            ]
            
            # 4. Call LLM
            logger.info(f"Generating {lecture.target_slide_count} slides with GPT-4")
            llm_response = self.llm_client.generate_completion(
                messages=messages,
                temperature=0.7,
                max_tokens=3000
            )
            
            # 5. Parse JSON response
            slides_json = json.loads(llm_response['content'])
            slides_data = slides_json.get('slides', [])
            
            if not slides_data:
                raise ValueError("LLM returned empty slides array")
            
            # 6. Save slides to database
            self._save_slides(lecture, slides_data, llm_response)
            
            # 7. Update lecture status
            lecture.status = 'ready'
            lecture.generated_at = timezone.now()
            lecture.generation_metadata = {
                'model': llm_response['model'],
                'total_tokens': llm_response['total_tokens'],
                'slide_count': len(slides_data),
                'generated_at': timezone.now().isoformat()
            }
            lecture.save()
            
            # 8. Update task log
            task_log.status = 'success'
            task_log.completed_at = timezone.now()
            task_log.model_name = llm_response['model']
            task_log.prompt_tokens = llm_response['prompt_tokens']
            task_log.completion_tokens = llm_response['completion_tokens']
            task_log.total_tokens = llm_response['total_tokens']
            task_log.estimated_cost_usd = self.llm_client.estimate_cost(
                llm_response['prompt_tokens'],
                llm_response['completion_tokens']
            )
            task_log.duration_seconds = (task_log.completed_at - task_log.started_at).total_seconds()
            task_log.save()
            
            logger.info(f"Successfully generated {len(slides_data)} slides for lecture {lecture.title}")
            
            return {
                'status': 'SUCCESS',
                'lecture_id': str(lecture_id),
                'slide_count': len(slides_data),
                'total_tokens': llm_response['total_tokens'],
                'estimated_cost': float(task_log.estimated_cost_usd)
            }
            
        except Exception as e:
            logger.error(f"Slide generation failed for lecture {lecture_id}: {e}", exc_info=True)
            
            # Update lecture
            try:
                lecture = Lecture.objects.get(id=lecture_id)
                lecture.status = 'failed'
                lecture.generation_error = str(e)
                lecture.save()
            except:
                pass
            
            # Update task log
            task_log.status = 'failed'
            task_log.error_message = str(e)
            task_log.completed_at = timezone.now()
            task_log.save()
            
            return {
                'status': 'FAILED',
                'lecture_id': str(lecture_id),
                'error': str(e)
            }
    
    def _save_slides(self, lecture, slides_data, llm_response):
        """Parse and save slides to database"""
        
        # Delete existing slides
        Slide.objects.filter(lecture=lecture).delete()
        
        # Create new slides
        for slide_data in slides_data:
            Slide.objects.create(
                lecture=lecture,
                slide_number=slide_data['slide_number'],
                slide_type=self._infer_slide_type(slide_data['slide_number'], len(slides_data)),
                title=slide_data['title'],
                content="\n".join(slide_data.get('content', [])),
                narration_script=slide_data.get('narration_script', ''),
                visual_hint=slide_data.get('visual_hint', ''),
                notes=slide_data.get('notes', ''),
                generation_metadata={
                    'model': llm_response['model'],
                    'generated_at': timezone.now().isoformat()
                }
            )
    
    def _infer_slide_type(self, slide_number, total_slides):
        """Infer slide type based on position"""
        if slide_number == 1:
            return 'title'
        elif slide_number == 2:
            return 'objectives'
        elif slide_number == total_slides - 1:
            return 'summary'
        elif slide_number == total_slides:
            return 'next'
        else:
            return 'content'
```

#### `prompts.py` (LLM prompt templates)

```python
SLIDE_GENERATION_SYSTEM_PROMPT = """You are an expert educator and instructional designer creating high-quality lecture slides.

Your task is to generate a complete slide deck based on lecture notes provided by an educator.

REQUIREMENTS:
1. Generate EXACTLY the requested number of slides (typically 13)
2. Each slide should be suitable for a 25-30 minute lecture
3. Slides should be clear, concise, and pedagogically sound
4. Include a 15-20 second narration script for each slide (for voice-over)
5. Output valid JSON format only

SLIDE STRUCTURE:
- Slide 1: Title slide (lecture title, key topics)
- Slide 2: Learning objectives and prerequisites
- Slides 3-N-2: Core content (concepts, examples, explanations)
- Slide N-1: Summary and key takeaways
- Slide N: Next lecture preview and assignments

JSON FORMAT:
{
  "slides": [
    {
      "slide_number": 1,
      "title": "Clear, concise title",
      "content": ["Bullet point 1", "Bullet point 2", "Bullet point 3"],
      "narration_script": "Natural 15-20 second script for voice narration",
      "visual_hint": "Suggestion for diagram/image (optional)",
      "notes": "Additional speaker notes (optional)"
    },
    ...
  ]
}

PEDAGOGICAL PRINCIPLES:
- Start with context and objectives
- Build from simple to complex
- Use clear examples
- Reinforce key concepts
- End with summary and next steps
- Keep bullet points concise (3-5 per slide max)
- Narration should be conversational and engaging
"""

SLIDE_GENERATION_USER_PROMPT = """Course: {course_title}
Grade Level: {grade_level}
Lecture Title: {lecture_title}

LECTURE NOTES (provided by educator):
{lecture_notes}

RELEVANT CONTEXT FROM SYLLABUS:
{rag_context}

TASK: Generate EXACTLY {target_slide_count} slides for this lecture.

Requirements:
1. Use the lecture notes as the primary source
2. Reference the syllabus context to ensure alignment with course objectives
3. Generate clear, concise slides suitable for {grade_level} students
4. Include 15-20 second narration scripts for each slide
5. Output ONLY valid JSON (no additional text)

Generate the slide deck now:
"""
```

#### `tasks.py` (Celery tasks)

```python
from celery import shared_task
from .slide_generator_service import SlideGeneratorService
from .rag_service import RAGService
import logging

logger = logging.getLogger(__name__)


@shared_task(bind=True, name='ai_service.generate_slides',
             autoretry_for=(Exception,),
             retry_kwargs={'max_retries': 3, 'countdown': 60},
             retry_backoff=True,
             retry_backoff_max=300)
def generate_slides_task(self, lecture_id: str):
    """
    Async task for slide generation
    
    Args:
        lecture_id: UUID of lecture to generate slides for
    """
    try:
        # Update progress
        self.update_state(
            state='PROGRESS',
            meta={'status': 'Initializing slide generation...', 'progress': 0}
        )
        
        # Initialize service
        service = SlideGeneratorService()
        
        # Update progress
        self.update_state(
            state='PROGRESS',
            meta={'status': 'Retrieving syllabus context (RAG)...', 'progress': 20}
        )
        
        # Generate slides
        result = service.generate_slides(lecture_id)
        
        # Update progress
        self.update_state(
            state='PROGRESS',
            meta={'status': 'Slide generation completed!', 'progress': 100}
        )
        
        return result
        
    except Exception as e:
        logger.error(f"Slide generation task failed: {e}", exc_info=True)
        return {
            'status': 'FAILED',
            'lecture_id': lecture_id,
            'error': str(e)
        }


@shared_task(bind=True, name='ai_service.index_syllabus')
def index_syllabus_task(self, syllabus_file_id: str):
    """
    Async task for syllabus PDF extraction and vector indexing
    
    Args:
        syllabus_file_id: UUID of syllabus file to process
    """
    try:
        from services.files.models import SyllabusFile
        
        self.update_state(
            state='PROGRESS',
            meta={'status': 'Extracting text from PDF...', 'progress': 0}
        )
        
        syllabus_file = SyllabusFile.objects.get(id=syllabus_file_id)
        
        # Initialize RAG service
        rag_service = RAGService()
        
        self.update_state(
            state='PROGRESS',
            meta={'status': 'Generating embeddings and indexing...', 'progress': 50}
        )
        
        # Index syllabus
        success = rag_service.index_syllabus(syllabus_file)
        
        if success:
            return {
                'status': 'SUCCESS',
                'syllabus_file_id': str(syllabus_file_id),
                'chunk_count': syllabus_file.chunk_count
            }
        else:
            return {
                'status': 'FAILED',
                'syllabus_file_id': str(syllabus_file_id),
                'error': syllabus_file.extraction_error
            }
            
    except Exception as e:
        logger.error(f"Syllabus indexing task failed: {e}", exc_info=True)
        return {
            'status': 'FAILED',
            'syllabus_file_id': syllabus_file_id,
            'error': str(e)
        }
```

---

## API Design

### URL Structure (following parliament_api pattern)

```python
# education_api/urls.py

urlpatterns = [
    # Root redirect to docs
    path('', home_redirect, name='home'),
    
    # Admin interface
    path('admin/', admin.site.urls),
    
    # API documentation (drf-spectacular)
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
    
    # API root
    path('api/', api_root, name='api-root'),
    
    # Service endpoints
    path('api/auth/', include('services.user_auth.urls')),
    path('api/courses/', include('services.courses.urls')),
    path('api/lectures/', include('services.lectures.urls')),
    path('api/files/', include('services.files.urls')),
    path('api/ai/', include('services.ai_service.urls')),
]
```

### Complete API Endpoints (Phase 1)

#### Authentication
```
POST   /api/auth/register
POST   /api/auth/login
POST   /api/auth/logout
GET    /api/auth/profile
PUT    /api/auth/profile
POST   /api/auth/change-password
```

#### Courses
```
GET    /api/courses/                  # List educator's courses
POST   /api/courses/                  # Create new course
GET    /api/courses/{id}/             # Get course details with weeks/lectures
PATCH  /api/courses/{id}/             # Update course
DELETE /api/courses/{id}/             # Delete course
POST   /api/courses/{id}/publish/     # Publish course
GET    /api/courses/{id}/statistics/  # Get course stats
```

#### Weeks
```
POST   /api/courses/{course_id}/weeks/  # Create week
GET    /api/weeks/{id}/                 # Get week details
PATCH  /api/weeks/{id}/                 # Update week
DELETE /api/weeks/{id}/                 # Delete week
```

#### Lectures
```
POST   /api/weeks/{week_id}/lectures/       # Create lecture
GET    /api/lectures/{id}/                  # Get lecture with slides
PATCH  /api/lectures/{id}/                  # Update lecture notes
DELETE /api/lectures/{id}/                  # Delete lecture

# Slide Generation (Core Phase 1)
POST   /api/lectures/{id}/generate/         # Generate slides (async)
GET    /api/lectures/{id}/status/           # Check generation status
POST   /api/lectures/{id}/regenerate/       # Regenerate all slides
```

#### Slides
```
GET    /api/lectures/{id}/slides/           # Get all slides for lecture
GET    /api/slides/{id}/                    # Get single slide
PATCH  /api/slides/{id}/                    # Edit slide
POST   /api/slides/{id}/regenerate/         # Regenerate single slide
DELETE /api/slides/{id}/                    # Delete slide
```

#### Files (Syllabus Management)
```
POST   /api/courses/{id}/syllabus/upload/  # Upload syllabus PDF
GET    /api/courses/{id}/syllabus/         # List syllabus files
GET    /api/syllabus/{id}/                 # Get syllabus file metadata
DELETE /api/syllabus/{id}/                 # Delete syllabus file
GET    /api/syllabus/{id}/download/        # Get presigned GCS URL
```

#### AI Service
```
GET    /api/ai/tasks/{task_id}/            # Get AI task status
GET    /api/ai/statistics/                 # Get AI usage statistics (tokens, costs)
GET    /api/ai/generation-history/{lecture_id}/  # Get generation history
```

---

## Cloud Storage & File Management

### GCS Bucket Strategy (mirrors parliament_api)

```
education-bot-syllabus-prod/
  └─ course_{course_id}/
      └─ syllabus_{filename}

education-bot-slides-prod/
  └─ course_{course_id}/
      └─ lecture_{lecture_id}/
          └─ slide_{slide_number}.png

education-bot-media-prod/
  └─ course_{course_id}/
      └─ user_uploads/
```

### File Upload Flow (reuse GCSService)

```python
# services/files/views.py

class SyllabusUploadView(APIView):
    """Upload syllabus PDF to GCS"""
    permission_classes = [IsAuthenticated]
    
    def post(self, request, course_id):
        try:
            course = Course.objects.get(id=course_id, created_by=request.user)
            uploaded_file = request.FILES['file']
            
            # Save temporarily to local disk
            temp_path = f"/tmp/{uploaded_file.name}"
            with open(temp_path, 'wb') as f:
                for chunk in uploaded_file.chunks():
                    f.write(chunk)
            
            # Upload to GCS
            gcs_service = GCSService()
            bucket_name = settings.GCS_SYLLABUS_BUCKET
            object_key = f"course_{course_id}/{uploaded_file.name}"
            
            upload_result = gcs_service.upload_file(
                temp_path,
                bucket_name,
                object_key,
                metadata={'course_id': str(course_id)}
            )
            
            if upload_result['success']:
                # Create SyllabusFile record
                syllabus_file = SyllabusFile.objects.create(
                    course=course,
                    uploaded_by=request.user,
                    file_name=uploaded_file.name,
                    file_size=uploaded_file.size,
                    gcs_bucket_name=bucket_name,
                    gcs_object_key=object_key,
                    gcs_url=upload_result['gcs_url']
                )
                
                # Trigger async text extraction and indexing
                from services.ai_service.tasks import index_syllabus_task
                task = index_syllabus_task.delay(str(syllabus_file.id))
                
                # Clean up temp file
                os.remove(temp_path)
                
                return Response({
                    'status': 'success',
                    'syllabus_file_id': str(syllabus_file.id),
                    'file_name': uploaded_file.name,
                    'task_id': task.id,
                    'message': 'Syllabus uploaded, text extraction in progress'
                }, status=201)
            else:
                return Response({
                    'error': 'GCS upload failed',
                    'details': upload_result.get('error')
                }, status=500)
                
        except Course.DoesNotExist:
            return Response({'error': 'Course not found'}, status=404)
```

---

## Task Queue & Background Jobs

### Celery Configuration (education_api/celery.py)

```python
# Identical to parliament_api/celery.py

import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'education_api.settings')

app = Celery('education_api')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

@app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}')
```

### Key Celery Tasks

1. **`generate_slides_task`**: Async slide generation (1-2 min)
2. **`index_syllabus_task`**: PDF text extraction + vector indexing (30-60 sec)
3. **`publish_course_task`**: Course validation and publishing

### Monitoring with Flower

```bash
# Start Flower monitoring UI
celery -A education_api flower --port=5555
# Access at http://localhost:5555
```

---

## Authentication & Authorization

### Token-Based Auth (reuse parliament_api pattern)

```python
# settings.py

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.TokenAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    ...
}
```

### User Roles & Permissions

| Role | Permissions |
|------|-------------|
| **Admin** | Full system access, manage all courses |
| **Educator** | Create/edit own courses, generate slides, upload syllabus |
| **Student** (Phase 2) | View published courses, track progress |

### API Key Support (for external integrations)

Reuse `APIKey` model from parliament_api for programmatic access.

---

## Environment Configuration

### `.env` File Structure

```bash
# Django Settings
SECRET_KEY=your-django-secret-key-here
DEBUG=true
ALLOWED_HOSTS=localhost,127.0.0.1

# Database (PostgreSQL)
DB_NAME=education_bot_api
DB_USER=education_bot_user
DB_PASSWORD=education_bot_pass_2025
DB_HOST=localhost
DB_PORT=5432
DB_CONN_MAX_AGE=600
DB_CONN_HEALTH_CHECKS=true

# Celery / Redis
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0
CELERY_WORKER_CONCURRENCY=8

# Google Cloud Storage
GCS_PROJECT_ID=education-bot-project-123456
GCS_CREDENTIALS_PATH=/path/to/education-bot-gcs-key.json
GCS_SYLLABUS_BUCKET=education-bot-syllabus-prod
GCS_SLIDES_BUCKET=education-bot-slides-prod
GCS_PRESIGNED_URL_EXPIRATION=3600
GCS_AUTO_DELETE_LOCAL=true
GCS_REGION=asia-south1

# OpenAI API
OPENAI_API_KEY=sk-...
AI_MODEL_NAME=gpt-4-turbo
EMBEDDING_MODEL=text-embedding-3-large

# Pinecone Vector DB
PINECONE_API_KEY=your-pinecone-api-key
PINECONE_ENVIRONMENT=us-east-1-aws
PINECONE_INDEX_NAME=education-bot-syllabus

# Admin User (for initial setup)
ADMIN_USERNAME=admin
ADMIN_PASSWORD=EducationBot@2025#Secure
ADMIN_EMAIL=admin@educationbot.com
```

---

## Deployment & Startup

### `startup.sh` Script (adapted from parliament_api)

```bash
#!/bin/bash

# Education Bot API Management Script
# Usage: ./startup.sh [start|stop|restart|status]

set -e

MODE=${1:-start}

# ... (copy entire startup.sh structure from parliament_api)
# Adapt the following:
# 1. Change project name references
# 2. Update bucket initialization logic
# 3. Add Pinecone connection check
# 4. Update management command: initialize_sample_courses
```

### Startup Flow

```bash
cd education_api
./startup.sh start

# This will:
# 1. Create/activate virtual environment
# 2. Install dependencies from requirements.txt
# 3. Setup PostgreSQL database (education_bot_api)
# 4. Run Django migrations
# 5. Create superuser (admin/admin)
# 6. Initialize GCS buckets
# 7. Check Pinecone connection
# 8. Start Redis server (tmux: education-redis)
# 9. Start Celery worker (tmux: education-celery)
# 10. Start Flower monitoring (tmux: education-flower)
# 11. Start Django dev server (tmux: education-api)
```

### Accessing Services

```
Django API:        http://localhost:8000
API Docs:          http://localhost:8000/api/docs/
Admin Panel:       http://localhost:8000/admin/
Celery Flower:     http://localhost:5555
```

---

## Management Commands

### Initialize Sample Courses

```python
# services/courses/management/commands/initialize_sample_courses.py

from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from services.courses.models import Course, Week
from services.lectures.models import Lecture

User = get_user_model()

class Command(BaseCommand):
    help = 'Initialize sample courses for testing'
    
    def handle(self, *args, **options):
        # Get or create admin user
        admin_user = User.objects.filter(is_superuser=True).first()
        
        if not admin_user:
            self.stdout.write(self.style.ERROR('No admin user found'))
            return
        
        # Create sample course
        course = Course.objects.create(
            title="Introduction to Linear Algebra",
            description="Fundamental concepts of linear algebra including vectors, matrices, and linear transformations",
            subject="mathematics",
            grade_level="undergraduate",
            total_weeks=12,
            lectures_per_week=3,
            created_by=admin_user,
            status="draft"
        )
        
        # Create weeks
        for week_num in range(1, 13):
            Week.objects.create(
                course=course,
                week_number=week_num,
                title=f"Week {week_num}",
                description=""
            )
        
        self.stdout.write(self.style.SUCCESS(f'Created sample course: {course.title}'))
```

### Usage

```bash
python manage.py initialize_sample_courses
```

---

## Testing Strategy

### Test Structure (following parliament_api)

```
services/courses/tests.py       # Course CRUD tests
services/lectures/tests.py      # Lecture CRUD + slide generation tests
services/ai_service/tests.py    # LLM integration tests (mocked)
services/files/tests.py         # File upload + GCS tests
```

### Sample Test (Slide Generation)

```python
# services/lectures/tests.py

from django.test import TestCase
from unittest.mock import patch, MagicMock
from services.lectures.models import Lecture, Slide
from services.courses.models import Course, Week
from services.ai_service.slide_generator_service import SlideGeneratorService

class SlideGenerationTestCase(TestCase):
    
    def setUp(self):
        # Create test course and lecture
        self.course = Course.objects.create(
            title="Test Course",
            subject="mathematics",
            grade_level="undergraduate",
            created_by=self.user
        )
        
        self.week = Week.objects.create(
            course=self.course,
            week_number=1,
            title="Week 1"
        )
        
        self.lecture = Lecture.objects.create(
            week=self.week,
            lecture_number=1,
            title="Introduction to Vectors",
            lecture_notes="Vectors are mathematical objects with magnitude and direction..."
        )
    
    @patch('services.ai_service.llm_client.openai.ChatCompletion.create')
    @patch('services.ai_service.rag_service.RAGService.retrieve_context')
    def test_slide_generation_success(self, mock_rag, mock_llm):
        """Test successful slide generation"""
        
        # Mock RAG context retrieval
        mock_rag.return_value = "Relevant syllabus content..."
        
        # Mock LLM response
        mock_llm.return_value = MagicMock(
            choices=[MagicMock(
                message=MagicMock(
                    content='{"slides": [{"slide_number": 1, "title": "Introduction", "content": ["Point 1"], "narration_script": "Welcome..."}]}'
                )
            )],
            usage=MagicMock(
                prompt_tokens=500,
                completion_tokens=1000,
                total_tokens=1500
            )
        )
        
        # Generate slides
        service = SlideGeneratorService()
        result = service.generate_slides(str(self.lecture.id))
        
        # Assertions
        self.assertEqual(result['status'], 'SUCCESS')
        self.assertTrue(Slide.objects.filter(lecture=self.lecture).exists())
        
        # Verify lecture status updated
        self.lecture.refresh_from_database()
        self.assertEqual(self.lecture.status, 'ready')
```

---

## Phase 1 Implementation Plan (6-8 Weeks)

### Week 1: Project Setup & Infrastructure

**Tasks**:
- [ ] Initialize Django project structure
- [ ] Copy `cloud_storage/gcs_service.py` from parliament_api
- [ ] Configure PostgreSQL database
- [ ] Set up Redis + Celery
- [ ] Create `.env` file and settings configuration
- [ ] Implement `startup.sh` script
- [ ] Set up GCS buckets (syllabus, slides)
- [ ] Create Pinecone index for vector storage

**Deliverables**: Working Django project with GCS and Celery configured

---

### Week 2: Core Models & Authentication

**Tasks**:
- [ ] Copy `user_auth` service from parliament_api
- [ ] Create Course, Week models
- [ ] Create Lecture, Slide models
- [ ] Create SyllabusFile model
- [ ] Create AITaskLog, GenerationHistory models
- [ ] Run migrations
- [ ] Implement admin user setup management command

**Deliverables**: Complete database schema ready for use

---

### Week 3: Course & Lecture APIs

**Tasks**:
- [ ] Implement CourseService and Course CRUD APIs
- [ ] Implement Week CRUD APIs
- [ ] Implement LectureService and Lecture CRUD APIs
- [ ] Implement Slide CRUD APIs (basic)
- [ ] Add drf-spectacular documentation
- [ ] Write unit tests for CRUD operations

**Deliverables**: Working REST APIs for course/lecture management

---

### Week 4: File Upload & GCS Integration

**Tasks**:
- [ ] Implement syllabus upload API (GCS integration)
- [ ] Implement file download API (presigned URLs)
- [ ] Create PDF text extraction service (PyPDF2)
- [ ] Test GCS upload/download flow end-to-end

**Deliverables**: Working file upload system with GCS storage

---

### Week 5-6: AI/LLM Integration (Core Feature)

**Tasks**:
- [ ] Set up OpenAI API client wrapper
- [ ] Implement RAG service (Pinecone integration)
- [ ] Create slide generation prompt templates
- [ ] Implement SlideGeneratorService
- [ ] Create Celery tasks: `generate_slides_task`, `index_syllabus_task`
- [ ] Implement slide generation status polling
- [ ] Add token usage tracking and cost estimation
- [ ] Test with real lecture notes + syllabus PDFs

**Deliverables**: Working AI-powered slide generation pipeline

---

### Week 7: API Refinement & Testing

**Tasks**:
- [ ] Add slide regeneration (single slide + full lecture)
- [ ] Implement generation history tracking
- [ ] Add AI statistics API endpoints
- [ ] Write integration tests for slide generation
- [ ] Optimize LLM prompts based on test results
- [ ] Add comprehensive error handling

**Deliverables**: Production-ready slide generation API

---

### Week 8: Documentation & Deployment Prep

**Tasks**:
- [ ] Write API documentation (README.md)
- [ ] Create sample course initialization script
- [ ] Test full end-to-end workflow (course creation → slide generation)
- [ ] Set up monitoring (logging, error tracking)
- [ ] Performance testing (concurrent slide generation)
- [ ] Prepare for production deployment (GCP setup)

**Deliverables**: Fully documented, tested Phase 1 backend

---

## Next Steps

1. **Clone parliament_api structure**: Start with exact folder structure
2. **Reuse proven components**: Copy `gcs_service.py`, `user_auth` service, `celery.py`
3. **Add AI layer**: Implement new `ai_service` with LLM/RAG integration
4. **Test incrementally**: Each week should have deployable features
5. **Document as you build**: Keep README.md and API docs updated

---

## Appendix: Key Differences from Parliament API

| Aspect | Parliament API | Education-Bot API |
|--------|---------------|-------------------|
| **Domain** | Scraping parliamentary questions | Course/lecture management |
| **Data Source** | External APIs (sansad.in) | User-generated content |
| **File Types** | PDFs (questions, debates) | PDFs (syllabus), audio (Phase 2) |
| **AI Integration** | None | LLM (GPT-4) + RAG (Pinecone) |
| **Background Jobs** | PDF downloads, scraping | Slide generation, TTS (Phase 2) |
| **GCS Buckets** | `debates`, `questions` | `syllabus`, `slides`, `media` |
| **User Roles** | Admin only | Admin + Educator + Student (Phase 2) |

---

## Environment Variables Quick Reference

```bash
# Database
DB_NAME=education_bot_api
DB_USER=education_bot_user
DB_PASSWORD=education_bot_pass_2025

# GCS Buckets
GCS_SYLLABUS_BUCKET=education-bot-syllabus-prod
GCS_SLIDES_BUCKET=education-bot-slides-prod

# AI APIs
OPENAI_API_KEY=sk-...
PINECONE_API_KEY=...
PINECONE_INDEX_NAME=education-bot-syllabus

# Redis/Celery
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0
```

---

**This specification provides a production-ready blueprint for Education-Bot backend that leverages all proven patterns from your parliament_api while adding the AI/LLM capabilities required for slide generation. Every component is designed to be scalable, maintainable, and follows your existing coding standards.**


