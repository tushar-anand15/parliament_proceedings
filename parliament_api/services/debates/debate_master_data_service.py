import requests
import logging
import time
import random
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from django.utils import timezone
from django.db import transaction
from django.conf import settings

from services.questions.models import LokSabha, Session
from .models import DebateMasterData

logger = logging.getLogger(__name__)


class DebateMasterDataService:
    """
    Service for fetching and managing CORRECTED debate metadata from Parliament APIs
    
    Note: This service handles CORRECTED debates (text-of-debate API).
    For UNCORRECTED debates, the API structure is different.
    
    This service handles the complete flow:
    1. Fetch Lok Sabha and Sessions metadata
    2. Fetch available debate dates for each session (corrected debates)
    3. Store master data in database
    4. Provide data for debate scraper service
    """
    
    def __init__(self):
        self.session = requests.Session()
        # Set headers to mimic browser requests (corrected debates)
        self.session.headers.update({
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Connection': 'keep-alive',
            'Referer': 'https://sansad.in/ls/debates/text-of-debates',  # No tab parameter = corrected
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-origin',
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36',
            'sec-ch-ua': '"Chromium";v="140", "Not=A?Brand";v="24", "Brave";v="140"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"macOS"'
        })
        
        self.base_url = "https://sansad.in/api_ls"
        self.eparlib_base_url = "https://eparlib.sansad.in/restv3"
        self.debate_category = 'corrected'  # This service handles CORRECTED debates
    
    def initialize_debate_master_data(self, force_update: bool = False) -> Dict:
        """
        Initialize debate master data - fetch sessions and all available debate dates
        
        Args:
            force_update: If True, refetch data even if it exists
            
        Returns:
            Dict with initialization results
        """
        try:
            print(f"🏛️ Initializing Parliament Debates Master Data...")
            
            # Check if we already have data
            existing_sessions = Session.objects.count()
            existing_debate_metadata = DebateMasterData.objects.count()
            
            if not force_update and existing_sessions > 0 and existing_debate_metadata > 0:
                print(f"📊 Debate master data already exists: {existing_sessions} sessions, {existing_debate_metadata} debate metadata records")
                print(f"💡 Use force_update=True to refresh from server")
                
                return {
                    'status': 'ALREADY_EXISTS',
                    'sessions_count': existing_sessions,
                    'debate_metadata_count': existing_debate_metadata,
                    'message': 'Debate master data already initialized. Use force_update=True to refresh.'
                }
            
            print(f"🚀 {'Updating' if force_update else 'Fetching'} debate master data from Parliament APIs...")
            
            # Step 1: Ensure we have Lok Sabha and Session data (reuse from questions service)
            print(f"📡 Step 1: Ensuring Lok Sabha and Session data exists...")
            
            # Import here to avoid circular imports
            from services.questions.master_data_service import QuestionMasterDataService
            questions_service = QuestionMasterDataService()
            
            # Fetch sessions if they don't exist
            if existing_sessions == 0 or force_update:
                sessions_result = questions_service.fetch_lok_sabha_sessions()
                print(f"   ✅ Sessions: {sessions_result.get('message', 'Updated')}")
            else:
                print(f"   ✅ Sessions: Using existing {existing_sessions} sessions")
            
            # Step 2: Fetch debate dates for all sessions
            print(f"📡 Step 2: Fetching debate dates for all sessions...")
            debate_result = self.fetch_debate_dates_for_all_sessions()
            
            result = {
                'status': 'SUCCESS',
                'debate_result': debate_result,
                'total_sessions': Session.objects.count(),
                'total_debate_metadata': DebateMasterData.objects.count(),
                'message': f'Debate master data initialized successfully'
            }
            
            print(f"✅ Debate master data initialization completed!")
            print(f"   📊 Sessions: {result['total_sessions']}")
            print(f"   📊 Debate Metadata Records: {result['total_debate_metadata']}")
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to initialize debate master data: {e}")
            raise
    
    def fetch_debate_dates_for_all_sessions(self, workers: int = 10) -> Dict:
        """
        Fetch debate dates for ALL sessions in the database using parallel processing
        
        Args:
            workers: Number of parallel workers (default: 10)
            
        Returns:
            Dict with overall statistics
        """
        try:
            # Get all sessions from database
            all_sessions = list(Session.objects.all().order_by('lok_sabha__number', 'session_number'))
            
            total_sessions = len(all_sessions)
            processed_sessions = 0
            total_created = 0
            total_updated = 0
            errors = []
            
            print(f"📊 Processing {total_sessions} sessions for corrected debate dates with {workers} parallel workers...")
            
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
                        result = future.result(timeout=120)
                        processed_sessions += 1
                        if result.get('created'):
                            total_created += 1
                        else:
                            total_updated += 1
                        
                        dates_count = result.get('dates_count', 0)
                        print(f"✅ ({completed}/{total_sessions}) LS{session.lok_sabha.number} Session{session.session_number}: {dates_count} dates")
                        
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
                'errors': errors,
                'message': f'Corrected debate dates fetch completed: {processed_sessions}/{total_sessions} sessions processed'
            }
            
            logger.info(f"All corrected debate dates fetch completed: {result}")
            return result
            
        except Exception as e:
            logger.error(f"Failed to fetch all debate dates: {e}")
            raise
    
    def _process_single_session(self, session: Session, max_retries: int = 3) -> Dict:
        """
        Process a single session with retry logic and randomized delay
        Called by parallel workers
        """
        for attempt in range(max_retries):
            try:
                # Add randomized delay (0.2-0.5 seconds) to avoid overwhelming API
                if attempt == 0:
                    random_delay = random.uniform(0.2, 0.5)
                    time.sleep(random_delay)
                elif attempt > 0:
                    # Exponential backoff on retries
                    delay = min(2 ** attempt, 60)
                    time.sleep(delay)
                    logger.info(f"Retry {attempt + 1}/{max_retries} for LS{session.lok_sabha.number} Session{session.session_number}")
                
                result = self.fetch_debate_dates_for_session(
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
    
    def fetch_debate_dates_for_session(self, lok_sabha_number: str, session_number: str) -> Dict:
        """
        Fetch all available debate dates for a specific Lok Sabha session
        
        Args:
            lok_sabha_number: Lok Sabha number (e.g., '18')
            session_number: Session number (e.g., '5')
            
        Returns:
            Dict with debate dates data and statistics
        """
        try:
            # Get or create LokSabha and Session objects
            lok_sabha = LokSabha.objects.get(number=lok_sabha_number)
            session = Session.objects.get(lok_sabha=lok_sabha, session_number=session_number)
            
            # Try sansad.in API first, fallback to eparlib if it fails
            logger.info(f"Fetching debate dates for LS{lok_sabha_number} Session{session_number}")
            
            # Method 1: Try sansad.in API first
            dates_data = self._get_debate_dates_sansad_api(lok_sabha_number, session_number)
            api_sources_used = ['sansad.in']
            
            if not dates_data.get('available_dates'):
                # Method 2: Fallback to eparlib API
                logger.info("Sansad API failed, trying eparlib API as fallback...")
                dates_data = self._get_debate_dates_eparlib_api(lok_sabha_number, session_number)
                if dates_data.get('available_dates'):
                    api_sources_used.append('eparlib.sansad.in')
            
            available_dates = dates_data.get('available_dates', [])
            session_period = dates_data.get('session_period', [])
            
            if not available_dates:
                logger.warning(f"No debate dates found for LS{lok_sabha_number} Session{session_number}")
                available_dates = []
            
            # Clean and validate dates, then parse date range
            available_dates = self._clean_and_validate_dates(available_dates)
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
                            logger.warning(f"Failed to parse cleaned date '{date_str}'")
                            continue
                    
                    if parsed_dates:
                        date_range_start = min(parsed_dates)
                        date_range_end = max(parsed_dates)
                        logger.info(f"Date range: {date_range_start} to {date_range_end}")
                except Exception as e:
                    logger.warning(f"Failed to parse date range: {e}")
            
            # Store or update master data
            master_data = {
                'available_dates': available_dates,
                'session_period': session_period,
                'date_range_start': date_range_start,
                'date_range_end': date_range_end,
                'total_debate_days': len(available_dates),
                'api_source': dates_data.get('api_source', 'sansad.in'),
                'fallback_api_sources': api_sources_used,
                'is_complete': True,
                'last_discovery_attempt': timezone.now(),
                'discovery_success': len(available_dates) > 0,
                'raw_api_data': dates_data,
                'lok_sabha': lok_sabha,
                'session': session,
                'last_fetched': timezone.now()
            }
            
            # Create or update master data
            debate_master, created = DebateMasterData.objects.get_or_create(
                lok_sabha_number=lok_sabha_number,
                session_number=session_number,
                defaults=master_data
            )
            
            if not created:
                # Update existing record
                for key, value in master_data.items():
                    if key not in ['lok_sabha_number', 'session_number']:
                        setattr(debate_master, key, value)
                debate_master.save()
            
            result = {
                'status': 'SUCCESS',
                'lok_sabha_number': lok_sabha_number,
                'session_number': session_number,
                'dates_count': len(available_dates),
                'created': created,
                'api_sources_used': api_sources_used,
                'date_range': {
                    'start': date_range_start.isoformat() if date_range_start else None,
                    'end': date_range_end.isoformat() if date_range_end else None
                },
                'message': f'Successfully processed debate dates for LS{lok_sabha_number} Session{session_number}'
            }
            
            logger.info(f"Debate dates fetch completed: {result}")
            return result
            
        except LokSabha.DoesNotExist:
            raise ValueError(f"Lok Sabha {lok_sabha_number} not found. Please fetch Lok Sabha sessions first.")
        except Session.DoesNotExist:
            raise ValueError(f"Session {session_number} for Lok Sabha {lok_sabha_number} not found. Please fetch Lok Sabha sessions first.")
        except Exception as e:
            logger.error(f"Failed to fetch debate dates for LS{lok_sabha_number} Session{session_number}: {e}")
            raise
    
    def _get_debate_dates_sansad_api(self, lok_sabha_number: str, session_number: str) -> Dict:
        """Get debate dates from the sansad.in API with comprehensive session format fallbacks"""
        
        try:
            url = f"{self.base_url}/business/AllLoksabhaAndSessionDates"
            
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            
            # Generate all possible session number formats to try
            session_formats_to_try = self._generate_session_formats(session_number)
            
            # Find the specific Lok Sabha and session
            for ls_data in data:
                if str(ls_data.get('loksabha')) == lok_sabha_number:
                    available_sessions = []
                    
                    for session_data in ls_data.get('sessions', []):
                        session_num = session_data.get('sessionNo')
                        available_sessions.append(str(session_num))
                        
                        # Try all possible session formats
                        for session_format in session_formats_to_try:
                            if self._sessions_match(str(session_num), session_format):
                                dates = session_data.get('dates', [])
                                session_period = session_data.get('sessionPeriod', [])
                                
                                logger.info(f"✅ Sansad API: Found session {session_num} (matched with format '{session_format}') with {len(dates)} debate dates")
                                
                                return {
                                    'available_dates': dates,
                                    'session_period': session_period,
                                    'api_source': 'sansad.in',
                                    'matched_format': session_format,
                                    'api_session_number': str(session_num),
                                    'raw_response': session_data
                                }
                    
                    logger.warning(f"Sansad API: Session {session_number} not found for LS{lok_sabha_number}. Available sessions: {', '.join(available_sessions)}. Tried formats: {', '.join(session_formats_to_try)}")
            
            logger.warning(f"Sansad API: Lok Sabha {lok_sabha_number} not found in API response")
            return {}
            
        except Exception as e:
            logger.error(f"Sansad API failed: {e}")
            return {}
    
    def _get_debate_dates_eparlib_api(self, lok_sabha_number: str, session_number: str) -> Dict:
        """Get debate dates from the eparlib.sansad.in API as fallback with comprehensive format handling"""
        
        try:
            # Step 1: Get available sessions for this Lok Sabha
            sessions_url = f"{self.eparlib_base_url}/field/browse"
            sessions_params = {
                'field': 'sessionNo',
                'collectionId': '2',  # Lok Sabha debates collection
                'loksabhaNo': lok_sabha_number.zfill(2),  # Zero-pad to 2 digits
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
            
            # Step 2: Generate all possible session formats for eparlib (which uses lowercase Roman numerals)
            eparlib_session_formats = self._generate_eparlib_session_formats(session_number)
            
            # Step 3: Find matching session using comprehensive matching
            matched_session = None
            matched_format = None
            
            for session_format in eparlib_session_formats:
                for available_session in available_sessions:
                    if self._sessions_match_case_insensitive(available_session, session_format):
                        matched_session = available_session
                        matched_format = session_format
                        break
                if matched_session:
                    break
            
            if not matched_session:
                logger.warning(f"Eparlib API: Session {session_number} not found. Available sessions: {', '.join(available_sessions)}. Tried formats: {', '.join(eparlib_session_formats)}")
                return {}
            
            # Step 4: Get dates for the matched session
            dates_url = f"{self.eparlib_base_url}/field/browse"
            dates_params = {
                'field': 'date',
                'collectionId': '2',
                'loksabhaNo': lok_sabha_number.zfill(2),
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
            
            logger.info(f"✅ Eparlib API: Found session {matched_session} (matched with format '{matched_format}') with {len(converted_dates)} debate dates")
            
            return {
                'available_dates': converted_dates,
                'session_period': [],  # Not available from eparlib API
                'api_source': 'eparlib.sansad.in',
                'matched_format': matched_format,
                'api_session_number': matched_session,
                'raw_response': dates_data.get('records', [])
            }
            
        except Exception as e:
            logger.error(f"Eparlib API failed: {e}")
            return {}
    
    def _get_debate_dates_with_retry(self, api_method, lok_sabha_number: str, session_number: str, 
                                   api_name: str = "API", max_retries: int = 3) -> Dict:
        """
        Get debate dates with retry mechanism and exponential backoff
        
        Args:
            api_method: The API method to call
            lok_sabha_number: Lok Sabha number
            session_number: Session number
            api_name: Name of the API for logging
            max_retries: Maximum number of retry attempts
            
        Returns:
            Dict with debate dates data or empty dict if all attempts fail
        """
        base_delay = 1  # Start with 1 second
        
        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    delay = base_delay * (2 ** (attempt - 1))  # 1s, 2s, 4s
                    logger.info(f"{api_name}: Retry attempt {attempt + 1}/{max_retries} after {delay}s delay")
                    time.sleep(delay)
                
                result = api_method(lok_sabha_number, session_number)
                
                # If we got results, return immediately
                if result.get('available_dates'):
                    return result
                elif result:
                    # Got a response but no dates - might be valid (empty session)
                    logger.warning(f"{api_name}: Got response but no dates for LS{lok_sabha_number} Session{session_number}")
                    return result
                
            except requests.exceptions.Timeout as e:
                logger.warning(f"{api_name}: Timeout on attempt {attempt + 1}/{max_retries}: {e}")
                if attempt == max_retries - 1:
                    logger.error(f"{api_name}: All {max_retries} attempts timed out for LS{lok_sabha_number} Session{session_number}")
            except requests.exceptions.ConnectionError as e:
                logger.warning(f"{api_name}: Connection error on attempt {attempt + 1}/{max_retries}: {e}")
                if attempt == max_retries - 1:
                    logger.error(f"{api_name}: All {max_retries} attempts failed with connection errors for LS{lok_sabha_number} Session{session_number}")
            except requests.exceptions.HTTPError as e:
                # For HTTP errors, don't retry if it's a client error (4xx)
                if hasattr(e, 'response') and e.response is not None and 400 <= e.response.status_code < 500:
                    logger.error(f"{api_name}: Client error {e.response.status_code}, not retrying: {e}")
                    break
                else:
                    logger.warning(f"{api_name}: HTTP error on attempt {attempt + 1}/{max_retries}: {e}")
                    if attempt == max_retries - 1:
                        logger.error(f"{api_name}: All {max_retries} attempts failed with HTTP errors for LS{lok_sabha_number} Session{session_number}")
            except Exception as e:
                logger.warning(f"{api_name}: Unexpected error on attempt {attempt + 1}/{max_retries}: {e}")
                if attempt == max_retries - 1:
                    logger.error(f"{api_name}: All {max_retries} attempts failed with errors for LS{lok_sabha_number} Session{session_number}: {e}")
        
        # All attempts failed
        return {}
    
    def _generate_session_formats(self, session_number: str) -> List[str]:
        """
        Generate all possible session number formats to try for sansad.in API
        
        Args:
            session_number: Original session number (could be numeric or Roman)
            
        Returns:
            List of all possible formats to try
        """
        formats = []
        
        if session_number.isdigit():
            # Numeric input: try as-is first, then Roman (uppercase and lowercase)
            num = int(session_number)
            roman_upper = self._int_to_roman(num)
            roman_lower = roman_upper.lower()
            
            formats = [
                session_number,      # Original numeric
                roman_upper,         # Roman uppercase  
                roman_lower,         # Roman lowercase
                str(num),           # Ensure it's string
            ]
        else:
            # Roman input: try as-is, then variations, then numeric
            try:
                numeric = str(self._roman_to_int(session_number))
                formats = [
                    session_number,                    # Original
                    session_number.upper(),           # Uppercase Roman
                    session_number.lower(),           # Lowercase Roman
                    session_number.capitalize(),      # Capitalized Roman
                    numeric,                          # Numeric equivalent
                ]
            except:
                # If Roman conversion fails, just use variations of the original
                formats = [
                    session_number,
                    session_number.upper(),
                    session_number.lower(),
                    session_number.capitalize(),
                ]
        
        # Remove duplicates while preserving order
        unique_formats = []
        for fmt in formats:
            if fmt and fmt not in unique_formats:
                unique_formats.append(fmt)
        
        return unique_formats
    
    def _generate_eparlib_session_formats(self, session_number: str) -> List[str]:
        """
        Generate all possible session formats for eparlib API (prefers lowercase Roman)
        
        Args:
            session_number: Original session number
            
        Returns:
            List of formats optimized for eparlib API
        """
        formats = []
        
        if session_number.isdigit():
            # Numeric input: convert to Roman (lowercase preferred for eparlib)
            num = int(session_number)
            roman_upper = self._int_to_roman(num)
            roman_lower = roman_upper.lower()
            
            formats = [
                roman_lower,         # Lowercase Roman (eparlib preferred)
                session_number,      # Original numeric
                roman_upper,         # Uppercase Roman
                str(num),           # Ensure string
            ]
        else:
            # Roman input: try lowercase first (eparlib preference)
            try:
                numeric = str(self._roman_to_int(session_number))
                formats = [
                    session_number.lower(),           # Lowercase (eparlib preferred)
                    session_number,                   # Original
                    session_number.upper(),           # Uppercase
                    session_number.capitalize(),      # Capitalized
                    numeric,                          # Numeric equivalent
                ]
            except:
                formats = [
                    session_number.lower(),
                    session_number,
                    session_number.upper(),
                    session_number.capitalize(),
                ]
        
        # Remove duplicates while preserving order
        unique_formats = []
        for fmt in formats:
            if fmt and fmt not in unique_formats:
                unique_formats.append(fmt)
        
        return unique_formats
    
    def _sessions_match(self, api_session: str, target_format: str) -> bool:
        """
        Check if an API session number matches our target format
        
        Args:
            api_session: Session number from API
            target_format: Format we're trying to match
            
        Returns:
            True if they match
        """
        # Direct string match
        if str(api_session) == str(target_format):
            return True
        
        # Case-insensitive match
        if str(api_session).lower() == str(target_format).lower():
            return True
        
        # Try numeric conversion if both could be numbers
        try:
            if api_session.isdigit() and target_format.isdigit():
                return int(api_session) == int(target_format)
        except:
            pass
        
        # Try Roman numeral conversion
        try:
            api_as_int = self._roman_to_int(api_session) if not api_session.isdigit() else int(api_session)
            target_as_int = self._roman_to_int(target_format) if not target_format.isdigit() else int(target_format)
            return api_as_int == target_as_int
        except:
            pass
        
        return False
    
    def _sessions_match_case_insensitive(self, api_session: str, target_format: str) -> bool:
        """
        Case-insensitive session matching (for eparlib API)
        
        Args:
            api_session: Session from API
            target_format: Target format
            
        Returns:
            True if they match (case-insensitive)
        """
        return self._sessions_match(api_session, target_format)
    
    def _clean_and_validate_dates(self, dates: List[str]) -> List[str]:
        """
        Clean and validate date strings, removing invalid ones
        
        Args:
            dates: List of date strings in various formats
            
        Returns:
            List of validated date strings in DD/MM/YYYY format
        """
        if not dates:
            return []
        
        cleaned_dates = []
        
        for date_str in dates:
            if not date_str or not isinstance(date_str, str):
                continue
            
            # Remove extra whitespace
            date_str = date_str.strip()
            
            if not date_str:
                continue
            
            # Try to parse and reformat the date to ensure consistency
            try:
                # Try DD/MM/YYYY format first
                if '/' in date_str and len(date_str.split('/')) == 3:
                    parts = date_str.split('/')
                    if len(parts[0]) <= 2 and len(parts[1]) <= 2 and len(parts[2]) == 4:
                        # Looks like DD/MM/YYYY
                        day, month, year = parts
                        # Validate by parsing
                        parsed_date = datetime.strptime(f"{day.zfill(2)}/{month.zfill(2)}/{year}", '%d/%m/%Y')
                        # Reformat to ensure consistency
                        formatted_date = f"{day.zfill(2)}/{month.zfill(2)}/{year}"
                        cleaned_dates.append(formatted_date)
                        continue
                
                # Try other common formats
                for fmt in ['%Y-%m-%d', '%d-%m-%Y', '%m/%d/%Y']:
                    try:
                        parsed_date = datetime.strptime(date_str, fmt)
                        # Convert to DD/MM/YYYY format
                        formatted_date = parsed_date.strftime('%d/%m/%Y')
                        cleaned_dates.append(formatted_date)
                        break
                    except ValueError:
                        continue
                else:
                    # If no format worked, log and skip
                    logger.warning(f"Could not parse date format: '{date_str}'")
                    
            except Exception as e:
                logger.warning(f"Error cleaning date '{date_str}': {e}")
                continue
        
        # Remove duplicates while preserving order
        unique_dates = []
        seen = set()
        for date_str in cleaned_dates:
            if date_str not in seen:
                unique_dates.append(date_str)
                seen.add(date_str)
        
        logger.info(f"Cleaned {len(dates)} dates -> {len(unique_dates)} valid unique dates")
        return unique_dates
    
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
    
    def get_debate_master_data_statistics(self) -> Dict:
        """
        Get statistics about debate master data
        
        Returns:
            Dict with statistics
        """
        try:
            total_sessions = DebateMasterData.objects.count()
            by_lok_sabha = {}
            
            # Group by Lok Sabha
            for lok_sabha in LokSabha.objects.all():
                count = DebateMasterData.objects.filter(lok_sabha=lok_sabha).count()
                total_dates = sum(
                    len(dmd.available_dates) 
                    for dmd in DebateMasterData.objects.filter(lok_sabha=lok_sabha)
                )
                by_lok_sabha[f"LS{lok_sabha.number}"] = {
                    'sessions': count,
                    'total_debate_dates': total_dates
                }
            
            # Completion status
            complete_sessions = DebateMasterData.objects.filter(is_complete=True).count()
            incomplete_sessions = total_sessions - complete_sessions
            
            # Total debate dates across all sessions
            total_debate_dates = sum(
                len(dmd.available_dates) 
                for dmd in DebateMasterData.objects.all()
            )
            
            # API source statistics
            api_sources = {}
            for dmd in DebateMasterData.objects.all():
                source = dmd.api_source
                if source not in api_sources:
                    api_sources[source] = 0
                api_sources[source] += 1
            
            return {
                'total_sessions_with_debate_data': total_sessions,
                'by_lok_sabha': by_lok_sabha,
                'total_debate_dates_available': total_debate_dates,
                'completion_status': {
                    'complete': complete_sessions,
                    'incomplete': incomplete_sessions
                },
                'api_sources_used': api_sources,
                'last_updated': timezone.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Failed to get debate master data statistics: {e}")
            raise
    
    def get_debate_dates_for_session(self, lok_sabha_number: str, session_number: str, 
                                   start_date: Optional[str] = None, end_date: Optional[str] = None) -> List[str]:
        """
        Get debate dates for a specific session with optional filtering
        
        Args:
            lok_sabha_number: Lok Sabha number
            session_number: Session number  
            start_date: Filter dates from this date (YYYY-MM-DD)
            end_date: Filter dates to this date (YYYY-MM-DD)
            
        Returns:
            List of date strings in DD/MM/YYYY format
        """
        try:
            debate_master = DebateMasterData.objects.get(
                lok_sabha_number=lok_sabha_number,
                session_number=session_number
            )
            
            if start_date or end_date:
                start_dt = datetime.strptime(start_date, '%Y-%m-%d').date() if start_date else None
                end_dt = datetime.strptime(end_date, '%Y-%m-%d').date() if end_date else None
                return debate_master.get_dates_for_period(start_dt, end_dt)
            else:
                return debate_master.available_dates
                
        except DebateMasterData.DoesNotExist:
            raise ValueError(f"Debate master data not found for LS{lok_sabha_number} Session{session_number}. Please initialize master data first.")
        except Exception as e:
            logger.error(f"Failed to get debate dates: {e}")
            raise
    
    def list_available_sessions_with_debates(self) -> List[Dict]:
        """
        List all available sessions with debate date counts
        
        Returns:
            List of session summaries with debate information
        """
        try:
            debate_masters = DebateMasterData.objects.all().order_by('lok_sabha__number', 'session_number')
            
            session_list = []
            for debate_master in debate_masters:
                session_list.append({
                    'lok_sabha_number': debate_master.lok_sabha_number,
                    'session_number': debate_master.session_number,
                    'total_debate_dates': len(debate_master.available_dates),
                    'date_range': {
                        'start': debate_master.date_range_start.isoformat() if debate_master.date_range_start else None,
                        'end': debate_master.date_range_end.isoformat() if debate_master.date_range_end else None
                    },
                    'is_complete': debate_master.is_complete,
                    'api_source': debate_master.api_source,
                    'last_updated': debate_master.last_fetched.isoformat(),
                    'debates_discovered': debate_master.debates_discovered,
                    'debates_downloaded': debate_master.debates_downloaded,
                    'completion_percentage': debate_master.completion_percentage,
                    'ready_for_scraping': len(debate_master.available_dates) > 0
                })
            
            return session_list
            
        except Exception as e:
            logger.error(f"Failed to list available sessions with debates: {e}")
            raise
