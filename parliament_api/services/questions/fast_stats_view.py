"""
Fast, lightweight statistics views optimized for continuous download monitoring
These endpoints skip expensive aggregations and only return essential counts
"""
import logging
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from drf_spectacular.utils import extend_schema
from django.db.models import Count
from django.utils import timezone

from .models import QuestionMasterData, ParliamentInstitution

logger = logging.getLogger(__name__)


class FastDownloadStatsView(APIView):
    """Super fast download statistics for both LS and RS questions"""
    permission_classes = [IsAuthenticated]
    
    @extend_schema(
        description="Get fast download statistics for questions (optimized for speed)",
        tags=['Questions']
    )
    def get(self, request):
        """Get fast question download statistics"""
        try:
            # Get institutions
            ls_inst = ParliamentInstitution.objects.get(name='lok_sabha')
            rs_inst = ParliamentInstitution.objects.get(name='rajya_sabha')
            
            # FAST queries: Only count, no aggregations
            # LS Questions
            ls_total = QuestionMasterData.objects.filter(
                parent_institution=ls_inst
            ).exclude(questions_file_path='').count()
            
            ls_downloaded = QuestionMasterData.objects.filter(
                parent_institution=ls_inst,
                pdf_downloaded=True
            ).count()
            
            # RS Questions
            rs_total = QuestionMasterData.objects.filter(
                parent_institution=rs_inst
            ).exclude(questions_file_path='').count()
            
            rs_downloaded = QuestionMasterData.objects.filter(
                parent_institution=rs_inst,
                pdf_downloaded=True
            ).count()
            
            return Response({
                'lok_sabha': {
                    'total_with_pdf': ls_total,
                    'downloaded': ls_downloaded,
                    'pending': ls_total - ls_downloaded
                },
                'rajya_sabha': {
                    'total_with_pdf': rs_total,
                    'downloaded': rs_downloaded,
                    'pending': rs_total - rs_downloaded
                },
                'combined': {
                    'total_with_pdf': ls_total + rs_total,
                    'downloaded': ls_downloaded + rs_downloaded,
                    'pending': (ls_total - ls_downloaded) + (rs_total - rs_downloaded)
                },
                'generated_at': timezone.now().isoformat()
            })
            
        except Exception as e:
            logger.error(f"Error getting fast download stats: {e}")
            return Response({
                'error': str(e)
            }, status=500)
