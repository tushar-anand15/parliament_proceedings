import requests
import logging
import time
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from django.utils import timezone
from django.db import transaction
from django.conf import settings

from .models import QuestionMasterData, LokSabha, Session

logger = logging.getLogger(__name__)


class QuestionMasterDataService:
    """
    Service for fetching and managing master questions metadata from sansad.in API
    
    This service handles the complete flow:
    1. Fetch Lok Sabha and Sessions metadata
    2. Fetch questions metadata for each session
    3. Store master data in database
    4. Provide data for PDF download service
    """
    
    def __init__(self):
        self.session = requests.Session()
        # Set headers to mimic browser requests
        self.session.headers.update({
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Connection': 'keep-alive',
            'Referer': 'https://sansad.in/ls/questions/questions-and-answers',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-origin',
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36',
            'sec-ch-ua': '"Chromium";v="140", "Not=A?Brand";v="24", "Brave";v="140"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"macOS"'
        })
    
    def fetch_lok_sabha_sessions(self) -> Dict:
        """
        Fetch all Lok Sabha and their sessions from the API
        
        Returns:
            Dict with lok_sabhas data and statistics
        """
        try:
            url = "https://sansad.in/api_ls/business/getAllLoksabhaAndSession?locale=en"
            
            logger.info(f"Fetching Lok Sabha sessions from: {url}")
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            
            if not isinstance(data, list):
                raise ValueError("Expected list response from API")
            
            # Store in database
            total_lok_sabhas = 0
            total_sessions = 0
            
            with transaction.atomic():
                for lok_sabha_data in data:
                    lok_sabha_number = str(lok_sabha_data.get('loksabha', ''))
                    sessions_data = lok_sabha_data.get('sessions', [])
                    
                    # Create or update LokSabha
                    lok_sabha, created = LokSabha.objects.get_or_create(
                        number=lok_sabha_number,
                        defaults={
                            'is_current': lok_sabha_number == '18'  # Current Lok Sabha
                        }
                    )
                    
                    if created:
                        total_lok_sabhas += 1
                        logger.info(f"Created Lok Sabha: {lok_sabha_number}")
                    
                    # Process sessions
                    for session_data in sessions_data:
                        session_number = str(session_data.get('sessionNo', ''))
                        session_period = session_data.get('sessionPeriod', [])
                        dates = session_data.get('dates', [])
                        
                        # Parse start and end dates from dates array
                        start_date = None
                        end_date = None
                        if dates:
                            try:
                                start_date = datetime.strptime(dates[0], '%d/%m/%Y').date()
                                end_date = datetime.strptime(dates[-1], '%d/%m/%Y').date()
                            except ValueError as e:
                                logger.warning(f"Failed to parse dates for LS{lok_sabha_number} Session{session_number}: {e}")
                        
                        session, session_created = Session.objects.get_or_create(
                            lok_sabha=lok_sabha,
                            session_number=session_number,
                            defaults={
                                'session_period': session_period,
                                'dates': dates,
                                'start_date': start_date,
                                'end_date': end_date,
                                'is_current': (lok_sabha_number == '18' and session_number == '5'),
                                'raw_api_data': session_data
                            }
                        )
                        
                        if session_created:
                            total_sessions += 1
            
            result = {
                'status': 'SUCCESS',
                'total_lok_sabhas_created': total_lok_sabhas,
                'total_sessions_created': total_sessions,
                'total_lok_sabhas_in_api': len(data),
                'total_sessions_in_api': sum(len(ls.get('sessions', [])) for ls in data),
                'message': f'Successfully processed {len(data)} Lok Sabhas with sessions'
            }
            
            logger.info(f"Lok Sabha sessions fetch completed: {result}")
            return result
            
        except Exception as e:
            logger.error(f"Failed to fetch Lok Sabha sessions: {e}")
            raise
    
    def fetch_questions_count_by_lok_sabha(self) -> Dict:
        """
        Fetch questions count by Lok Sabha from the browse API
        
        Returns:
            Dict with count data by Lok Sabha
        """
        try:
            url = "https://eparlib.sansad.in/restv3/field/browse?field=loksabhaNo&collectionId=3&start=0&rows=5000&order=desc&locale=en"
            
            logger.info(f"Fetching questions count by Lok Sabha from: {url}")
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            
            if data.get('statusCode') != '200':
                raise ValueError(f"API returned error: {data.get('message', 'Unknown error')}")
            
            records = data.get('records', [])
            count_data = {record['name']: int(record['count']) for record in records}
            
            result = {
                'status': 'SUCCESS',
                'total_lok_sabhas': len(records),
                'counts_by_lok_sabha': count_data,
                'total_questions_across_all': sum(count_data.values()),
                'message': f'Successfully fetched question counts for {len(records)} Lok Sabhas'
            }
            
            logger.info(f"Questions count fetch completed: {result}")
            return result
            
        except Exception as e:
            logger.error(f"Failed to fetch questions count: {e}")
            raise
    
    def fetch_questions_for_session(self, lok_sabha_number: str, session_number: str, 
                                  page_size: int = 10000, use_fallback: bool = True, timeout: int = 60) -> Dict:
        """
        Fetch all questions for a specific Lok Sabha session
        
        Args:
            lok_sabha_number: Lok Sabha number (e.g., '18')
            session_number: Session number (e.g., '5')
            page_size: Maximum records to fetch (default 10000 to get all)
            
        Returns:
            Dict with questions data and statistics
        """
        try:
            url = f"https://sansad.in/api_ls/question/qetFilteredQuestionsAns?loksabhaNo={lok_sabha_number}&sessionNumber={session_number}&pageNo=1&locale=en&pageSize={page_size}"
            
            logger.info(f"Fetching questions for LS{lok_sabha_number} Session{session_number} from: {url}")
            response = self.session.get(url, timeout=timeout)
            response.raise_for_status()
            
            data = response.json()
            
            if not isinstance(data, list) or not data:
                raise ValueError("Expected non-empty list response from API")
            
            questions_data = data[0].get('listOfQuestions', [])
            total_record_size = data[0].get('totalRecordSize', len(questions_data))
            
            # Get or create LokSabha and Session objects
            lok_sabha = LokSabha.objects.get(number=lok_sabha_number)
            session = Session.objects.get(lok_sabha=lok_sabha, session_number=session_number)
            
            # Store questions in database
            created_count = 0
            updated_count = 0
            
            with transaction.atomic():
                for q_data in questions_data:
                    question_number = str(q_data.get('quesNo', ''))
                    if not question_number:
                        continue
                    
                    # Parse date
                    question_date = None
                    date_str = q_data.get('date', '')
                    if date_str:
                        try:
                            question_date = datetime.strptime(date_str, '%d.%m.%Y').date()
                        except ValueError:
                            logger.warning(f"Failed to parse date '{date_str}' for question {question_number}")
                    
                    # Prepare master data with safe null handling
                    master_data = {
                        'question_number': question_number,
                        'subjects': q_data.get('subjects') or '',
                        'lok_sabha_number': lok_sabha_number,
                        'members': q_data.get('member') or [],
                        'ministry': q_data.get('ministry') or '',
                        'question_type': q_data.get('type') or 'STARRED',
                        'date': question_date,
                        'session_number': session_number,
                        'questions_file_path': q_data.get('questionsFilePath') or '',
                        'questions_file_path_hindi': q_data.get('questionsFilePathHindi') or '',
                        'question_text': q_data.get('questionText'),  # Allow None
                        'answer_text': q_data.get('answerText'),  # Allow None
                        'answer_text_hindi': q_data.get('answerTextHindi'),  # Allow None
                        'supplementary_type': q_data.get('supplementaryType') or False,
                        'supplementary_questions': q_data.get('supplementaryQuestionResDtoList') or [],
                        'lok_sabha': lok_sabha,
                        'session': session,
                        'raw_api_data': q_data,
                        'last_fetched': timezone.now()
                    }
                    
                    # Create or update master data
                    question_master, created = QuestionMasterData.objects.get_or_create(
                        question_number=question_number,
                        lok_sabha_number=lok_sabha_number,
                        session_number=session_number,
                        defaults=master_data
                    )
                    
                    if created:
                        created_count += 1
                    else:
                        # Update existing record
                        for key, value in master_data.items():
                            if key not in ['question_number', 'lok_sabha_number', 'session_number']:
                                setattr(question_master, key, value)
                        question_master.save()
                        updated_count += 1
            
            result = {
                'status': 'SUCCESS',
                'lok_sabha_number': lok_sabha_number,
                'session_number': session_number,
                'total_available': total_record_size,
                'fetched': len(questions_data),
                'created': created_count,
                'updated': updated_count,
                'message': f'Successfully processed {len(questions_data)} questions for LS{lok_sabha_number} Session{session_number}'
            }
            
            logger.info(f"Questions fetch completed: {result}")
            return result
            
        except LokSabha.DoesNotExist:
            raise ValueError(f"Lok Sabha {lok_sabha_number} not found. Please fetch Lok Sabha sessions first.")
        except Session.DoesNotExist:
            raise ValueError(f"Session {session_number} for Lok Sabha {lok_sabha_number} not found. Please fetch Lok Sabha sessions first.")
        except Exception as e:
            # Try fallback to legacy API if modern API fails
            if use_fallback and 'Server Error' in str(e):
                logger.info(f"Trying legacy API fallback for LS{lok_sabha_number} Session{session_number}...")
                try:
                    return self._fetch_questions_legacy_api(lok_sabha_number, session_number, page_size, timeout)
                except Exception as fallback_error:
                    logger.error(f"Both modern and legacy APIs failed for LS{lok_sabha_number} Session{session_number}")
                    logger.error(f"Modern API error: {e}")
                    logger.error(f"Legacy API error: {fallback_error}")
                    raise e  # Raise original error
            else:
                logger.error(f"Failed to fetch questions for LS{lok_sabha_number} Session{session_number}: {e}")
                raise
    
    def _fetch_questions_legacy_api(self, lok_sabha_number: str, session_number: str, page_size: int = 5000, timeout: int = 60) -> Dict:
        """
        Fetch questions using the legacy eparlib.sansad.in API
        """
        try:
            # Convert session number to Roman if it's numeric
            roman_session = self._convert_to_roman_session(session_number)
            
            # Format Lok Sabha number with leading zero for legacy API
            formatted_lok_sabha = lok_sabha_number.zfill(2)
            
            url = f"https://eparlib.sansad.in/restv3/fetch/all?collectionId=3&start=0&rows={page_size}&loksabhaNo={formatted_lok_sabha}&sessionNo={roman_session}"
            
            logger.info(f"Fetching questions from legacy API: {url}")
            response = self.session.get(url, timeout=timeout)
            response.raise_for_status()
            
            data = response.json()
            
            if data.get('statusCode') != '200':
                raise ValueError(f"Legacy API returned error: {data.get('message', 'Unknown error')}")
            
            questions_data = data.get('records', [])
            total_record_size = int(data.get('rowsCount', len(questions_data)))
            
            if not questions_data:
                raise ValueError(f"No questions found in legacy API for LS{lok_sabha_number} Session{session_number}")
            
            # Get or create LokSabha and Session objects
            lok_sabha = LokSabha.objects.get(number=lok_sabha_number)
            session = Session.objects.get(lok_sabha=lok_sabha, session_number=session_number)
            
            return self._store_questions_from_legacy_api(questions_data, total_record_size, lok_sabha, session, lok_sabha_number, session_number)
            
        except Exception as e:
            logger.error(f"Legacy API failed for LS{lok_sabha_number} Session{session_number}: {e}")
            raise
    
    def _convert_to_roman_session(self, session_number: str) -> str:
        """
        Convert numeric session to Roman numeral for legacy API
        """
        # If already Roman, return uppercase
        if session_number.lower() in ['i', 'ii', 'iii', 'iv', 'v', 'vi', 'vii', 'viii', 'ix', 'x', 'xi', 'xii', 'xiii', 'xiv', 'xv']:
            return session_number.upper()
        
        # Convert numeric to Roman
        roman_map = {
            '1': 'I', '2': 'II', '3': 'III', '4': 'IV', '5': 'V',
            '6': 'VI', '7': 'VII', '8': 'VIII', '9': 'IX', '10': 'X',
            '11': 'XI', '12': 'XII', '13': 'XIII', '14': 'XIV', '15': 'XV'
        }
        
        return roman_map.get(session_number, session_number.upper())
    
    def _transform_legacy_pdf_url(self, legacy_url: str) -> str:
        """
        Transform legacy eparlib.sansad.in PDF URLs to working sansad.in/getFile format
        
        Args:
            legacy_url: Original URL from legacy API
            
        Returns:
            Transformed URL that actually works
        """
        if not legacy_url:
            return ''
        
        # Check if it's already a legacy URL that needs transformation
        if 'eparlib.sansad.in/bitstream/' in legacy_url:
            # Transform: https://eparlib.sansad.in/bitstream/123456789/1090136/1/file.pdf
            # To:        https://sansad.in/getFile/bitstream/123456789/1090136/1/file.pdf?source=eparlib
            
            # Extract the path after /bitstream/
            bitstream_path = legacy_url.split('/bitstream/', 1)[1]
            
            # Construct the working URL
            working_url = f"https://sansad.in/getFile/bitstream/{bitstream_path}?source=eparlib"
            
            return working_url
        
        # If it's already a sansad.in URL or different format, return as-is
        return legacy_url
    
    def _store_questions_from_legacy_api(self, questions_data: List, total_record_size: int, 
                                       lok_sabha, session, lok_sabha_number: str, session_number: str) -> Dict:
        """
        Store questions from legacy API response
        """
        created_count = 0
        updated_count = 0
        
        with transaction.atomic():
            for q_data in questions_data:
                question_number = str(q_data.get('questionNo', ''))
                if not question_number:
                    continue
                
                # Parse date from legacy format (YYYY-MM-DD)
                question_date = None
                date_str = q_data.get('date', '')
                if date_str:
                    try:
                        question_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                    except ValueError:
                        logger.warning(f"Failed to parse legacy date '{date_str}' for question {question_number}")
                
                # Extract PDF URLs from files array and transform them
                files = q_data.get('files', [])
                pdf_url = self._transform_legacy_pdf_url(files[0]) if files else ''
                pdf_url_hindi = ''
                
                # Look for Hindi PDF in files
                for file_url in files:
                    if 'hindi' in file_url.lower():
                        pdf_url_hindi = self._transform_legacy_pdf_url(file_url)
                        break
                
                # Convert legacy question type
                question_type = q_data.get('questionType', 'Starred')
                if question_type.lower() == 'starred':
                    question_type = 'STARRED'
                elif question_type.lower() == 'unstarred':
                    question_type = 'UNSTARRED'
                else:
                    question_type = 'STARRED'  # Default
                
                # Prepare master data for legacy API
                master_data = {
                    'question_number': question_number,
                    'subjects': q_data.get('title') or '',
                    'lok_sabha_number': lok_sabha_number,
                    'members': q_data.get('members') or [],
                    'ministry': ', '.join(q_data.get('ministry', [])) if q_data.get('ministry') else '',
                    'question_type': question_type,
                    'date': question_date,
                    'session_number': session_number,
                    'questions_file_path': pdf_url,
                    'questions_file_path_hindi': pdf_url_hindi,
                    'question_text': None,  # Legacy API doesn't have question text
                    'answer_text': None,    # Legacy API doesn't have answer text
                    'answer_text_hindi': None,
                    'supplementary_type': False,
                    'supplementary_questions': [],
                    'lok_sabha': lok_sabha,
                    'session': session,
                    'raw_api_data': q_data,
                    'last_fetched': timezone.now()
                }
                
                # Create or update master data
                question_master, created = QuestionMasterData.objects.get_or_create(
                    question_number=question_number,
                    lok_sabha_number=lok_sabha_number,
                    session_number=session_number,
                    defaults=master_data
                )
                
                if created:
                    created_count += 1
                else:
                    # Update existing record
                    for key, value in master_data.items():
                        if key not in ['question_number', 'lok_sabha_number', 'session_number']:
                            setattr(question_master, key, value)
                    question_master.save()
                    updated_count += 1
        
        result = {
            'status': 'SUCCESS',
            'api_source': 'legacy',
            'lok_sabha_number': lok_sabha_number,
            'session_number': session_number,
            'total_available': total_record_size,
            'fetched': len(questions_data),
            'created': created_count,
            'updated': updated_count,
            'message': f'Successfully processed {len(questions_data)} questions for LS{lok_sabha_number} Session{session_number} via legacy API'
        }
        
        logger.info(f"Legacy API questions fetch completed: {result}")
        return result
    
    def initialize_master_data(self, force_update: bool = False) -> Dict:
        """
        Initialize master data - fetch sessions and all questions once
        
        Args:
            force_update: If True, refetch data even if it exists
            
        Returns:
            Dict with initialization results
        """
        try:
            print(f"🏛️ Initializing Parliament Questions Master Data...")
            
            # Check if we already have data
            existing_sessions = Session.objects.count()
            existing_questions = QuestionMasterData.objects.count()
            
            if not force_update and existing_sessions > 0 and existing_questions > 0:
                print(f"📊 Master data already exists: {existing_sessions} sessions, {existing_questions} questions")
                print(f"💡 Use force_update=True to refresh from server")
                
                return {
                    'status': 'ALREADY_EXISTS',
                    'sessions_count': existing_sessions,
                    'questions_count': existing_questions,
                    'message': 'Master data already initialized. Use force_update=True to refresh.'
                }
            
            print(f"🚀 {'Updating' if force_update else 'Fetching'} master data from sansad.in API...")
            
            # Step 1: Fetch and store all Lok Sabha sessions
            print(f"📡 Step 1: Fetching Lok Sabha sessions...")
            sessions_result = self.fetch_lok_sabha_sessions()
            
            # Step 2: Fetch questions for all sessions
            print(f"📡 Step 2: Fetching questions for all sessions...")
            questions_result = self.fetch_all_questions_for_all_sessions()
            
            result = {
                'status': 'SUCCESS',
                'sessions_result': sessions_result,
                'questions_result': questions_result,
                'total_sessions': Session.objects.count(),
                'total_questions': QuestionMasterData.objects.count(),
                'message': f'Master data initialized successfully'
            }
            
            print(f"✅ Master data initialization completed!")
            print(f"   📊 Sessions: {result['total_sessions']}")
            print(f"   📊 Questions: {result['total_questions']}")
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to initialize master data: {e}")
            raise
    
    def fetch_all_questions_for_all_sessions(self) -> Dict:
        """
        Fetch questions for ALL sessions in the database
        
        Returns:
            Dict with overall statistics
        """
        try:
            # Get all sessions from database
            all_sessions = Session.objects.all().order_by('lok_sabha__number', 'session_number')
            
            total_sessions = all_sessions.count()
            processed_sessions = 0
            total_created = 0
            total_updated = 0
            errors = []
            
            print(f"📊 Processing {total_sessions} sessions for questions...")
            
            # Process sessions in batches to avoid overwhelming the API
            batch_size = 5
            current_batch = []
            
            for session in all_sessions:
                current_batch.append(session)
                
                if len(current_batch) >= batch_size:
                    batch_result = self._process_session_batch(current_batch)
                    processed_sessions += batch_result['processed']
                    total_created += batch_result['created']
                    total_updated += batch_result['updated']
                    errors.extend(batch_result['errors'])
                    current_batch = []
                    
                    # Brief pause between batches to be respectful to the API
                    time.sleep(2)
            
            # Process remaining sessions
            if current_batch:
                batch_result = self._process_session_batch(current_batch)
                processed_sessions += batch_result['processed']
                total_created += batch_result['created']
                total_updated += batch_result['updated']
                errors.extend(batch_result['errors'])
            
            result = {
                'status': 'SUCCESS' if not errors else 'PARTIAL_SUCCESS',
                'total_sessions': total_sessions,
                'processed_sessions': processed_sessions,
                'total_created': total_created,
                'total_updated': total_updated,
                'errors': errors,
                'message': f'Questions fetch completed: {processed_sessions}/{total_sessions} sessions processed'
            }
            
            logger.info(f"All questions fetch completed: {result}")
            return result
            
        except Exception as e:
            logger.error(f"Failed to fetch all questions: {e}")
            raise
    
    def _process_session_batch(self, sessions: List) -> Dict:
        """
        Process a batch of sessions for questions
        """
        batch_result = {
            'processed': 0,
            'created': 0,
            'updated': 0,
            'errors': []
        }
        
        for session in sessions:
            try:
                print(f"   Processing LS{session.lok_sabha.number} Session{session.session_number}...")
                result = self.fetch_questions_for_session(
                    session.lok_sabha.number,
                    session.session_number,
                    page_size=10000  # Get all questions
                )
                
                batch_result['processed'] += 1
                batch_result['created'] += result.get('created', 0)
                batch_result['updated'] += result.get('updated', 0)
                
                print(f"      ✅ +{result.get('created', 0)} created, +{result.get('updated', 0)} updated")
                
            except Exception as e:
                error_msg = f"LS{session.lok_sabha.number} Session{session.session_number}: {str(e)}"
                batch_result['errors'].append(error_msg)
                logger.error(f"Failed to process session: {error_msg}")
                print(f"      ❌ {error_msg}")
        
        return batch_result
    
    def fetch_all_questions(self, lok_sabha_numbers: Optional[List[str]] = None,
                           max_sessions_per_lok_sabha: Optional[int] = None) -> Dict:
        """
        Fetch questions for all sessions or specified Lok Sabhas
        
        Args:
            lok_sabha_numbers: List of Lok Sabha numbers to process (None for all)
            max_sessions_per_lok_sabha: Limit sessions per Lok Sabha (None for all)
            
        Returns:
            Dict with overall statistics
        """
        try:
            # Get sessions to process
            sessions_query = Session.objects.all()
            
            if lok_sabha_numbers:
                sessions_query = sessions_query.filter(lok_sabha__number__in=lok_sabha_numbers)
            
            if max_sessions_per_lok_sabha:
                # Get latest sessions per Lok Sabha
                sessions_query = sessions_query.order_by('lok_sabha__number', '-session_number')
            
            sessions = list(sessions_query)
            
            # Group by Lok Sabha if limiting sessions
            if max_sessions_per_lok_sabha:
                sessions_by_lok_sabha = {}
                for session in sessions:
                    lok_sabha_num = session.lok_sabha.number
                    if lok_sabha_num not in sessions_by_lok_sabha:
                        sessions_by_lok_sabha[lok_sabha_num] = []
                    if len(sessions_by_lok_sabha[lok_sabha_num]) < max_sessions_per_lok_sabha:
                        sessions_by_lok_sabha[lok_sabha_num].append(session)
                
                sessions = [s for sessions_list in sessions_by_lok_sabha.values() for s in sessions_list]
            
            total_sessions = len(sessions)
            processed_sessions = 0
            total_created = 0
            total_updated = 0
            errors = []
            
            logger.info(f"Starting bulk fetch for {total_sessions} sessions")
            
            for session in sessions:
                try:
                    result = self.fetch_questions_for_session(
                        session.lok_sabha.number,
                        session.session_number
                    )
                    
                    processed_sessions += 1
                    total_created += result['created']
                    total_updated += result['updated']
                    
                    logger.info(f"Processed session {processed_sessions}/{total_sessions}: LS{session.lok_sabha.number} Session{session.session_number}")
                    
                except Exception as e:
                    error_msg = f"LS{session.lok_sabha.number} Session{session.session_number}: {str(e)}"
                    errors.append(error_msg)
                    logger.error(f"Failed to process session: {error_msg}")
            
            result = {
                'status': 'SUCCESS' if not errors else 'PARTIAL_SUCCESS',
                'total_sessions': total_sessions,
                'processed_sessions': processed_sessions,
                'total_created': total_created,
                'total_updated': total_updated,
                'errors': errors,
                'message': f'Bulk fetch completed: {processed_sessions}/{total_sessions} sessions processed'
            }
            
            logger.info(f"Bulk questions fetch completed: {result}")
            return result
            
        except Exception as e:
            logger.error(f"Failed bulk questions fetch: {e}")
            raise
    
    def get_master_data_statistics(self) -> Dict:
        """
        Get statistics about master questions data
        
        Returns:
            Dict with statistics
        """
        try:
            total_questions = QuestionMasterData.objects.count()
            by_lok_sabha = {}
            by_question_type = {}
            
            # Group by Lok Sabha
            for lok_sabha in LokSabha.objects.all():
                count = QuestionMasterData.objects.filter(lok_sabha=lok_sabha).count()
                by_lok_sabha[f"LS{lok_sabha.number}"] = count
            
            # Group by question type
            for question_type, _ in QuestionMasterData.QUESTION_TYPES:
                count = QuestionMasterData.objects.filter(question_type=question_type).count()
                by_question_type[question_type] = count
            
            # Processing status
            processed_count = QuestionMasterData.objects.filter(is_processed=True).count()
            unprocessed_count = total_questions - processed_count
            
            # Questions with PDF URLs
            with_pdf_count = QuestionMasterData.objects.exclude(questions_file_path='').count()
            without_pdf_count = total_questions - with_pdf_count
            
            return {
                'total_questions': total_questions,
                'by_lok_sabha': by_lok_sabha,
                'by_question_type': by_question_type,
                'processing_status': {
                    'processed': processed_count,
                    'unprocessed': unprocessed_count
                },
                'pdf_availability': {
                    'with_pdf': with_pdf_count,
                    'without_pdf': without_pdf_count
                },
                'last_updated': timezone.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Failed to get master data statistics: {e}")
            raise
    
    def get_questions_for_download(self, lok_sabha_number: Optional[str] = None,
                                 session_number: Optional[str] = None,
                                 question_type: Optional[str] = None,
                                 limit: Optional[int] = None) -> List[QuestionMasterData]:
        """
        Get questions ready for PDF download
        
        Args:
            lok_sabha_number: Filter by Lok Sabha
            session_number: Filter by session
            question_type: Filter by question type
            limit: Limit number of results
            
        Returns:
            List of QuestionMasterData objects with PDF URLs
        """
        try:
            queryset = QuestionMasterData.objects.exclude(questions_file_path='')
            
            if lok_sabha_number:
                queryset = queryset.filter(lok_sabha_number=lok_sabha_number)
            
            if session_number:
                queryset = queryset.filter(session_number=session_number)
            
            if question_type:
                queryset = queryset.filter(question_type=question_type)
            
            queryset = queryset.order_by('-date', '-question_number')
            
            if limit:
                queryset = queryset[:limit]
            
            return list(queryset)
            
        except Exception as e:
            logger.error(f"Failed to get questions for download: {e}")
            raise
    
    # Removed get_random_questions_for_session - moved to test_celery_integration.py
    
    def get_session_summary(self, lok_sabha_number: str, session_number: str) -> Dict:
        """
        Get summary statistics for a specific session
        
        Args:
            lok_sabha_number: Lok Sabha number
            session_number: Session number
            
        Returns:
            Dict with session statistics
        """
        try:
            # Get session object
            session = Session.objects.get(
                lok_sabha__number=lok_sabha_number,
                session_number=session_number
            )
            
            # Get questions for this session
            questions_query = QuestionMasterData.objects.filter(
                lok_sabha_number=lok_sabha_number,
                session_number=session_number
            )
            
            total_questions = questions_query.count()
            questions_with_pdf = questions_query.exclude(questions_file_path='').count()
            
            # Group by question type
            by_type = {}
            for question_type, _ in QuestionMasterData.QUESTION_TYPES:
                count = questions_query.filter(question_type=question_type).count()
                if count > 0:
                    by_type[question_type] = count
            
            # Get ministries involved
            ministries = list(questions_query.exclude(ministry='').values_list('ministry', flat=True).distinct())
            
            return {
                'lok_sabha_number': lok_sabha_number,
                'session_number': session_number,
                'session_dates': session.dates,
                'session_period': session.session_period,
                'total_questions': total_questions,
                'questions_with_pdf': questions_with_pdf,
                'questions_by_type': by_type,
                'ministries_count': len(ministries),
                'top_ministries': ministries[:10],  # Top 10 ministries
                'data_completeness': {
                    'has_pdf_urls': (questions_with_pdf / max(total_questions, 1)) * 100,
                    'ready_for_download': questions_with_pdf
                }
            }
            
        except Session.DoesNotExist:
            raise ValueError(f"Session LS{lok_sabha_number} Session{session_number} not found in database")
        except Exception as e:
            logger.error(f"Failed to get session summary: {e}")
            raise
    
    def list_available_sessions(self) -> List[Dict]:
        """
        List all available sessions with question counts
        
        Returns:
            List of session summaries
        """
        try:
            sessions = Session.objects.all().order_by('lok_sabha__number', 'session_number')
            
            session_list = []
            for session in sessions:
                # Get question count for this session
                question_count = QuestionMasterData.objects.filter(
                    lok_sabha_number=session.lok_sabha.number,
                    session_number=session.session_number
                ).count()
                
                questions_with_pdf = QuestionMasterData.objects.filter(
                    lok_sabha_number=session.lok_sabha.number,
                    session_number=session.session_number
                ).exclude(questions_file_path='').count()
                
                session_list.append({
                    'lok_sabha_number': session.lok_sabha.number,
                    'session_number': session.session_number,
                    'is_current': session.is_current,
                    'start_date': session.start_date.isoformat() if session.start_date else None,
                    'end_date': session.end_date.isoformat() if session.end_date else None,
                    'total_questions': question_count,
                    'questions_with_pdf': questions_with_pdf,
                    'ready_for_testing': questions_with_pdf > 0
                })
            
            return session_list
            
        except Exception as e:
            logger.error(f"Failed to list available sessions: {e}")
            raise
