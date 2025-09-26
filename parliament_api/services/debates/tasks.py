from celery import shared_task
from django.utils import timezone
from django.db import transaction
import logging

from services.questions.models import LokSabha, Session
from services.scraper.models import ScrapingJob
from .models import Debate, DebateSpeech, DebateTag, SessionDateCache
from .debate_scraper_service import DebateScraperService

logger = logging.getLogger(__name__)


@shared_task(bind=True, name='debates.scrape_debates')
def scrape_debates_task(self, 
                       loksabha_no: str,
                       session_no: str,
                       start_date: str = None,
                       end_date: str = None,
                       job_id: int = None,
                       download_pdfs: bool = True):
    """
    Celery task for scraping debates
    
    Args:
        loksabha_no: Lok Sabha number (e.g., "18")
        session_no: Session number (e.g., "V")
        start_date: Start date in YYYY-MM-DD format (optional)
        end_date: End date in YYYY-MM-DD format (optional)
        job_id: ScrapingJob ID to update
        download_pdfs: Whether to download PDFs
    """
    
    try:
        # Update task status
        self.update_state(
            state='PROGRESS',
            meta={'status': 'Starting debate scraping...', 'progress': 0}
        )
        
        # Get the scraping job
        if job_id:
            try:
                job = ScrapingJob.objects.get(id=job_id)
                job.status = 'running'
                job.started_at = timezone.now()
                job.save()
            except ScrapingJob.DoesNotExist:
                logger.error(f"ScrapingJob {job_id} not found")
                return {'status': 'FAILED', 'error': 'Job not found'}
        
        # Create or get LokSabha
        lok_sabha, created = LokSabha.objects.get_or_create(
            number=loksabha_no,
            defaults={'is_current': loksabha_no == "18"}
        )
        
        # Create or get Session
        session, created = Session.objects.get_or_create(
            lok_sabha=lok_sabha,
            session_number=session_no
        )
        
        # Update progress
        self.update_state(
            state='PROGRESS',
            meta={'status': 'Fetching session dates...', 'progress': 10}
        )
        
        # Initialize scraper service
        scraper = DebateScraperService()
        scraper.scraping_job = job if job_id else None
        
        # Get session dates
        session_dates = scraper._get_session_dates(loksabha_no, session_no)
        
        if not session_dates:
            error_msg = f"No session dates found for LS{loksabha_no} Session {session_no}"
            logger.error(error_msg)
            
            if job_id:
                job.status = 'failed'
                job.completed_at = timezone.now()
                job.save()
            
            return {'status': 'FAILED', 'error': error_msg}
        
        # Filter dates if start_date/end_date provided
        if start_date or end_date:
            from datetime import datetime
            
            # Convert session_dates from strings to date objects for comparison
            # session_dates come as strings in DD/MM/YYYY format from API
            converted_dates = []
            parse_errors = 0
            
            for date_str in session_dates:
                try:
                    # Parse DD/MM/YYYY format to date object
                    date_obj = datetime.strptime(date_str, '%d/%m/%Y').date()
                    converted_dates.append(date_obj)
                except ValueError as e:
                    parse_errors += 1
                    logger.warning(f"Could not parse date '{date_str}': {e}")
                    continue
            
            if parse_errors > 0:
                logger.warning(f"Failed to parse {parse_errors} out of {len(session_dates)} dates")
            
            if not converted_dates:
                error_msg = f"No valid dates could be parsed from session dates: {session_dates}"
                logger.error(error_msg)
                return {'status': 'FAILED', 'error': error_msg}
            
            session_dates = converted_dates
            logger.info(f"Successfully converted {len(session_dates)} dates for filtering")
            
            original_count = len(session_dates)
            
            if start_date:
                start_dt = datetime.strptime(start_date, '%Y-%m-%d').date()
                session_dates = [d for d in session_dates if d >= start_dt]
                logger.info(f"After start_date filter ({start_date}): {len(session_dates)} dates remaining")
            
            if end_date:
                end_dt = datetime.strptime(end_date, '%Y-%m-%d').date()
                session_dates = [d for d in session_dates if d <= end_dt]
                logger.info(f"After end_date filter ({end_date}): {len(session_dates)} dates remaining")
            
            logger.info(f"Date filtering: {original_count} -> {len(session_dates)} dates")
        
        total_dates = len(session_dates)
        debates_created = 0
        debates_updated = 0
        errors = []
        
        logger.info(f"Processing {total_dates} dates for LS{loksabha_no} Session {session_no}")
        
        # Process each date
        for i, date in enumerate(session_dates):
            try:
                # Update progress
                progress = int((i / total_dates) * 80) + 10  # 10-90% range
                self.update_state(
                    state='PROGRESS',
                    meta={
                        'status': f'Processing date {date} ({i+1}/{total_dates})',
                        'progress': progress,
                        'current_date': str(date),
                        'processed': i,
                        'total': total_dates
                    }
                )
                
                # Fetch debate info for this date
                debate_info = scraper._fetch_debate_info_with_fallback(
                    loksabha_no, session_no, date
                )
                
                if not debate_info:
                    logger.warning(f"No debate info found for {date}")
                    continue
                
                # Process each debate
                for debate_data in debate_info:
                    try:
                        with transaction.atomic():
                            # Generate debate ID
                            debate_id = f"{loksabha_no}_{session_no}_{date.strftime('%Y%m%d')}"
                            
                            # Create or update debate
                            debate, created = Debate.objects.get_or_create(
                                debate_id=debate_id,
                                defaults={
                                    'lok_sabha': lok_sabha,
                                    'session': session,
                                    'debate_date': date,
                                    'pdf_url': debate_data.get('pdf_url', ''),
                                    'status': 'pending' if download_pdfs else 'not_available',
                                    'raw_api_data': debate_data
                                }
                            )
                            
                            if created:
                                debates_created += 1
                                logger.info(f"Created debate: {debate.debate_id}")
                            else:
                                # Update existing debate
                                debate.pdf_url = debate_data.get('pdf_url', debate.pdf_url)
                                debate.raw_api_data = debate_data
                                debate.save()
                                debates_updated += 1
                                logger.info(f"Updated debate: {debate.debate_id}")
                            
                            # Download PDF if requested and URL available
                            if download_pdfs and debate.pdf_url:
                                try:
                                    logger.info(f"Starting PDF download for {debate.debate_id}")
                                    pdf_path = scraper.download_debate_pdf(debate)
                                    if pdf_path:
                                        debate.status = 'completed'
                                        debate.save()
                                        logger.info(f"Downloaded PDF: {pdf_path}")
                                    else:
                                        debate.status = 'failed'
                                        debate.save()
                                        logger.warning(f"Failed to download PDF for {debate.debate_id}")
                                except Exception as e:
                                    logger.error(f"PDF download error for {debate.debate_id}: {str(e)}")
                                    debate.status = 'failed'
                                    debate.error_message = str(e)
                                    debate.save()
                                    errors.append(f"PDF download failed for {debate.debate_id}: {str(e)}")
                    
                    except Exception as e:
                        error_msg = f"Error processing debate data: {str(e)}"
                        logger.error(error_msg)
                        errors.append(error_msg)
            
            except Exception as e:
                error_msg = f"Error processing date {date}: {str(e)}"
                logger.error(error_msg)
                errors.append(error_msg)
        
        # Download pending PDFs if requested
        pdfs_downloaded = 0
        if download_pdfs:
            self.update_state(
                state='PROGRESS',
                meta={
                    'status': 'Downloading pending PDFs...',
                    'progress': 90,
                    'debates_created': debates_created,
                    'debates_updated': debates_updated,
                    'errors': len(errors)
                }
            )
            
            # Get all pending debates for this session
            pending_debates = Debate.objects.filter(
                lok_sabha=lok_sabha,
                session=session,
                status='pending',
                pdf_url__isnull=False
            ).exclude(pdf_url='')
            
            logger.info(f"Found {pending_debates.count()} pending debates to download")
            
            for debate in pending_debates:
                try:
                    logger.info(f"Downloading PDF for {debate.debate_id}")
                    success = scraper.download_debate_pdf(debate)
                    if success:
                        pdfs_downloaded += 1
                        logger.info(f"Successfully downloaded PDF for {debate.debate_id}")
                    else:
                        logger.warning(f"Failed to download PDF for {debate.debate_id}")
                except Exception as e:
                    logger.error(f"Error downloading PDF for {debate.debate_id}: {e}")
                    errors.append(f"PDF download failed for {debate.debate_id}: {str(e)}")
        
        # Final progress update
        self.update_state(
            state='PROGRESS',
            meta={
                'status': 'Finalizing...',
                'progress': 95,
                'debates_created': debates_created,
                'debates_updated': debates_updated,
                'pdfs_downloaded': pdfs_downloaded,
                'errors': len(errors)
            }
        )
        
        # Update job status
        if job_id:
            job.status = 'completed'
            job.completed_at = timezone.now()
            job.save()
        
        # Return final result
        result = {
            'status': 'SUCCESS',
            'loksabha_no': loksabha_no,
            'session_no': session_no,
            'dates_processed': total_dates,
            'debates_created': debates_created,
            'debates_updated': debates_updated,
            'total_debates': debates_created + debates_updated,
            'pdfs_downloaded': pdfs_downloaded,
            'errors': errors,
            'error_count': len(errors)
        }
        
        logger.info(f"Debate scraping completed: {result}")
        return result
        
    except Exception as e:
        error_msg = f"Debate scraping task failed: {str(e)}"
        logger.error(error_msg, exc_info=True)
        
        # Update job status
        if job_id:
            try:
                job = ScrapingJob.objects.get(id=job_id)
                job.status = 'failed'
                job.completed_at = timezone.now()
                job.save()
            except ScrapingJob.DoesNotExist:
                pass
        
        return {'status': 'FAILED', 'error': error_msg}


@shared_task(bind=True, name='debates.download_pdf')
def download_pdf_task(self, debate_id: int):
    """
    Celery task for downloading a single debate PDF
    
    Args:
        debate_id: ID of the Debate to download PDF for
    """
    try:
        from .models import Debate
        
        debate = Debate.objects.get(id=debate_id)
        
        # Update task status
        self.update_state(
            state='PROGRESS',
            meta={'status': f'Downloading PDF for {debate.title}', 'progress': 0}
        )
        
        # Initialize scraper service
        scraper = DebateScraperService()
        
        # Download PDF
        pdf_path = scraper.download_debate_pdf(debate)
        
        if pdf_path:
            debate.status = 'downloaded'
            debate.pdf_path = pdf_path
            debate.save()
            
            return {
                'status': 'SUCCESS',
                'debate_id': debate_id,
                'pdf_path': pdf_path,
                'message': f'PDF downloaded successfully for {debate.title}'
            }
        else:
            debate.status = 'download_failed'
            debate.save()
            
            return {
                'status': 'FAILED',
                'debate_id': debate_id,
                'error': 'PDF download failed'
            }
    
    except Debate.DoesNotExist:
        return {
            'status': 'FAILED',
            'debate_id': debate_id,
            'error': 'Debate not found'
        }
    except Exception as e:
        logger.error(f"PDF download task failed for debate {debate_id}: {str(e)}")
        return {
            'status': 'FAILED',
            'debate_id': debate_id,
            'error': str(e)
        }


@shared_task(bind=True, name='debates.bulk_download_pdfs')
def bulk_download_pdfs_task(self, debate_ids: list):
    """
    Celery task for downloading multiple debate PDFs
    
    Args:
        debate_ids: List of Debate IDs to download PDFs for
    """
    try:
        from .models import Debate
        
        total_debates = len(debate_ids)
        downloaded = 0
        failed = 0
        errors = []
        
        for i, debate_id in enumerate(debate_ids):
            try:
                # Update progress
                progress = int((i / total_debates) * 100)
                self.update_state(
                    state='PROGRESS',
                    meta={
                        'status': f'Downloading PDF {i+1}/{total_debates}',
                        'progress': progress,
                        'downloaded': downloaded,
                        'failed': failed
                    }
                )
                
                # Download PDF for this debate
                result = download_pdf_task.delay(debate_id).get()
                
                if result['status'] == 'SUCCESS':
                    downloaded += 1
                else:
                    failed += 1
                    errors.append(f"Debate {debate_id}: {result.get('error', 'Unknown error')}")
            
            except Exception as e:
                failed += 1
                error_msg = f"Debate {debate_id}: {str(e)}"
                errors.append(error_msg)
                logger.error(error_msg)
        
        return {
            'status': 'SUCCESS',
            'total_debates': total_debates,
            'downloaded': downloaded,
            'failed': failed,
            'errors': errors
        }
    
    except Exception as e:
        logger.error(f"Bulk PDF download task failed: {str(e)}")
        return {
            'status': 'FAILED',
            'error': str(e)
        }
