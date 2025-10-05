import os
import time
import requests
import logging
from datetime import datetime
from typing import List, Dict, Optional
from django.utils import timezone
from django.conf import settings

from .models import Question, QuestionMasterData
from services.files.models import DocumentFile, DownloadQueue
from services.cloud_storage.gcs_service import GCSService

logger = logging.getLogger(__name__)


class QuestionDownloadService:
    """
    Service for downloading question PDFs following the same pattern as debates
    """
    
    def __init__(self):
        self.session = requests.Session()
        # Set headers for both modern and legacy PDF downloads
        self.session.headers.update({
            'Accept': 'application/pdf,*/*',
            'Referer': 'https://sansad.in/ls/questions/questions-and-answers',
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36',
            'sec-ch-ua': '"Chromium";v="140", "Not=A?Brand";v="24", "Brave";v="140"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"macOS"'
        })
        self.gcs_service = GCSService()
    
    def _generate_filename(self, question: Question) -> str:
        """Generate consistent filename for question PDF with session identifiers"""
        question_type = question.question_type.lower().replace(' ', '_')
        
        # Include session identifiers to prevent filename collisions
        if question.lok_sabha and question.session:
            return f"question_ls{question.lok_sabha.number}_s{question.session.session_number}_{question.question_number}_{question_type}.pdf"
        elif question.master_data:
            # Fallback to master data for session info
            return f"question_ls{question.master_data.lok_sabha_number}_s{question.master_data.session_number}_{question.question_number}_{question_type}.pdf"
        else:
            # Fallback to basic filename (legacy support)
            logger.warning(f"No session info available for Q.{question.question_number}, using basic filename")
            return f"question_{question.question_number}_{question_type}.pdf"
    
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
            
            # Download PDF with exponential backoff retry logic
            max_retries = 3
            base_delay = 1  # Start with 1 second
            
            for attempt in range(max_retries):
                try:
                    # Calculate exponential backoff delay
                    if attempt > 0:
                        delay = base_delay * (2 ** (attempt - 1))  # 1s, 2s, 4s
                        logger.info(f"Retry attempt {attempt + 1}/{max_retries} for question {question.question_number} after {delay}s delay")
                        time.sleep(delay)
                    else:
                        logger.info(f"Downloading question PDF from {pdf_url} (attempt {attempt + 1}/{max_retries})")
                    
                    # Use proper headers for PDF download (same as debate scraper)
                    pdf_headers = {
                        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
                        'Accept-Language': 'en-US,en;q=0.9',
                        'Connection': 'keep-alive',
                        'Referer': 'https://sansad.in/' if 'sansad.in' in pdf_url else 'https://eparlib.sansad.in/',
                        'Sec-Fetch-Dest': 'document',
                        'Sec-Fetch-Mode': 'navigate',
                        'Sec-Fetch-Site': 'same-origin',
                        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36',
                        'sec-ch-ua': '"Chromium";v="140", "Not=A?Brand";v="24", "Brave";v="140"',
                        'sec-ch-ua-mobile': '?0',
                        'sec-ch-ua-platform': '"macOS"',
                        'Upgrade-Insecure-Requests': '1'
                    }
                    
                    # URL encode the PDF URL to handle spaces and special characters
                    from urllib.parse import quote
                    
                    # Split URL and encode path properly
                    if '?' in pdf_url:
                        base_url, params = pdf_url.split('?', 1)
                        # Only encode the path part, not the domain
                        url_parts = base_url.split('/')
                        encoded_parts = url_parts[:3] + [quote(part, safe='') for part in url_parts[3:]]
                        encoded_url = '/'.join(encoded_parts) + '?' + params
                    else:
                        url_parts = pdf_url.split('/')
                        encoded_parts = url_parts[:3] + [quote(part, safe='') for part in url_parts[3:]]
                        encoded_url = '/'.join(encoded_parts)
                    
                    logger.info(f"Downloading from encoded URL: {encoded_url}")
                    
                    # Download PDF with proper headers and SSL settings
                    response = self.session.get(encoded_url, headers=pdf_headers, timeout=60, stream=True, verify=False)
                    
                    # If we get 403, try to establish session by visiting the main page first
                    if response.status_code == 403:
                        logger.info("PDF access forbidden, attempting to establish session...")
                        
                        # Visit main questions page to establish session
                        session_headers = {
                            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                            'Accept-Language': 'en-US,en;q=0.9',
                            'Connection': 'keep-alive',
                            'User-Agent': pdf_headers['User-Agent'],
                            'Upgrade-Insecure-Requests': '1'
                        }
                        
                        try:
                            # Visit main page to get session cookies
                            if 'sansad.in' in pdf_url:
                                session_resp = self.session.get('https://sansad.in/ls/questions/questions-and-answers', headers=session_headers, timeout=30)
                            else:
                                session_resp = self.session.get('https://eparlib.sansad.in/', headers=session_headers, timeout=30)
                                
                            if session_resp.status_code == 200:
                                logger.info("Session established, retrying PDF download...")
                                # Retry PDF download with updated session
                                response = self.session.get(encoded_url, headers=pdf_headers, timeout=60, stream=True, verify=False)
                        except Exception as e:
                            logger.warning(f"Failed to establish session: {e}")
                    
                    response.raise_for_status()
                    break  # Success, exit retry loop
                    
                except (requests.exceptions.SSLError, requests.exceptions.ConnectionError, 
                        requests.exceptions.Timeout, requests.exceptions.HTTPError) as network_error:
                    logger.warning(f"Network error on attempt {attempt + 1}/{max_retries} for question {question.question_number}: {network_error}")
                    
                    if attempt == max_retries - 1:  # Last attempt
                        logger.error(f"All {max_retries} download attempts failed for question {question.question_number}")
                        raise
                    # Continue to next attempt
                    continue
                    
                except Exception as e:
                    logger.error(f"Unexpected error on attempt {attempt + 1} for question {question.question_number}: {e}")
                    if attempt < max_retries - 1:
                        delay = base_delay * (2 ** attempt)
                        time.sleep(delay)
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
            
            # Upload to Google Cloud Storage
            try:
                bucket_name = self.gcs_service.get_bucket_for_document_type('parl_question')
                
                # Generate object key with session-based path for better organization
                if question.lok_sabha and question.session:
                    session_path = f"ls{question.lok_sabha.number}/session{question.session.session_number}"
                elif question.master_data:
                    session_path = f"ls{question.master_data.lok_sabha_number}/session{question.master_data.session_number}"
                else:
                    session_path = "unknown_session"
                
                object_key = self.gcs_service.generate_object_key('parl_question', file_name, session_path)
                
                # Update GCS upload status
                doc_file.gcs_upload_status = 'uploading'
                doc_file.gcs_bucket_name = bucket_name
                doc_file.gcs_object_key = object_key
                doc_file.save()
                
                # Upload to GCS
                upload_result = self.gcs_service.upload_file(
                    file_path,
                    bucket_name,
                    object_key,
                    metadata={
                        'question_id': question.question_id,
                        'question_number': question.question_number,
                        'document_type': 'parliamentary_question',
                        'uploaded_by': 'question_download_service'
                    }
                )
                
                if upload_result['success']:
                    # Update GCS metadata
                    doc_file.gcs_upload_status = 'completed'
                    doc_file.gcs_uploaded_at = timezone.now()
                    doc_file.gcs_etag = upload_result.get('etag', '')
                    doc_file.gcs_url = upload_result.get('gcs_url', '')
                    doc_file.save()
                    
                    # Delete local file if configured to do so
                    if settings.GCS_AUTO_DELETE_LOCAL:
                        try:
                            os.remove(file_path)
                            doc_file.file_path = None
                            doc_file.save()
                            logger.info(f"Deleted local file after GCS upload: {file_path}")
                        except Exception as delete_error:
                            logger.warning(f"Failed to delete local file: {delete_error}")
                    
                    logger.info(f"Successfully uploaded question PDF to GCS: {object_key}")
                else:
                    doc_file.gcs_upload_status = 'failed'
                    doc_file.save()
                    logger.error(f"Failed to upload to GCS: {upload_result.get('error')}")
                    
            except Exception as gcs_error:
                logger.error(f"GCS upload error: {gcs_error}")
                doc_file.gcs_upload_status = 'failed'
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
    
    def bulk_download_questions_from_master_data(self, master_data_list: List[QuestionMasterData], 
                                               use_celery: bool = True) -> Dict:
        """Download PDFs for questions from master data using Celery tasks"""
        
        if use_celery:
            # Use Celery for bulk download
            master_data_ids = [md.id for md in master_data_list]
            
            from .tasks import bulk_download_question_pdfs_from_master_data_task
            
            # Start Celery task
            task = bulk_download_question_pdfs_from_master_data_task.delay(master_data_ids)
            
            return {
                'total': len(master_data_list),
                'task_id': task.id,
                'status': 'started',
                'message': 'Bulk download from master data started via Celery. Use task status endpoint to monitor progress.'
            }
        else:
            # Synchronous implementation
            results = {
                'total': len(master_data_list),
                'queued': 0,
                'already_downloaded': 0,
                'no_pdf': 0,
                'errors': []
            }
            
            for master_data in master_data_list:
                try:
                    # Get PDF URL from master data
                    pdf_url = master_data.get_pdf_url()
                    
                    if not pdf_url:
                        results['no_pdf'] += 1
                        continue
                    
                    # Create or get corresponding Question object
                    question = self._create_question_from_master_data(master_data)
                    
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
                    error_msg = f"Q.{master_data.question_number}: {str(e)}"
                    results['errors'].append(error_msg)
                    logger.error(error_msg)
            
            return results
    
    def bulk_download_questions(self, questions: List[Question], use_celery: bool = True) -> Dict:
        """Download PDFs for multiple questions using Celery tasks (legacy method)"""
        
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
        
        # Master data statistics
        stats['master_data'] = {
            'total_master_records': QuestionMasterData.objects.count(),
            'metadata_processed': QuestionMasterData.objects.filter(is_processed=True).count(),
            'metadata_unprocessed': QuestionMasterData.objects.filter(is_processed=False).count(),
            'pdfs_downloaded': QuestionMasterData.objects.filter(pdf_downloaded=True).count(),
            'pdfs_pending': QuestionMasterData.objects.filter(pdf_downloaded=False).exclude(questions_file_path='').count(),
            'with_pdf_urls': QuestionMasterData.objects.exclude(questions_file_path='').count()
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
    
    def process_download_queue(self, max_items: int = 10, use_celery: bool = False) -> Dict:
        """
        Process pending items in the download queue
        
        Args:
            max_items: Maximum number of items to process
            
        Returns:
            Dict with processing results
        """
        from services.files.models import DownloadQueue
        
        # Get pending queue items for questions
        pending_items = DownloadQueue.objects.filter(
            document_file__document_category='parl_question',
            status='queued'
        ).order_by('priority', 'created_at')[:max_items]
        
        results = {
            'processed': 0,
            'successful': 0,
            'failed': 0,
            'errors': []
        }
        
        logger.info(f"Processing {pending_items.count()} pending question downloads")
        
        for queue_item in pending_items:
            try:
                doc_file = queue_item.document_file
                question = doc_file.question
                
                if not question:
                    results['failed'] += 1
                    results['errors'].append(f"No question associated with {doc_file.file_name}")
                    queue_item.mark_failed("No associated question")
                    continue
                
                # Get PDF URL from question
                pdf_urls = question.pdf_files if isinstance(question.pdf_files, list) else []
                if not pdf_urls:
                    results['failed'] += 1
                    results['errors'].append(f"No PDF URL for question {question.question_number}")
                    queue_item.mark_failed("No PDF URL available")
                    continue
                
                pdf_url = pdf_urls[0]
                
                # Mark as processing
                queue_item.mark_started('question_download_service')
                
                # Download with GCS integration
                success = self.download_question_pdf(question, pdf_url)
                
                if success:
                    queue_item.mark_completed()
                    results['successful'] += 1
                    logger.info(f"Successfully processed question {question.question_number}")
                else:
                    queue_item.mark_failed("Download failed")
                    results['failed'] += 1
                    results['errors'].append(f"Download failed for question {question.question_number}")
                
                results['processed'] += 1
                
            except Exception as e:
                results['failed'] += 1
                results['processed'] += 1
                error_msg = f"Error processing queue item {queue_item.id}: {str(e)}"
                results['errors'].append(error_msg)
                logger.error(error_msg)
                
                try:
                    queue_item.mark_failed(str(e))
                except:
                    pass
        
        logger.info(f"Queue processing completed: {results['processed']} processed, {results['successful']} successful, {results['failed']} failed")
        return results
    
    def _create_question_from_master_data(self, master_data: QuestionMasterData) -> Question:
        """Create or get Question object from QuestionMasterData"""
        try:
            # Check if Question already exists
            try:
                if master_data.question:
                    return master_data.question
            except QuestionMasterData.question.RelatedObjectDoesNotExist:
                # No related question exists yet
                pass
            
            # Create Question from master data
            question_data = {
                'question_id': f"master_{master_data.id}",
                'question_number': master_data.question_number,
                'question_type': master_data.question_type.title(),  # Convert to title case
                'title': master_data.subjects,
                'subject': master_data.subjects,
                'question_text': master_data.question_text,
                'answer_text': master_data.answer_text,
                'date': master_data.date,
                'lok_sabha': master_data.lok_sabha,
                'session': master_data.session,
                'pdf_files': [master_data.get_pdf_url()] if master_data.get_pdf_url() else [],
                'minister_names': [master_data.ministry] if master_data.ministry else [],
                'raw_api_data': master_data.raw_api_data,
                'last_scraped': master_data.last_fetched
            }
            
            question, created = Question.objects.get_or_create(
                question_number=master_data.question_number,
                lok_sabha=master_data.lok_sabha,
                session=master_data.session,
                defaults=question_data
            )
            
            # Link master data to question
            master_data.question = question
            master_data.is_processed = True
            master_data.processed_at = timezone.now()
            master_data.save()
            
            # Handle members and ministries
            if master_data.members:
                from .models import Member
                for member_name in master_data.members:
                    if member_name.strip():
                        member, _ = Member.objects.get_or_create(name=member_name.strip())
                        question.members.add(member)
            
            if master_data.ministry:
                from .models import Ministry
                ministry, _ = Ministry.objects.get_or_create(name=master_data.ministry)
                question.ministries.add(ministry)
            
            if created:
                logger.info(f"Created Question from master data: Q.{question.question_number}")
            else:
                logger.info(f"Found existing Question for master data: Q.{question.question_number}")
            
            return question
            
        except Exception as e:
            logger.error(f"Failed to create Question from master data {master_data.id}: {e}")
            raise

