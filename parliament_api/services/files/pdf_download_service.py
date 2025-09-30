import os
import time
import requests
import logging
from datetime import datetime
from typing import Dict, Optional, Tuple, List
from urllib.parse import quote, urlparse
from django.utils import timezone
from django.conf import settings

from .models import DocumentFile, DownloadQueue
from services.cloud_storage.gcs_service import GCSService
from services.questions.models import Question, QuestionMasterData
from services.debates.models import Debate

logger = logging.getLogger(__name__)


class UnifiedPDFDownloadService:
    """
    Centralized PDF download service with proper authentication, headers, and GCS integration
    
    This service handles:
    1. Session establishment and cookie management
    2. Proper headers for different PDF sources (sansad.in, eparlib.sansad.in, rsdoc.nic.in)
    3. Exponential backoff retry logic
    4. URL encoding and validation
    5. GCS upload with metadata
    6. Comprehensive error handling
    """
    
    def __init__(self):
        self.session = requests.Session()
        self.gcs_service = GCSService()
        self._setup_session()
    
    def _setup_session(self):
        """Setup session with base configuration"""
        # Base headers that work across all Parliament sites
        self.session.headers.update({
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Language': 'en-US,en;q=0.9',
            'Connection': 'keep-alive',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'same-origin',
            'Sec-GPC': '1',
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36',
            'sec-ch-ua': '"Chromium";v="140", "Not=A?Brand";v="24", "Brave";v="140"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"macOS"',
            'Upgrade-Insecure-Requests': '1'
        })
        
        # SSL and connection settings
        self.session.verify = True
        self.session.timeout = 60
    
    def _get_site_specific_headers(self, pdf_url: str) -> Dict[str, str]:
        """Get site-specific headers based on PDF URL"""
        parsed_url = urlparse(pdf_url)
        domain = parsed_url.netloc.lower()
        
        # Base headers (already set in session)
        headers = {}
        
        # Site-specific referer and origin
        if 'sansad.in' in domain:
            if 'api_rs' in pdf_url or 'rsdoc.nic.in' in domain:
                # Rajya Sabha specific
                headers.update({
                    'Referer': 'https://sansad.in/rs/questions/questions-and-answers',
                    'Origin': 'https://sansad.in'
                })
            else:
                # Lok Sabha specific
                headers.update({
                    'Referer': 'https://sansad.in/ls/questions/questions-and-answers',
                    'Origin': 'https://sansad.in'
                })
        elif 'eparlib.sansad.in' in domain:
            headers.update({
                'Referer': 'https://sansad.in/',
                'Origin': 'https://sansad.in'
            })
        elif 'rsdoc.nic.in' in domain:
            headers.update({
                'Referer': 'https://sansad.in/',
                'Origin': 'https://sansad.in'
            })
        
        return headers
    
    def _establish_session(self, pdf_url: str) -> bool:
        """
        Establish session by visiting appropriate main page to get cookies
        
        Args:
            pdf_url: The PDF URL to determine which site to visit
            
        Returns:
            True if session established successfully
        """
        try:
            parsed_url = urlparse(pdf_url)
            domain = parsed_url.netloc.lower()
            
            # Determine which main page to visit
            if 'api_rs' in pdf_url or 'rsdoc.nic.in' in domain:
                # Rajya Sabha
                main_page_url = 'https://sansad.in/rs/questions/questions-and-answers'
            elif 'sansad.in' in domain:
                # Lok Sabha
                main_page_url = 'https://sansad.in/ls/questions/questions-and-answers'
            elif 'eparlib.sansad.in' in domain:
                # Legacy eparlib
                main_page_url = 'https://sansad.in/ls/questions/questions-and-answers'
            else:
                logger.warning(f"Unknown domain for session establishment: {domain}")
                return False
            
            # Visit main page to establish session
            session_headers = {
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
                'Connection': 'keep-alive',
                'User-Agent': self.session.headers['User-Agent'],
                'Upgrade-Insecure-Requests': '1'
            }
            
            logger.info(f"Establishing session by visiting: {main_page_url}")
            response = self.session.get(main_page_url, headers=session_headers, timeout=30)
            
            if response.status_code == 200:
                logger.info("Session established successfully")
                return True
            else:
                logger.warning(f"Failed to establish session: HTTP {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"Error establishing session: {e}")
            return False
    
    def _encode_pdf_url(self, pdf_url: str) -> str:
        """
        Properly encode PDF URL to handle spaces and special characters
        
        Args:
            pdf_url: Original PDF URL
            
        Returns:
            Encoded URL
        """
        try:
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
            
            return encoded_url
        except Exception as e:
            logger.warning(f"Failed to encode URL {pdf_url}: {e}")
            return pdf_url  # Return original if encoding fails
    
    def test_pdf_accessibility(self, pdf_url: str) -> Dict[str, any]:
        """
        Test if a PDF URL is accessible without downloading the full file
        
        Args:
            pdf_url: PDF URL to test
            
        Returns:
            Dict with accessibility info
        """
        try:
            # Get site-specific headers
            headers = self._get_site_specific_headers(pdf_url)
            
            # Encode URL
            encoded_url = self._encode_pdf_url(pdf_url)
            
            # First, establish session
            session_established = self._establish_session(pdf_url)
            
            # Try HEAD request first
            try:
                response = self.session.head(encoded_url, headers=headers, timeout=10, allow_redirects=True)
                if response.status_code == 200:
                    return {
                        'accessible': True,
                        'method': 'HEAD',
                        'status_code': response.status_code,
                        'content_length': response.headers.get('content-length', 'unknown'),
                        'content_type': response.headers.get('content-type', 'unknown')
                    }
            except Exception as head_error:
                logger.debug(f"HEAD request failed: {head_error}")
            
            # If HEAD fails, try GET with range header (first 1KB)
            range_headers = headers.copy()
            range_headers['Range'] = 'bytes=0-1023'  # First 1KB
            
            response = self.session.get(encoded_url, headers=range_headers, timeout=10)
            
            return {
                'accessible': response.status_code in [200, 206],  # 206 for partial content
                'method': 'GET (partial)',
                'status_code': response.status_code,
                'content_length': len(response.content),
                'content_type': response.headers.get('content-type', 'unknown'),
                'session_established': session_established
            }
            
        except Exception as e:
            return {
                'accessible': False,
                'method': 'error',
                'status_code': None,
                'error': str(e),
                'session_established': False
            }
    
    def download_pdf(self, pdf_url: str, document_type: str, metadata: Dict = None, 
                    max_retries: int = 3) -> Dict[str, any]:
        """
        Download PDF with comprehensive error handling and GCS upload
        
        Args:
            pdf_url: URL of the PDF to download
            document_type: Type of document ('question', 'debate', 'rs_question', etc.)
            metadata: Additional metadata for the file
            max_retries: Maximum number of retry attempts
            
        Returns:
            Dict with download results
        """
        if not pdf_url:
            return {'success': False, 'error': 'No PDF URL provided'}
        
        # Initialize metadata
        if metadata is None:
            metadata = {}
        
        # Generate filename
        filename = self._generate_filename(pdf_url, document_type, metadata)
        local_path = os.path.join(settings.MEDIA_ROOT, document_type, filename)
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        
        # Get site-specific headers
        headers = self._get_site_specific_headers(pdf_url)
        
        # Encode URL
        encoded_url = self._encode_pdf_url(pdf_url)
        
        # Retry logic with exponential backoff
        base_delay = 1
        last_error = None
        
        for attempt in range(max_retries):
            try:
                # Calculate delay for retries
                if attempt > 0:
                    delay = base_delay * (2 ** (attempt - 1))  # 1s, 2s, 4s
                    logger.info(f"Retry attempt {attempt + 1}/{max_retries} after {delay}s delay")
                    time.sleep(delay)
                
                logger.info(f"Downloading PDF (attempt {attempt + 1}/{max_retries}): {encoded_url}")
                
                # Establish session on first attempt or after 403 error
                if attempt == 0 or (last_error and '403' in str(last_error)):
                    self._establish_session(pdf_url)
                
                # Download PDF
                response = self.session.get(encoded_url, headers=headers, timeout=60, stream=True)
                
                # Handle 403 by establishing session and retrying once
                if response.status_code == 403 and attempt == 0:
                    logger.info("Got 403, establishing session and retrying...")
                    self._establish_session(pdf_url)
                    response = self.session.get(encoded_url, headers=headers, timeout=60, stream=True)
                
                response.raise_for_status()
                
                # Validate content type
                content_type = response.headers.get('content-type', '').lower()
                if 'pdf' not in content_type and 'application/octet-stream' not in content_type:
                    logger.warning(f"Unexpected content type: {content_type}")
                
                # Save file locally
                with open(local_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                
                file_size = os.path.getsize(local_path)
                
                # Validate file size
                if file_size < 1024:  # Less than 1KB is suspicious
                    logger.warning(f"Downloaded file is very small: {file_size} bytes")
                
                logger.info(f"Successfully downloaded PDF: {filename} ({file_size} bytes)")
                
                # Upload to GCS
                gcs_result = self._upload_to_gcs(local_path, document_type, filename, metadata)
                
                return {
                    'success': True,
                    'local_path': local_path,
                    'filename': filename,
                    'file_size': file_size,
                    'gcs_result': gcs_result,
                    'attempts': attempt + 1
                }
                
            except Exception as e:
                last_error = e
                logger.warning(f"Download attempt {attempt + 1} failed: {e}")
                
                if attempt == max_retries - 1:
                    logger.error(f"All {max_retries} download attempts failed for {pdf_url}")
                    return {
                        'success': False,
                        'error': str(last_error),
                        'attempts': max_retries,
                        'pdf_url': pdf_url
                    }
        
        return {'success': False, 'error': 'Unexpected end of retry loop'}
    
    def _generate_filename(self, pdf_url: str, document_type: str, metadata: Dict) -> str:
        """Generate consistent filename for PDF"""
        try:
            # Extract filename from URL or generate one
            parsed_url = urlparse(pdf_url)
            url_filename = os.path.basename(parsed_url.path)
            
            if url_filename and url_filename.endswith('.pdf'):
                base_name = url_filename
            else:
                # Generate filename from metadata
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                if document_type == 'rs_question':
                    session = metadata.get('session_number', 'unknown')
                    question_no = metadata.get('question_number', 'unknown')
                    base_name = f"rs_q_{session}_{question_no}_{timestamp}.pdf"
                elif document_type == 'question':
                    ls_no = metadata.get('lok_sabha_number', 'unknown')
                    session = metadata.get('session_number', 'unknown')
                    question_no = metadata.get('question_number', 'unknown')
                    base_name = f"ls_q_{ls_no}_{session}_{question_no}_{timestamp}.pdf"
                elif document_type == 'debate':
                    ls_no = metadata.get('lok_sabha_number', 'unknown')
                    session = metadata.get('session_number', 'unknown')
                    date = metadata.get('debate_date', timestamp[:8])
                    base_name = f"debate_{ls_no}_{session}_{date}_{timestamp}.pdf"
                else:
                    base_name = f"{document_type}_{timestamp}.pdf"
            
            return base_name
            
        except Exception as e:
            logger.warning(f"Error generating filename: {e}")
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            return f"{document_type}_{timestamp}.pdf"
    
    def _upload_to_gcs(self, local_path: str, document_type: str, filename: str, metadata: Dict) -> Dict:
        """Upload file to Google Cloud Storage with metadata"""
        try:
            bucket_name = self.gcs_service.get_bucket_for_document_type(f'parl_{document_type}')
            
            # Generate session-based path for consistent organization (like LS)
            session_path = self._generate_session_path(document_type, metadata)
            object_key = self.gcs_service.generate_object_key(f'parl_{document_type}', filename, session_path)
            
            # Prepare GCS metadata
            gcs_metadata = {
                'document_type': f'parliamentary_{document_type}',
                'uploaded_by': 'unified_pdf_service',
                'upload_timestamp': timezone.now().isoformat(),
                **metadata  # Include any additional metadata
            }
            
            # Upload to GCS
            upload_result = self.gcs_service.upload_file(
                local_path,
                bucket_name,
                object_key,
                metadata=gcs_metadata
            )
            
            if upload_result['success']:
                # Delete local file if configured to do so
                if getattr(settings, 'GCS_AUTO_DELETE_LOCAL', False):
                    try:
                        os.remove(local_path)
                        logger.info(f"Deleted local file after GCS upload: {local_path}")
                    except Exception as delete_error:
                        logger.warning(f"Failed to delete local file: {delete_error}")
                
                logger.info(f"Successfully uploaded to GCS: {object_key}")
            
            return upload_result
            
        except Exception as e:
            logger.error(f"GCS upload failed: {e}")
            return {'success': False, 'error': str(e)}
    
    def bulk_test_accessibility(self, pdf_urls: List[str]) -> Dict[str, Dict]:
        """
        Test accessibility of multiple PDF URLs
        
        Args:
            pdf_urls: List of PDF URLs to test
            
        Returns:
            Dict mapping URLs to accessibility results
        """
        results = {}
        
        for i, url in enumerate(pdf_urls):
            logger.info(f"Testing PDF {i+1}/{len(pdf_urls)}: {url[:80]}...")
            results[url] = self.test_pdf_accessibility(url)
            
            # Small delay between tests to be respectful
            if i < len(pdf_urls) - 1:
                time.sleep(0.5)
        
        return results
    
    def _generate_session_path(self, document_type: str, metadata: Dict) -> str:
        """Generate session-based path for GCS organization (consistent with LS pattern)"""
        try:
            if document_type == 'rs_question':
                # RS questions: rs/session{number}
                session_number = metadata.get('session_number', 'unknown')
                return f"rs/session{session_number}"
            elif document_type == 'question':
                # LS questions: ls{number}/session{number}
                ls_number = metadata.get('lok_sabha_number', 'unknown')
                session_number = metadata.get('session_number', 'unknown')
                return f"ls{ls_number}/session{session_number}"
            elif document_type == 'debate':
                # LS debates: ls{number}/session{number}
                ls_number = metadata.get('lok_sabha_number', 'unknown')
                session_number = metadata.get('session_number', 'unknown')
                return f"ls{ls_number}/session{session_number}"
            else:
                return "unknown"
        except Exception as e:
            logger.warning(f"Error generating session path: {e}")
            return "unknown"
    
    def download_question_pdf_unified(self, question: Question, pdf_url: str = None) -> Dict[str, any]:
        """
        Download PDF for a Question using unified service (replaces old question download service)
        
        Args:
            question: Question instance
            pdf_url: Optional specific PDF URL (will use question.pdf_files[0] if not provided)
            
        Returns:
            Dict with download results
        """
        try:
            # Get PDF URL
            if not pdf_url:
                pdf_urls = question.pdf_files if isinstance(question.pdf_files, list) else []
                if not pdf_urls:
                    return {'success': False, 'error': 'No PDF URL available for this question'}
                pdf_url = pdf_urls[0]
            
            # Prepare metadata
            metadata = {
                'question_id': question.id,
                'question_number': question.question_number,
                'lok_sabha_number': question.lok_sabha.number if question.lok_sabha else 'unknown',
                'session_number': question.session.session_number if question.session else 'unknown',
                'question_type': question.question_type,
                'ministry': ', '.join(question.get_ministries_list()) if hasattr(question, 'get_ministries_list') else '',
                'date': question.date.isoformat() if question.date else None
            }
            
            # Download using unified service
            result = self.download_pdf(pdf_url, 'question', metadata)
            
            if result['success']:
                # Update question record
                question.last_scraped = timezone.now()
                question.save()
                
                # Create/update DocumentFile record
                doc_file, created = DocumentFile.objects.get_or_create(
                    question=question,
                    original_url=pdf_url,
                    defaults={
                        'document_category': 'parl_question',
                        'file_type': 'question',
                        'file_name': result['filename'],
                        'file_path': result.get('local_path', ''),
                        'file_size': result['file_size'],
                        'status': 'completed',
                        'downloaded_at': timezone.now(),
                        'download_priority': 5
                    }
                )
                
                if not created:
                    # Update existing record
                    doc_file.file_name = result['filename']
                    doc_file.file_path = result.get('local_path', '')
                    doc_file.file_size = result['file_size']
                    doc_file.status = 'completed'
                    doc_file.downloaded_at = timezone.now()
                    doc_file.save()
                
                # Update GCS info if available
                gcs_result = result.get('gcs_result', {})
                if gcs_result.get('success'):
                    doc_file.gcs_upload_status = 'completed'
                    doc_file.gcs_bucket_name = gcs_result.get('bucket_name', '')
                    doc_file.gcs_object_key = gcs_result.get('object_key', '')
                    doc_file.gcs_url = gcs_result.get('gcs_url', '')
                    doc_file.gcs_uploaded_at = timezone.now()
                    doc_file.save()
            
            return result
            
        except Exception as e:
            logger.error(f"Unified question PDF download failed: {e}")
            return {'success': False, 'error': str(e)}
    
    def download_debate_pdf_unified(self, debate: Debate) -> Dict[str, any]:
        """
        Download PDF for a Debate using unified service (replaces old debate download service)
        
        Args:
            debate: Debate instance
            
        Returns:
            Dict with download results
        """
        try:
            if not debate.pdf_url:
                return {'success': False, 'error': 'No PDF URL available for this debate'}
            
            # Prepare metadata
            metadata = {
                'debate_id': debate.debate_id,
                'lok_sabha_number': debate.lok_sabha.number if debate.lok_sabha else 'unknown',
                'session_number': debate.session.session_number if debate.session else 'unknown',
                'debate_date': debate.debate_date.isoformat() if debate.debate_date else None,
                'debate_type': debate.debate_type,
                'debate_category': debate.debate_category,
                'language': debate.language
            }
            
            # Update debate status
            debate.status = 'downloading'
            debate.download_attempts += 1
            debate.last_download_attempt = timezone.now()
            debate.save()
            
            # Download using unified service
            result = self.download_pdf(debate.pdf_url, 'debate', metadata)
            
            if result['success']:
                # Update debate record
                debate.status = 'completed'
                debate.file_size = result['file_size']
                debate.last_scraped = timezone.now()
                debate.save()
                
                # Create/update DocumentFile record
                if debate.pdf_file:
                    doc_file = debate.pdf_file
                else:
                    doc_file, created = DocumentFile.objects.get_or_create(
                        original_url=debate.pdf_url,
                        defaults={
                            'document_category': 'parl_debate',
                            'file_type': 'debate',
                            'file_name': result['filename'],
                            'download_priority': 5
                        }
                    )
                    debate.pdf_file = doc_file
                    debate.save()
                
                # Update document file
                doc_file.file_name = result['filename']
                doc_file.file_path = result.get('local_path', '')
                doc_file.file_size = result['file_size']
                doc_file.status = 'completed'
                doc_file.downloaded_at = timezone.now()
                doc_file.save()
                
                # Update GCS info if available
                gcs_result = result.get('gcs_result', {})
                if gcs_result.get('success'):
                    doc_file.gcs_upload_status = 'completed'
                    doc_file.gcs_bucket_name = gcs_result.get('bucket_name', '')
                    doc_file.gcs_object_key = gcs_result.get('object_key', '')
                    doc_file.gcs_url = gcs_result.get('gcs_url', '')
                    doc_file.gcs_uploaded_at = timezone.now()
                    doc_file.save()
            else:
                # Update debate with error
                debate.status = 'failed'
                debate.error_message = result.get('error', 'Download failed')
                debate.save()
            
            return result
            
        except Exception as e:
            logger.error(f"Unified debate PDF download failed: {e}")
            debate.status = 'failed'
            debate.error_message = str(e)
            debate.save()
            return {'success': False, 'error': str(e)}
    
    def download_rs_question_pdf_unified(self, master_data: QuestionMasterData) -> Dict[str, any]:
        """
        Download PDF for RS Question using unified service
        
        Args:
            master_data: QuestionMasterData instance for RS question
            
        Returns:
            Dict with download results
        """
        try:
            pdf_url = master_data.get_pdf_url()
            if not pdf_url:
                return {'success': False, 'error': 'No PDF URL available for this RS question'}
            
            # Prepare metadata
            metadata = {
                'question_id': master_data.id,
                'question_number': master_data.question_number,
                'session_number': master_data.session_number,
                'question_type': master_data.question_type,
                'ministry': master_data.ministry,
                'date': master_data.date.isoformat() if master_data.date else None,
                'institution': 'rajya_sabha'
            }
            
            # Download using unified service
            result = self.download_pdf(pdf_url, 'rs_question', metadata)
            
            if result['success']:
                # Update master data record
                master_data.is_processed = True
                master_data.processed_at = timezone.now()
                master_data.last_fetched = timezone.now()
                master_data.save()
                
                # Create DocumentFile record
                doc_file, created = DocumentFile.objects.get_or_create(
                    original_url=pdf_url,
                    defaults={
                        'document_category': 'parl_rs_question',
                        'file_type': 'rs_question',
                        'file_name': result['filename'],
                        'file_path': result.get('local_path', ''),
                        'file_size': result['file_size'],
                        'status': 'completed',
                        'downloaded_at': timezone.now(),
                        'download_priority': 5
                    }
                )
                
                if not created:
                    # Update existing record
                    doc_file.file_name = result['filename']
                    doc_file.file_path = result.get('local_path', '')
                    doc_file.file_size = result['file_size']
                    doc_file.status = 'completed'
                    doc_file.downloaded_at = timezone.now()
                    doc_file.save()
                
                # Update GCS info if available
                gcs_result = result.get('gcs_result', {})
                if gcs_result.get('success'):
                    doc_file.gcs_upload_status = 'completed'
                    doc_file.gcs_bucket_name = gcs_result.get('bucket_name', '')
                    doc_file.gcs_object_key = gcs_result.get('object_key', '')
                    doc_file.gcs_url = gcs_result.get('gcs_url', '')
                    doc_file.gcs_uploaded_at = timezone.now()
                    doc_file.save()
            
            return result
            
        except Exception as e:
            logger.error(f"Unified RS question PDF download failed: {e}")
            return {'success': False, 'error': str(e)}
