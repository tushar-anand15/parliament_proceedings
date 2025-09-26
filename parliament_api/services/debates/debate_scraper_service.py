import sys
import os
import json
import logging
import uuid
import threading
import queue
import time
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from django.utils import timezone
from django.db import transaction, models
from django.conf import settings

# Add the scraper directory to Python path
scraper_path = os.path.join(settings.BASE_DIR.parent, 'scraper')
if scraper_path not in sys.path:
    sys.path.append(scraper_path)

from services.questions.models import LokSabha, Session
from services.files.models import DocumentFile, DownloadQueue
from services.scraper.models import ScrapingJob, ScrapingError, ScrapingConfig, DataSource
from .models import Debate, DebateSpeech, DebateTag, SessionDateCache

logger = logging.getLogger(__name__)


class DebateScraperService:
    """
    Service for scraping parliamentary debates and downloading PDFs
    """
    
    def __init__(self, scraping_job: ScrapingJob = None):
        self.scraping_job = scraping_job
        self.base_url = "https://sansad.in/api_ls"
        self.session = requests.Session()
        self.config = ScrapingConfig.get_default()
        
        # Set headers for API requests
        self.session.headers.update({
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Connection': 'keep-alive',
            'Referer': 'https://sansad.in/ls/debates/text-of-debates?tab=uncorrected',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-origin',
            'Sec-GPC': '1',
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36',
            'sec-ch-ua': '"Chromium";v="140", "Not=A?Brand";v="24", "Brave";v="140"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"macOS"'
        })
    
    def start_debate_scraping(self,
                            loksabha_no: str,
                            session_no: str,
                            start_date: Optional[str] = None,
                            end_date: Optional[str] = None,
                            job_name: Optional[str] = None,
                            download_pdfs: bool = True) -> ScrapingJob:
        """
        Start scraping debates for specified Lok Sabha and session using Celery
        
        Args:
            loksabha_no: Lok Sabha number (e.g., "18")
            session_no: Session number (e.g., "V")
            start_date: Start date in YYYY-MM-DD format (optional)
            end_date: End date in YYYY-MM-DD format (optional)
            job_name: Custom job name
            download_pdfs: Whether to download PDFs
        """
        
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
        
        # Create scraping job
        if not job_name:
            job_name = f"Scrape Debates {loksabha_no}th LS Session {session_no}"
        
        job = ScrapingJob.objects.create(
            name=job_name,
            description=f"Scraping debates from {loksabha_no}th Lok Sabha Session {session_no}",
            job_type='debates',
            batch_size=self.config.default_batch_size if self.config else 10,
            worker_count=self.config.default_workers if self.config else 3,
            status='pending'
        )
        
        # Add targets
        job.target_lok_sabhas.add(lok_sabha)
        job.target_sessions.add(session)
        
        self.scraping_job = job
        
        # Start scraping using Celery task
        from .tasks import scrape_debates_task
        
        task = scrape_debates_task.delay(
            loksabha_no=loksabha_no,
            session_no=session_no,
            start_date=start_date,
            end_date=end_date,
            job_id=job.id,
            download_pdfs=download_pdfs
        )
        
        # Store task ID in job for tracking
        job.task_id = task.id
        job.save()
        
        logger.info(f"Started Celery task {task.id} for job {job.id}")
        
        return job
    
    def _execute_debate_scraping(self, 
                               lok_sabha: LokSabha,
                               session: Session,
                               start_date: Optional[str],
                               end_date: Optional[str],
                               download_pdfs: bool):
        """Execute the actual debate scraping process"""
        
        job = self.scraping_job
        job.start_job()
        
        try:
            # Get session dates from the API
            session_dates = self._get_session_dates(lok_sabha.number, session.session_number)
            
            if not session_dates:
                raise Exception(f"No session dates found for {lok_sabha.number}th LS Session {session.session_number}")
            
            # Filter dates if start/end provided
            if start_date:
                start_dt = datetime.strptime(start_date, '%Y-%m-%d').date()
                session_dates = [d for d in session_dates if datetime.strptime(d, '%d/%m/%Y').date() >= start_dt]
            
            if end_date:
                end_dt = datetime.strptime(end_date, '%Y-%m-%d').date()
                session_dates = [d for d in session_dates if datetime.strptime(d, '%d/%m/%Y').date() <= end_dt]
            
            logger.info(f"Found {len(session_dates)} dates to process for debates")
            job.total_questions_expected = len(session_dates)  # Using same field for debates count
            job.save()
            
            # Process each date
            created_count = 0
            updated_count = 0
            failed_count = 0
            
            for date_str in session_dates:
                try:
                    # Transform date: "21/07/2025" → "7/21/2025" (dd/mm/yyyy → m/d/yyyy)
                    date_parts = date_str.split('/')
                    api_date = f"{int(date_parts[1])}/{int(date_parts[0])}/{date_parts[2]}"
                    
                    logger.info(f"Processing debate: LS{lok_sabha.number} Session {session.session_number} Date {api_date}")
                    
                    # Try both session number formats since Parliament API is inconsistent
                    debate_info = self._fetch_debate_info_with_fallback(lok_sabha.number, session.session_number, api_date)
                    
                    if debate_info:
                        # Save or update debate
                        debate, created = self._save_debate(lok_sabha, session, date_str, debate_info)
                        
                        if created:
                            created_count += 1
                        else:
                            updated_count += 1
                        
                        # Queue PDF download if enabled
                        if download_pdfs and debate.pdf_url and not debate.is_downloaded:
                            self._queue_pdf_download(debate)
                    else:
                        logger.warning(f"No debate info found for {date_str}")
                        failed_count += 1
                    
                    # Update progress
                    job.questions_processed += 1  # Using same field
                    job.save()
                    
                    # Small delay between requests
                    time.sleep(0.5)
                    
                except Exception as e:
                    logger.error(f"Error processing debate for {date_str}: {e}")
                    failed_count += 1
                    
                    # Record error
                    ScrapingError.objects.create(
                        scraping_job=job,
                        error_type='api_error',
                        error_message=str(e),
                        api_endpoint=f"{self.base_url}/debate/text-of-debate",
                        request_data={'date': date_str}
                    )
            
            # Update final counts
            job.questions_created = created_count
            job.questions_updated = updated_count
            job.questions_failed = failed_count
            job.complete_job()
            
            logger.info(f"Debate scraping completed: {created_count} created, {updated_count} updated, {failed_count} failed")
            
        except Exception as e:
            logger.error(f"Debate scraping failed: {e}")
            job.fail_job(str(e))
            raise
    
    def _get_session_dates(self, loksabha_no: str, session_no: str, force_refresh: bool = False) -> List[str]:
        """Get all business dates for a session with caching and fallback APIs"""
        
        # Get or create Lok Sabha and Session objects
        lok_sabha = LokSabha.objects.filter(number=loksabha_no).first()
        session_obj = None
        if lok_sabha:
            session_obj = Session.objects.filter(lok_sabha=lok_sabha, session_number=session_no).first()
        
        # Check cache first
        if session_obj and not force_refresh:
            cache = SessionDateCache.objects.filter(lok_sabha=lok_sabha, session=session_obj).first()
            if cache and not cache.is_stale:
                logger.info(f"Using cached dates for {loksabha_no}th LS Session {session_no} (last updated: {cache.last_updated})")
                return cache.available_dates
            elif cache and cache.is_stale:
                logger.info(f"Cache for {loksabha_no}th LS Session {session_no} is stale (last updated: {cache.last_updated})")
        
        # Try multiple API sources with fallback
        logger.info(f"Fetching fresh session dates from API for {loksabha_no}th LS Session {session_no}...")
        
        # Method 1: Try current sansad.in API
        dates = self._get_session_dates_sansad_api(loksabha_no, session_no, lok_sabha, session_obj)
        if dates:
            return dates
            
        # Method 2: Try eparlib API as fallback
        logger.info("Sansad API failed, trying eparlib API as fallback...")
        dates = self._get_session_dates_eparlib_api(loksabha_no, session_no, lok_sabha, session_obj)
        if dates:
            return dates
        
        # Method 3: Fall back to stale cache if available
        if session_obj:
            cache = SessionDateCache.objects.filter(lok_sabha=lok_sabha, session=session_obj).first()
            if cache:
                logger.warning(f"Using stale cache as last resort (last updated: {cache.last_updated})")
                return cache.available_dates
        
        logger.error(f"All methods failed to fetch session dates for {loksabha_no}th LS Session {session_no}")
        return []
    
    def _get_session_dates_sansad_api(self, loksabha_no: str, session_no: str, lok_sabha, session_obj) -> List[str]:
        """Get session dates from the original sansad.in API"""
        
        url = f"{self.base_url}/business/AllLoksabhaAndSessionDates"
        
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            
            # Find the specific Lok Sabha and session
            for ls_data in data:
                if str(ls_data.get('loksabha')) == loksabha_no:
                    available_sessions = []
                    for session_data in ls_data.get('sessions', []):
                        session_number = session_data.get('sessionNo')
                        available_sessions.append(str(session_number))
                        
                        # Try different matching strategies
                        if (str(session_number) == session_no or 
                            str(session_number) == str(self._roman_to_int(session_no)) or
                            str(self._int_to_roman(int(session_number) if str(session_number).isdigit() else 0)) == session_no):
                            dates = session_data.get('dates', [])
                            session_period = session_data.get('sessionPeriod', [])
                            
                            logger.info(f"✅ Sansad API: Found session {session_number} with {len(dates)} dates")
                            
                            # Update cache if we have session object
                            if lok_sabha and session_obj:
                                cache, created = SessionDateCache.objects.update_or_create(
                                    lok_sabha=lok_sabha,
                                    session=session_obj,
                                    defaults={
                                        'available_dates': dates,
                                        'session_period': session_period,
                                        'api_source': 'sansad.in'
                                    }
                                )
                                logger.info(f"{'Created' if created else 'Updated'} date cache for {loksabha_no}th LS Session {session_no}")
                            
                            return dates
                    
                    logger.warning(f"Sansad API: Session {session_no} not found. Available sessions: {', '.join(available_sessions)}")
            
            return []
            
        except Exception as e:
            logger.error(f"Sansad API failed: {e}")
            return []
    
    def _get_session_dates_eparlib_api(self, loksabha_no: str, session_no: str, lok_sabha, session_obj) -> List[str]:
        """Get session dates from the eparlib.sansad.in API as fallback"""
        
        base_url = "https://eparlib.sansad.in/restv3"
        
        try:
            # Step 1: Get available sessions for this Lok Sabha
            sessions_url = f"{base_url}/field/browse"
            sessions_params = {
                'field': 'sessionNo',
                'collectionId': '2',  # Lok Sabha debates collection
                'loksabhaNo': loksabha_no.zfill(2),  # Zero-pad to 2 digits
                'order': 'desc',
                'start': '0',
                'rows': '100',
                'locale': 'en'
            }
            
            # Set headers for eparlib API
            eparlib_headers = {
                'Accept': 'application/json, text/plain, */*',
                'Accept-Language': 'en-US,en;q=0.9',
                'Connection': 'keep-alive',
                'Origin': 'https://sansad.in',
                'Referer': 'https://sansad.in/',
                'Sec-Fetch-Dest': 'empty',
                'Sec-Fetch-Mode': 'cors',
                'Sec-Fetch-Site': 'same-site',
                'User-Agent': self.session.headers['User-Agent']
            }
            
            response = self.session.get(sessions_url, params=sessions_params, headers=eparlib_headers, timeout=30)
            response.raise_for_status()
            
            sessions_data = response.json()
            available_sessions = [record['name'] for record in sessions_data.get('records', [])]
            
            # Step 2: Find matching session (try both Roman and numeric formats)
            target_session_formats = []
            if session_no.isdigit():
                # Convert numeric to Roman
                target_session_formats = [session_no, self._int_to_roman(int(session_no)).lower()]
            else:
                # Convert Roman to numeric or use as-is
                try:
                    numeric = str(self._roman_to_int(session_no))
                    target_session_formats = [session_no.lower(), numeric]
                except:
                    target_session_formats = [session_no.lower()]
            
            matched_session = None
            for session_format in target_session_formats:
                if session_format in available_sessions:
                    matched_session = session_format
                    break
            
            if not matched_session:
                logger.warning(f"Eparlib API: Session {session_no} not found. Available sessions: {', '.join(available_sessions)}")
                return []
            
            # Step 3: Get dates for the matched session
            dates_url = f"{base_url}/field/browse"
            dates_params = {
                'field': 'date',
                'collectionId': '2',
                'loksabhaNo': loksabha_no.zfill(2),
                'sessionNo': matched_session,
                'order': 'desc',
                'start': '0',
                'rows': '1000',  # Get all available dates
                'locale': 'en'
            }
            
            response = self.session.get(dates_url, params=dates_params, headers=eparlib_headers, timeout=30)
            response.raise_for_status()
            
            dates_data = response.json()
            
            # Extract and convert dates from YYYY-MM-DD to DD/MM/YYYY format
            raw_dates = [record['name'] for record in dates_data.get('records', [])]
            converted_dates = []
            
            for date_str in raw_dates:
                try:
                    # Convert YYYY-MM-DD to DD/MM/YYYY
                    year, month, day = date_str.split('-')
                    converted_date = f"{day}/{month}/{year}"
                    converted_dates.append(converted_date)
                except ValueError:
                    logger.warning(f"Could not convert date format: {date_str}")
                    continue
            
            logger.info(f"✅ Eparlib API: Found session {matched_session} with {len(converted_dates)} dates")
            
            # Update cache if we have session object
            if lok_sabha and session_obj and converted_dates:
                cache, created = SessionDateCache.objects.update_or_create(
                    lok_sabha=lok_sabha,
                    session=session_obj,
                    defaults={
                        'available_dates': converted_dates,
                        'session_period': [],  # Not available from eparlib API
                        'api_source': 'eparlib.sansad.in'
                    }
                )
                logger.info(f"{'Created' if created else 'Updated'} date cache for {loksabha_no}th LS Session {session_no} (eparlib)")
            
            return converted_dates
            
        except Exception as e:
            logger.error(f"Eparlib API failed: {e}")
            return []
    
    def _roman_to_int(self, s: str) -> int:
        """Convert Roman numeral to integer"""
        roman_values = {
            'I': 1, 'V': 5, 'X': 10, 'L': 50,
            'C': 100, 'D': 500, 'M': 1000
        }
        total = 0
        prev_value = 0
        
        for char in reversed(s.upper()):
            if char in roman_values:
                value = roman_values[char]
                if value < prev_value:
                    total -= value
                else:
                    total += value
                prev_value = value
        
        return total
    
    def _int_to_roman(self, num: int) -> str:
        """Convert integer to Roman numeral"""
        if num == 0:
            return ''
        
        val = [
            1000, 900, 500, 400,
            100, 90, 50, 40,
            10, 9, 5, 4,
            1
        ]
        syms = [
            "M", "CM", "D", "CD",
            "C", "XC", "L", "XL",
            "X", "IX", "V", "IV",
            "I"
        ]
        roman_num = ''
        i = 0
        while num > 0:
            for _ in range(num // val[i]):
                roman_num += syms[i]
                num -= val[i]
            i += 1
        return roman_num
    
    def _fetch_debate_info(self, loksabha_no: str, session_no: str, date: str, locale: str = "en") -> Dict:
        """Fetch debate information from API"""
        
        url = f"{self.base_url}/debate/text-of-debate"
        
        params = {
            'loksabha': loksabha_no,
            'sessionNo': session_no,
            'debateDate': date,
            'locale': locale
        }
        
        try:
            logger.info(f"Fetching debate for LS{loksabha_no} Session {session_no} Date {date}")
            response = self.session.get(url, params=params, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                # The API returns JSON with 'pdfUrl' key
                if isinstance(data, dict) and data.get('pdfUrl'):
                    return {'pdf_url': data['pdfUrl']}
                # Fallback: The API returns a URL directly in some cases
                elif isinstance(data, str) and data.startswith('http'):
                    return {'pdf_url': data}
                return data
            else:
                logger.warning(f"API returned status {response.status_code} for debate on {date}")
                return {}
                
        except Exception as e:
            logger.debug(f"Failed to fetch debate info: {e}")
            return {}
    
    def _fetch_debate_info_with_fallback(self, loksabha_no: str, session_no: str, date: str, locale: str = "en") -> Dict:
        """Fetch debate info with fallback - try multiple APIs and session formats"""
        
        # Method 1: Try current sansad.in API with different session formats
        debate_info = self._fetch_debate_info_sansad_api(loksabha_no, session_no, date, locale)
        if debate_info:
            return debate_info
        
        # Method 2: Try eparlib API as fallback
        logger.info("Sansad API failed for PDF, trying eparlib API as fallback...")
        debate_info = self._fetch_debate_info_eparlib_api(loksabha_no, session_no, date, locale)
        if debate_info:
            return debate_info
        
        logger.warning(f"All API methods failed for LS{loksabha_no} Session {session_no} Date {date}")
        return {}
    
    def _fetch_debate_info_sansad_api(self, loksabha_no: str, session_no: str, date: str, locale: str = "en") -> Dict:
        """Fetch debate info from sansad.in API with session format fallback"""
        
        # Generate both possible session number formats
        session_formats = []
        
        if session_no.isdigit():
            # Numeric: try as-is first, then Roman
            session_formats = [session_no, self._int_to_roman(int(session_no))]
        else:
            # Roman: try as-is first, then numeric
            try:
                numeric = str(self._roman_to_int(session_no))
                session_formats = [session_no, numeric]
            except:
                # If Roman conversion fails, just use as-is
                session_formats = [session_no]
        
        # Try each format until one works
        logger.info(f"Sansad API: Will try session formats: {session_formats}")
        
        for i, session_format in enumerate(session_formats, 1):
            try:
                logger.info(f"Sansad API: [{i}/{len(session_formats)}] Trying session format: '{session_format}'")
                debate_info = self._fetch_debate_info(loksabha_no, session_format, date, locale)
                
                # Check if we got a valid response with actual content
                if debate_info and isinstance(debate_info, dict):
                    # Valid if we have a PDF URL or if dict is not empty (and not just {})
                    if debate_info.get('pdf_url') or (len(debate_info) > 0 and debate_info != {}):
                        logger.info(f"✅ Sansad API SUCCESS with session format: '{session_format}' → {debate_info}")
                        return debate_info
                    else:
                        logger.debug(f"Sansad API: Empty response with session format: '{session_format}'")
                else:
                    logger.debug(f"Sansad API: Invalid response with session format: '{session_format}': {debate_info}")
                    
            except Exception as e:
                logger.debug(f"❌ Sansad API: Exception with session format '{session_format}': {e}")
                continue
        
        logger.info(f"Sansad API: All session formats failed for LS{loksabha_no} Session {session_no} Date {date}")
        return {}
    
    def _fetch_debate_info_eparlib_api(self, loksabha_no: str, session_no: str, date: str, locale: str = "en") -> Dict:
        """Fetch debate info from eparlib.sansad.in API"""
        
        base_url = "https://eparlib.sansad.in/restv3"
        
        try:
            # Convert date from m/d/yyyy to yyyy-mm-dd format for eparlib API
            date_parts = date.split('/')
            if len(date_parts) == 3:
                month, day, year = date_parts
                eparlib_date = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
            else:
                logger.warning(f"Invalid date format for eparlib API: {date}")
                return {}
            
            # Convert session to lowercase Roman numeral
            if session_no.isdigit():
                session_format = self._int_to_roman(int(session_no)).lower()
            else:
                session_format = session_no.lower()
            
            # Set headers for eparlib API
            eparlib_headers = {
                'Accept': 'application/json, text/plain, */*',
                'Accept-Language': 'en-US,en;q=0.9',
                'Connection': 'keep-alive',
                'Origin': 'https://sansad.in',
                'Referer': 'https://sansad.in/',
                'Sec-Fetch-Dest': 'empty',
                'Sec-Fetch-Mode': 'cors',
                'Sec-Fetch-Site': 'same-site',
                'User-Agent': self.session.headers['User-Agent']
            }
            
            # Fetch from eparlib API
            fetch_url = f"{base_url}/fetch/all"
            params = {
                'collectionId': '2',  # Lok Sabha debates collection
                'loksabhaNo': loksabha_no.zfill(2),  # Zero-pad to 2 digits
                'sessionNo': session_format,
                'date': eparlib_date,
                'locale': locale
            }
            
            logger.info(f"Eparlib API: Fetching debate for LS{loksabha_no} Session {session_format} Date {eparlib_date}")
            response = self.session.get(fetch_url, params=params, headers=eparlib_headers, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                
                # Extract PDF URL from the first record
                records = data.get('records', [])
                if records and len(records) > 0:
                    first_record = records[0]
                    files = first_record.get('files', [])
                    
                    if files and len(files) > 0:
                        pdf_url = files[0]  # Take the first file URL
                        logger.info(f"✅ Eparlib API SUCCESS: Found PDF URL: {pdf_url}")
                        return {
                            'pdf_url': pdf_url,
                            'api_source': 'eparlib.sansad.in',
                            'raw_data': first_record
                        }
                    else:
                        logger.debug(f"Eparlib API: No files found in record")
                else:
                    logger.debug(f"Eparlib API: No records found")
                    
            else:
                logger.warning(f"Eparlib API returned status {response.status_code}")
                
        except Exception as e:
            logger.error(f"Eparlib API failed: {e}")
            
        return {}
    
    def _test_pdf_accessibility(self, pdf_url: str) -> Dict:
        """Test if a PDF URL is accessible with proper headers and encoding"""
        from urllib.parse import quote
        
        try:
            # URL encode the PDF URL to handle spaces and special characters
            if '?' in pdf_url:
                base_url, params = pdf_url.split('?', 1)
                url_parts = base_url.split('/')
                encoded_parts = url_parts[:3] + [quote(part, safe='') for part in url_parts[3:]]
                encoded_pdf_url = '/'.join(encoded_parts) + '?' + params
            else:
                url_parts = pdf_url.split('/')
                encoded_parts = url_parts[:3] + [quote(part, safe='') for part in url_parts[3:]]
                encoded_pdf_url = '/'.join(encoded_parts)
            
            # Use proper headers
            pdf_headers = {
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
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
            
            resp = self.session.head(encoded_pdf_url, headers=pdf_headers, timeout=10)
            
            if resp.status_code == 200:
                return {
                    'accessible': True,
                    'status': f"HTTP {resp.status_code}",
                    'size': resp.headers.get('content-length', 'unknown')
                }
            elif resp.status_code in [302, 301]:
                return {
                    'accessible': True,
                    'status': f"HTTP {resp.status_code} (redirect)"
                }
            else:
                return {
                    'accessible': False,
                    'status': f"HTTP {resp.status_code}",
                    'reason': 'Access restricted or file not found'
                }
                
        except Exception as e:
            return {
                'accessible': False,
                'status': 'error',
                'reason': str(e)
            }
    
    def _save_debate(self, lok_sabha: LokSabha, session: Session, date_str: str, debate_info: Dict) -> Tuple[Debate, bool]:
        """Save or update debate record"""
        
        # Parse date
        date_parts = date_str.split('/')
        debate_date = datetime(int(date_parts[2]), int(date_parts[1]), int(date_parts[0])).date()
        
        # Extract PDF URL
        pdf_url = debate_info.get('pdf_url', '') or debate_info.get('url', '')
        
        # Generate debate ID
        debate_id = f"{lok_sabha.number}_{session.session_number}_{debate_date.strftime('%Y%m%d')}"
        
        # Create or update debate
        debate, created = Debate.objects.update_or_create(
            debate_id=debate_id,
            defaults={
                'lok_sabha': lok_sabha,
                'session': session,
                'debate_date': debate_date,
                'pdf_url': pdf_url,
                'raw_api_data': debate_info,
                'last_scraped': timezone.now(),
                'status': 'pending' if pdf_url else 'not_available'
            }
        )
        
        return debate, created
    
    def _queue_pdf_download(self, debate: Debate):
        """Queue PDF for download"""
        
        # Create document file record
        doc_file, created = DocumentFile.objects.get_or_create(
            original_url=debate.pdf_url,
            defaults={
                'document_category': 'parl_debate',
                'file_type': 'debate',
                'file_name': debate.get_pdf_filename(),
                'question': None,  # Debates don't have associated questions
                'download_priority': 5
            }
        )
        
        # Link to debate
        debate.pdf_file = doc_file
        debate.save()
        
        # Create download queue entry
        DownloadQueue.objects.create(
            document_file=doc_file,
            priority=5
        )
        
        logger.info(f"Queued PDF download for debate {debate.debate_id}")
    
    def download_debate_pdf(self, debate: Debate) -> bool:
        """Download PDF for a specific debate"""
        
        if not debate.pdf_url:
            logger.warning(f"No PDF URL for debate {debate.debate_id}")
            return False
        
        try:
            logger.info(f"Downloading PDF from {debate.pdf_url}")
            
            # Update status
            debate.status = 'downloading'
            debate.download_attempts += 1
            debate.last_download_attempt = timezone.now()
            debate.save()
            
            # Set proper headers for PDF download to avoid 403 errors
            pdf_headers = {
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
                'Accept-Language': 'en-US,en;q=0.9',
                'Connection': 'keep-alive',
                'Referer': 'https://sansad.in/' if 'sansad.in' in debate.pdf_url else 'https://eparlib.sansad.in/',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'same-origin',
                'Sec-GPC': '1',
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36',
                'sec-ch-ua': '"Chromium";v="140", "Not=A?Brand";v="24", "Brave";v="140"',
                'sec-ch-ua-mobile': '?0',
                'sec-ch-ua-platform': '"macOS"',
                'Upgrade-Insecure-Requests': '1'
            }
            
            # URL encode the PDF URL to handle spaces and special characters
            from urllib.parse import quote
            
            # Split URL and encode path properly
            if '?' in debate.pdf_url:
                base_url, params = debate.pdf_url.split('?', 1)
                # Only encode the path part, not the domain
                url_parts = base_url.split('/')
                encoded_parts = url_parts[:3] + [quote(part, safe='') for part in url_parts[3:]]
                encoded_url = '/'.join(encoded_parts) + '?' + params
            else:
                url_parts = debate.pdf_url.split('/')
                encoded_parts = url_parts[:3] + [quote(part, safe='') for part in url_parts[3:]]
                encoded_url = '/'.join(encoded_parts)
            
            logger.info(f"Downloading from encoded URL: {encoded_url}")
            
            # Download PDF with proper headers
            response = self.session.get(encoded_url, headers=pdf_headers, timeout=60, stream=True)
            
            # If we get 403, try to establish session by visiting the main page first
            if response.status_code == 403:
                logger.info("PDF access forbidden, attempting to establish session...")
                
                # Visit main debates page to establish session
                session_headers = {
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.9',
                    'Connection': 'keep-alive',
                    'User-Agent': pdf_headers['User-Agent'],
                    'Upgrade-Insecure-Requests': '1'
                }
                
                try:
                    # Visit main page to get session cookies
                    session_resp = self.session.get('https://sansad.in/ls/debates/text-of-debates', headers=session_headers, timeout=30)
                    if session_resp.status_code == 200:
                        logger.info("Session established, retrying PDF download...")
                        # Retry PDF download with updated session
                        response = self.session.get(encoded_url, headers=pdf_headers, timeout=60, stream=True)
                except Exception as e:
                    logger.warning(f"Failed to establish session: {e}")
            
            response.raise_for_status()
            
            # Save to file
            file_name = debate.get_pdf_filename()
            file_path = os.path.join(settings.MEDIA_ROOT, 'debates', file_name)
            
            # Create directory if needed
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            
            # Write file
            with open(file_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            # Get file size
            file_size = os.path.getsize(file_path)
            
            # Update debate record
            debate.status = 'completed'
            debate.file_size = file_size
            debate.save()
            
            # Update document file if exists
            if debate.pdf_file:
                debate.pdf_file.file_path = f'debates/{file_name}'
                debate.pdf_file.file_size = file_size
                debate.pdf_file.status = 'completed'
                debate.pdf_file.downloaded_at = timezone.now()
                debate.pdf_file.save()
            
            logger.info(f"Successfully downloaded debate PDF: {file_name} ({file_size} bytes)")
            return True
            
        except Exception as e:
            logger.error(f"Failed to download debate PDF: {e}")
            
            # Update status
            debate.status = 'failed'
            debate.error_message = str(e)
            debate.save()
            
            return False
    
    def get_debate_statistics(self, loksabha_no: Optional[str] = None, session_no: Optional[str] = None) -> Dict:
        """Get statistics about debates"""
        
        queryset = Debate.objects.all()
        
        if loksabha_no:
            queryset = queryset.filter(lok_sabha__number=loksabha_no)
        
        if session_no:
            queryset = queryset.filter(session__session_number=session_no)
        
        total_debates = queryset.count()
        downloaded_debates = queryset.filter(status='completed').count()
        pending_debates = queryset.filter(status='pending').count()
        failed_debates = queryset.filter(status='failed').count()
        
        # Get date range
        date_range = queryset.aggregate(
            earliest_date=models.Min('debate_date'),
            latest_date=models.Max('debate_date')
        )
        
        # Get total file size
        total_size = queryset.filter(status='completed').aggregate(
            total=models.Sum('file_size')
        )['total'] or 0
        
        return {
            'total_debates': total_debates,
            'downloaded_debates': downloaded_debates,
            'pending_debates': pending_debates,
            'failed_debates': failed_debates,
            'download_percentage': round((downloaded_debates / max(total_debates, 1)) * 100, 2),
            'date_range': date_range,
            'total_size_mb': round(total_size / (1024 * 1024), 2),
            'average_size_mb': round((total_size / max(downloaded_debates, 1)) / (1024 * 1024), 2)
        }
