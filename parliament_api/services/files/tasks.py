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
    Unified bulk PDF download task for any document type
    
    Args:
        downloads: List of dicts with keys: {'document_type': str, 'document_id': int, 'pdf_url': str (optional)}
    """
    try:
        total_downloads = len(downloads)
        successful = 0
        failed = 0
        errors = []
        
        # Update initial progress
        self.update_state(
            state='PROGRESS',
            meta={
                'status': f'Starting bulk download of {total_downloads} documents',
                'progress': 0,
                'total': total_downloads,
                'successful': 0,
                'failed': 0
            }
        )
        
        # Process downloads
        for i, download_spec in enumerate(downloads):
            try:
                # Update progress
                progress = int((i / total_downloads) * 90)  # 0-90% range
                self.update_state(
                    state='PROGRESS',
                    meta={
                        'status': f'Processing download {i+1}/{total_downloads}',
                        'progress': progress,
                        'total': total_downloads,
                        'successful': successful,
                        'failed': failed,
                        'current_document': download_spec
                    }
                )
                
                # Execute download task
                result = download_pdf_unified_task.delay(
                    download_spec['document_type'],
                    download_spec['document_id'],
                    download_spec.get('pdf_url')
                ).get()
                
                if result['status'] == 'SUCCESS':
                    successful += 1
                else:
                    failed += 1
                    errors.append(f"{result.get('document_identifier', 'Unknown')}: {result.get('error', 'Unknown error')}")
            
            except Exception as e:
                failed += 1
                error_msg = f"Download {i+1}: {str(e)}"
                errors.append(error_msg)
                logger.error(error_msg)
        
        # Final progress update
        self.update_state(
            state='PROGRESS',
            meta={
                'status': 'Bulk download completed',
                'progress': 100,
                'total': total_downloads,
                'successful': successful,
                'failed': failed
            }
        )
        
        return {
            'status': 'SUCCESS',
            'total_downloads': total_downloads,
            'successful': successful,
            'failed': failed,
            'errors': errors,
            'success_rate': (successful / total_downloads * 100) if total_downloads > 0 else 0
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
