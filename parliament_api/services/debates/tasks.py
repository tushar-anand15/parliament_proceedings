from celery import shared_task
from django.utils import timezone
from django.db import transaction
import logging

from services.questions.models import LokSabha, Session
from services.scraper.models import ScrapingJob
from .models import Debate, DebateSpeech, DebateTag, SessionDateCache
from .debate_scraper_service import DebateScraperService
from services.files.pdf_download_service import UnifiedPDFDownloadService

logger = logging.getLogger(__name__)


@shared_task(bind=True, name='debates.scrape_debates', 
              autoretry_for=(Exception,), 
              retry_kwargs={'max_retries': 3, 'countdown': 60},
              retry_backoff=True,
              retry_backoff_max=300,
              retry_jitter=True)
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
                # Convert date object to string format expected by API (DD/MM/YYYY)
                date_str = date.strftime('%d/%m/%Y')
                debate_info = scraper._fetch_debate_info_with_fallback(
                    loksabha_no, session_no, date_str
                )
                
                if not debate_info:
                    logger.warning(f"No debate info found for {date}")
                    continue
                
                # Handle both single dict and list responses
                if isinstance(debate_info, dict):
                    debate_list = [debate_info]
                elif isinstance(debate_info, list):
                    debate_list = debate_info
                else:
                    logger.warning(f"Unexpected debate_info format: {type(debate_info)}")
                    continue
                
                # Process each debate
                for debate_data in debate_list:
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
                            
                            # Queue PDF download if requested and URL available (includes GCS upload)
                            if download_pdfs and debate.pdf_url and not debate.is_downloaded:
                                try:
                                    logger.info(f"Queuing PDF download for {debate.debate_id}")
                                    scraper._queue_pdf_download(debate)
                                    logger.info(f"PDF download queued for {debate.debate_id}")
                                except Exception as e:
                                    logger.error(f"PDF queue error for {debate.debate_id}: {str(e)}")
                                    debate.status = 'failed'
                                    debate.error_message = str(e)
                                    debate.save()
                                    errors.append(f"PDF queue failed for {debate.debate_id}: {str(e)}")
                    
                    except Exception as e:
                        error_msg = f"Error processing debate data: {str(e)}"
                        logger.error(error_msg)
                        errors.append(error_msg)
            
            except Exception as e:
                error_msg = f"Error processing date {date}: {str(e)}"
                logger.error(error_msg)
                errors.append(error_msg)
        
        # Download pending PDFs if requested - PARALLEL DISPATCH
        pdfs_dispatched = 0
        if download_pdfs:
            self.update_state(
                state='PROGRESS',
                meta={
                    'status': 'Preparing parallel PDF downloads...',
                    'progress': 90,
                    'debates_created': debates_created,
                    'debates_updated': debates_updated,
                    'errors': len(errors),
                    'phase': 'pdf_dispatch'
                }
            )
            
            # Get all pending debates for this session
            pending_debates = Debate.objects.filter(
                lok_sabha=lok_sabha,
                session=session,
                status='pending',
                pdf_url__isnull=False
            ).exclude(pdf_url='')
            
            pending_count = pending_debates.count()
            logger.info(f"Found {pending_count} pending debates for PARALLEL PDF download")
            
            if pending_count > 0:
                # Collect all download tasks for parallel dispatch
                from celery import group
                from services.files.tasks import download_pdf_unified_task
                
                download_tasks = []
                for debate in pending_debates:
                    try:
                        # Create task signature for this debate
                        download_tasks.append(
                            download_pdf_unified_task.si('debate', debate.id)
                        )
                    except Exception as e:
                        logger.error(f"Error preparing download for {debate.debate_id}: {e}")
                        errors.append(f"PDF prep failed for {debate.debate_id}: {str(e)}")
                
                # Dispatch ALL PDFs in parallel using group()
                if download_tasks:
                    job = group(download_tasks)
                    group_result = job.apply_async()
                    pdfs_dispatched = len(download_tasks)
                    
                    logger.info(f"✅ PARALLEL DISPATCH: {pdfs_dispatched} debate PDFs dispatched simultaneously!")
                    logger.info(f"   Group ID: {group_result.id}")
                    logger.info(f"   Worker pool will process these {pdfs_dispatched} debate PDFs in parallel")
        
        # Final progress update
        self.update_state(
            state='PROGRESS',
            meta={
                'status': 'Finalizing...',
                'progress': 95,
                'debates_created': debates_created,
                'debates_updated': debates_updated,
                'pdfs_dispatched': pdfs_dispatched,
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
            'pdfs_dispatched': pdfs_dispatched,
            'note': f'{pdfs_dispatched} PDF downloads dispatched in parallel - check Celery Flower for progress',
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


@shared_task(bind=True, name='debates.download_pdf',
              autoretry_for=(Exception,),
              retry_kwargs={'max_retries': 3, 'countdown': 60},
              retry_backoff=True,
              retry_backoff_max=300,
              retry_jitter=True)
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
        
        # Initialize unified PDF service
        pdf_service = UnifiedPDFDownloadService()
        
        # Download PDF using unified service
        result = pdf_service.download_debate_pdf_unified(debate)
        
        if result['success']:
            return {
                'status': 'SUCCESS',
                'debate_id': debate_id,
                'filename': result.get('filename', ''),
                'file_size': result.get('file_size', 0),
                'gcs_uploaded': result.get('gcs_result', {}).get('success', False),
                'message': f'PDF downloaded successfully for {debate.debate_id}'
            }
        else:
            return {
                'status': 'FAILED',
                'debate_id': debate_id,
                'error': result.get('error', 'PDF download failed')
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


# ==========================================
# RS DEBATES TASKS
# ==========================================

@shared_task(bind=True, name='debates.scrape_rs_verbatim_debates',
              autoretry_for=(Exception,),
              retry_kwargs={'max_retries': 3, 'countdown': 60},
              retry_backoff=True)
def scrape_rs_verbatim_debates_task(self, session_no: int, download_pdfs: bool = True, limit_dates: int = None):
    """
    Celery task for scraping RS verbatim debates for a session
    
    Args:
        session_no: RS session number (e.g., 268)
        download_pdfs: Whether to download PDFs
        limit_dates: Limit to first N dates (for testing)
    """
    try:
        from .rs_debate_scraper_service import RSDebateScraperService
        
        self.update_state(
            state='PROGRESS',
            meta={'status': f'Scraping RS verbatim debates for session {session_no}', 'progress': 0}
        )
        
        logger.info(f"Starting RS verbatim debate scraping for session {session_no}")
        
        scraper = RSDebateScraperService()
        result = scraper.scrape_verbatim_debates_for_session(
            session_no=session_no,
            download_pdfs=download_pdfs,
            limit_dates=limit_dates
        )
        
        logger.info(f"RS verbatim scraping completed: {result['debates_created']} created, {result['debates_updated']} updated")
        
        return result
        
    except Exception as e:
        logger.error(f"RS verbatim scraping failed: {e}")
        raise


@shared_task(bind=True, name='debates.scrape_rs_official_debates',
              autoretry_for=(Exception,),
              retry_kwargs={'max_retries': 3, 'countdown': 60},
              retry_backoff=True)
def scrape_rs_official_debates_task(self, session_no: int, download_pdfs: bool = True, batch_size: int = 50):
    """
    Celery task for scraping RS official debates (Q&A) for a session
    
    Args:
        session_no: RS session number
        download_pdfs: Whether to download PDFs
        batch_size: Number of records per API call
    """
    try:
        from .rs_debate_scraper_service import RSDebateScraperService
        
        self.update_state(
            state='PROGRESS',
            meta={'status': f'Scraping RS official debates for session {session_no}', 'progress': 0}
        )
        
        logger.info(f"Starting RS official debate scraping for session {session_no}")
        
        scraper = RSDebateScraperService()
        result = scraper.scrape_official_debates_for_session(
            session_no=session_no,
            download_pdfs=download_pdfs,
            batch_size=batch_size
        )
        
        logger.info(f"RS official scraping completed: {result['debates_created']} created, {result['debates_updated']} updated")
        
        return result
        
    except Exception as e:
        logger.error(f"RS official scraping failed: {e}")
        raise


@shared_task(bind=True, name='debates.scrape_recent_rs_debates',
              autoretry_for=(Exception,),
              retry_kwargs={'max_retries': 2, 'countdown': 120},
              retry_backoff=True)
def scrape_recent_rs_debates_task(self, recent_sessions: int = 5, download_pdfs: bool = True):
    """
    Celery task for scraping recent RS debates (both verbatim and official)
    
    Args:
        recent_sessions: Number of recent sessions to scrape
        download_pdfs: Whether to download PDFs
    """
    try:
        from .rs_debate_scraper_service import RSDebateScraperService
        
        self.update_state(
            state='PROGRESS',
            meta={'status': f'Scraping recent RS debates ({recent_sessions} sessions)', 'progress': 0}
        )
        
        logger.info(f"Starting recent RS debate scraping ({recent_sessions} sessions)")
        
        scraper = RSDebateScraperService()
        result = scraper.scrape_recent_rs_debates(
            recent_sessions=recent_sessions,
            download_pdfs=download_pdfs
        )
        
        # Aggregate results
        total_created = sum(r['debates_created'] for r in result['verbatim_results']) + \
                        sum(r['debates_created'] for r in result['official_results'])
        total_updated = sum(r['debates_updated'] for r in result['verbatim_results']) + \
                        sum(r['debates_updated'] for r in result['official_results'])
        
        logger.info(f"Recent RS scraping completed: {total_created} created, {total_updated} updated")
        
        return result
        
    except Exception as e:
        logger.error(f"Recent RS scraping failed: {e}")
        raise


@shared_task(bind=True, name='debates.download_rs_debate_pdf',
              autoretry_for=(Exception,),
              retry_kwargs={'max_retries': 3, 'countdown': 30},
              retry_backoff=True)
def download_rs_debate_pdf_task(self, debate_id: str):
    """
    Celery task for downloading a single RS debate PDF
    
    Args:
        debate_id: Debate UUID
    """
    try:
        from .rs_debate_scraper_service import RSDebateScraperService
        
        self.update_state(
            state='PROGRESS',
            meta={'status': f'Downloading RS debate {debate_id}', 'progress': 50}
        )
        
        # Get debate
        debate = Debate.objects.get(debate_id=debate_id)
        
        scraper = RSDebateScraperService()
        result = scraper.download_debate_pdf(debate)
        
        if result['status'] == 'SUCCESS':
            logger.info(f"RS debate PDF downloaded: {debate_id}")
        else:
            logger.error(f"RS debate PDF download failed: {debate_id} - {result.get('error')}")
        
        return result
        
    except Debate.DoesNotExist:
        logger.error(f"Debate not found: {debate_id}")
        return {
            'status': 'ERROR',
            'message': f'Debate {debate_id} not found'
        }
    except Exception as e:
        logger.error(f"RS PDF download failed: {e}")
        raise
