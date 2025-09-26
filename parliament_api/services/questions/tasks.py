from celery import shared_task
from django.utils import timezone
from django.db import transaction
from django.conf import settings
import logging
import os
import requests

from .models import Question, LokSabha, Session
from services.files.models import DocumentFile, DownloadQueue
from .question_download_service import QuestionDownloadService

logger = logging.getLogger(__name__)


@shared_task(bind=True, name='questions.download_question_pdf')
def download_question_pdf_task(self, question_id: int, pdf_url: str = None):
    """
    Celery task for downloading a single question PDF
    
    Args:
        question_id: ID of the Question to download PDF for
        pdf_url: Optional specific PDF URL to download
    """
    try:
        # Update task status
        self.update_state(
            state='PROGRESS',
            meta={'status': 'Starting PDF download...', 'progress': 0}
        )
        
        # Get the question
        question = Question.objects.get(id=question_id)
        
        # Initialize download service
        service = QuestionDownloadService()
        
        # Update progress
        self.update_state(
            state='PROGRESS',
            meta={'status': f'Downloading PDF for Q.{question.question_number}', 'progress': 25}
        )
        
        # Use provided URL or get from question
        if not pdf_url:
            pdf_urls = question.pdf_files if isinstance(question.pdf_files, list) else []
            if not pdf_urls:
                return {
                    'status': 'FAILED',
                    'question_id': question_id,
                    'error': 'No PDF URL available for this question'
                }
            pdf_url = pdf_urls[0]
        
        # Download PDF
        success = service.download_question_pdf(question, pdf_url)
        
        if success:
            # Update progress
            self.update_state(
                state='PROGRESS',
                meta={'status': 'PDF downloaded successfully', 'progress': 100}
            )
            
            return {
                'status': 'SUCCESS',
                'question_id': question_id,
                'question_number': question.question_number,
                'pdf_url': pdf_url,
                'message': f'PDF downloaded successfully for Q.{question.question_number}'
            }
        else:
            return {
                'status': 'FAILED',
                'question_id': question_id,
                'question_number': question.question_number,
                'error': 'PDF download failed'
            }
    
    except Question.DoesNotExist:
        return {
            'status': 'FAILED',
            'question_id': question_id,
            'error': 'Question not found'
        }
    except Exception as e:
        logger.error(f"Question PDF download task failed for question {question_id}: {str(e)}")
        return {
            'status': 'FAILED',
            'question_id': question_id,
            'error': str(e)
        }


@shared_task(bind=True, name='questions.bulk_download_question_pdfs')
def bulk_download_question_pdfs_task(self, question_ids: list, max_concurrent: int = 5):
    """
    Celery task for downloading multiple question PDFs with concurrency control
    
    Args:
        question_ids: List of Question IDs to download PDFs for
        max_concurrent: Maximum number of concurrent downloads
    """
    try:
        total_questions = len(question_ids)
        downloaded = 0
        failed = 0
        skipped = 0
        errors = []
        
        # Update initial progress
        self.update_state(
            state='PROGRESS',
            meta={
                'status': f'Starting bulk download of {total_questions} questions',
                'progress': 0,
                'total': total_questions,
                'downloaded': 0,
                'failed': 0,
                'skipped': 0
            }
        )
        
        # Process questions in batches
        for i, question_id in enumerate(question_ids):
            try:
                # Update progress
                progress = int((i / total_questions) * 90)  # 0-90% range
                self.update_state(
                    state='PROGRESS',
                    meta={
                        'status': f'Processing question {i+1}/{total_questions}',
                        'progress': progress,
                        'total': total_questions,
                        'downloaded': downloaded,
                        'failed': failed,
                        'skipped': skipped,
                        'current_question': question_id
                    }
                )
                
                # Get question
                question = Question.objects.get(id=question_id)
                
                # Check if already downloaded
                pdf_urls = question.pdf_files if isinstance(question.pdf_files, list) else []
                if not pdf_urls:
                    skipped += 1
                    continue
                
                pdf_url = pdf_urls[0]
                
                # Check if already downloaded
                existing_doc = DocumentFile.objects.filter(
                    question=question,
                    original_url=pdf_url,
                    status='completed'
                ).first()
                
                if existing_doc:
                    skipped += 1
                    continue
                
                # Download PDF
                success = download_question_pdf_task.delay(question_id, pdf_url).get()
                
                if success['status'] == 'SUCCESS':
                    downloaded += 1
                else:
                    failed += 1
                    errors.append(f"Q.{question.question_number}: {success.get('error', 'Unknown error')}")
            
            except Question.DoesNotExist:
                failed += 1
                errors.append(f"Question {question_id}: Not found")
            except Exception as e:
                failed += 1
                error_msg = f"Question {question_id}: {str(e)}"
                errors.append(error_msg)
                logger.error(error_msg)
        
        # Final progress update
        self.update_state(
            state='PROGRESS',
            meta={
                'status': 'Bulk download completed',
                'progress': 100,
                'total': total_questions,
                'downloaded': downloaded,
                'failed': failed,
                'skipped': skipped
            }
        )
        
        return {
            'status': 'SUCCESS',
            'total_questions': total_questions,
            'downloaded': downloaded,
            'failed': failed,
            'skipped': skipped,
            'errors': errors,
            'success_rate': (downloaded / total_questions * 100) if total_questions > 0 else 0
        }
    
    except Exception as e:
        logger.error(f"Bulk question PDF download task failed: {str(e)}")
        return {
            'status': 'FAILED',
            'error': str(e)
        }


@shared_task(bind=True, name='questions.process_download_queue')
def process_download_queue_task(self, max_items: int = 10):
    """
    Celery task for processing the question download queue
    
    Args:
        max_items: Maximum number of items to process
    """
    try:
        # Update task status
        self.update_state(
            state='PROGRESS',
            meta={'status': 'Processing download queue...', 'progress': 0}
        )
        
        # Initialize service
        service = QuestionDownloadService()
        
        # Process queue
        results = service.process_download_queue(max_items)
        
        # Update progress
        self.update_state(
            state='PROGRESS',
            meta={
                'status': 'Queue processing completed',
                'progress': 100,
                'processed': results['processed'],
                'successful': results['successful'],
                'failed': results['failed']
            }
        )
        
        return {
            'status': 'SUCCESS',
            'processed': results['processed'],
            'successful': results['successful'],
            'failed': results['failed'],
            'errors': results['errors']
        }
    
    except Exception as e:
        logger.error(f"Download queue processing task failed: {str(e)}")
        return {
            'status': 'FAILED',
            'error': str(e)
        }


@shared_task(bind=True, name='questions.scrape_questions')
def scrape_questions_task(self, 
                         loksabha_no: str,
                         session_no: str = None,
                         question_type: str = None,
                         start_date: str = None,
                         end_date: str = None,
                         job_id: int = None,
                         download_pdfs: bool = True):
    """
    Celery task for scraping questions (placeholder for future implementation)
    
    Args:
        loksabha_no: Lok Sabha number
        session_no: Session number (optional)
        question_type: Type of questions to scrape (optional)
        start_date: Start date in YYYY-MM-DD format (optional)
        end_date: End date in YYYY-MM-DD format (optional)
        job_id: ScrapingJob ID to update
        download_pdfs: Whether to download PDFs
    """
    try:
        # Update task status
        self.update_state(
            state='PROGRESS',
            meta={'status': 'Starting question scraping...', 'progress': 0}
        )
        
        # This is a placeholder for future question scraping implementation
        # For now, we'll just return a success message
        
        self.update_state(
            state='PROGRESS',
            meta={'status': 'Question scraping completed', 'progress': 100}
        )
        
        return {
            'status': 'SUCCESS',
            'message': 'Question scraping task completed (placeholder implementation)',
            'loksabha_no': loksabha_no,
            'session_no': session_no,
            'question_type': question_type,
            'download_pdfs': download_pdfs
        }
    
    except Exception as e:
        logger.error(f"Question scraping task failed: {str(e)}")
        return {
            'status': 'FAILED',
            'error': str(e)
        }


@shared_task(bind=True, name='questions.get_download_statistics')
def get_download_statistics_task(self):
    """
    Celery task for getting question download statistics
    """
    try:
        # Update task status
        self.update_state(
            state='PROGRESS',
            meta={'status': 'Calculating statistics...', 'progress': 0}
        )
        
        # Initialize service
        service = QuestionDownloadService()
        
        # Get statistics
        stats = service.get_download_statistics()
        
        # Update progress
        self.update_state(
            state='PROGRESS',
            meta={'status': 'Statistics calculated', 'progress': 100}
        )
        
        return {
            'status': 'SUCCESS',
            'statistics': stats
        }
    
    except Exception as e:
        logger.error(f"Download statistics task failed: {str(e)}")
        return {
            'status': 'FAILED',
            'error': str(e)
        }
