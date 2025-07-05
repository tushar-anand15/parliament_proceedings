from django.contrib import admin
from .models import ScrapingJob, ScrapingSession, ScrapingError, ScrapingConfig, DataSource


@admin.register(ScrapingJob)
class ScrapingJobAdmin(admin.ModelAdmin):
    list_display = ['name', 'job_type', 'status', 'progress_percent', 'started_at', 'completed_at']
    list_filter = ['job_type', 'status', 'started_at']
    search_fields = ['name', 'description']
    readonly_fields = ['progress_percent', 'duration']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'description', 'job_type', 'status')
        }),
        ('Progress', {
            'fields': ('progress_percent', 'total_questions_expected', 'questions_processed', 
                      'questions_created', 'questions_updated', 'questions_failed')
        }),
        ('Configuration', {
            'fields': ('batch_size', 'worker_count', 'max_retries', 'delay_between_requests')
        }),
        ('Execution Details', {
            'fields': ('started_by', 'worker_id', 'pid', 'duration')
        }),
        ('Error Information', {
            'fields': ('error_message', 'error_count', 'last_error')
        }),
    )


@admin.register(ScrapingSession)
class ScrapingSessionAdmin(admin.ModelAdmin):
    list_display = ['scraping_job', 'lok_sabha', 'session', 'status', 'progress_percent', 'started_at']
    list_filter = ['status', 'lok_sabha', 'started_at']
    readonly_fields = ['progress_percent']


@admin.register(ScrapingError)
class ScrapingErrorAdmin(admin.ModelAdmin):
    list_display = ['error_type', 'scraping_job', 'occurred_at', 'is_resolved', 'retry_count']
    list_filter = ['error_type', 'is_resolved', 'occurred_at']
    search_fields = ['error_message', 'question_id']
    readonly_fields = ['occurred_at']


@admin.register(ScrapingConfig)
class ScrapingConfigAdmin(admin.ModelAdmin):
    list_display = ['name', 'is_default', 'is_active', 'auto_scrape_enabled', 'created_at']
    list_filter = ['is_default', 'is_active', 'auto_scrape_enabled']
    search_fields = ['name', 'description']


@admin.register(DataSource)
class DataSourceAdmin(admin.ModelAdmin):
    list_display = ['name', 'source_type', 'is_active', 'last_success', 'error_count']
    list_filter = ['source_type', 'is_active']
    search_fields = ['name', 'description', 'base_url'] 