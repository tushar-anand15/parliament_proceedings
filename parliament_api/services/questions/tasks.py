from celery import shared_task
from django.utils import timezone
from django.db import transaction
from django.conf import settings
import logging
import os
import requests

from .models import Question, QuestionMasterData, LokSabha, Session, ParliamentInstitution
from services.files.models import DocumentFile, DownloadQueue
from .question_download_service import QuestionDownloadService
from .rs_master_data_service import RajyaSabhaMasterDataService
from services.files.pdf_download_service import UnifiedPDFDownloadService

logger = logging.getLogger(__name__)


@shared_task(bind=True, name='questions.download_question_pdf',
              autoretry_for=(Exception,),
              retry_kwargs={'max_retries': 3, 'countdown': 60},
              retry_backoff=True,
              retry_backoff_max=300,
              retry_jitter=True)
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
        
        # Initialize unified download service
        service = UnifiedPDFDownloadService()
        
        # Update progress
        self.update_state(
            state='PROGRESS',
            meta={'status': f'Downloading PDF for Q.{question.question_number}', 'progress': 25}
        )
        
        # Download PDF using unified service
        result = service.download_question_pdf_unified(question, pdf_url)
        success = result.get('success', False)
        
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
                'filename': result.get('filename', ''),
                'file_size': result.get('file_size', 0),
                'gcs_uploaded': result.get('gcs_result', {}).get('success', False),
                'message': f'PDF downloaded successfully for Q.{question.question_number}'
            }
        else:
            return {
                'status': 'FAILED',
                'question_id': question_id,
                'question_number': question.question_number,
                'error': result.get('error', 'PDF download failed')
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


@shared_task(bind=True, name='questions.bulk_download_question_pdfs',
              autoretry_for=(Exception,),
              retry_kwargs={'max_retries': 2, 'countdown': 120},
              retry_backoff=True,
              retry_backoff_max=600,
              retry_jitter=True)
def bulk_download_question_pdfs_task(self, question_ids: list, max_concurrent: int = 5):
    """
    Celery task for downloading multiple question PDFs with TRUE PARALLELISM
    
    This task now:
    1. Collects all questions that need downloading (metadata phase)
    2. Dispatches ALL downloads in parallel using celery.group()
    3. Returns immediately without waiting for downloads to complete
    
    Args:
        question_ids: List of Question IDs to download PDFs for
        max_concurrent: Maximum number of concurrent downloads (note: actual concurrency controlled by worker pool)
    """
    try:
        from celery import group
        
        total_questions = len(question_ids)
        skipped = 0
        download_tasks = []
        
        # Update initial progress
        self.update_state(
            state='PROGRESS',
            meta={
                'status': f'Preparing {total_questions} questions for parallel download',
                'progress': 10,
                'total': total_questions,
                'phase': 'metadata_collection'
            }
        )
        
        logger.info(f"Starting parallel bulk download for {total_questions} questions")
        
        # PHASE 1: Collect all questions that need downloading (fast metadata check)
        for i, question_id in enumerate(question_ids):
            try:
                # Update progress
                if i % 10 == 0:  # Update every 10 items to reduce overhead
                    progress = 10 + int((i / total_questions) * 40)  # 10-50% range
                    self.update_state(
                        state='PROGRESS',
                        meta={
                            'status': f'Checking question {i+1}/{total_questions}',
                            'progress': progress,
                            'total': total_questions,
                            'phase': 'metadata_collection'
                        }
                    )
                
                # Get question
                question = Question.objects.get(id=question_id)
                
                # Check if has PDF URL
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
                
                # Add to download list
                download_tasks.append(
                    download_question_pdf_task.si(question_id, pdf_url)
                )
            
            except Question.DoesNotExist:
                skipped += 1
                logger.warning(f"Question {question_id}: Not found")
            except Exception as e:
                skipped += 1
                logger.error(f"Error preparing question {question_id}: {str(e)}")
        
        # PHASE 2: Dispatch ALL downloads in parallel
        tasks_to_dispatch = len(download_tasks)
        
        self.update_state(
            state='PROGRESS',
            meta={
                'status': f'Dispatching {tasks_to_dispatch} downloads in parallel',
                'progress': 60,
                'total': total_questions,
                'tasks_to_dispatch': tasks_to_dispatch,
                'skipped': skipped,
                'phase': 'dispatching'
            }
        )
        
        if download_tasks:
            # Use group() for TRUE PARALLELISM - all tasks dispatched at once
            job = group(download_tasks)
            group_result = job.apply_async()
            
            logger.info(f"✅ PARALLEL DISPATCH: {tasks_to_dispatch} PDF downloads dispatched simultaneously!")
            logger.info(f"   Group ID: {group_result.id}")
            logger.info(f"   Worker pool will process these {tasks_to_dispatch} tasks in parallel")
            
            # Return immediately - don't wait!
            return {
                'status': 'DISPATCHED',
                'message': 'All downloads dispatched in parallel - check Celery Flower for progress',
                'total_questions': total_questions,
                'tasks_dispatched': tasks_to_dispatch,
                'skipped': skipped,
                'group_id': group_result.id,
                'note': 'Downloads are running in parallel. Use group_id to track progress.'
            }
        else:
            logger.info(f"No downloads needed - all {skipped} questions skipped")
            return {
                'status': 'SUCCESS',
                'total_questions': total_questions,
                'tasks_dispatched': 0,
                'skipped': skipped,
                'message': 'No downloads needed - all questions already downloaded or have no PDFs'
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


@shared_task(bind=True, name='questions.bulk_download_question_pdfs_from_master_data',
              autoretry_for=(Exception,),
              retry_kwargs={'max_retries': 3, 'countdown': 60},
              retry_backoff=True,
              retry_backoff_max=300,
              retry_jitter=True)
def bulk_download_question_pdfs_from_master_data_task(self, master_data_ids: list):
    """
    Celery task for bulk downloading question PDFs from master data
    
    Args:
        master_data_ids: List of QuestionMasterData IDs to process
    """
    try:
        # Update task status
        self.update_state(
            state='PROGRESS',
            meta={'status': 'Starting bulk download from master data...', 'progress': 0}
        )
        
        # Get master data objects
        master_data_list = QuestionMasterData.objects.filter(id__in=master_data_ids)
        total_count = master_data_list.count()
        
        if total_count == 0:
            return {
                'status': 'FAILED',
                'error': 'No master data found with provided IDs'
            }
        
        # Update progress
        self.update_state(
            state='PROGRESS',
            meta={'status': f'Processing {total_count} questions from master data', 'progress': 10}
        )
        
        # Initialize download service
        service = QuestionDownloadService()
        
        # Process downloads
        results = {
            'total': total_count,
            'queued': 0,
            'already_downloaded': 0,
            'no_pdf': 0,
            'errors': []
        }
        
        for i, master_data in enumerate(master_data_list, 1):
            try:
                # Update progress
                progress = 10 + (i / total_count) * 80
                self.update_state(
                    state='PROGRESS',
                    meta={
                        'status': f'Processing question {i}/{total_count}: Q.{master_data.question_number}',
                        'progress': progress
                    }
                )
                
                # Get PDF URL from master data
                pdf_url = master_data.get_pdf_url()
                
                if not pdf_url:
                    results['no_pdf'] += 1
                    continue
                
                # Create or get corresponding Question object
                question = service._create_question_from_master_data(master_data)
                
                # Check if already downloaded
                existing_doc = DocumentFile.objects.filter(
                    question=question,
                    original_url=pdf_url,
                    status='completed'
                ).first()
                
                if existing_doc:
                    results['already_downloaded'] += 1
                    continue
                
                # Download immediately to GCS
                success = service.download_question_pdf(question, pdf_url)
                if success:
                    results['queued'] += 1
                else:
                    results['errors'].append(f"Q.{master_data.question_number}: Download failed")
                
            except Exception as e:
                error_msg = f"Q.{master_data.question_number}: {str(e)}"
                results['errors'].append(error_msg)
                logger.error(error_msg)
        
        # Final status update
        self.update_state(
            state='PROGRESS',
            meta={
                'status': 'Bulk download from master data completed',
                'progress': 100,
                'results': results
            }
        )
        
        return {
            'status': 'SUCCESS',
            'message': f'Bulk download from master data completed: {results["queued"]} queued, {results["already_downloaded"]} already downloaded',
            'results': results
        }
        
    except Exception as e:
        logger.error(f"Bulk download from master data task failed: {str(e)}")
        
        self.update_state(
            state='FAILURE',
            meta={'status': 'Task failed', 'error': str(e)}
        )
        
        return {
            'status': 'FAILED',
            'error': str(e)
        }


# ============================================================================
# RAJYA SABHA TASKS (Integrated into existing tasks.py)
# ============================================================================

@shared_task(bind=True, name='rs_questions.scrape_rs_questions',
              autoretry_for=(Exception,),
              retry_kwargs={'max_retries': 3, 'countdown': 60},
              retry_backoff=True,
              retry_backoff_max=300,
              retry_jitter=True)
def scrape_rs_questions_task(self, 
                            session_no: str,
                            download_pdfs: bool = True,
                            job_id: int = None):
    """
    Celery task for scraping Rajya Sabha questions
    
    Args:
        session_no: RS Session number (e.g., "268")
        download_pdfs: Whether to download PDFs
        job_id: ScrapingJob ID to update (optional)
    """
    try:
        # Update task status
        self.update_state(
            state='PROGRESS',
            meta={'status': 'Starting RS question scraping...', 'progress': 0}
        )
        
        # Initialize RS service
        rs_service = RajyaSabhaMasterDataService()
        
        # Update progress
        self.update_state(
            state='PROGRESS',
            meta={'status': f'Fetching RS questions for session {session_no}...', 'progress': 10}
        )
        
        # Fetch questions for session
        result = rs_service.fetch_questions_for_session(session_no)
        
        if result.get('status') != 'SUCCESS':
            error_msg = f"Failed to fetch RS questions: {result.get('message', 'Unknown error')}"
            logger.error(error_msg)
            return {'status': 'FAILED', 'error': error_msg}
        
        questions_created = result.get('created', 0)
        questions_updated = result.get('updated', 0)
        total_questions = questions_created + questions_updated
        
        # Update progress
        self.update_state(
            state='PROGRESS',
            meta={
                'status': f'Scraped {total_questions} RS questions, preparing downloads...',
                'progress': 50,
                'questions_created': questions_created,
                'questions_updated': questions_updated
            }
        )
        
        pdfs_queued = 0
        if download_pdfs:
            # Get RS questions with PDF URLs for this session
            rs_institution = ParliamentInstitution.objects.get(name='rajya_sabha')
            questions_with_pdfs = QuestionMasterData.objects.filter(
                parent_institution=rs_institution,
                session_number=session_no,
                pdf_downloaded=False  # FIXED: Only download questions without PDFs in GCS
            ).exclude(questions_file_path='')
            
            logger.info(f"Found {questions_with_pdfs.count()} RS questions with PDFs to download")
            
            # Prepare bulk download list
            download_specs = []
            for master_data in questions_with_pdfs:
                download_specs.append({
                    'document_type': 'rs_question',
                    'document_id': master_data.id,
                    'pdf_url': master_data.get_pdf_url()
                })
            
            if download_specs:
                # Update progress
                self.update_state(
                    state='PROGRESS',
                    meta={
                        'status': f'Queuing {len(download_specs)} RS question PDFs for download...',
                        'progress': 75
                    }
                )
                
                # Queue bulk download task
                from services.files.tasks import bulk_download_pdfs_unified_task
                bulk_task = bulk_download_pdfs_unified_task.delay(download_specs)
                pdfs_queued = len(download_specs)
                
                logger.info(f"Queued {pdfs_queued} RS question PDFs for download (task: {bulk_task.id})")
        
        # Final progress update
        self.update_state(
            state='PROGRESS',
            meta={
                'status': 'RS question scraping completed',
                'progress': 100,
                'questions_created': questions_created,
                'questions_updated': questions_updated,
                'pdfs_queued': pdfs_queued
            }
        )
        
        return {
            'status': 'SUCCESS',
            'institution': 'rajya_sabha',
            'session_no': session_no,
            'questions_created': questions_created,
            'questions_updated': questions_updated,
            'total_questions': total_questions,
            'pdfs_queued': pdfs_queued,
            'message': f'Successfully scraped {total_questions} RS questions for session {session_no}'
        }
        
    except Exception as e:
        error_msg = f"RS question scraping task failed: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return {'status': 'FAILED', 'error': error_msg}


@shared_task(bind=True, name='rs_questions.download_rs_question_pdf',
              autoretry_for=(Exception,),
              retry_kwargs={'max_retries': 3, 'countdown': 60},
              retry_backoff=True,
              retry_backoff_max=300,
              retry_jitter=True)
def download_rs_question_pdf_task(self, master_data_id: int, pdf_url: str = None):
    """
    Celery task for downloading a single RS question PDF
    
    Args:
        master_data_id: ID of the QuestionMasterData to download PDF for
        pdf_url: Optional specific PDF URL to download
    """
    try:
        # Update task status
        self.update_state(
            state='PROGRESS',
            meta={'status': 'Starting RS question PDF download...', 'progress': 0}
        )
        
        # Get the master data
        master_data = QuestionMasterData.objects.get(id=master_data_id)
        
        # Use unified download task
        from services.files.tasks import download_pdf_unified_task
        result = download_pdf_unified_task.delay('rs_question', master_data_id, pdf_url).get()
        
        if result['status'] == 'SUCCESS':
            # Update progress
            self.update_state(
                state='PROGRESS',
                meta={'status': 'RS question PDF downloaded successfully', 'progress': 100}
            )
            
            return {
                'status': 'SUCCESS',
                'master_data_id': master_data_id,
                'question_number': master_data.question_number,
                'session_number': master_data.session_number,
                'filename': result['filename'],
                'message': f'PDF downloaded successfully for RS Q.{master_data.question_number}'
            }
        else:
            return {
                'status': 'FAILED',
                'master_data_id': master_data_id,
                'question_number': master_data.question_number,
                'error': result.get('error', 'Download failed')
            }
    
    except QuestionMasterData.DoesNotExist:
        return {
            'status': 'FAILED',
            'master_data_id': master_data_id,
            'error': 'RS Question master data not found'
        }
    except Exception as e:
        logger.error(f"RS question PDF download task failed for master_data {master_data_id}: {str(e)}")
        return {
            'status': 'FAILED',
            'master_data_id': master_data_id,
            'error': str(e)
        }


@shared_task(bind=True, name='rs_questions.bulk_download_rs_question_pdfs',
              autoretry_for=(Exception,),
              retry_kwargs={'max_retries': 2, 'countdown': 120},
              retry_backoff=True,
              retry_backoff_max=600,
              retry_jitter=True)
def bulk_download_rs_question_pdfs_task(self, master_data_ids: list):
    """
    Celery task for downloading multiple RS question PDFs with TRUE PARALLELISM
    
    Args:
        master_data_ids: List of QuestionMasterData IDs to download PDFs for
    """
    try:
        from celery import group
        from services.files.tasks import download_pdf_unified_task
        
        total_questions = len(master_data_ids)
        
        # Update initial progress
        self.update_state(
            state='PROGRESS',
            meta={
                'status': f'Preparing {total_questions} RS questions for parallel download',
                'progress': 10,
                'total': total_questions,
                'phase': 'metadata_collection'
            }
        )
        
        logger.info(f"Starting parallel bulk download for {total_questions} RS questions")
        
        # Prepare download tasks for parallel dispatch
        download_tasks = []
        skipped = 0
        
        for master_data_id in master_data_ids:
            try:
                master_data = QuestionMasterData.objects.get(id=master_data_id)
                pdf_url = master_data.get_pdf_url()
                
                if pdf_url:
                    # Create task signature for this download
                    download_tasks.append(
                        download_pdf_unified_task.si('rs_question', master_data_id, pdf_url)
                    )
                else:
                    skipped += 1
            except QuestionMasterData.DoesNotExist:
                logger.warning(f"RS QuestionMasterData {master_data_id} not found")
                skipped += 1
                continue
        
        if not download_tasks:
            return {
                'status': 'SUCCESS',
                'message': 'No RS questions with PDFs found to download',
                'total_questions': total_questions,
                'tasks_dispatched': 0,
                'skipped': skipped
            }
        
        # Update progress
        tasks_to_dispatch = len(download_tasks)
        self.update_state(
            state='PROGRESS',
            meta={
                'status': f'Dispatching {tasks_to_dispatch} RS question downloads in parallel',
                'progress': 50,
                'total': total_questions,
                'tasks_to_dispatch': tasks_to_dispatch,
                'skipped': skipped,
                'phase': 'dispatching'
            }
        )
        
        # Execute parallel bulk download using group()
        job = group(download_tasks)
        group_result = job.apply_async()
        
        logger.info(f"✅ PARALLEL DISPATCH: {tasks_to_dispatch} RS question PDF downloads dispatched simultaneously!")
        logger.info(f"   Group ID: {group_result.id}")
        logger.info(f"   Worker pool will process these {tasks_to_dispatch} tasks in parallel")
        
        # Return immediately - don't wait!
        return {
            'status': 'DISPATCHED',
            'message': 'All RS question downloads dispatched in parallel - check Celery Flower for progress',
            'institution': 'rajya_sabha',
            'total_questions': total_questions,
            'tasks_dispatched': tasks_to_dispatch,
            'skipped': skipped,
            'group_id': group_result.id,
            'note': 'RS question downloads are running in parallel. Use group_id to track progress.'
        }
        
    except Exception as e:
        logger.error(f"RS bulk question PDF download task failed: {str(e)}")
        return {
            'status': 'FAILED',
            'error': str(e)
        }


@shared_task(bind=True, name='rs_questions.initialize_rs_master_data')
def initialize_rs_master_data_task(self, force_update: bool = False):
    """
    Celery task for initializing RS master data
    
    Args:
        force_update: Whether to force update existing data
    """
    try:
        # Update task status
        self.update_state(
            state='PROGRESS',
            meta={'status': 'Initializing RS master data...', 'progress': 0}
        )
        
        # Initialize RS service
        rs_service = RajyaSabhaMasterDataService()
        
        # Initialize master data
        result = rs_service.initialize_rs_master_data(force_update=force_update)
        
        # Update progress
        self.update_state(
            state='PROGRESS',
            meta={'status': 'RS master data initialization completed', 'progress': 100}
        )
        
        return {
            'status': 'SUCCESS',
            'result': result,
            'message': 'RS master data initialization completed successfully'
        }
        
    except Exception as e:
        logger.error(f"RS master data initialization task failed: {str(e)}")
        return {
            'status': 'FAILED',
            'error': str(e)
        }
