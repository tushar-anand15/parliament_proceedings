from django.contrib import admin
from .models import Debate, DebateSpeech, DebateTag, DebateTagging, SessionDateCache


@admin.register(Debate)
class DebateAdmin(admin.ModelAdmin):
    list_display = ['debate_id', 'lok_sabha', 'session', 'debate_date', 'debate_type', 'status', 'file_size_mb']
    list_filter = ['status', 'debate_type', 'lok_sabha', 'session', 'language']
    search_fields = ['debate_id', 'debate_date']
    date_hierarchy = 'debate_date'
    readonly_fields = ['debate_id', 'created_at', 'updated_at', 'last_scraped']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('debate_id', 'lok_sabha', 'session', 'debate_date', 'debate_type', 'language')
        }),
        ('PDF Information', {
            'fields': ('pdf_url', 'pdf_file', 'status', 'file_size', 'page_count')
        }),
        ('Download Status', {
            'fields': ('download_attempts', 'last_download_attempt', 'error_message')
        }),
        ('Metadata', {
            'fields': ('raw_api_data', 'created_at', 'updated_at', 'last_scraped')
        })
    )


@admin.register(DebateSpeech)
class DebateSpeechAdmin(admin.ModelAdmin):
    list_display = ['debate', 'speaker_name', 'speaker_designation', 'speech_order']
    list_filter = ['debate__lok_sabha', 'debate__session']
    search_fields = ['speaker_name', 'speech_text']
    ordering = ['debate', 'speech_order']


@admin.register(DebateTag)
class DebateTagAdmin(admin.ModelAdmin):
    list_display = ['name', 'is_active', 'created_at']
    list_filter = ['is_active']
    search_fields = ['name', 'description']


@admin.register(DebateTagging)
class DebateTaggingAdmin(admin.ModelAdmin):
    list_display = ['debate', 'tag', 'confidence', 'created_by', 'created_at']
    list_filter = ['tag', 'created_by']
    search_fields = ['debate__debate_id', 'tag__name']


@admin.register(SessionDateCache)
class SessionDateCacheAdmin(admin.ModelAdmin):
    list_display = ['lok_sabha', 'session', 'date_count', 'last_updated', 'is_stale']
    list_filter = ['lok_sabha', 'session__session_number']
    readonly_fields = ['created_at', 'last_updated', 'is_stale', 'date_count']
    
    fieldsets = (
        ('Session Information', {
            'fields': ('lok_sabha', 'session')
        }),
        ('Cached Data', {
            'fields': ('available_dates', 'session_period', 'date_count')
        }),
        ('Cache Management', {
            'fields': ('is_stale', 'last_updated', 'created_at')
        })
    )
