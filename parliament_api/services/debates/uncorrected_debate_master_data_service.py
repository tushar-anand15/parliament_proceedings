import requests
import logging
import time
import random
from datetime import datetime
from typing import List, Dict, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from django.utils import timezone
from django.db import transaction
from django.conf import settings

from services.questions.models import LokSabha, Session
from .models import DebateMasterData

logger = logging.getLogger(__name__)


class UncorrectedDebateMasterDataService:
    """
    Service for fetching and managing UNCORRECTED debate metadata from Parliament APIs
    
    This service handles the complete flow:
    1. Fetch Lok Sabha and Sessions metadata
    2. For each session, fetch available uncorrected debate dates
    3. For each date, fetch all PDF file URLs
    4. Store complete master data in database (dates + PDF URLs)
    """
    
    def __init__(self):
        self.session = requests.Session()
        # Set headers to mimic browser requests (uncorrected debates)
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
        
        self.base_url = "https://sansad.in/api_ls"
        self.debate_category = 'uncorrected'
    
    def fetch_uncorrected_session_dates(self, lok_sabha_number: str, session_number: str) -> Dict:
        """
        Fetch available dates with uncorrected debates for a session
        
        Args:
            lok_sabha_number: Lok Sabha number (e.g., '18')
            session_number: Session number (e.g., '5')
            
        Returns:
            Dict with available dates
        """
        try:
            url = f"{self.base_url}/debate/uncorrected-session-dates"
            params = {
                'lsno': lok_sabha_number,
                'sessionNo': session_number,
                'locale': 'en'
            }
            
            logger.info(f"Fetching uncorrected debate dates for LS{lok_sabha_number} Session{session_number}")
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            
            # API returns array of date strings: ["21/07/2025", "28/07/2025", ...]
            if isinstance(data, list):
                dates = data
            else:
                dates = []
            
            logger.info(f"Found {len(dates)} dates with uncorrected debates")
            
            return {
                'status': 'SUCCESS',
                'available_dates': dates,
                'dates_count': len(dates),
                'raw_response': data
            }
            
        except Exception as e:
            logger.error(f"Failed to fetch uncorrected dates for LS{lok_sabha_number} Session{session_number}: {e}")
            return {
                'status': 'ERROR',
                'available_dates': [],
                'dates_count': 0,
                'error': str(e)
            }
    
    def fetch_uncorrected_pdfs_for_date(self, lok_sabha_number: str, session_number: str, debate_date: str) -> Dict:
        """
        Fetch PDF URLs for a specific uncorrected debate date
        
        Args:
            lok_sabha_number: Lok Sabha number
            session_number: Session number
            debate_date: Date in DD/MM/YYYY format
            
        Returns:
            Dict with PDF file information
        """
        try:
            url = f"{self.base_url}/debate/uncorrected-debate-pdfs"
            params = {
                'lsno': lok_sabha_number,
                'sessionNo': session_number,
                'debateDate': debate_date,
                'locale': 'en'
            }
            
            logger.info(f"Fetching PDF URLs for LS{lok_sabha_number} Session{session_number} Date{debate_date}")
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            
            # API returns: [{"fileName":"...", "fileType":"pdf", "fileUrl":"..."}]
            pdf_files = []
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and item.get('fileUrl'):
                        pdf_files.append({
                            'fileName': item.get('fileName', ''),
                            'fileType': item.get('fileType', 'pdf'),
                            'fileUrl': item.get('fileUrl')
                        })
            
            logger.info(f"Found {len(pdf_files)} PDF files for date {debate_date}")
            
            return {
                'status': 'SUCCESS',
                'pdf_files': pdf_files,
                'files_count': len(pdf_files),
                'raw_response': data
            }
            
        except Exception as e:
            logger.error(f"Failed to fetch PDFs for LS{lok_sabha_number} Session{session_number} Date{debate_date}: {e}")
            return {
                'status': 'ERROR',
                'pdf_files': [],
                'files_count': 0,
                'error': str(e)
            }
    
    def fetch_uncorrected_master_data_for_session(self, lok_sabha_number: str, session_number: str) -> Dict:
        """
        Fetch COMPLETE master data for uncorrected debates in a session
        This includes:
        - Available dates
        - PDF URLs for each date
        
        Args:
            lok_sabha_number: Lok Sabha number
            session_number: Session number
            
        Returns:
            Dict with complete master data
        """
        try:
            # Get or create LokSabha and Session objects
            lok_sabha = LokSabha.objects.get(number=lok_sabha_number)
            session = Session.objects.get(lok_sabha=lok_sabha, session_number=session_number)
            
            logger.info(f"Fetching uncorrected debate master data for LS{lok_sabha_number} Session{session_number}")
            
            # Step 1: Get available dates
            dates_result = self.fetch_uncorrected_session_dates(lok_sabha_number, session_number)
            
            if dates_result['status'] != 'SUCCESS' or not dates_result['available_dates']:
                logger.warning(f"No uncorrected debate dates found")
                return {
                    'status': 'NO_DATA',
                    'lok_sabha_number': lok_sabha_number,
                    'session_number': session_number,
                    'available_dates': [],
                    'dates_with_pdfs': {}
                }
            
            available_dates = dates_result['available_dates']
            
            # Step 2: For each date, get PDF URLs
            dates_with_pdfs = {}
            total_pdfs = 0
            
            for date_str in available_dates:
                try:
                    pdfs_result = self.fetch_uncorrected_pdfs_for_date(
                        lok_sabha_number, session_number, date_str
                    )
                    
                    if pdfs_result['status'] == 'SUCCESS' and pdfs_result['pdf_files']:
                        dates_with_pdfs[date_str] = pdfs_result['pdf_files']
                        total_pdfs += len(pdfs_result['pdf_files'])
                    else:
                        dates_with_pdfs[date_str] = []
                    
                    # Small delay between requests
                    time.sleep(0.2)
                    
                except Exception as e:
                    logger.error(f"Error fetching PDFs for date {date_str}: {e}")
                    dates_with_pdfs[date_str] = []
            
            # Parse date range
            date_range_start = None
            date_range_end = None
            
            if available_dates:
                try:
                    parsed_dates = []
                    for date_str in available_dates:
                        try:
                            parsed_date = datetime.strptime(date_str, '%d/%m/%Y').date()
                            parsed_dates.append(parsed_date)
                        except ValueError:
                            continue
                    
                    if parsed_dates:
                        date_range_start = min(parsed_dates)
                        date_range_end = max(parsed_dates)
                except Exception as e:
                    logger.warning(f"Failed to parse date range: {e}")
            
            # Store master data
            master_data = {
                'available_dates': available_dates,
                'session_period': [],  # Uncorrected debates don't have session period
                'date_range_start': date_range_start,
                'date_range_end': date_range_end,
                'total_debate_days': len(available_dates),
                'api_source': 'sansad.in/uncorrected-session-dates',
                'fallback_api_sources': ['sansad.in/uncorrected-debate-pdfs'],
                'is_complete': True,
                'last_discovery_attempt': timezone.now(),
                'discovery_success': len(available_dates) > 0,
                'raw_api_data': {
                    'dates_response': dates_result['raw_response'],
                    'dates_with_pdfs': dates_with_pdfs,  # THIS IS THE KEY PART - PDF URLs in master data!
                    'total_pdf_files': total_pdfs,
                    'debate_category': 'uncorrected'
                },
                'lok_sabha': lok_sabha,
                'session': session,
                'last_fetched': timezone.now()
            }
            
            # Get or create LS institution
            from services.questions.models import ParliamentInstitution
            ls_institution, _ = ParliamentInstitution.objects.get_or_create(
                name='lok_sabha',
                defaults={'full_name': 'Lok Sabha', 'is_active': True}
            )
            
            # MERGE with existing corrected debate data (don't overwrite!)
            debate_master, created = DebateMasterData.objects.get_or_create(
                parent_institution=ls_institution,
                lok_sabha_number=lok_sabha_number,
                session_number=session_number,
                defaults=master_data
            )
            
            # If not created, MERGE uncorrected data with existing corrected data
            if not created:
                existing_raw = debate_master.raw_api_data or {}
                debate_master.raw_api_data = {
                    **existing_raw,  # Keep corrected data
                    'uncorrected': master_data['raw_api_data'],  # Add uncorrected data
                }
                debate_master.save()
            
            # Store debate category in raw_api_data to differentiate
            if not created:
                for key, value in master_data.items():
                    if key not in ['lok_sabha_number', 'session_number']:
                        setattr(debate_master, key, value)
                debate_master.save()
            
            result = {
                'status': 'SUCCESS',
                'lok_sabha_number': lok_sabha_number,
                'session_number': session_number,
                'dates_count': len(available_dates),
                'total_pdf_files': total_pdfs,
                'created': created,
                'date_range': {
                    'start': date_range_start.isoformat() if date_range_start else None,
                    'end': date_range_end.isoformat() if date_range_end else None
                },
                'message': f'Successfully processed uncorrected debate master data: {len(available_dates)} dates, {total_pdfs} PDF files'
            }
            
            logger.info(f"Uncorrected debate master data fetch completed: {result}")
            return result
            
        except LokSabha.DoesNotExist:
            raise ValueError(f"Lok Sabha {lok_sabha_number} not found. Please fetch Lok Sabha sessions first.")
        except Session.DoesNotExist:
            raise ValueError(f"Session {session_number} for Lok Sabha {lok_sabha_number} not found. Please fetch Lok Sabha sessions first.")
        except Exception as e:
            logger.error(f"Failed to fetch uncorrected master data for LS{lok_sabha_number} Session{session_number}: {e}")
            raise
    
    def fetch_uncorrected_master_data_for_all_sessions(self, workers: int = 10) -> Dict:
        """
        Fetch uncorrected debate master data for ALL sessions in the database using parallel processing
        
        Args:
            workers: Number of parallel workers (default: 10)
            
        Returns:
            Dict with overall statistics
        """
        try:
            # Get all sessions from database
            all_sessions = list(Session.objects.exclude(lok_sabha__number='RS').order_by('lok_sabha__number', 'session_number'))
            
            total_sessions = len(all_sessions)
            processed_sessions = 0
            total_created = 0
            total_updated = 0
            total_dates = 0
            total_pdfs = 0
            errors = []
            
            print(f"📊 Processing {total_sessions} sessions for uncorrected debate master data with {workers} parallel workers...")
            
            # Process sessions in parallel
            with ThreadPoolExecutor(max_workers=workers) as executor:
                # Submit all sessions for processing
                future_to_session = {}
                for session in all_sessions:
                    future = executor.submit(self._process_single_session, session)
                    future_to_session[future] = session
                
                # Collect results as they complete
                completed = 0
                for future in as_completed(future_to_session):
                    session = future_to_session[future]
                    completed += 1
                    
                    try:
                        result = future.result(timeout=180)  # Longer timeout for uncorrected (fetches PDFs too)
                        processed_sessions += 1
                        if result.get('created'):
                            total_created += 1
                        else:
                            total_updated += 1
                        
                        total_dates += result.get('dates_count', 0)
                        total_pdfs += result.get('total_pdf_files', 0)
                        
                        dates_count = result.get('dates_count', 0)
                        pdfs_count = result.get('total_pdf_files', 0)
                        print(f"✅ ({completed}/{total_sessions}) LS{session.lok_sabha.number} Session{session.session_number}: {dates_count} dates, {pdfs_count} PDFs")
                        
                    except Exception as e:
                        error_msg = f"LS{session.lok_sabha.number} Session{session.session_number}: {str(e)}"
                        errors.append(error_msg)
                        print(f"❌ ({completed}/{total_sessions}) {error_msg}")
            
            result = {
                'status': 'SUCCESS' if not errors else 'PARTIAL_SUCCESS',
                'total_sessions': total_sessions,
                'processed_sessions': processed_sessions,
                'total_created': total_created,
                'total_updated': total_updated,
                'total_dates': total_dates,
                'total_pdf_files': total_pdfs,
                'errors': errors,
                'message': f'Uncorrected debate master data fetch completed: {processed_sessions}/{total_sessions} sessions, {total_dates} dates, {total_pdfs} PDF files'
            }
            
            logger.info(f"All uncorrected debate master data fetch completed: {result}")
            return result
            
        except Exception as e:
            logger.error(f"Failed to fetch all uncorrected debate master data: {e}")
            raise
    
    def _process_single_session(self, session: Session, max_retries: int = 3) -> Dict:
        """
        Process a single session with retry logic and randomized delay
        Called by parallel workers
        """
        for attempt in range(max_retries):
            try:
                # No delay on first attempt for metadata fetching
                # Only exponential backoff on retries
                if attempt > 0:
                    # Exponential backoff on retries
                    delay = min(2 ** attempt, 60)
                    time.sleep(delay)
                    logger.info(f"Retry {attempt + 1}/{max_retries} for LS{session.lok_sabha.number} Session{session.session_number}")
                
                result = self.fetch_uncorrected_master_data_for_session(
                    session.lok_sabha.number,
                    session.session_number
                )
                return result
                
            except Exception as e:
                logger.warning(f"Attempt {attempt + 1}/{max_retries} failed for LS{session.lok_sabha.number} Session{session.session_number}: {e}")
                
                if attempt == max_retries - 1:
                    logger.error(f"All {max_retries} attempts failed for LS{session.lok_sabha.number} Session{session.session_number}: {e}")
                    raise
                
                continue
    
    def get_uncorrected_master_data_for_session(self, lok_sabha_number: str, session_number: str) -> Optional[Dict]:
        """
        Get stored uncorrected debate master data for a session
        
        Returns:
            Dict with master data including PDF URLs, or None if not found
        """
        try:
            # Find master data - check raw_api_data for debate_category
            debate_master = DebateMasterData.objects.filter(
                lok_sabha_number=lok_sabha_number,
                session_number=session_number
            ).first()
            
            # Check if this is uncorrected debate data
            if debate_master and debate_master.raw_api_data.get('debate_category') == 'uncorrected':
                dates_with_pdfs = debate_master.raw_api_data.get('dates_with_pdfs', {})
                
                return {
                    'lok_sabha_number': lok_sabha_number,
                    'session_number': session_number,
                    'available_dates': debate_master.available_dates,
                    'dates_with_pdfs': dates_with_pdfs,
                    'total_pdf_files': debate_master.raw_api_data.get('total_pdf_files', 0),
                    'date_range': {
                        'start': debate_master.date_range_start.isoformat() if debate_master.date_range_start else None,
                        'end': debate_master.date_range_end.isoformat() if debate_master.date_range_end else None
                    },
                    'last_fetched': debate_master.last_fetched.isoformat()
                }
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to get uncorrected master data: {e}")
            return None
