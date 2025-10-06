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

from .models import DebateMasterData
from services.questions.models import LokSabha, Session, ParliamentInstitution

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
        max_workers: int = 10,
        recent_sessions_only: int = 0,
        batch_size: int = 10
    ) -> Dict:
        """
        Initialize RS verbatim debate master data - STORES ALL INDIVIDUAL DEBATES WITH PDF URLS
        
        Args:
            force_update: Force refresh even if data exists
            max_workers: Number of parallel workers (default: 10)
            recent_sessions_only: If > 0, only fetch N recent sessions. If 0, fetch ALL (default: 0 = ALL)
            batch_size: Number of sessions to process in each batch (default: 10)
        """
        result = {
            'status': 'SUCCESS',
            'sessions_processed': 0,
            'dates_processed': 0,
            'debates_discovered': 0,
            'master_records_created': 0,
            'master_records_updated': 0,
            'errors': []
        }
        
        try:
            logger.info("🏛️  Initializing RS Verbatim Debates Master Data...")
            
            # Get or create RS institution
            rs_institution, _ = ParliamentInstitution.objects.get_or_create(
                name='rajya_sabha',
                defaults={
                    'full_name': 'Rajya Sabha',
                    'description': 'Upper House of Parliament of India',
                    'is_active': True
                }
            )
            
            # Get or create RS placeholder in LokSabha model
            rs_lok_sabha, _ = LokSabha.objects.get_or_create(
                number='RS',
                defaults={'is_current': True}
            )
            
            # Step 1: Get all sessions
            sessions = self.fetch_verbatim_rs_sessions()
            
            if not sessions:
                result['status'] = 'ERROR'
                result['errors'].append('No sessions fetched')
                return result
            
            # Filter to recent sessions if specified (0 = ALL)
            if recent_sessions_only > 0:
                sessions = sessions[-recent_sessions_only:]
                logger.info(f"📅 Processing last {len(sessions)} sessions only")
            else:
                logger.info(f"📅 Processing ALL {len(sessions)} available sessions")
            
            # Step 2: Process each session and STORE ALL INDIVIDUAL DEBATE METADATA
            def process_session(session_no: int) -> Tuple[int, int, int, bool]:
                """Process a single session, return (dates_count, debates_count, errors_count, created)"""
                dates_count = 0
                debates_count = 0
                errors_count = 0
                available_dates = []
                all_debates_data = []
                
                try:
                    dates = self.fetch_verbatim_session_dates(session_no)
                    
                    for i, date_obj in enumerate(dates, 1):
                        sitting_date = date_obj.get('SittingDate', '')
                        date_str = self.convert_iso_to_dd_mm_yyyy(sitting_date)
                        
                        if not date_str:
                            continue
                        
                        try:
                            debates = self.fetch_verbatim_debates(session_no, date_str)
                            dates_count += 1
                            debates_count += len(debates)
                            available_dates.append(date_str)
                            
                            # Show progress every 5 dates
                            if i % 5 == 0 or i == len(dates):
                                logger.info(f"   📅 Session {session_no}: Processed {i}/{len(dates)} dates, {debates_count} debates")
                            
                            # STORE ALL INDIVIDUAL DEBATE METADATA
                            for debate in debates:
                                all_debates_data.append({
                                    'id': debate.get('Id', ''),
                                    'session': debate.get('session', ''),
                                    'date': date_str,
                                    'time_slot': debate.get('Time', '') or debate.get('Time_H', ''),
                                    'pdf_url': debate.get('FileUrl', ''),
                                    'file_name': debate.get('Name', ''),
                                    'file_type': debate.get('FileType', ''),
                                    'file_location': debate.get('FileLocation', ''),
                                    'file_size': debate.get('FileSize', 0),
                                    'language': debate.get('Language', 'Verbatim'),
                                    'subject': debate.get('Subject', ''),
                                    'section': debate.get('Section', ''),
                                    'sub_section': debate.get('SubSection', ''),
                                    'is_published': debate.get('isPublished', False),
                                    'is_approved': debate.get('isApproved', False),
                                    'published_on': debate.get('PublishedOn', ''),
                                })
                        except Exception as e:
                            logger.error(f"Error fetching debates for {session_no}/{date_str}: {e}")
                            errors_count += 1
                    
                    # WRITE TO DATABASE
                    if available_dates:
                        session_obj, _ = Session.objects.get_or_create(
                            lok_sabha=rs_lok_sabha,
                            session_number=str(session_no),
                            defaults={'session_period': [], 'dates': available_dates, 'is_current': session_no == 268}
                        )
                        
                        master_data = {
                            'parent_institution': rs_institution,
                            'rajya_sabha_number': 'RS',
                            'available_dates': available_dates,
                            'total_debate_days': dates_count,
                            'debates_discovered': debates_count,
                            'api_source': 'rsdoc.nic.in',
                            'is_complete': True,
                            'last_discovery_attempt': timezone.now(),
                            'discovery_success': True,
                            'lok_sabha': rs_lok_sabha,
                            'session': session_obj,
                            'last_fetched': timezone.now(),
                            'raw_api_data': {
                                'all_debates_data': all_debates_data,
                                'total_debates': debates_count,
                                'source': 'verbatim'
                            }
                        }
                        
                        # Check if record exists and force_update is False
                        if not force_update:
                            existing_record = DebateMasterData.objects.filter(
                                parent_institution=rs_institution,
                                lok_sabha_number='RS',
                                session_number=str(session_no)
                            ).first()
                            
                            if existing_record:
                                logger.info(f"⏭️  Session {session_no} already exists, skipping (use --force to update)")
                                return (dates_count, debates_count, errors_count, False)
                        
                        debate_master, created = DebateMasterData.objects.update_or_create(
                            parent_institution=rs_institution,
                            lok_sabha_number='RS',
                            session_number=str(session_no),
                            defaults=master_data
                        )
                        return (dates_count, debates_count, errors_count, created)
                    
                except Exception as e:
                    logger.error(f"Error processing session {session_no}: {e}")
                    errors_count += 1
                
                return (dates_count, debates_count, errors_count, False)
            
            # Process sessions in batches to prevent memory issues
            total_sessions = len(sessions)
            # Use provided batch_size or default to 10 if too many sessions
            if total_sessions > 20:
                effective_batch_size = batch_size
            else:
                effective_batch_size = total_sessions
                
            logger.info(f"🚀 Starting verbatim processing: {total_sessions} sessions in batches of {effective_batch_size} with {max_workers} workers")
            
            # Split sessions into batches
            session_batches = [sessions[i:i + effective_batch_size] for i in range(0, total_sessions, effective_batch_size)]
            
            for batch_num, session_batch in enumerate(session_batches, 1):
                logger.info(f"📦 Processing batch {batch_num}/{len(session_batches)}: {len(session_batch)} sessions")
                batch_start_time = time.time()
                
                try:
                    with ThreadPoolExecutor(max_workers=max_workers) as executor:
                        futures = {
                            executor.submit(process_session, session_no): session_no 
                            for session_no in session_batch
                        }
                        
                        for future in as_completed(futures):
                            session_no = futures[future]
                            try:
                                dates_count, debates_count, errors_count, created = future.result()
                                result['sessions_processed'] += 1
                                result['dates_processed'] += dates_count
                                result['debates_discovered'] += debates_count
                                if created:
                                    result['master_records_created'] += 1
                                else:
                                    result['master_records_updated'] += 1
                                
                                if errors_count > 0:
                                    result['errors'].append(f"Session {session_no}: {errors_count} errors")
                                
                                # Show progress every session
                                sessions_processed = result.get('sessions_processed', 0)
                                progress = (sessions_processed / total_sessions) * 100
                                logger.info(f"📊 Verbatim Progress: {sessions_processed}/{total_sessions} sessions ({progress:.1f}%) - Session {session_no}: {dates_count} dates, {debates_count} debates")
                            except Exception as e:
                                logger.error(f"❌ Error processing session {session_no}: {e}")
                                result['errors'].append(f"Session {session_no}: {str(e)}")
                    
                    batch_duration = time.time() - batch_start_time
                    logger.info(f"✅ Batch {batch_num}/{len(session_batches)} completed in {batch_duration:.1f}s")
                    
                    # Add a small delay between batches to prevent overwhelming the API
                    if batch_num < len(session_batches):
                        delay = random.uniform(1, 3)
                        logger.info(f"⏳ Waiting {delay:.1f}s before next batch...")
                        time.sleep(delay)
                        
                except Exception as e:
                    logger.error(f"❌ Error processing batch {batch_num}: {e}")
                    result['errors'].append(f"Batch {batch_num}: {str(e)}")
                    continue
            
            logger.info(f"✅ Verbatim master data initialization complete")
            logger.info(f"   Records: {result['master_records_created']} created, {result['master_records_updated']} updated")
            return result
            
        except Exception as e:
            logger.error(f"❌ Error in verbatim initialization: {e}")
            result['status'] = 'ERROR'
            result['errors'].append(str(e))
            return result
    
    def initialize_official_master_data(
        self, 
        force_update: bool = False,
        recent_sessions_count: int = 0,
        batch_size: int = 5
    ) -> Dict:
        """
        Initialize RS official debate master data - STORES ALL INDIVIDUAL DEBATES WITH METADATA
        
        Args:
            force_update: Force refresh even if data exists
            recent_sessions_count: If > 0, process N sessions. If 0, process ALL (default: 0 = ALL)
            batch_size: Number of sessions to process in each batch (default: 5)
        """
        result = {
            'status': 'SUCCESS',
            'years_available': 0,
            'sessions_available': 0,
            'total_debates': 0,
            'part1_debates': 0,
            'part2_debates': 0,
            'recent_sessions': [],
            'sessions_processed': 0,
            'master_records_created': 0,
            'master_records_updated': 0,
            'errors': []
        }
        
        try:
            logger.info("📚 Initializing RS Official Debates Master Data...")
            
            # Get or create RS institution
            rs_institution, _ = ParliamentInstitution.objects.get_or_create(
                name='rajya_sabha',
                defaults={'full_name': 'Rajya Sabha', 'is_active': True}
            )
            rs_lok_sabha, _ = LokSabha.objects.get_or_create(number='RS', defaults={'is_current': True})
            
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
            
            # Process sessions (0 = ALL sessions)
            sessions_to_process = sessions if recent_sessions_count == 0 else sessions[:recent_sessions_count]
            total_sessions = len(sessions_to_process)
            
            # Use provided batch_size or default to 5 if too many sessions
            if total_sessions > 10:
                effective_batch_size = batch_size
            else:
                effective_batch_size = total_sessions
                
            logger.info(f"🚀 Starting official processing: {total_sessions} sessions in batches of {effective_batch_size}")
            logger.info(f"📅 Processing {total_sessions} sessions")
            
            # Split sessions into batches
            session_batches = [sessions_to_process[i:i + effective_batch_size] for i in range(0, total_sessions, effective_batch_size)]
            
            for batch_num, session_batch in enumerate(session_batches, 1):
                logger.info(f"📦 Processing official batch {batch_num}/{len(session_batches)}: {len(session_batch)} sessions")
                batch_start_time = time.time()
                
                try:
                    for i, session_info in enumerate(session_batch, 1):
                        session_no = session_info['name']
                        count = int(session_info['count'])
                        result['recent_sessions'].append({'session_no': session_no, 'debate_count': count})
                        
                        # Process this session
                        result['sessions_processed'] += 1
                        
                        # Show progress
                        sessions_processed = result.get('sessions_processed', 0)
                        progress = (sessions_processed / total_sessions) * 100
                        logger.info(f"📊 Official Progress: {sessions_processed}/{total_sessions} sessions ({progress:.1f}%) - Session {session_no}: {count:,} debates")
                        
                        # FETCH ALL debates metadata with pagination for this session
                        all_debates_data = []
                        try:
                            fetch_batch_size = 500
                            total_fetched = 0
                            
                            while total_fetched < count:
                                batch_response = self.fetch_official_debates(start=total_fetched, rows=fetch_batch_size, session_no=int(session_no))
                                batch_debates = batch_response.get('records', [])
                            
                                if not batch_debates:
                                    break
                                
                                for debate in batch_debates:
                                    all_debates_data.append({
                                        'type': debate.get('type', ''),
                                        'date': debate.get('date', ''),
                                        'title': debate.get('title', ''),
                                        'debate_title_subject': debate.get('debateTitleSubject', ''),
                                        'pdf_url': debate.get('files', '') or debate.get('filepath', ''),
                                        'question_no': debate.get('questionNo', ''),
                                        'question_type': debate.get('questionType', ''),
                                        'questioner_name': debate.get('questionerName', ''),
                                        'minister_name': debate.get('ministerName', ''),
                                        'ministry': debate.get('ministry', ''),
                                        'session': debate.get('sessionNo', ''),
                                        'year': debate.get('year', ''),
                                        'page_no': debate.get('pageNoFromTo', ''),
                                        'handle': debate.get('handle', ''),
                                        'resource_id': debate.get('resourceId', ''),
                                    })
                                
                                total_fetched += len(batch_debates)
                                
                                # Show progress every 500 debates
                                if total_fetched % 500 == 0 or total_fetched >= count:
                                    logger.info(f"   📈 Session {session_no}: Fetched {total_fetched:,}/{count:,} debates ({total_fetched/count*100:.1f}%)")
                                
                                if len(batch_debates) < fetch_batch_size:
                                    break
                        
                            logger.info(f"✅ Session {session_no}: Fetched ALL {len(all_debates_data)}/{count} debates")
                            
                        except Exception as e:
                            logger.error(f"❌ Session {session_no}: {e}")
                            all_debates_data = []
                        
                        # WRITE TO DATABASE
                        logger.info(f"💾 Writing session {session_no} to database...")
                        try:
                            session_obj, _ = Session.objects.get_or_create(lok_sabha=rs_lok_sabha, session_number=str(session_no), defaults={'session_period': [], 'dates': []})
                            
                            master_data = {
                                'parent_institution': rs_institution,
                                'rajya_sabha_number': 'RS',
                                'total_debate_days': 0,
                                'debates_discovered': count,
                                'api_source': 'rsdebate.nic.in',
                                'is_complete': True,
                                'last_discovery_attempt': timezone.now(),
                                'lok_sabha': rs_lok_sabha,
                                'session': session_obj,
                                'last_fetched': timezone.now(),
                                'raw_api_data': {
                                    'all_debates_data': all_debates_data,
                                    'total_available': count,
                                    'fetched_count': len(all_debates_data),
                                    'source': 'official_debates'
                                }
                            }
                            
                            # Check if record exists and force_update is False
                            if not force_update:
                                existing_record = DebateMasterData.objects.filter(
                                    parent_institution=rs_institution,
                                    lok_sabha_number='RS',
                                    session_number=str(session_no)
                                ).first()
                                
                                if existing_record:
                                    logger.info(f"⏭️  Session {session_no} already exists, skipping (use --force to update)")
                                    continue
                            
                            debate_master, created = DebateMasterData.objects.update_or_create(
                                parent_institution=rs_institution,
                                lok_sabha_number='RS',
                                session_number=str(session_no),
                                defaults=master_data
                            )
                            
                            if created:
                                result['master_records_created'] += 1
                            else:
                                result['master_records_updated'] += 1
                            
                            logger.info(f"✅ Session {session_no} stored: {len(all_debates_data)} debates in database")
                            
                        except Exception as e:
                            logger.error(f"Error storing session {session_no}: {e}")
                            result['errors'].append(f"Session {session_no}: {str(e)}")
                    
                    batch_duration = time.time() - batch_start_time
                    logger.info(f"✅ Official batch {batch_num}/{len(session_batches)} completed in {batch_duration:.1f}s")
                    
                    # Add a small delay between batches to prevent overwhelming the API
                    if batch_num < len(session_batches):
                        delay = random.uniform(2, 5)
                        logger.info(f"⏳ Waiting {delay:.1f}s before next batch...")
                        time.sleep(delay)
                        
                except Exception as e:
                    logger.error(f"❌ Error processing official batch {batch_num}: {e}")
                    result['errors'].append(f"Official batch {batch_num}: {str(e)}")
                    continue
            
            logger.info(f"✅ Official master data initialization complete")
            logger.info(f"   Records: {result['master_records_created']} created, {result['master_records_updated']} updated")
            return result
            
        except Exception as e:
            logger.error(f"❌ Error in official initialization: {e}")
            result['status'] = 'ERROR'
            result['errors'].append(str(e))
            return result
    
    def initialize_complete_rs_master_data(
        self, 
        force_update: bool = False,
        verbatim_workers: int = 10,
        verbatim_recent_only: int = 0,
        official_recent_sessions: int = 0,
        verbatim_batch_size: int = 10,
        official_batch_size: int = 5
    ) -> Dict:
        """
        Initialize BOTH verbatim and official RS debate master data - COMPREHENSIVE
        
        Args:
            force_update: Force refresh even if data exists
            verbatim_workers: Parallel workers (default: 10)
            verbatim_recent_only: If 0, process ALL sessions (default: 0 = ALL)
            official_recent_sessions: If 0, process ALL sessions (default: 0 = ALL)
            verbatim_batch_size: Number of sessions per batch for verbatim (default: 10)
            official_batch_size: Number of sessions per batch for official (default: 5)
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
                recent_sessions_only=verbatim_recent_only,
                batch_size=verbatim_batch_size
            )
            result['verbatim'] = verbatim_result
            
            # Initialize official debates  
            logger.info("\n📚 Part 2: Official Debates")
            official_result = self.initialize_official_master_data(
                force_update=force_update,
                recent_sessions_count=official_recent_sessions,
                batch_size=official_batch_size
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
