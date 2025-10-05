"""
Batch Writer Utility for Efficient Database Operations

Automatically accumulates records and writes in batches to optimize DB performance
and memory usage.
"""

import logging
from typing import List, Dict, Callable, Optional, Any
from django.db import transaction, models

logger = logging.getLogger(__name__)


class BatchWriter:
    """
    Smart batch collector that automatically flushes to database
    when threshold is reached
    
    Usage:
        writer = BatchWriter(
            model_class=QuestionMasterData,
            batch_size=2000,
            unique_fields=['question_number', 'lok_sabha_number', 'session_number'],
            update_fields=['subjects', 'ministry', 'date', ...]
        )
        
        for item in large_dataset:
            writer.add(item_data)
        
        writer.flush()  # Write remaining
        stats = writer.get_stats()
    """
    
    def __init__(
        self,
        model_class: models.Model,
        batch_size: int = 2000,
        unique_fields: List[str] = None,
        update_fields: List[str] = None,
        bulk_field: str = None
    ):
        """
        Initialize batch writer
        
        Args:
            model_class: Django model class to write to
            batch_size: Number of records to accumulate before auto-flush
            unique_fields: Fields that uniquely identify a record (for deduplication)
            update_fields: Fields to update if record exists
            bulk_field: Field to use for in_bulk() query (default: first unique_field)
        """
        self.model_class = model_class
        self.batch_size = batch_size
        self.unique_fields = unique_fields or ['id']
        self.update_fields = update_fields or []
        self.bulk_field = bulk_field or unique_fields[0] if unique_fields else 'id'
        
        # Accumulators
        self.pending_items = []
        
        # Statistics
        self.total_added = 0
        self.total_created = 0
        self.total_updated = 0
        self.total_skipped = 0
        self.flush_count = 0
        
        logger.info(f"BatchWriter initialized: {model_class.__name__}, batch_size={batch_size}")
    
    def add(self, item_data: Dict) -> None:
        """
        Add item to batch. Automatically flushes when batch_size is reached.
        
        Args:
            item_data: Dictionary with field values for the model
        """
        self.pending_items.append(item_data)
        self.total_added += 1
        
        # Auto-flush when batch is full
        if len(self.pending_items) >= self.batch_size:
            self.flush()
    
    def flush(self) -> Dict[str, int]:
        """
        Write all pending items to database and clear memory
        
        Returns:
            Dict with stats for this flush: {'created': X, 'updated': Y, 'skipped': Z}
        """
        if not self.pending_items:
            return {'created': 0, 'updated': 0, 'skipped': 0}
        
        flush_stats = {
            'created': 0,
            'updated': 0,
            'skipped': 0
        }
        
        try:
            # Step 1: Get unique identifiers from pending items
            bulk_field_values = []
            for item in self.pending_items:
                if self.bulk_field in item:
                    bulk_field_values.append(item[self.bulk_field])
            
            if not bulk_field_values:
                logger.warning(f"No valid items to flush (missing {self.bulk_field} field)")
                self.pending_items = []
                return flush_stats
            
            # Step 2: Single query to get all existing records
            existing_objects = self.model_class.objects.filter(
                **{f"{self.bulk_field}__in": bulk_field_values}
            ).in_bulk(field_name=self.bulk_field)
            
            # Step 3: Separate into create vs update
            to_create = []
            to_update = []
            
            for item_data in self.pending_items:
                bulk_value = item_data.get(self.bulk_field)
                
                if not bulk_value:
                    flush_stats['skipped'] += 1
                    continue
                
                if bulk_value in existing_objects:
                    # Update existing
                    obj = existing_objects[bulk_value]
                    for field, value in item_data.items():
                        if field not in self.unique_fields:  # Don't update unique fields
                            setattr(obj, field, value)
                    to_update.append(obj)
                else:
                    # Create new
                    to_create.append(self.model_class(**item_data))
            
            # Step 4: Bulk write to database
            with transaction.atomic():
                if to_create:
                    created_objects = self.model_class.objects.bulk_create(
                        to_create,
                        batch_size=1000,
                        ignore_conflicts=False
                    )
                    flush_stats['created'] = len(created_objects)
                    self.total_created += flush_stats['created']
                
                if to_update and self.update_fields:
                    self.model_class.objects.bulk_update(
                        to_update,
                        fields=self.update_fields,
                        batch_size=1000
                    )
                    flush_stats['updated'] = len(to_update)
                    self.total_updated += flush_stats['updated']
            
            self.flush_count += 1
            logger.info(
                f"Batch flush #{self.flush_count}: "
                f"{flush_stats['created']} created, "
                f"{flush_stats['updated']} updated, "
                f"{flush_stats['skipped']} skipped"
            )
            
        except Exception as e:
            logger.error(f"Error during batch flush: {e}")
            raise
        
        finally:
            # CRITICAL: Clear memory regardless of success/failure
            self.pending_items = []
        
        return flush_stats
    
    def get_stats(self) -> Dict[str, int]:
        """
        Get overall statistics
        
        Returns:
            Dict with total stats
        """
        return {
            'total_added': self.total_added,
            'total_created': self.total_created,
            'total_updated': self.total_updated,
            'total_skipped': self.total_skipped,
            'flush_count': self.flush_count,
            'pending_count': len(self.pending_items)
        }
    
    def __enter__(self):
        """Context manager support"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Auto-flush on context exit"""
        if self.pending_items:
            self.flush()
        return False


class MultiModelBatchWriter:
    """
    Manages multiple BatchWriters for different models
    Useful when processing data that affects multiple tables
    
    Usage:
        writers = MultiModelBatchWriter({
            'questions': BatchWriter(QuestionMasterData, batch_size=2000, ...),
            'debates': BatchWriter(Debate, batch_size=1500, ...)
        })
        
        for item in dataset:
            writers.add('questions', question_data)
            writers.add('debates', debate_data)
        
        writers.flush_all()
        stats = writers.get_all_stats()
    """
    
    def __init__(self, writers: Dict[str, BatchWriter]):
        """
        Args:
            writers: Dict of {name: BatchWriter instance}
        """
        self.writers = writers
    
    def add(self, writer_name: str, item_data: Dict) -> None:
        """Add item to a specific writer"""
        if writer_name in self.writers:
            self.writers[writer_name].add(item_data)
        else:
            raise ValueError(f"Writer '{writer_name}' not found")
    
    def flush(self, writer_name: str) -> Dict:
        """Flush a specific writer"""
        if writer_name in self.writers:
            return self.writers[writer_name].flush()
        return {}
    
    def flush_all(self) -> Dict[str, Dict]:
        """Flush all writers"""
        results = {}
        for name, writer in self.writers.items():
            results[name] = writer.flush()
        return results
    
    def get_all_stats(self) -> Dict[str, Dict]:
        """Get stats from all writers"""
        stats = {}
        for name, writer in self.writers.items():
            stats[name] = writer.get_stats()
        return stats
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.flush_all()
        return False


# Example usage with context manager
def example_usage():
    """Example of how to use BatchWriter"""
    
    # Method 1: Simple usage
    with BatchWriter(
        model_class=QuestionMasterData,
        batch_size=2000,
        unique_fields=['question_number', 'lok_sabha_number', 'session_number'],
        update_fields=['subjects', 'ministry', 'date', 'question_text']
    ) as writer:
        
        # Process large dataset
        for question_data in api_response['questions']:  # Could be 10,000 items
            writer.add({
                'question_number': question_data['quesNo'],
                'lok_sabha_number': '18',
                'session_number': 'V',
                'subjects': question_data['subjects'],
                'ministry': question_data['ministry'],
                # ... all fields
            })
            # Auto-flushes every 2000 records!
        
        # Auto-flushes remaining on context exit
    
    # Get final statistics
    print(writer.get_stats())
    # {'total_added': 10000, 'total_created': 9500, 'total_updated': 500, ...}
