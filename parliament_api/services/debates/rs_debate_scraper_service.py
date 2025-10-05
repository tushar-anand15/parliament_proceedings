"""
RS Debate Scraper Service
Handles scraping and downloading RS debates (both verbatim and official)
"""

import logging
import uuid
import time
import random
import requests
from datetime import datetime
from typing import Dict, List, Optional
from django.utils import timezone
from django.db import transaction
from django.conf import settings

from services.questions.models import ParliamentInstitution
from services.files.models import DocumentFile, DownloadQueue
from services.scraper.models import ScrapingJob, ScrapingError
from services.cloud_storage.gcs_service import GCSService
from services.utils.batch_writer import BatchWriter
from .models import Debate
from .rs_debate_master_data_service import RSDebateMasterDataService

logger = logging.getLogger(__name__)


class RSDebateScraperService:
    """Service for scraping RS debates and downloading PDFs"""
    
    def __init__(self, scraping_job: ScrapingJob = None):
        self.scraping_job = scraping_job
        self.master_service = RSDebateMasterDataService()
        self.gcs_service = GCSService()
        self.session = requests.Session()
        
        # Set headers
        self.session.headers.update({
            'Accept': 'application/json, text/plain, */*',
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        })
    
    # ==========================================
    # VERBATIM DEBATES SCRAPING
    # ==========================================
    
    def scrape_verbatim_debates_for_session(
        self, 
        session_no: int,
        download_pdfs: bool = True,
        limit_dates: Optional[int] = None
    ) -> Dict:
        """
        Scrape all verbatim debates for an RS session
        
        Args:
            session_no: RS session number (e.g., 268)
            download_pdfs: Whether to download PDFs
            limit_dates: Limit to first N dates (for testing)
        """
        result = {
            'status': 'SUCCESS',
            'session_no': session_no,
            'debates_created': 0,
            'debates_updated': 0,
            'pdfs_queued': 0,
            'errors': []
        }
        
        try:
            logger.info(f"🏛️  Scraping RS verbatim debates for session {session_no}")
            
            # Get RS institution
            rs_institution, _ = ParliamentInstitution.objects.get_or_create(
                name='rajya_sabha',
                defaults={'full_name': 'Rajya Sabha'}
            )
            
            # Get session dates
            dates = self.master_service.fetch_verbatim_session_dates(session_no)
            
            if not dates:
                result['status'] = 'NO_DATA'
                result['errors'].append(f'No sitting dates found for session {session_no}')
                return result
            
            # Limit dates if specified (for testing)
            if limit_dates:
                dates = dates[:limit_dates]
            
            logger.info(f"📅 Processing {len(dates)} dates for session {session_no}")
            
            # Process each date
            for date_obj in dates:
                sitting_date_iso = date_obj.get('SittingDate', '')
                date_str = self.master_service.convert_iso_to_dd_mm_yyyy(sitting_date_iso)
                
                if not date_str:
                    continue
                
                try:
                    # Fetch verbatim debates for this date
                    debates_data = self.master_service.fetch_verbatim_debates(session_no, date_str)
                    
                    if not debates_data:
                        logger.warning(f"No verbatim debates found for {session_no}/{date_str}")
                        continue
                    
                    # Create debate records for each time slot
                    for debate_item in debates_data:
                        try:
                            debate, created = self._save_verbatim_debate(
                                rs_institution,
                                session_no,
                                date_str,
                                debate_item
                            )
                            
                            if created:
                                result['debates_created'] += 1
                                logger.info(f"✅ Created: {debate.debate_date} - {debate.time_slot}")
                            else:
                                result['debates_updated'] += 1
                                logger.info(f"🔄 Updated: {debate.debate_date} - {debate.time_slot}")
                            
                            # Queue PDF download
                            if download_pdfs and debate.pdf_url and debate.status == 'pending':
                                self._queue_verbatim_pdf_download(debate)
                                result['pdfs_queued'] += 1
                        
                        except Exception as e:
                            error_msg = f"Error saving debate: {e}"
                            logger.error(error_msg)
                            result['errors'].append(error_msg)
                    
                    # Random delay between dates
                    from django.conf import settings
                    time.sleep(random.uniform(settings.API_REQUEST_DELAY_MIN, settings.API_REQUEST_DELAY_MAX))
                
                except Exception as e:
                    error_msg = f"Error processing date {date_str}: {e}"
                    logger.error(error_msg)
                    result['errors'].append(error_msg)
            
            logger.info(f"✅ Verbatim scraping complete: {result['debates_created']} created, {result['debates_updated']} updated")
            return result
            
        except Exception as e:
            logger.error(f"❌ Error scraping verbatim debates: {e}")
            result['status'] = 'ERROR'
            result['errors'].append(str(e))
            return result
    
    def _save_verbatim_debate(
        self,
        rs_institution: ParliamentInstitution,
        session_no: int,
        date_str: str,
        debate_item: Dict
    ) -> tuple:
        """Save or update a verbatim debate record"""
        
        # Extract fields
        file_url = debate_item.get('FileUrl', '')
        time_slot = debate_item.get('Time', '')
        file_name = debate_item.get('Name', '')
        file_size = debate_item.get('FileSize', 0)
        language = debate_item.get('Language', 'Verbatim')
        
        # Convert date
        debate_date = datetime.strptime(date_str, '%d/%m/%Y').date()
        
        # Create or update Debate record
        debate, created = Debate.objects.update_or_create(
            parent_institution=rs_institution,
            debate_date=debate_date,
            debate_category='verbatim',
            time_slot=time_slot or 'Unknown',
            language='en',
            defaults={
                'debate_id': str(uuid.uuid4()),
                'pdf_url': file_url,
                'file_size': file_size,
                'raw_api_data': debate_item,
                'status': 'pending',
                'debate_type': 'verbatim'
            }
        )
        
        return debate, created
    
    def _queue_verbatim_pdf_download(self, debate: Debate):
        """Queue a verbatim debate PDF for download"""
        try:
            # Create download queue entry
            DownloadQueue.objects.get_or_create(
                url=debate.pdf_url,
                defaults={
                    'file_type': 'debate',
                    'priority': 5,
                    'status': 'pending',
                    'metadata': {
                        'debate_id': str(debate.debate_id),
                        'date': str(debate.debate_date),
                        'time_slot': debate.time_slot,
                        'session': 'RS',
                        'category': 'verbatim'
                    }
                }
            )
            logger.info(f"📥 Queued PDF download: {debate.debate_date} - {debate.time_slot}")
        except Exception as e:
            logger.error(f"Error queuing PDF: {e}")
    
    # ==========================================
    # OFFICIAL DEBATES SCRAPING
    # ==========================================
    
    def scrape_official_debates_for_session(
        self,
        session_no: int,
        download_pdfs: bool = True,
        api_batch_size: int = 50,
        db_batch_size: int = 2000
    ) -> Dict:
        """
        Scrape official debates (Q&A) for an RS session using smart batch writer
        
        Args:
            session_no: RS session number
            download_pdfs: Whether to download PDFs
            api_batch_size: Number of records per API call
            db_batch_size: Number of records to accumulate before DB write
        """
        result = {
            'status': 'SUCCESS',
            'session_no': session_no,
            'debates_created': 0,
            'debates_updated': 0,
            'pdfs_queued': 0,
            'total_records': 0,
            'api_calls': 0,
            'db_flushes': 0,
            'errors': []
        }
        
        try:
            logger.info(f"📚 Scraping RS official debates for session {session_no}")
            
            # Get RS institution
            rs_institution, _ = ParliamentInstitution.objects.get_or_create(
                name='rajya_sabha',
                defaults={'full_name': 'Rajya Sabha'}
            )
            
            # Initialize smart batch writer (auto-flushes every 2000 records)
            with BatchWriter(
                model_class=Debate,
                batch_size=db_batch_size,
                unique_fields=['parent_institution', 'debate_date', 'debate_category', 'time_slot'],
                update_fields=['pdf_url', 'file_size', 'raw_api_data', 'status']
            ) as batch_writer:
                
                # Fetch all debates for this session (paginated API calls)
                start = 0
                
                while True:
                    # Fetch batch from API
                    data = self.master_service.fetch_official_debates(
                        start=start,
                        rows=api_batch_size,
                        session_no=session_no
                    )
                    
                    records = data.get('records', [])
                    total = int(data.get('rowsCount', 0))
                    
                    if not records:
                        break
                    
                    result['total_records'] = total
                    result['api_calls'] += 1
                    
                    # Add each record to batch writer (auto-flushes at 2000)
                    for record in records:
                        try:
                            debate_data = self._prepare_official_debate_data(
                                rs_institution,
                                record
                            )
                            
                            if debate_data:
                                batch_writer.add(debate_data)
                        
                        except Exception as e:
                            error_msg = f"Error preparing record {record.get('resourceId')}: {e}"
                            logger.error(error_msg)
                            result['errors'].append(error_msg)
                    
                    # Move to next batch
                    start += api_batch_size
                    
                    # Check if we've fetched all
                    if start >= total:
                        break
                    
                    # Random delay between API calls
                    from django.conf import settings
                    time.sleep(random.uniform(settings.API_REQUEST_DELAY_MIN, settings.API_REQUEST_DELAY_MAX))
                
                # Context manager will auto-flush remaining items
            
            # Get batch writer stats
            writer_stats = batch_writer.get_stats()
            result['debates_created'] = writer_stats['total_created']
            result['debates_updated'] = writer_stats['total_updated']
            result['db_flushes'] = writer_stats['flush_count']
            
            logger.info(
                f"✅ Official debates scraping complete: "
                f"{result['debates_created']} created, "
                f"{result['debates_updated']} updated "
                f"({result['db_flushes']} DB flushes, {result['api_calls']} API calls)"
            )
            
            # Queue PDFs if requested (done separately to avoid memory issues)
            if download_pdfs:
                result['pdfs_queued'] = self._queue_official_pdfs_for_session(session_no)
            
            return result
            
        except Exception as e:
            logger.error(f"❌ Error scraping official debates: {e}")
            result['status'] = 'ERROR'
            result['errors'].append(str(e))
            return result
    
    def _prepare_official_debate_data(
        self,
        rs_institution: ParliamentInstitution,
        record: Dict
    ) -> Optional[Dict]:
        """
        Prepare official debate data for batch writer
        Returns dict ready for BatchWriter.add()
        """
        try:
            # Extract fields
            resource_id = record.get('resourceId', '')
            title = record.get('title', '')
            date_str = record.get('date', '')  # YYYY-MM-DD format
            debate_type = record.get('type', '')
            session_no = record.get('sessionNo', '')
            question_no = record.get('questionNo', '')
            question_type = record.get('questionType', '')
            
            # Get PDF URL (first file in array)
            files = record.get('files', [])
            pdf_url = files[0] if files else ''
            
            # Parse date
            if not date_str:
                return None
            debate_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            
            # Determine debate category
            if 'Part 1' in debate_type:
                debate_category = 'official_qa'
            elif 'Part 2' in debate_type:
                debate_category = 'official_other'
            else:
                debate_category = 'official'
            
            # Prepare data for batch writer
            return {
                'debate_id': str(uuid.uuid4()),
                'parent_institution': rs_institution,
                'debate_date': debate_date,
                'debate_category': debate_category,
                'time_slot': question_no or '',
                'language': 'en',
                'pdf_url': pdf_url,
                'raw_api_data': record,
                'status': 'pending',
                'debate_type': 'official'
            }
        
        except Exception as e:
            logger.error(f"Error preparing debate data: {e}")
            return None
    
    def _queue_official_pdfs_for_session(self, session_no: int) -> int:
        """
        Queue all pending official debate PDFs for a session
        Done separately after batch write to avoid memory issues
        
        Returns number of PDFs queued
        """
        try:
            # Query only pending debates for this session
            pending_debates = Debate.objects.filter(
                debate_category__in=['official_qa', 'official_other', 'official'],
                status='pending',
                pdf_url__isnull=False
            ).exclude(pdf_url='')[:1000]  # Limit to 1000 at a time
            
            queued = 0
            for debate in pending_debates:
                self._queue_official_pdf_download(debate)
                queued += 1
            
            return queued
        
        except Exception as e:
            logger.error(f"Error queuing PDFs: {e}")
            return 0
    
    def _queue_official_pdf_download(self, debate: Debate):
        """Queue an official debate PDF for download"""
        try:
            # Create download queue entry
            DownloadQueue.objects.get_or_create(
                url=debate.pdf_url,
                defaults={
                    'file_type': 'debate',
                    'priority': 5,
                    'status': 'pending',
                    'metadata': {
                        'debate_id': str(debate.debate_id),
                        'date': str(debate.debate_date),
                        'question_no': debate.time_slot,
                        'session': 'RS',
                        'category': debate.debate_category
                    }
                }
            )
            logger.info(f"📥 Queued official PDF: {debate.debate_date} Q#{debate.time_slot}")
        except Exception as e:
            logger.error(f"Error queuing PDF: {e}")
    
    # ==========================================
    # PDF DOWNLOAD EXECUTION
    # ==========================================
    
    def download_debate_pdf(self, debate: Debate) -> Dict:
        """
        Download PDF for a specific debate
        
        Args:
            debate: Debate model instance
            
        Returns:
            Dict with download result
        """
        try:
            if not debate.pdf_url:
                return {
                    'status': 'ERROR',
                    'message': 'No PDF URL available'
                }
            
            # Update status
            debate.status = 'downloading'
            debate.download_attempts += 1
            debate.last_download_attempt = timezone.now()
            debate.save()
            
            logger.info(f"📥 Downloading PDF: {debate.pdf_url}")
            
            # Download PDF
            response = self.session.get(debate.pdf_url, timeout=120, stream=True)
            response.raise_for_status()
            
            # Generate filename
            date_str = debate.debate_date.strftime('%Y%m%d')
            time_slot = debate.time_slot.replace(':', '').replace(' ', '_').replace('/', '_') if debate.time_slot else 'unknown'
            filename = f"rs_debate_{debate.debate_category}_{date_str}_{time_slot}.pdf"
            
            # Create DocumentFile
            doc_file = DocumentFile.objects.create(
                file_type='debate',
                original_filename=filename,
                file_size=len(response.content),
                upload_date=timezone.now(),
                metadata={
                    'debate_id': str(debate.debate_id),
                    'session': 'RS',
                    'date': str(debate.debate_date),
                    'category': debate.debate_category
                }
            )
            
            # Upload to GCS
            try:
                gcs_path = f"debates/rs/{debate.debate_category}/{date_str}/{filename}"
                upload_result = self.gcs_service.upload_file_content(
                    content=response.content,
                    destination_path=gcs_path,
                    content_type='application/pdf'
                )
                
                if upload_result['status'] == 'success':
                    doc_file.gcs_path = gcs_path
                    doc_file.gcs_bucket = self.gcs_service.debates_bucket_name
                    doc_file.save()
                    logger.info(f"☁️  Uploaded to GCS: {gcs_path}")
            except Exception as gcs_error:
                logger.warning(f"GCS upload failed (will use local storage): {gcs_error}")
            
            # Save local file as backup
            local_path = f"media/debates/rs/{debate.debate_category}/{date_str}/{filename}"
            doc_file.file.save(filename, response.raw, save=True)
            
            # Update debate record
            debate.pdf_file = doc_file
            debate.status = 'completed'
            debate.file_size = doc_file.file_size
            debate.save()
            
            logger.info(f"✅ PDF downloaded successfully: {filename}")
            
            return {
                'status': 'SUCCESS',
                'debate_id': str(debate.debate_id),
                'file_path': doc_file.gcs_path or doc_file.file.name,
                'file_size': doc_file.file_size
            }
            
        except Exception as e:
            logger.error(f"❌ Error downloading PDF: {e}")
            
            debate.status = 'failed'
            debate.error_message = str(e)
            debate.save()
            
            return {
                'status': 'FAILED',
                'debate_id': str(debate.debate_id),
                'error': str(e)
            }
    
    # ==========================================
    # BATCH OPERATIONS
    # ==========================================
    
    def scrape_recent_rs_debates(
        self,
        recent_sessions: int = 5,
        download_pdfs: bool = True
    ) -> Dict:
        """
        Scrape recent RS debates (both verbatim and official)
        
        Args:
            recent_sessions: Number of recent sessions to scrape
            download_pdfs: Whether to download PDFs
        """
        result = {
            'status': 'SUCCESS',
            'verbatim_results': [],
            'official_results': [],
            'errors': []
        }
        
        try:
            logger.info(f"🏛️  Scraping recent RS debates ({recent_sessions} sessions)")
            
            # Get recent sessions
            sessions = self.master_service.fetch_verbatim_rs_sessions()
            recent = sessions[-recent_sessions:] if len(sessions) >= recent_sessions else sessions
            
            logger.info(f"📅 Processing sessions: {recent}")
            
            # Process each session
            for session_no in recent:
                # Scrape verbatim debates
                verbatim_result = self.scrape_verbatim_debates_for_session(
                    session_no=session_no,
                    download_pdfs=download_pdfs,
                    limit_dates=3  # Limit to 3 most recent dates
                )
                result['verbatim_results'].append(verbatim_result)
                
                # Scrape official debates
                official_result = self.scrape_official_debates_for_session(
                    session_no=session_no,
                    download_pdfs=download_pdfs,
                    batch_size=50
                )
                result['official_results'].append(official_result)
                
                # Collect errors
                result['errors'].extend(verbatim_result.get('errors', []))
                result['errors'].extend(official_result.get('errors', []))
            
            logger.info(f"✅ Recent RS debates scraping completed")
            return result
            
        except Exception as e:
            logger.error(f"❌ Error scraping recent debates: {e}")
            result['status'] = 'ERROR'
            result['errors'].append(str(e))
            return result
