"""
Optimized statistics views using materialized views for instant response
"""
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from drf_spectacular.utils import extend_schema
from django.db import connection
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)


class OptimizedQuestionStatsView(APIView):
    """Ultra-fast question statistics using materialized views"""
    permission_classes = [IsAuthenticated]
    
    @extend_schema(
        description="Get question statistics from materialized view (instant response)",
        tags=['Questions']
    )
    def get(self, request):
        """Get statistics from materialized view"""
        try:
            with connection.cursor() as cursor:
                # Query the materialized view directly
                cursor.execute("""
                    SELECT 
                        pi.name as institution_name,
                        mqs.total_questions,
                        mqs.total_with_pdf,
                        mqs.downloaded,
                        mqs.pending,
                        mqs.starred,
                        mqs.unstarred,
                        mqs.short_notice,
                        mqs.unique_lok_sabhas,
                        mqs.unique_sessions,
                        mqs.earliest_date,
                        mqs.latest_date,
                        mqs.last_refreshed
                    FROM mv_question_statistics mqs
                    JOIN questions_parliamentinstitution pi ON mqs.parent_institution_id = pi.id
                    WHERE pi.name IN ('lok_sabha', 'rajya_sabha')
                """)
                
                results = cursor.fetchall()
                
                stats = {}
                for row in results:
                    institution = row[0]
                    stats[institution] = {
                        'total_questions': row[1],
                        'total_with_pdf': row[2],
                        'downloaded': row[3],
                        'pending': row[4],
                        'by_type': {
                            'starred': row[5],
                            'unstarred': row[6],
                            'short_notice': row[7]
                        },
                        'coverage': {
                            'unique_lok_sabhas': row[8],
                            'unique_sessions': row[9],
                            'date_range': {
                                'earliest': row[10].isoformat() if row[10] else None,
                                'latest': row[11].isoformat() if row[11] else None
                            }
                        },
                        'last_refreshed': row[12].isoformat() if row[12] else None
                    }
                
                # Calculate combined stats
                combined = {
                    'total_with_pdf': sum(s['total_with_pdf'] for s in stats.values()),
                    'downloaded': sum(s['downloaded'] for s in stats.values()),
                    'pending': sum(s['pending'] for s in stats.values())
                }
                
                return Response({
                    'status': 'success',
                    'source': 'materialized_view',
                    'lok_sabha': stats.get('lok_sabha', {}),
                    'rajya_sabha': stats.get('rajya_sabha', {}),
                    'combined': combined,
                    'generated_at': timezone.now().isoformat()
                })
                
        except Exception as e:
            logger.error(f"Error querying materialized view: {e}")
            # Fallback to regular query if materialized view doesn't exist
            return Response({
                'error': 'Materialized view not available. Run migrations first.',
                'details': str(e)
            }, status=503)


class RefreshQuestionStatsView(APIView):
    """Refresh the materialized view for question statistics"""
    permission_classes = [IsAuthenticated]
    
    @extend_schema(
        description="Manually refresh the question statistics materialized view",
        tags=['Questions']
    )
    def post(self, request):
        """Refresh materialized view"""
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT refresh_question_statistics();")
                
            return Response({
                'status': 'success',
                'message': 'Statistics refreshed successfully',
                'refreshed_at': timezone.now().isoformat()
            })
            
        except Exception as e:
            logger.error(f"Error refreshing materialized view: {e}")
            return Response({
                'error': 'Failed to refresh statistics',
                'details': str(e)
            }, status=500)


class OptimizedDebateStatsView(APIView):
    """Ultra-fast debate statistics using materialized views"""
    permission_classes = [IsAuthenticated]
    
    @extend_schema(
        description="Get debate statistics from materialized view (instant response)",
        tags=['Debates']
    )
    def get(self, request):
        """Get statistics from materialized view"""
        try:
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT 
                        pi.name as institution_name,
                        mds.total_debates,
                        mds.completed,
                        mds.pending,
                        mds.downloading,
                        mds.failed,
                        mds.not_available,
                        mds.uncorrected,
                        mds.corrected,
                        mds.synopsis,
                        mds.verbatim,
                        mds.earliest_date,
                        mds.latest_date,
                        mds.last_refreshed
                    FROM mv_debate_statistics mds
                    JOIN questions_parliamentinstitution pi ON mds.parent_institution_id = pi.id
                """)
                
                results = cursor.fetchall()
                
                stats = {}
                for row in results:
                    institution = row[0]
                    stats[institution] = {
                        'total_debates': row[1],
                        'by_status': {
                            'completed': row[2],
                            'pending': row[3],
                            'downloading': row[4],
                            'failed': row[5],
                            'not_available': row[6]
                        },
                        'by_category': {
                            'uncorrected': row[7],
                            'corrected': row[8],
                            'synopsis': row[9],
                            'verbatim': row[10]
                        },
                        'date_range': {
                            'earliest': row[11].isoformat() if row[11] else None,
                            'latest': row[12].isoformat() if row[12] else None
                        },
                        'last_refreshed': row[13].isoformat() if row[13] else None
                    }
                
                return Response({
                    'status': 'success',
                    'source': 'materialized_view',
                    'stats': stats,
                    'generated_at': timezone.now().isoformat()
                })
                
        except Exception as e:
            logger.error(f"Error querying debate materialized view: {e}")
            return Response({
                'error': 'Materialized view not available. Run migrations first.',
                'details': str(e)
            }, status=503)
