from celery import shared_task
from django.utils import timezone
from django.db import transaction
import logging

from .pdf_download_service import UnifiedPDFDownloadService
from services.questions.models import Question, QuestionMasterData
from services.debates.models import Debate

logger = logging.getLogger(__name__)


@shared_task(bind=True, name='files.download_pdf_unified',
              autoretry_for=(Exception,),
              retry_kwargs={'max_retries': 3, 'countdown': 60},
              retry_backoff=True,
              retry_backoff_max=300,
              retry_jitter=True)
def download_pdf_unified_task(self, document_type: str, document_id: int, pdf_url: str = None):
    """
    Unified Celery task for downloading PDFs (works for LS questions, RS questions, debates)
    
    Args:
        document_type: Type of document ('question', 'debate', 'rs_question')
        document_id: ID of the document (Question.id, Debate.id, or QuestionMasterData.id)
        pdf_url: Optional specific PDF URL to download
    """
    try:
        # Update task status
        self.update_state(
            state='PROGRESS',
            meta={'status': f'Starting {document_type} PDF download...', 'progress': 0}
        )
        
        # Initialize unified PDF service
        pdf_service = UnifiedPDFDownloadService()
        
        # Update progress
        self.update_state(
            state='PROGRESS',
            meta={'status': f'Downloading {document_type} PDF...', 'progress': 25}
        )
        
        # Route to appropriate download method based on document type
        if document_type == 'question':
            question = Question.objects.get(id=document_id)
            result = pdf_service.download_question_pdf_unified(question, pdf_url)
            doc_identifier = f"Q.{question.question_number}"
            
        elif document_type == 'debate':
            debate = Debate.objects.get(id=document_id)
            result = pdf_service.download_debate_pdf_unified(debate)
            doc_identifier = f"Debate {debate.debate_id}"
            
        elif document_type == 'rs_question':
            master_data = QuestionMasterData.objects.get(id=document_id)
            result = pdf_service.download_rs_question_pdf_unified(master_data)
            doc_identifier = f"RS Q.{master_data.question_number}"
            
        else:
            return {
                'status': 'FAILED',
                'error': f'Unsupported document type: {document_type}'
            }
        
        if result['success']:
            # Update progress
            self.update_state(
                state='PROGRESS',
                meta={'status': f'{document_type} PDF downloaded successfully', 'progress': 100}
            )
            
            # Update QuestionMasterData.pdf_downloaded after successful GCS upload
            if result.get('gcs_result', {}).get('success'):
                try:
                    if document_type == 'question':
                        # LS Question - find master_data via reverse relationship
                        question = Question.objects.get(id=document_id)
                        # Use reverse lookup: master_data.question -> QuestionMasterData
                        master_data = QuestionMasterData.objects.filter(question=question).first()
                        if master_data:
                            master_data.pdf_downloaded = True
                            master_data.pdf_gcs_path = result.get('gcs_result', {}).get('object_key', '')
                            master_data.save(update_fields=['pdf_downloaded', 'pdf_gcs_path'])
                            logger.info(f"✅ Updated LS master_data {master_data.id} pdf_downloaded=True")
                        else:
                            logger.warning(f"No master_data found for question {document_id}")
                    
                    elif document_type == 'rs_question':
                        # RS Question - update the master_data directly (document_id IS the master_data_id)
                        master_data = QuestionMasterData.objects.get(id=document_id)
                        master_data.pdf_downloaded = True
                        master_data.pdf_gcs_path = result.get('gcs_result', {}).get('object_key', '')
                        master_data.save(update_fields=['pdf_downloaded', 'pdf_gcs_path'])
                        logger.info(f"✅ Updated RS master_data {master_data.id} pdf_downloaded=True")
                        
                except Exception as e:
                    logger.warning(f"❌ Failed to update master_data pdf_downloaded for {document_type}: {e}")
            
            return {
                'status': 'SUCCESS',
                'document_type': document_type,
                'document_id': document_id,
                'document_identifier': doc_identifier,
                'filename': result['filename'],
                'file_size': result['file_size'],
                'gcs_uploaded': result.get('gcs_result', {}).get('success', False),
                'attempts': result.get('attempts', 1),
                'message': f'PDF downloaded successfully for {doc_identifier}'
            }
        else:
            return {
                'status': 'FAILED',
                'document_type': document_type,
                'document_id': document_id,
                'document_identifier': doc_identifier,
                'error': result.get('error', 'Download failed'),
                'attempts': result.get('attempts', 1)
            }
    
    except (Question.DoesNotExist, Debate.DoesNotExist, QuestionMasterData.DoesNotExist):
        return {
            'status': 'FAILED',
            'document_type': document_type,
            'document_id': document_id,
            'error': f'{document_type.title()} not found'
        }
    except Exception as e:
        logger.error(f"Unified PDF download task failed for {document_type} {document_id}: {str(e)}")
        return {
            'status': 'FAILED',
            'document_type': document_type,
            'document_id': document_id,
            'error': str(e)
        }


@shared_task(bind=True, name='files.bulk_download_pdfs_unified',
              autoretry_for=(Exception,),
              retry_kwargs={'max_retries': 2, 'countdown': 120},
              retry_backoff=True,
              retry_backoff_max=600,
              retry_jitter=True)
def bulk_download_pdfs_unified_task(self, downloads: list):
    """
    Unified bulk PDF download task for any document type with TRUE PARALLELISM
    
    This task now:
    1. Collects all download specifications (metadata phase)
    2. Dispatches ALL downloads in parallel using celery.group()
    3. Returns immediately without waiting for downloads to complete
    
    Args:
        downloads: List of dicts with keys: {'document_type': str, 'document_id': int, 'pdf_url': str (optional)}
    """
    try:
        from celery import group
        
        total_downloads = len(downloads)
        
        # Update initial progress
        self.update_state(
            state='PROGRESS',
            meta={
                'status': f'Preparing {total_downloads} documents for parallel download',
                'progress': 10,
                'total': total_downloads,
                'phase': 'preparing'
            }
        )
        
        logger.info(f"Starting parallel bulk download for {total_downloads} documents")
        
        # Build task signatures for all downloads
        download_tasks = []
        for i, download_spec in enumerate(downloads):
            try:
                # Create task signature for this download
                download_tasks.append(
                    download_pdf_unified_task.si(
                        download_spec['document_type'],
                        download_spec['document_id'],
                        download_spec.get('pdf_url')
                    )
                )
            except Exception as e:
                logger.error(f"Error preparing download {i+1}: {str(e)}")
                continue
        
        if not download_tasks:
            return {
                'status': 'FAILED',
                'error': 'No valid downloads to process'
            }
        
        # Update progress
        tasks_to_dispatch = len(download_tasks)
        self.update_state(
            state='PROGRESS',
            meta={
                'status': f'Dispatching {tasks_to_dispatch} downloads in parallel',
                'progress': 50,
                'total': total_downloads,
                'tasks_to_dispatch': tasks_to_dispatch,
                'phase': 'dispatching'
            }
        )
        
        # Dispatch ALL downloads in parallel using group()
        job = group(download_tasks)
        group_result = job.apply_async()
        
        logger.info(f"✅ PARALLEL DISPATCH: {tasks_to_dispatch} PDF downloads dispatched simultaneously!")
        logger.info(f"   Group ID: {group_result.id}")
        logger.info(f"   Worker pool will process these {tasks_to_dispatch} tasks in parallel")
        
        # Return immediately - don't wait!
        return {
            'status': 'DISPATCHED',
            'message': 'All downloads dispatched in parallel - check Celery Flower for progress',
            'total_downloads': total_downloads,
            'tasks_dispatched': tasks_to_dispatch,
            'group_id': group_result.id,
            'note': 'Downloads are running in parallel. Use group_id to track progress.'
        }
    
    except Exception as e:
        logger.error(f"Bulk PDF download task failed: {str(e)}")
        return {
            'status': 'FAILED',
            'error': str(e)
        }


@shared_task(bind=True, name='files.test_pdf_accessibility_bulk')
def test_pdf_accessibility_bulk_task(self, pdf_urls: list):
    """
    Test accessibility of multiple PDF URLs using unified service
    
    Args:
        pdf_urls: List of PDF URLs to test
    """
    try:
        # Update task status
        self.update_state(
            state='PROGRESS',
            meta={'status': 'Testing PDF accessibility...', 'progress': 0}
        )
        
        # Initialize unified PDF service
        pdf_service = UnifiedPDFDownloadService()
        
        # Test accessibility
        results = pdf_service.bulk_test_accessibility(pdf_urls)
        
        # Calculate statistics
        total_urls = len(pdf_urls)
        accessible_count = sum(1 for result in results.values() if result.get('accessible', False))
        success_rate = (accessible_count / total_urls * 100) if total_urls > 0 else 0
        
        # Update progress
        self.update_state(
            state='PROGRESS',
            meta={'status': 'PDF accessibility testing completed', 'progress': 100}
        )
        
        return {
            'status': 'SUCCESS',
            'total_urls': total_urls,
            'accessible_count': accessible_count,
            'success_rate': success_rate,
            'results': results
        }
    
    except Exception as e:
        logger.error(f"PDF accessibility test task failed: {str(e)}")
        return {
            'status': 'FAILED',
            'error': str(e)
        }
