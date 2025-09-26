import os
import time
import requests
import logging
from datetime import datetime
from typing import List, Dict, Optional
from django.utils import timezone
from django.conf import settings

from .models import Question
from services.files.models import DocumentFile, DownloadQueue

logger = logging.getLogger(__name__)


class QuestionDownloadService:
    """
    Service for downloading question PDFs following the same pattern as debates
    """
    
    def __init__(self):
        self.session = requests.Session()
        # Set headers similar to debate scraper
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36'
        })
    
    def queue_question_pdf_download(self, question: Question, pdf_url: str) -> DocumentFile:
        """Queue a question PDF for download using the existing infrastructure"""
        
        # Generate filename
        file_name = self._generate_filename(question)
        
        # Create document file record
        doc_file, created = DocumentFile.objects.get_or_create(
            original_url=pdf_url,
            question=question,
            defaults={
                'document_category': 'parl_question',
                'file_type': 'question',
                'file_name': file_name,
                'download_priority': 5
            }
        )
        
        # Only queue if not already downloaded
        if not doc_file.is_downloaded:
            # Create download queue entry
            DownloadQueue.objects.get_or_create(
                document_file=doc_file,
                defaults={
                    'status': 'queued',
                    'priority': doc_file.download_priority
                }
            )
            
            logger.info(f"Queued PDF download for question {question.question_number}")
        
        return doc_file
    
    def download_question_pdf(self, question: Question, pdf_url: str) -> bool:
        """Download PDF for a specific question following debate pattern"""
        
        if not pdf_url:
            logger.warning(f"No PDF URL for question {question.question_number}")
            return False
        
        # Get or create document file
        doc_file = self.queue_question_pdf_download(question, pdf_url)
        
        try:
            logger.info(f"Downloading PDF from {pdf_url}")
            
            # Update status
            doc_file.status = 'downloading'
            doc_file.download_attempts += 1
            doc_file.last_download_attempt = timezone.now()
            doc_file.save()
            
            # Download PDF with retry logic for SSL issues
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    response = self.session.get(pdf_url, timeout=30, stream=True, verify=True)
                    response.raise_for_status()
                    break
                except requests.exceptions.SSLError as ssl_error:
                    if attempt < max_retries - 1:
                        logger.warning(f"SSL error on attempt {attempt + 1}, retrying: {ssl_error}")
                        time.sleep(1)  # Brief delay before retry
                        continue
                    else:
                        logger.error(f"SSL error after {max_retries} attempts: {ssl_error}")
                        raise
                except Exception as e:
                    logger.error(f"Download error on attempt {attempt + 1}: {e}")
                    if attempt < max_retries - 1:
                        time.sleep(1)
                        continue
                    else:
                        raise
            
            # Save to file
            file_name = doc_file.file_name
            file_path = os.path.join(settings.MEDIA_ROOT, 'questions', file_name)
            
            # Create directory if needed
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            
            # Write file
            with open(file_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            # Get file size
            file_size = os.path.getsize(file_path)
            
            # Update document file record
            doc_file.file_path = f'questions/{file_name}'
            doc_file.file_size = file_size
            doc_file.status = 'completed'
            doc_file.downloaded_at = timezone.now()
            doc_file.save()
            
            # Update download queue status
            queue_item = DownloadQueue.objects.filter(document_file=doc_file).first()
            if queue_item:
                queue_item.mark_completed()
            
            logger.info(f"Successfully downloaded question PDF: {file_name} ({file_size} bytes)")
            return True
            
        except Exception as e:
            logger.error(f"Failed to download question PDF: {e}")
            
            # Update status
            doc_file.status = 'failed'
            doc_file.download_error = str(e)
            doc_file.save()
            
            # Update download queue status
            queue_item = DownloadQueue.objects.filter(document_file=doc_file).first()
            if queue_item:
                queue_item.mark_failed(str(e))
            
            return False
    
    def bulk_download_questions(self, questions: List[Question], use_celery: bool = True) -> Dict:
        """Download PDFs for multiple questions using Celery tasks"""
        
        if use_celery:
            # Use Celery for bulk download
            question_ids = [q.id for q in questions]
            
            from .tasks import bulk_download_question_pdfs_task
            
            # Start Celery task
            task = bulk_download_question_pdfs_task.delay(question_ids)
            
            return {
                'total': len(questions),
                'task_id': task.id,
                'status': 'started',
                'message': 'Bulk download started via Celery. Use task status endpoint to monitor progress.'
            }
        else:
            # Original synchronous implementation
            results = {
                'total': len(questions),
                'queued': 0,
                'already_downloaded': 0,
                'no_pdf': 0,
                'errors': []
            }
            
            for question in questions:
                try:
                    # Get PDF URLs from question
                    pdf_urls = question.pdf_files if isinstance(question.pdf_files, list) else []
                    
                    if not pdf_urls:
                        results['no_pdf'] += 1
                        continue
                    
                    # Use first PDF URL
                    pdf_url = pdf_urls[0]
                    
                    # Check if already downloaded
                    existing_doc = DocumentFile.objects.filter(
                        question=question,
                        original_url=pdf_url,
                        status='completed'
                    ).first()
                    
                    if existing_doc:
                        results['already_downloaded'] += 1
                        continue
                    
                    # Queue for download
                    doc_file = self.queue_question_pdf_download(question, pdf_url)
                    results['queued'] += 1
                    
                except Exception as e:
                    error_msg = f"Q.{question.question_number}: {str(e)}"
                    results['errors'].append(error_msg)
                    logger.error(error_msg)
            
            return results
    
    def process_download_queue(self, max_items: int = 10, use_celery: bool = True) -> Dict:
        """Process pending question downloads from queue using Celery"""
        
        if use_celery:
            # Use Celery for queue processing
            from .tasks import process_download_queue_task
            
            # Start Celery task
            task = process_download_queue_task.delay(max_items)
            
            return {
                'task_id': task.id,
                'status': 'started',
                'max_items': max_items,
                'message': 'Queue processing started via Celery. Use task status endpoint to monitor progress.'
            }
        else:
            # Original synchronous implementation
            # Get pending question downloads
            pending_items = DownloadQueue.objects.filter(
                status='queued',
                document_file__document_category='parl_question'
            ).order_by('priority', 'created_at')[:max_items]
            
            results = {
                'processed': 0,
                'successful': 0,
                'failed': 0,
                'errors': []
            }
            
            for queue_item in pending_items:
                try:
                    doc_file = queue_item.document_file
                    question = doc_file.question
                    
                    if not question:
                        continue
                    
                    success = self.download_question_pdf(question, doc_file.original_url)
                    results['processed'] += 1
                    
                    if success:
                        results['successful'] += 1
                    else:
                        results['failed'] += 1
                        
                except Exception as e:
                    error_msg = f"Queue item {queue_item.id}: {str(e)}"
                    results['errors'].append(error_msg)
                    results['failed'] += 1
                    logger.error(error_msg)
            
            return results
    
    def _generate_filename(self, question: Question) -> str:
        """Generate consistent filename for question PDF"""
        question_type = question.question_type.lower().replace(' ', '_')
        return f"question_{question.question_number}_{question_type}.pdf"
    
    def get_download_statistics(self) -> Dict:
        """Get download statistics for questions"""
        
        question_files = DocumentFile.objects.filter(document_category='parl_question')
        
        stats = {
            'total_files': question_files.count(),
            'completed': question_files.filter(status='completed').count(),
            'pending': question_files.filter(status='pending').count(),
            'downloading': question_files.filter(status='downloading').count(),
            'failed': question_files.filter(status='failed').count(),
            'queued': DownloadQueue.objects.filter(
                document_file__document_category='parl_question',
                status='queued'
            ).count()
        }
        
        # Calculate total size
        completed_files = question_files.filter(status='completed')
        total_size = sum(f.file_size for f in completed_files if f.file_size)
        stats['total_size_bytes'] = total_size
        stats['total_size_mb'] = round(total_size / (1024 * 1024), 2)
        
        # Calculate average size
        if stats['completed'] > 0:
            stats['average_size_mb'] = round(stats['total_size_mb'] / stats['completed'], 2)
        else:
            stats['average_size_mb'] = 0
        
        return stats

