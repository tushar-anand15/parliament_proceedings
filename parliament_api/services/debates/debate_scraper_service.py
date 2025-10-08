import sys
import os
import json
import logging
import uuid
import threading
import queue
import time
import random
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
from services.cloud_storage.gcs_service import GCSService
from .models import Debate, DebateSpeech, DebateTag, SessionDateCache, DebateMasterData
from .debate_master_data_service import DebateMasterDataService

logger = logging.getLogger(__name__)


class DebateScraperService:
    """
    Service for scraping parliamentary CORRECTED debates and downloading PDFs
    
    Note: This service handles CORRECTED debates (text-of-debate API).
    For UNCORRECTED debates, use UncorrectedDebateScraperService.
    """
    
    def __init__(self, scraping_job: ScrapingJob = None):
        self.scraping_job = scraping_job
        self.base_url = "https://sansad.in/api_ls"
        self.session = requests.Session()
        self.config = ScrapingConfig.get_default()
        self.gcs_service = GCSService()
        self.master_data_service = DebateMasterDataService()
        self.debate_category = 'corrected'  # This service handles CORRECTED debates
        # Load delay configuration from settings
        self.min_delay = getattr(settings, 'API_REQUEST_DELAY_MIN', 0.1)
        self.max_delay = getattr(settings, 'API_REQUEST_DELAY_MAX', 0.3)
        
        # Set headers for API requests (corrected debates)
        self.session.headers.update({
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Connection': 'keep-alive',
            'Referer': 'https://sansad.in/ls/debates/text-of-debates',  # No tab parameter = corrected
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
            # Get session dates from master data service
            session_dates = self.master_data_service.get_debate_dates_for_session(
                lok_sabha.number, 
                session.session_number,
                start_date=start_date,
                end_date=end_date
            )
            
            if not session_dates:
                # Try to fetch fresh data if none exists
                logger.info(f"No cached debate dates found, attempting to fetch from API...")
                try:
                    fetch_result = self.master_data_service.fetch_debate_dates_for_session(
                        lok_sabha.number, 
                        session.session_number
                    )
                    if fetch_result.get('dates_count', 0) > 0:
                        session_dates = self.master_data_service.get_debate_dates_for_session(
                            lok_sabha.number, 
                            session.session_number,
                            start_date=start_date,
                            end_date=end_date
                        )
                except Exception as fetch_error:
                    logger.warning(f"Failed to fetch fresh debate dates: {fetch_error}")
            
            if not session_dates:
                raise Exception(f"No debate dates found for {lok_sabha.number}th LS Session {session.session_number}")
            
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
    
    def discover_all_available_sessions(self) -> List[Dict]:
        """Discover all available sessions using the master data service"""
        try:
            # Use the master data service to get comprehensive session information
            available_sessions = self.master_data_service.list_available_sessions_with_debates()
            
            # Convert to the expected format for backward compatibility
            formatted_sessions = []
            for session_info in available_sessions:
                formatted_sessions.append({
                    'loksabha_no': session_info['lok_sabha_number'],
                    'session_no': session_info['session_number'],
                    'available_dates': session_info['total_debate_dates'],  # This is a count, not actual dates
                    'date_count': session_info['total_debate_dates'],
                    'api_source': session_info['api_source'],
                    'is_complete': session_info['is_complete'],
                    'last_updated': session_info['last_updated'],
                    'debates_discovered': session_info['debates_discovered'],
                    'debates_downloaded': session_info['debates_downloaded'],
                    'completion_percentage': session_info['completion_percentage'],
                    'date_range': session_info['date_range']
                })
            
            logger.info(f"Found {len(formatted_sessions)} sessions with debate data from master data service")
            return formatted_sessions
            
        except Exception as e:
            logger.error(f"Failed to discover sessions from master data service: {e}")
            # Fallback to direct API discovery if master data service fails
            logger.info("Falling back to direct API discovery...")
            return self._discover_sessions_direct_api()
    
    def _discover_sessions_direct_api(self) -> List[Dict]:
        """Discover all available sessions from both modern and historical APIs (fallback method)"""
        all_sessions = []
        
        # Method 1: Get modern sessions (LS13+) from main Parliament API
        try:
            url = f"{self.base_url}/business/AllLoksabhaAndSessionDates"
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            for ls_data in data:
                loksabha_no = str(ls_data.get('loksabha'))
                for session_data in ls_data.get('sessions', []):
                    session_no = str(session_data.get('sessionNo'))
                    dates = session_data.get('dates', [])
                    
                    if dates:
                        all_sessions.append({
                            'loksabha_no': loksabha_no,
                            'session_no': session_no,
                            'available_dates': dates,
                            'date_count': len(dates),
                            'api_source': 'sansad.in'
                        })
            
            logger.info(f"Found {len(all_sessions)} modern sessions from Parliament API")
            
        except Exception as e:
            logger.error(f"Failed to fetch modern sessions: {e}")
        
        # Method 2: Get historical sessions (LS01-LS12) from eparlib API
        historical_sessions = self._discover_historical_sessions()
        all_sessions.extend(historical_sessions)
        
        logger.info(f"Total sessions discovered: {len(all_sessions)}")
        return all_sessions
    
    def _discover_historical_sessions(self) -> List[Dict]:
        """Discover historical sessions from eparlib API"""
        historical_sessions = []
        
        for ls_num in range(1, 13):  # LS01 to LS12
            ls_padded = str(ls_num).zfill(2)
            
            try:
                # Get available sessions for this LS
                url = "https://eparlib.sansad.in/restv3/field/browse"
                params = {
                    'field': 'sessionNo',
                    'collectionId': '2',
                    'loksabhaNo': ls_padded,
                    'order': 'desc',
                    'start': '0',
                    'rows': '100',
                    'locale': 'en'
                }
                
                headers = {
                    'Accept': 'application/json, text/plain, */*',
                    'Origin': 'https://sansad.in',
                    'Referer': 'https://sansad.in/',
                    'User-Agent': self.session.headers['User-Agent']
                }
                
                response = self.session.get(url, params=params, headers=headers, timeout=30)
                response.raise_for_status()
                
                data = response.json()
                sessions = data.get('records', [])
                
                for session_record in sessions:
                    session_name = session_record.get('name')
                    session_count = int(session_record.get('count', 0))
                    
                    if session_count > 0:
                        # Get sample dates for this session
                        dates = self._get_eparlib_session_dates_direct(ls_padded, session_name, limit=5)
                        
                        if dates:
                            historical_sessions.append({
                                'loksabha_no': str(ls_num),
                                'session_no': session_name,
                                'available_dates': dates,
                                'date_count': len(dates),
                                'total_debates': session_count,
                                'api_source': 'eparlib'
                            })
                
                if sessions:
                    logger.info(f"Discovered {len(sessions)} historical sessions for LS{ls_num}")
                
            except Exception as e:
                logger.warning(f"Failed to discover historical sessions for LS{ls_num}: {e}")
                continue
        
        logger.info(f"Total historical sessions discovered: {len(historical_sessions)}")
        return historical_sessions
    
    def _get_eparlib_session_dates_direct(self, loksabha_no: str, session_no: str, limit: int = 10) -> List[str]:
        """Get dates directly from eparlib for a specific session"""
        try:
            url = "https://eparlib.sansad.in/restv3/field/browse"
            params = {
                'field': 'date',
                'collectionId': '2',
                'loksabhaNo': loksabha_no,
                'sessionNo': session_no,
                'order': 'desc',
                'start': '0',
                'rows': str(limit),
                'locale': 'en'
            }
            
            headers = {
                'Accept': 'application/json, text/plain, */*',
                'Origin': 'https://sansad.in',
                'Referer': 'https://sansad.in/',
                'User-Agent': self.session.headers['User-Agent']
            }
            
            response = self.session.get(url, params=params, headers=headers, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            raw_dates = [record['name'] for record in data.get('records', [])]
            
            # Convert YYYY-MM-DD to DD/MM/YYYY format
            converted_dates = []
            for date_str in raw_dates:
                try:
                    year, month, day = date_str.split('-')
                    converted_date = f"{day}/{month}/{year}"
                    converted_dates.append(converted_date)
                except ValueError:
                    continue
            
            return converted_dates
            
        except Exception as e:
            logger.warning(f"Failed to get dates for LS{loksabha_no} Session {session_no}: {e}")
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
        
        # Convert date from DD/MM/YYYY to M/D/YYYY format for sansad API
        try:
            date_parts = date.split('/')
            if len(date_parts) == 3:
                day, month, year = date_parts
                sansad_date = f"{int(month)}/{int(day)}/{year}"  # M/D/YYYY format
            else:
                logger.warning(f"Invalid date format for sansad API: {date}")
                return {}
        except ValueError as e:
            logger.warning(f"Date conversion error for sansad API: {date} - {e}")
            return {}
        
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
        logger.info(f"Sansad API: Will try session formats: {session_formats} with date {sansad_date}")
        
        for i, session_format in enumerate(session_formats, 1):
            try:
                logger.info(f"Sansad API: [{i}/{len(session_formats)}] Trying session format: '{session_format}'")
                debate_info = self._fetch_debate_info(loksabha_no, session_format, sansad_date, locale)
                
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
            # Convert date from dd/mm/yyyy to yyyy-mm-dd format for eparlib API
            date_parts = date.split('/')
            if len(date_parts) == 3:
                day, month, year = date_parts  # Fixed: DD/MM/YYYY format
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
        """Save or update CORRECTED debate record"""
        
        # Parse date
        date_parts = date_str.split('/')
        debate_date = datetime(int(date_parts[2]), int(date_parts[1]), int(date_parts[0])).date()
        
        # Extract PDF URL
        pdf_url = debate_info.get('pdf_url', '') or debate_info.get('url', '')
        
        # Generate debate ID (include category to differentiate corrected/uncorrected)
        debate_id = f"{lok_sabha.number}_{session.session_number}_{debate_date.strftime('%Y%m%d')}_corrected"
        
        # Create or update debate
        debate, created = Debate.objects.update_or_create(
            debate_id=debate_id,
            defaults={
                'lok_sabha': lok_sabha,
                'session': session,
                'debate_date': debate_date,
                'debate_category': 'corrected',  # Explicitly mark as CORRECTED
                'debate_type': 'text_of_debate',
                'pdf_url': pdf_url,
                'raw_api_data': debate_info,
                'last_scraped': timezone.now(),
                'status': 'pending' if pdf_url else 'not_available'
            }
        )
        
        return debate, created
    
    def _queue_pdf_download(self, debate: Debate):
        """
        Queue PDF for ASYNC download via Celery - NO BLOCKING!
        
        This method now:
        1. Creates DocumentFile record for tracking
        2. Dispatches Celery task for PARALLEL download
        3. Returns IMMEDIATELY without waiting
        """
        
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
        
        # Create download queue entry for tracking
        queue_entry = DownloadQueue.objects.create(
            document_file=doc_file,
            priority=5
        )
        
        logger.info(f"Dispatching async PDF download for debate {debate.debate_id}")
        
        # Dispatch to Celery worker - ASYNC, NO BLOCKING!
        try:
            from services.files.tasks import download_pdf_unified_task
            
            # Dispatch async download task
            task = download_pdf_unified_task.delay('debate', debate.id)
            
            logger.info(f"✅ PDF download task dispatched for debate {debate.debate_id} (task: {task.id})")
            
        except Exception as e:
            queue_entry.mark_failed(str(e))
            logger.error(f"Error dispatching PDF download for debate {debate.debate_id}: {e}")
            raise
    
    def download_debate_pdf(self, debate: Debate) -> bool:
        """Download PDF for a specific debate with exponential backoff retry"""
        
        if not debate.pdf_url:
            logger.warning(f"No PDF URL for debate {debate.debate_id}")
            return False
        
        max_retries = 3
        base_delay = 1  # Start with 1 second
        
        for attempt in range(max_retries):
            try:
                # Calculate exponential backoff delay
                if attempt > 0:
                    delay = base_delay * (2 ** (attempt - 1))  # 1s, 2s, 4s
                    logger.info(f"Retry attempt {attempt + 1}/{max_retries} for {debate.debate_id} after {delay}s delay")
                    time.sleep(delay)
                else:
                    logger.info(f"Downloading PDF from {debate.pdf_url} (attempt {attempt + 1}/{max_retries})")
                    # Add random delay to avoid overloading the source API
                    api_delay = random.uniform(self.min_delay, self.max_delay)
                    logger.debug(f"Waiting {api_delay:.2f}s before API call (rate limiting)")
                    time.sleep(api_delay)
                
                # Update status and attempt count
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
                        # Add random delay before session establishment
                        session_delay = random.uniform(self.min_delay, self.max_delay)
                        logger.debug(f"Waiting {session_delay:.2f}s before session establishment (rate limiting)")
                        time.sleep(session_delay)
                        
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
                    
                    # Upload to Google Cloud Storage
                    try:
                        bucket_name = self.gcs_service.get_bucket_for_document_type('parl_debate')
                        object_key = self.gcs_service.generate_object_key('parl_debate', file_name)
                        
                        # Update GCS upload status
                        debate.pdf_file.gcs_upload_status = 'uploading'
                        debate.pdf_file.gcs_bucket_name = bucket_name
                        debate.pdf_file.gcs_object_key = object_key
                        debate.pdf_file.save()
                        
                        # Upload to GCS
                        upload_result = self.gcs_service.upload_file(
                            file_path,
                            bucket_name,
                            object_key,
                            metadata={
                                'debate_id': debate.debate_id,
                                'lok_sabha': str(debate.lok_sabha.number),
                                'session': str(debate.session.session_number),
                                'debate_date': debate.debate_date.isoformat(),
                                'document_type': 'parliamentary_debate',
                                'uploaded_by': 'debate_scraper_service'
                            }
                        )
                        
                        if upload_result['success']:
                            # Update GCS metadata
                            debate.pdf_file.gcs_upload_status = 'completed'
                            debate.pdf_file.gcs_uploaded_at = timezone.now()
                            debate.pdf_file.gcs_etag = upload_result.get('etag', '')
                            debate.pdf_file.gcs_url = upload_result.get('gcs_url', '')
                            debate.pdf_file.save()
                            
                            # Delete local file if configured to do so
                            if settings.GCS_AUTO_DELETE_LOCAL:
                                try:
                                    os.remove(file_path)
                                    debate.pdf_file.file_path = None
                                    debate.pdf_file.save()
                                    logger.info(f"Deleted local file after GCS upload: {file_path}")
                                except Exception as delete_error:
                                    logger.warning(f"Failed to delete local file: {delete_error}")
                            
                            logger.info(f"Successfully uploaded debate PDF to GCS: {object_key}")
                        else:
                            debate.pdf_file.gcs_upload_status = 'failed'
                            debate.pdf_file.save()
                            logger.error(f"Failed to upload to GCS: {upload_result.get('error')}")
                            
                    except Exception as gcs_error:
                        logger.error(f"GCS upload error: {gcs_error}")
                        debate.pdf_file.gcs_upload_status = 'failed'
                        debate.pdf_file.save()
                
                logger.info(f"Successfully downloaded debate PDF: {file_name} ({file_size} bytes) on attempt {attempt + 1}")
                return True
                
            except (requests.exceptions.RequestException, requests.exceptions.Timeout, 
                    requests.exceptions.ConnectionError, requests.exceptions.HTTPError) as e:
                logger.warning(f"Download attempt {attempt + 1}/{max_retries} failed for {debate.debate_id}: {e}")
                
                if attempt == max_retries - 1:  # Last attempt
                    logger.error(f"All {max_retries} download attempts failed for {debate.debate_id}")
                    debate.status = 'failed'
                    debate.error_message = f"Download failed after {max_retries} attempts: {str(e)}"
                    debate.save()
                    return False
                # Continue to next attempt
                continue
                
            except Exception as e:
                logger.error(f"Unexpected error downloading debate PDF {debate.debate_id}: {e}")
                debate.status = 'failed'
                debate.error_message = str(e)
                debate.save()
                return False
        
        # Should never reach here, but just in case
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


class UncorrectedDebateScraperService:
    """
    Service for scraping parliamentary UNCORRECTED debates and downloading PDFs
    
    Note: This service handles UNCORRECTED debates which have a different API structure:
    - Uses /api_ls/debate/uncorrected-session-dates to get available dates
    - Uses /api_ls/debate/uncorrected-debate-pdfs to get PDF files for each date
    """
    
    def __init__(self, scraping_job: ScrapingJob = None):
        self.scraping_job = scraping_job
        self.base_url = "https://sansad.in/api_ls"
        self.session = requests.Session()
        self.config = ScrapingConfig.get_default()
        self.gcs_service = GCSService()
        self.debate_category = 'uncorrected'  # This service handles UNCORRECTED debates
        
        # Set headers for API requests (uncorrected debates)
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
    
    def fetch_uncorrected_session_dates(self, loksabha_no: str, session_no: str, locale: str = "en") -> Dict:
        """
        Fetch dates that have uncorrected debates for a specific session
        
        Args:
            loksabha_no: Lok Sabha number (e.g., "18")
            session_no: Session number (e.g., "5")
            locale: Language locale (default: "en")
            
        Returns:
            Dict with available dates and metadata
        """
        try:
            url = f"{self.base_url}/debate/uncorrected-session-dates"
            params = {
                'lsno': loksabha_no,
                'sessionNo': session_no,
                'locale': locale
            }
            
            logger.info(f"Fetching uncorrected debate dates for LS{loksabha_no} Session {session_no}")
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            
            # The API returns a list of date strings
            if isinstance(data, list):
                dates = data
            elif isinstance(data, dict) and 'dates' in data:
                dates = data['dates']
            else:
                logger.warning(f"Unexpected response format: {data}")
                dates = []
            
            logger.info(f"Found {len(dates)} dates with uncorrected debates for LS{loksabha_no} Session{session_no}")
            
            return {
                'status': 'SUCCESS',
                'loksabha_no': loksabha_no,
                'session_no': session_no,
                'dates': dates,
                'dates_count': len(dates),
                'raw_response': data
            }
            
        except Exception as e:
            logger.error(f"Failed to fetch uncorrected session dates for LS{loksabha_no} Session{session_no}: {e}")
            return {
                'status': 'ERROR',
                'loksabha_no': loksabha_no,
                'session_no': session_no,
                'dates': [],
                'dates_count': 0,
                'error': str(e)
            }
    
    def fetch_uncorrected_debate_pdfs(self, loksabha_no: str, session_no: str, debate_date: str, locale: str = "en") -> Dict:
        """
        Fetch PDF files available for a specific uncorrected debate date
        
        Args:
            loksabha_no: Lok Sabha number (e.g., "18")
            session_no: Session number (e.g., "5")
            debate_date: Date in DD/MM/YYYY format (e.g., "21/08/2025")
            locale: Language locale (default: "en")
            
        Returns:
            Dict with PDF file URLs and metadata
        """
        try:
            url = f"{self.base_url}/debate/uncorrected-debate-pdfs"
            params = {
                'lsno': loksabha_no,
                'sessionNo': session_no,
                'debateDate': debate_date,
                'locale': locale
            }
            
            logger.info(f"Fetching uncorrected debate PDFs for LS{loksabha_no} Session {session_no} Date {debate_date}")
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            
            # Extract PDF URLs from response
            # API returns: [{"fileName":"...", "fileType":"pdf", "fileUrl":"..."}]
            pdf_files = []
            if isinstance(data, list):
                # Extract fileUrl from each object
                for item in data:
                    if isinstance(item, dict):
                        url = item.get('fileUrl') or item.get('url') or item.get('pdfUrl')
                        if url:
                            pdf_files.append({
                                'url': url,
                                'fileName': item.get('fileName', ''),
                                'fileType': item.get('fileType', 'pdf')
                            })
                    elif isinstance(item, str):
                        # Sometimes might be a direct URL string
                        pdf_files.append({'url': item, 'fileName': '', 'fileType': 'pdf'})
            elif isinstance(data, dict):
                # Single file response
                url = data.get('fileUrl') or data.get('url') or data.get('pdfUrl')
                if url:
                    pdf_files = [{
                        'url': url,
                        'fileName': data.get('fileName', ''),
                        'fileType': data.get('fileType', 'pdf')
                    }]
            
            logger.info(f"Found {len(pdf_files)} PDF files for LS{loksabha_no} Session{session_no} Date{debate_date}")
            
            return {
                'status': 'SUCCESS',
                'loksabha_no': loksabha_no,
                'session_no': session_no,
                'debate_date': debate_date,
                'pdf_files': pdf_files,
                'files_count': len(pdf_files),
                'raw_response': data
            }
            
        except Exception as e:
            logger.error(f"Failed to fetch uncorrected debate PDFs for LS{loksabha_no} Session{session_no} Date{debate_date}: {e}")
            return {
                'status': 'ERROR',
                'loksabha_no': loksabha_no,
                'session_no': session_no,
                'debate_date': debate_date,
                'pdf_files': [],
                'files_count': 0,
                'error': str(e)
            }
    
    def scrape_uncorrected_debates(self, loksabha_no: str, session_no: str, download_pdfs: bool = True) -> Dict:
        """
        Complete flow to scrape uncorrected debates for a session
        
        Args:
            loksabha_no: Lok Sabha number (e.g., "18")
            session_no: Session number (e.g., "5")
            download_pdfs: Whether to download PDFs (default: True)
            
        Returns:
            Dict with scraping results and statistics
        """
        try:
            logger.info(f"Starting uncorrected debates scraping for LS{loksabha_no} Session{session_no}")
            
            # Get or create LokSabha and Session objects
            lok_sabha, _ = LokSabha.objects.get_or_create(
                number=loksabha_no,
                defaults={'is_current': loksabha_no == "18"}
            )
            
            session, _ = Session.objects.get_or_create(
                lok_sabha=lok_sabha,
                session_number=session_no
            )
            
            # Step 1: Get all dates with uncorrected debates
            dates_result = self.fetch_uncorrected_session_dates(loksabha_no, session_no)
            
            if dates_result['status'] != 'SUCCESS' or not dates_result['dates']:
                logger.warning(f"No uncorrected debate dates found for LS{loksabha_no} Session{session_no}")
                return {
                    'status': 'NO_DATA',
                    'loksabha_no': loksabha_no,
                    'session_no': session_no,
                    'dates_processed': 0,
                    'debates_created': 0,
                    'message': 'No uncorrected debate dates available'
                }
            
            available_dates = dates_result['dates']
            logger.info(f"Processing {len(available_dates)} dates with uncorrected debates")
            
            # Step 2: For each date, get PDF files and save debates
            debates_created = 0
            debates_updated = 0
            debates_failed = 0
            total_files = 0
            
            for date_str in available_dates:
                try:
                    # Get PDF files for this date
                    pdfs_result = self.fetch_uncorrected_debate_pdfs(loksabha_no, session_no, date_str)
                    
                    if pdfs_result['status'] != 'SUCCESS' or not pdfs_result['pdf_files']:
                        logger.warning(f"No PDF files found for date {date_str}")
                        debates_failed += 1
                        continue
                    
                    pdf_files = pdfs_result['pdf_files']
                    total_files += len(pdf_files)
                    
                    # Save debate records for each PDF file
                    for idx, pdf_file_obj in enumerate(pdf_files):
                        # Extract URL from the file object
                        pdf_url = pdf_file_obj['url'] if isinstance(pdf_file_obj, dict) else pdf_file_obj
                        file_name = pdf_file_obj.get('fileName', '') if isinstance(pdf_file_obj, dict) else ''
                        
                        debate_info = {
                            'pdf_url': pdf_url,
                            'file_name': file_name,
                            'file_index': idx,
                            'total_files': len(pdf_files),
                            'api_response': pdfs_result['raw_response']
                        }
                        
                        debate, created = self._save_uncorrected_debate(
                            lok_sabha, session, date_str, debate_info, file_index=idx
                        )
                        
                        if created:
                            debates_created += 1
                        else:
                            debates_updated += 1
                        
                        # Queue PDF download if enabled
                        if download_pdfs and debate.pdf_url and not debate.is_downloaded:
                            self._queue_pdf_download(debate)
                    
                    # Small delay between dates
                    time.sleep(0.3)
                    
                except Exception as e:
                    logger.error(f"Error processing uncorrected debate for date {date_str}: {e}")
                    debates_failed += 1
            
            result = {
                'status': 'SUCCESS',
                'loksabha_no': loksabha_no,
                'session_no': session_no,
                'dates_processed': len(available_dates),
                'debates_created': debates_created,
                'debates_updated': debates_updated,
                'debates_failed': debates_failed,
                'total_pdf_files': total_files,
                'message': f'Processed {len(available_dates)} dates, created {debates_created} debates, {total_files} PDF files'
            }
            
            logger.info(f"Uncorrected debates scraping completed: {result}")
            return result
            
        except Exception as e:
            logger.error(f"Failed to scrape uncorrected debates for LS{loksabha_no} Session{session_no}: {e}")
            return {
                'status': 'ERROR',
                'loksabha_no': loksabha_no,
                'session_no': session_no,
                'error': str(e)
            }
    
    def _save_uncorrected_debate(self, lok_sabha: LokSabha, session: Session, date_str: str, 
                                debate_info: Dict, file_index: int = 0) -> Tuple[Debate, bool]:
        """Save or update UNCORRECTED debate record"""
        
        # Parse date
        date_parts = date_str.split('/')
        debate_date = datetime(int(date_parts[2]), int(date_parts[1]), int(date_parts[0])).date()
        
        # Extract PDF URL
        pdf_url = debate_info.get('pdf_url', '') or debate_info.get('url', '')
        
        # Generate debate ID (include category and file index for multiple files per date)
        debate_id = f"{lok_sabha.number}_{session.session_number}_{debate_date.strftime('%Y%m%d')}_uncorrected_{file_index}"
        
        # Create or update debate
        debate, created = Debate.objects.update_or_create(
            debate_id=debate_id,
            defaults={
                'lok_sabha': lok_sabha,
                'session': session,
                'debate_date': debate_date,
                'debate_category': 'uncorrected',  # Explicitly mark as UNCORRECTED
                'debate_type': 'uncorrected',
                'pdf_url': pdf_url,
                'raw_api_data': debate_info,
                'last_scraped': timezone.now(),
                'status': 'pending' if pdf_url else 'not_available'
            }
        )
        
        return debate, created
    
    def _queue_pdf_download(self, debate: Debate):
        """
        Queue PDF for ASYNC download via Celery - NO BLOCKING!
        
        This method now:
        1. Creates DocumentFile record for tracking
        2. Dispatches Celery task for PARALLEL download
        3. Returns IMMEDIATELY without waiting
        """
        
        # Create document file record
        doc_file, created = DocumentFile.objects.get_or_create(
            original_url=debate.pdf_url,
            defaults={
                'document_category': 'parl_debate_uncorrected',
                'file_type': 'debate',
                'file_name': debate.get_pdf_filename(),
                'question': None,
                'download_priority': 5
            }
        )
        
        # Link to debate
        debate.pdf_file = doc_file
        debate.save()
        
        # Create download queue entry for tracking
        queue_entry = DownloadQueue.objects.create(
            document_file=doc_file,
            priority=5
        )
        
        logger.info(f"Dispatching async PDF download for uncorrected debate {debate.debate_id}")
        
        # Dispatch to Celery worker - ASYNC, NO BLOCKING!
        try:
            from services.files.tasks import download_pdf_unified_task
            
            # Dispatch async download task
            task = download_pdf_unified_task.delay('debate', debate.id)
            
            logger.info(f"✅ PDF download task dispatched for uncorrected debate {debate.debate_id} (task: {task.id})")
            
        except Exception as e:
            queue_entry.mark_failed(str(e))
            logger.error(f"Error dispatching PDF download for uncorrected debate {debate.debate_id}: {e}")
            raise
