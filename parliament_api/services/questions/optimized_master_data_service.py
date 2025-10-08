"""
Optimized version of QuestionMasterDataService with performance improvements
This replaces the inefficient order_by('?') with indexed random selection
"""
import random
import logging
from typing import List, Optional
from .models import QuestionMasterData

logger = logging.getLogger(__name__)


class OptimizedQuestionMasterDataService:
    """
    Optimized service for QuestionMasterData operations
    Uses indexed random_selection field instead of order_by('?')
    """
    
    def get_questions_for_download(
        self, 
        lok_sabha_number: Optional[str] = None,
        session_number: Optional[str] = None,
        question_type: Optional[str] = None,
        limit: Optional[int] = None,
        pending_only: bool = True
    ) -> List[QuestionMasterData]:
        """
        Get questions ready for PDF download with optimized random selection
        
        PERFORMANCE IMPROVEMENT:
        - Old: order_by('?') causes full table scan and sort (O(n log n))
        - New: Uses indexed random_selection field (O(log n))
        
        Args:
            lok_sabha_number: Filter by Lok Sabha
            session_number: Filter by session
            question_type: Filter by question type
            limit: Limit number of results
            pending_only: If True, only return questions without downloaded PDFs
            
        Returns:
            List of QuestionMasterData objects with PDF URLs that need downloading
        """
        try:
            # Start with questions that have PDF URLs
            queryset = QuestionMasterData.objects.exclude(questions_file_path='')
            
            if pending_only:
                # Use the pdf_downloaded field to filter out already downloaded items
                queryset = queryset.filter(pdf_downloaded=False)
                logger.info(f"Filtering for pending downloads (pdf_downloaded=False)")
            
            if lok_sabha_number:
                queryset = queryset.filter(lok_sabha_number=lok_sabha_number)
            
            if session_number:
                queryset = queryset.filter(session_number=session_number)
            
            if question_type:
                queryset = queryset.filter(question_type=question_type)
            
            # OPTIMIZED RANDOM SELECTION
            # Use indexed random_selection field for efficient random ordering
            random_threshold = random.random()
            
            # Get items with random_selection >= threshold
            result_queryset = queryset.filter(
                random_selection__gte=random_threshold
            ).order_by('random_selection')
            
            if limit:
                # Check if we have enough results
                count = result_queryset.count()
                if count < limit:
                    # Need to wrap around - get items from the beginning
                    remaining = limit - count
                    wrap_queryset = queryset.filter(
                        random_selection__lt=random_threshold
                    ).order_by('random_selection')[:remaining]
                    
                    # Combine results
                    results = list(result_queryset[:limit]) + list(wrap_queryset)
                else:
                    results = list(result_queryset[:limit])
            else:
                results = list(result_queryset)
            
            logger.info(f"get_questions_for_download: Found {len(results)} pending questions (pending_only={pending_only})")
            
            return results
            
        except Exception as e:
            logger.error(f"Failed to get questions for download: {e}")
            raise
    
    @staticmethod
    def refresh_random_selection(batch_size: int = 10000):
        """
        Refresh random_selection values for all records
        Call this periodically (e.g., daily) to ensure good randomization
        
        Args:
            batch_size: Number of records to update in each batch
        """
        try:
            total = QuestionMasterData.objects.count()
            updated = 0
            
            logger.info(f"Refreshing random_selection for {total} records...")
            
            # Update in batches to avoid memory issues
            for offset in range(0, total, batch_size):
                batch = QuestionMasterData.objects.all()[offset:offset + batch_size]
                
                # Update random_selection for each item in batch
                for item in batch:
                    item.random_selection = random.random()
                
                # Bulk update
                QuestionMasterData.objects.bulk_update(
                    batch, ['random_selection'], batch_size=1000
                )
                
                updated += len(batch)
                logger.info(f"Updated {updated}/{total} records...")
            
            logger.info(f"Successfully refreshed random_selection for {total} records")
            
        except Exception as e:
            logger.error(f"Failed to refresh random_selection: {e}")
            raise
