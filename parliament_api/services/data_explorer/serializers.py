"""
Optimized serializers for Data Explorer
Designed for high performance with large datasets
"""
from rest_framework import serializers
from services.questions.models import QuestionMasterData, Question, LokSabha, Session
from services.debates.models import Debate, DebateMasterData
from datetime import datetime


class LightLokSabhaSerializer(serializers.ModelSerializer):
    """Lightweight Lok Sabha serializer"""
    class Meta:
        model = LokSabha
        fields = ['number']


class LightSessionSerializer(serializers.ModelSerializer):
    """Lightweight Session serializer"""
    class Meta:
        model = Session
        fields = ['session_number']


class LSQuestionExplorerSerializer(serializers.ModelSerializer):
    """Optimized serializer for LS Questions in Data Explorer"""
    lok_sabha = serializers.CharField(source='lok_sabha_number')
    session = serializers.CharField(source='session_number')
    member_names = serializers.SerializerMethodField()
    has_pdf = serializers.SerializerMethodField()
    has_answer = serializers.SerializerMethodField()
    
    class Meta:
        model = QuestionMasterData
        fields = [
            'id',
            'question_number',
            'subjects',
            'question_type',
            'ministry',
            'date',
            'lok_sabha',
            'session',
            'member_names',
            'has_pdf',
            'has_answer',
            'is_processed',
            'pdf_downloaded',
            'created_at',
            'updated_at'
        ]
    
    def get_member_names(self, obj):
        """Extract member names from JSON field"""
        if not obj.members:
            return []
        return [m.get('name', '') for m in obj.members if isinstance(m, dict)][:3]  # Limit to 3 for performance
    
    def get_has_pdf(self, obj):
        """Check if PDF is available"""
        return bool(obj.questions_file_path or obj.questions_file_path_hindi)
    
    def get_has_answer(self, obj):
        """Check if answer is available"""
        return bool(obj.answer_text)


class RSQuestionExplorerSerializer(serializers.ModelSerializer):
    """Optimized serializer for RS Questions in Data Explorer"""
    session = serializers.CharField(source='session_number')
    member_names = serializers.SerializerMethodField()
    has_pdf = serializers.SerializerMethodField()
    has_answer = serializers.SerializerMethodField()
    
    class Meta:
        model = QuestionMasterData
        fields = [
            'id',
            'question_number',
            'subjects',
            'question_type',
            'ministry',
            'date',
            'session',
            'member_names',
            'has_pdf',
            'has_answer',
            'is_processed',
            'pdf_downloaded',
            'created_at',
            'updated_at'
        ]
    
    def get_member_names(self, obj):
        """Extract member names from JSON field"""
        if not obj.members:
            return []
        return [m.get('name', '') for m in obj.members if isinstance(m, dict)][:3]
    
    def get_has_pdf(self, obj):
        """Check if PDF is available"""
        return bool(obj.questions_file_path or obj.questions_file_path_hindi)
    
    def get_has_answer(self, obj):
        """Check if answer is available"""
        return bool(obj.answer_text)


class LSDebateExplorerSerializer(serializers.ModelSerializer):
    """Optimized serializer for LS Debates in Data Explorer"""
    lok_sabha = serializers.CharField(source='lok_sabha.number')
    session = serializers.CharField(source='session.session_number')
    is_downloaded = serializers.BooleanField()
    file_size_mb = serializers.FloatField()
    
    class Meta:
        model = Debate
        fields = [
            'id',
            'debate_id',
            'debate_date',
            'debate_type',
            'debate_category',
            'language',
            'time_slot',
            'lok_sabha',
            'session',
            'status',
            'is_downloaded',
            'file_size_mb',
            'page_count',
            'download_attempts',
            'created_at',
            'updated_at'
        ]


class RSDebateExplorerSerializer(serializers.ModelSerializer):
    """Optimized serializer for RS Debates in Data Explorer"""
    session = serializers.CharField(source='session.session_number')
    is_downloaded = serializers.BooleanField()
    file_size_mb = serializers.FloatField()
    
    class Meta:
        model = Debate
        fields = [
            'id',
            'debate_id',
            'debate_date',
            'debate_type',
            'debate_category',
            'language',
            'time_slot',
            'session',
            'status',
            'is_downloaded',
            'file_size_mb',
            'page_count',
            'download_attempts',
            'created_at',
            'updated_at'
        ]


class QuestionDetailSerializer(serializers.ModelSerializer):
    """Detailed serializer for individual question view"""
    lok_sabha = serializers.CharField(source='lok_sabha_number')
    session = serializers.CharField(source='session_number')
    member_names = serializers.SerializerMethodField()
    pdf_url = serializers.SerializerMethodField()
    
    class Meta:
        model = QuestionMasterData
        fields = [
            'id',
            'question_number',
            'subjects',
            'question_type',
            'ministry',
            'date',
            'lok_sabha',
            'session',
            'member_names',
            'members',  # Full member data
            'question_text',
            'answer_text',
            'answer_text_hindi',
            'supplementary_type',
            'supplementary_questions',
            'is_processed',
            'pdf_downloaded',
            'pdf_gcs_path',
            'pdf_url',
            'created_at',
            'updated_at',
            'last_fetched'
        ]
    
    def get_member_names(self, obj):
        """Extract member names from JSON field"""
        if not obj.members:
            return []
        return [m.get('name', '') for m in obj.members if isinstance(m, dict)]
    
    def get_pdf_url(self, obj):
        """Get PDF URL"""
        return obj.questions_file_path or obj.questions_file_path_hindi or None


class DebateDetailSerializer(serializers.ModelSerializer):
    """Detailed serializer for individual debate view"""
    lok_sabha = serializers.CharField(source='lok_sabha.number', allow_null=True)
    session = serializers.CharField(source='session.session_number')
    is_downloaded = serializers.BooleanField()
    file_size_mb = serializers.FloatField()
    institution = serializers.SerializerMethodField()
    
    class Meta:
        model = Debate
        fields = [
            'id',
            'debate_id',
            'debate_date',
            'debate_type',
            'debate_category',
            'language',
            'time_slot',
            'institution',
            'lok_sabha',
            'session',
            'status',
            'is_downloaded',
            'file_size_mb',
            'file_size',
            'page_count',
            'pdf_url',
            'download_attempts',
            'last_download_attempt',
            'error_message',
            'created_at',
            'updated_at',
            'last_scraped'
        ]
    
    def get_institution(self, obj):
        """Get institution name"""
        if obj.parent_institution:
            return obj.parent_institution.name
        return None


class DebateMasterDataSerializer(serializers.ModelSerializer):
    """Serializer for Debate Master Data (session-level metadata)"""
    lok_sabha = serializers.CharField(source='lok_sabha_number')
    rajya_sabha = serializers.CharField(source='rajya_sabha_number')
    session = serializers.CharField(source='session_number')
    institution = serializers.SerializerMethodField()
    date_count = serializers.IntegerField(source='total_debate_days')
    completion_percentage = serializers.SerializerMethodField()
    date_range_formatted = serializers.SerializerMethodField()
    
    class Meta:
        model = DebateMasterData
        fields = [
            'id',
            'institution',
            'lok_sabha',
            'rajya_sabha',
            'session',
            'debate_category',
            'date_count',
            'total_debate_days',
            'debates_discovered',
            'debates_downloaded',
            'completion_percentage',
            'api_source',
            'date_range_start',
            'date_range_end',
            'date_range_formatted',
            'is_complete',
            'discovery_success',
            'created_at',
            'updated_at',
            'last_fetched'
        ]
    
    def get_institution(self, obj):
        """Get institution name"""
        if obj.parent_institution:
            return obj.parent_institution.name
        return None
    
    def get_completion_percentage(self, obj):
        """Calculate completion percentage"""
        if obj.debates_discovered == 0:
            return 0
        return round((obj.debates_downloaded / obj.debates_discovered) * 100, 2)
    
    def get_date_range_formatted(self, obj):
        """Format date range"""
        if obj.date_range_start and obj.date_range_end:
            return f"{obj.date_range_start} to {obj.date_range_end}"
        return None
