"""
RS Debate Master Data Service
Handles fetching and managing RS debate metadata from Parliament APIs

Supports two types of RS debates:
1. Verbatim Debates - Recent proceedings with time slots (rsdoc.nic.in)
2. Official Debates - Historical Q&A and debates (rsdebate.nic.in)
"""

import requests
import logging
import time
import random
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from django.utils import timezone
from django.db import transaction

logger = logging.getLogger(__name__)


class RSDebateMasterDataService:
    """Service for fetching RS debate metadata"""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Origin': 'https://sansad.in',
            'Referer': 'https://sansad.in/',
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36',
            'sec-fetch-site': 'cross-site',
            'sec-fetch-mode': 'cors',
            'sec-fetch-dest': 'empty'
        })
        
        # API endpoints
        self.api_rs_base = "https://sansad.in/api_rs"
        self.rsdoc_base = "https://rsdoc.nic.in/business"
        self.rsdebate_base = "https://rsdebate.nic.in/restv3"
    
    # ==========================================
    # VERBATIM DEBATES (Recent proceedings)
    # ==========================================
    
    def fetch_verbatim_rs_sessions(self) -> List[int]:
        """
        Fetch all RS session numbers for verbatim debates
        Returns: [189, 190, 191, ..., 268]
        """
        try:
            url = f"{self.api_rs_base}/debate/rs-session"
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            
            sessions = response.json()
            logger.info(f"✅ Fetched {len(sessions)} RS sessions (verbatim)")
            return sessions
            
        except Exception as e:
            logger.error(f"❌ Error fetching RS verbatim sessions: {e}")
            return []
    
    def fetch_verbatim_session_dates(self, session_no: int) -> List[Dict]:
        """
        Fetch sitting dates for an RS session (verbatim)
        
        Returns list of dicts with structure:
        {
            "Id": 17165,
            "sessionNo": 268,
            "SittingDate": "2025-08-21T00:00:00",
            ...
        }
        """
        try:
            url = f"{self.rsdoc_base}/SessionDates"
            params = {'Sessionno': session_no}
            
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()
            
            dates = response.json()
            logger.info(f"✅ Session {session_no}: {len(dates)} sitting dates (verbatim)")
            return dates
            
        except Exception as e:
            logger.error(f"❌ Error fetching verbatim dates for session {session_no}: {e}")
            return []
    
    def fetch_verbatim_debates(self, session_no: int, date_str: str) -> List[Dict]:
        """
        Fetch verbatim debate PDFs for a specific date
        
        Args:
            session_no: RS session number (e.g., 268)
            date_str: Date in DD/MM/YYYY format (e.g., "21/07/2025")
            
        Returns list of dicts with PDF metadata
        """
        try:
            url = f"{self.rsdoc_base}/BusinessVerbatim"
            params = {
                'ses_no': session_no,
                'ses_dt': date_str
            }
            
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()
            
            debates = response.json()
            logger.info(f"✅ Session {session_no}, Date {date_str}: {len(debates)} PDFs (verbatim)")
            return debates
            
        except Exception as e:
            logger.error(f"❌ Error fetching verbatim debates for {session_no}/{date_str}: {e}")
            return []
    
    # ==========================================
    # OFFICIAL DEBATES (Historical Q&A)
    # ==========================================
    
    def browse_official_field(self, field: str, rows: int = 200) -> List[Dict]:
        """
        Browse/aggregate by specific field in official debates
        
        Args:
            field: Field to browse (year, sessionNo, type, ministry, etc.)
            rows: Number of results to fetch
            
        Returns list of dicts with name and count
        """
        try:
            url = f"{self.rsdebate_base}/field/browse"
            params = {
                'field': field,
                'start': 0,
                'rows': rows,
                'collectionId': '(1,2)'
            }
            
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            records = data.get('records', [])
            logger.info(f"✅ Fetched {len(records)} {field} entries (official)")
            return records
            
        except Exception as e:
            logger.error(f"❌ Error browsing field {field} (official): {e}")
            return []
    
    def fetch_official_debates(
        self, 
        start: int = 0, 
        rows: int = 50,
        year: Optional[int] = None,
        session_no: Optional[int] = None,
        date: Optional[str] = None
    ) -> Dict:
        """
        Fetch official debates with optional filters
        
        Args:
            start: Pagination offset
            rows: Number of records
            year: Filter by year (e.g., 2024)
            session_no: Filter by session (e.g., 265)
            date: Filter by date (YYYY-MM-DD)
            
        Returns dict with records and metadata
        """
        try:
            url = f"{self.rsdebate_base}/fetch/all"
            params = {
                'start': start,
                'rows': rows,
                'order': 'all_desc',
                'collectionId': '(1,2)'
            }
            
            if year:
                params['year'] = year
            if session_no:
                params['sessionNo'] = session_no
            if date:
                params['date'] = date
            
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            logger.info(f"✅ Fetched {len(data.get('records', []))} official debates (start={start})")
            return data
            
        except Exception as e:
            logger.error(f"❌ Error fetching official debates: {e}")
            return {'records': [], 'rowsCount': '0'}
    
    # ==========================================
    # UTILITY METHODS
    # ==========================================
    
    @staticmethod
    def convert_iso_to_dd_mm_yyyy(iso_date_str: str) -> str:
        """
        Convert ISO date to DD/MM/YYYY format
        Input: "2025-08-21T00:00:00"
        Output: "21/08/2025"
        """
        try:
            if 'T' in iso_date_str:
                dt = datetime.fromisoformat(iso_date_str.replace('Z', '+00:00'))
            else:
                dt = datetime.fromisoformat(iso_date_str)
            
            return dt.strftime('%d/%m/%Y')
        except Exception as e:
            logger.error(f"Date conversion error: {e}")
            return ""
    
    # ==========================================
    # MASTER DATA INITIALIZATION
    # ==========================================
    
    def initialize_verbatim_master_data(
        self, 
        force_update: bool = False,
        max_workers: int = 3,
        recent_sessions_only: int = 0
    ) -> Dict:
        """
        Initialize RS verbatim debate master data
        
        Args:
            force_update: Force refresh even if data exists
            max_workers: Number of parallel workers
            recent_sessions_only: If > 0, only fetch this many recent sessions
        """
        result = {
            'status': 'SUCCESS',
            'sessions_processed': 0,
            'dates_processed': 0,
            'debates_discovered': 0,
            'errors': []
        }
        
        try:
            logger.info("🏛️  Initializing RS Verbatim Debates Master Data...")
            
            # Step 1: Get all sessions
            sessions = self.fetch_verbatim_rs_sessions()
            
            if not sessions:
                result['status'] = 'ERROR'
                result['errors'].append('No sessions fetched')
                return result
            
            # Filter to recent sessions if specified
            if recent_sessions_only > 0:
                sessions = sessions[-recent_sessions_only:]
                logger.info(f"📅 Processing last {len(sessions)} sessions only")
            
            # Step 2: Process each session
            def process_session(session_no: int) -> Tuple[int, int, int]:
                """Process a single session, return (dates_count, debates_count, errors_count)"""
                dates_count = 0
                debates_count = 0
                errors_count = 0
                
                try:
                    from django.conf import settings
                    
                    # Random delay before starting session
                    time.sleep(random.uniform(settings.API_REQUEST_DELAY_MIN, settings.API_REQUEST_DELAY_MAX))
                    
                    dates = self.fetch_verbatim_session_dates(session_no)
                    
                    for date_obj in dates:
                        sitting_date = date_obj.get('SittingDate', '')
                        date_str = self.convert_iso_to_dd_mm_yyyy(sitting_date)
                        
                        if not date_str:
                            continue
                        
                        try:
                            debates = self.fetch_verbatim_debates(session_no, date_str)
                            dates_count += 1
                            debates_count += len(debates)
                            
                            # Random delay between date requests
                            time.sleep(random.uniform(settings.API_REQUEST_DELAY_MIN, settings.API_REQUEST_DELAY_MAX))
                        except Exception as e:
                            logger.error(f"Error fetching debates for {session_no}/{date_str}: {e}")
                            errors_count += 1
                    
                except Exception as e:
                    logger.error(f"Error processing session {session_no}: {e}")
                    errors_count += 1
                
                return (dates_count, debates_count, errors_count)
            
            # Process sessions in parallel
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {
                    executor.submit(process_session, session_no): session_no 
                    for session_no in sessions
                }
                
                for future in as_completed(futures):
                    session_no = futures[future]
                    try:
                        dates_count, debates_count, errors_count = future.result()
                        result['sessions_processed'] += 1
                        result['dates_processed'] += dates_count
                        result['debates_discovered'] += debates_count
                        
                        if errors_count > 0:
                            result['errors'].append(f"Session {session_no}: {errors_count} errors")
                        
                        logger.info(f"✅ Session {session_no}: {dates_count} dates, {debates_count} debates")
                    except Exception as e:
                        logger.error(f"❌ Error processing session {session_no}: {e}")
                        result['errors'].append(f"Session {session_no}: {str(e)}")
            
            logger.info(f"✅ Verbatim master data initialization complete")
            return result
            
        except Exception as e:
            logger.error(f"❌ Error in verbatim initialization: {e}")
            result['status'] = 'ERROR'
            result['errors'].append(str(e))
            return result
    
    def initialize_official_master_data(
        self, 
        force_update: bool = False,
        recent_sessions_count: int = 10
    ) -> Dict:
        """
        Initialize RS official debate master data (metadata only)
        
        Args:
            force_update: Force refresh even if data exists
            recent_sessions_count: Number of recent sessions to analyze
        """
        result = {
            'status': 'SUCCESS',
            'years_available': 0,
            'sessions_available': 0,
            'total_debates': 0,
            'part1_debates': 0,
            'part2_debates': 0,
            'recent_sessions': [],
            'errors': []
        }
        
        try:
            logger.info("📚 Initializing RS Official Debates Master Data...")
            
            # Get years
            years = self.browse_official_field('year', rows=100)
            result['years_available'] = len(years)
            logger.info(f"✅ Years: {len(years)} ({years[0]['name']} - {years[-1]['name']})")
            
            # Get sessions
            sessions = self.browse_official_field('sessionNo', rows=300)
            result['sessions_available'] = len(sessions)
            logger.info(f"✅ Sessions: {len(sessions)} (Session {sessions[-1]['name']} - {sessions[0]['name']})")
            
            # Get types
            types = self.browse_official_field('type', rows=10)
            for type_info in types:
                if 'Part 1' in type_info['name']:
                    result['part1_debates'] = int(type_info['count'])
                elif 'Part 2' in type_info['name']:
                    result['part2_debates'] = int(type_info['count'])
            
            result['total_debates'] = result['part1_debates'] + result['part2_debates']
            logger.info(f"✅ Total Debates: {result['total_debates']:,} (Part 1: {result['part1_debates']:,}, Part 2: {result['part2_debates']:,})")
            
            # Analyze recent sessions
            recent_sessions = sessions[:recent_sessions_count] if len(sessions) >= recent_sessions_count else sessions
            for session_info in recent_sessions:
                session_no = session_info['name']
                count = int(session_info['count'])
                result['recent_sessions'].append({
                    'session_no': session_no,
                    'debate_count': count
                })
            
            logger.info(f"✅ Official master data initialization complete")
            return result
            
        except Exception as e:
            logger.error(f"❌ Error in official initialization: {e}")
            result['status'] = 'ERROR'
            result['errors'].append(str(e))
            return result
    
    def initialize_complete_rs_master_data(
        self, 
        force_update: bool = False,
        verbatim_workers: int = 3,
        verbatim_recent_only: int = 5,
        official_recent_sessions: int = 10
    ) -> Dict:
        """
        Initialize BOTH verbatim and official RS debate master data
        
        Args:
            force_update: Force refresh even if data exists
            verbatim_workers: Parallel workers for verbatim
            verbatim_recent_only: If > 0, only last N sessions for verbatim
            official_recent_sessions: Recent sessions to analyze for official
        """
        result = {
            'status': 'SUCCESS',
            'verbatim': {},
            'official': {},
            'errors': []
        }
        
        try:
            logger.info("🏛️  Initializing COMPLETE RS Debates Master Data...")
            
            # Initialize verbatim debates
            logger.info("\n📝 Part 1: Verbatim Debates")
            verbatim_result = self.initialize_verbatim_master_data(
                force_update=force_update,
                max_workers=verbatim_workers,
                recent_sessions_only=verbatim_recent_only
            )
            result['verbatim'] = verbatim_result
            
            # Initialize official debates  
            logger.info("\n📚 Part 2: Official Debates")
            official_result = self.initialize_official_master_data(
                force_update=force_update,
                recent_sessions_count=official_recent_sessions
            )
            result['official'] = official_result
            
            # Aggregate errors
            result['errors'].extend(verbatim_result.get('errors', []))
            result['errors'].extend(official_result.get('errors', []))
            
            if verbatim_result['status'] == 'ERROR' or official_result['status'] == 'ERROR':
                result['status'] = 'PARTIAL'
            
            logger.info("✅ Complete RS debates master data initialization finished")
            return result
            
        except Exception as e:
            logger.error(f"❌ Error in complete RS initialization: {e}")
            result['status'] = 'ERROR'
            result['errors'].append(str(e))
            return result
