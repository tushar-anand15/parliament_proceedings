import requests
import logging
import time
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from django.utils import timezone
from django.db import transaction
from django.conf import settings

from .models import QuestionMasterData, LokSabha, Session, ParliamentInstitution

logger = logging.getLogger(__name__)


class RajyaSabhaMasterDataService:
    """
    Service for fetching and managing Rajya Sabha master questions metadata
    
    This service handles the complete RS flow:
    1. Fetch RS Sessions metadata
    2. Fetch questions metadata for each RS session
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
            'Origin': 'https://sansad.in',
            'Referer': 'https://sansad.in/rs/questions/questions-and-answers',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'cross-site',
            'Sec-GPC': '1',
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36',
            'sec-ch-ua': '"Chromium";v="140", "Not=A?Brand";v="24", "Brave";v="140"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"macOS"'
        })
    
    def fetch_available_question_sessions(self) -> List[str]:
        """
        Fetch available sessions that have questions data from rsdoc.nic.in
        
        Returns:
            List of session numbers that have questions
        """
        try:
            url = "https://rsdoc.nic.in/question/Get_sessionforQuestionSearch"
            
            logger.info(f"Fetching available RS question sessions from: {url}")
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            
            if not isinstance(data, list):
                raise ValueError("Expected list response from RS questions sessions API")
            
            # Extract session numbers
            available_sessions = [str(item.get('ssn_no', '')) for item in data if item.get('ssn_no')]
            
            logger.info(f"Found {len(available_sessions)} sessions with questions data: {min(available_sessions)}-{max(available_sessions)}")
            return available_sessions
            
        except Exception as e:
            logger.error(f"Failed to fetch available RS question sessions: {e}")
            # Fallback to known range if API fails
            return [str(i) for i in range(174, 269)]  # 174-268 based on our testing
    
    def fetch_rajya_sabha_sessions(self) -> Dict:
        """
        Fetch all Rajya Sabha sessions from the API and cross-reference with questions availability
        
        Returns:
            Dict with sessions data and statistics
        """
        try:
            # Get session dates from main API
            url = "https://sansad.in/api_rs/business/sessionDates"
            
            logger.info(f"Fetching Rajya Sabha sessions from: {url}")
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            
            if not isinstance(data, list):
                raise ValueError("Expected list response from RS API")
            
            # Get available sessions that have questions
            available_question_sessions = self.fetch_available_question_sessions()
            logger.info(f"Sessions with questions available: {len(available_question_sessions)} sessions")
            
            # Get or create ParliamentInstitution for Rajya Sabha
            rs_institution, created = ParliamentInstitution.objects.get_or_create(
                name='rajya_sabha',
                defaults={
                    'full_name': 'Rajya Sabha',
                    'description': 'Upper House of Parliament of India',
                    'is_active': True
                }
            )
            
            # Store in database - RS doesn't have Lok Sabha numbers, so we'll use a placeholder
            total_sessions = 0
            
            with transaction.atomic():
                # Create a placeholder "Rajya Sabha" record (similar to LokSabha model)
                rajya_sabha, created = LokSabha.objects.get_or_create(
                    number='RS',  # Use 'RS' as identifier for Rajya Sabha
                    defaults={
                        'is_current': True  # RS is ongoing
                    }
                )
                
                for session_data in data:
                    session_number = str(session_data.get('session', ''))
                    sitting_dates = session_data.get('sittingDates', [])
                    
                    if not session_number:
                        continue
                    
                    # Parse start and end dates from sitting dates
                    start_date = None
                    end_date = None
                    if sitting_dates:
                        try:
                            # Convert DD/MM/YYYY to date objects and find min/max
                            parsed_dates = []
                            for date_str in sitting_dates:
                                parsed_date = datetime.strptime(date_str, '%d/%m/%Y').date()
                                parsed_dates.append(parsed_date)
                            
                            if parsed_dates:
                                start_date = min(parsed_dates)
                                end_date = max(parsed_dates)
                        except ValueError as e:
                            logger.warning(f"Failed to parse dates for RS Session{session_number}: {e}")
                    
                    session, session_created = Session.objects.get_or_create(
                        lok_sabha=rajya_sabha,  # Reusing LokSabha model for RS
                        session_number=session_number,
                        defaults={
                            'session_period': [],  # RS API doesn't provide period info
                            'dates': sitting_dates,
                            'start_date': start_date,
                            'end_date': end_date,
                            'is_current': session_number == '268',  # Current session (update as needed)
                            'raw_api_data': session_data
                        }
                    )
                    
                    if session_created:
                        total_sessions += 1
            
            result = {
                'status': 'SUCCESS',
                'total_sessions_created': total_sessions,
                'total_sessions_in_api': len(data),
                'message': f'Successfully processed {len(data)} Rajya Sabha sessions'
            }
            
            logger.info(f"Rajya Sabha sessions fetch completed: {result}")
            return result
            
        except Exception as e:
            logger.error(f"Failed to fetch Rajya Sabha sessions: {e}")
            raise
    
    def fetch_questions_for_session(self, session_number: str, timeout: int = 60) -> Dict:
        """
        Fetch all questions for a specific Rajya Sabha session (both starred and unstarred)
        
        Args:
            session_number: RS Session number (e.g., '268')
            timeout: Request timeout in seconds
            
        Returns:
            Dict with questions data and statistics
        """
        try:
            # Fetch both starred and unstarred questions separately
            all_questions_data = []
            
            # 1. Fetch STARRED questions
            starred_url = f"https://rsdoc.nic.in/Question/Search_Questions?whereclause=ses_no={session_number}%20and%20qtype=%27STARRED%27"
            logger.info(f"Fetching RS STARRED questions for Session{session_number} from: {starred_url}")
            
            starred_response = self.session.get(starred_url, timeout=timeout)
            starred_response.raise_for_status()
            starred_data = starred_response.json()
            
            if isinstance(starred_data, list):
                all_questions_data.extend(starred_data)
                logger.info(f"Found {len(starred_data)} STARRED questions")
            
            # 2. Fetch UNSTARRED questions  
            unstarred_url = f"https://rsdoc.nic.in/Question/Search_Questions?whereclause=ses_no={session_number}%20and%20qtype=%27UNSTARRED%27"
            logger.info(f"Fetching RS UNSTARRED questions for Session{session_number} from: {unstarred_url}")
            
            unstarred_response = self.session.get(unstarred_url, timeout=timeout)
            unstarred_response.raise_for_status()
            unstarred_data = unstarred_response.json()
            
            if isinstance(unstarred_data, list):
                all_questions_data.extend(unstarred_data)
                logger.info(f"Found {len(unstarred_data)} UNSTARRED questions")
            
            questions_data = all_questions_data
            total_record_size = len(questions_data)
            
            logger.info(f"Total RS questions fetched: {total_record_size} (starred: {len(starred_data)}, unstarred: {len(unstarred_data)})")
            
            # Get Rajya Sabha and Session objects
            rajya_sabha = LokSabha.objects.get(number='RS')
            session = Session.objects.get(lok_sabha=rajya_sabha, session_number=session_number)
            
            # Get or create ParliamentInstitution for Rajya Sabha
            rs_institution = ParliamentInstitution.objects.get(name='rajya_sabha')
            
            # Store questions in database
            created_count = 0
            updated_count = 0
            
            with transaction.atomic():
                for q_data in questions_data:
                    question_number = str(q_data.get('qno', ''))
                    if not question_number:
                        continue
                    
                    # Parse date from RS format (YYYY-MM-DD)
                    question_date = None
                    date_str = q_data.get('adate', '')  # Answer date
                    if date_str:
                        try:
                            # RS API returns ISO format: "2025-07-21T00:00:00"
                            question_date = datetime.fromisoformat(date_str.replace('T00:00:00', '')).date()
                        except ValueError:
                            logger.warning(f"Failed to parse date '{date_str}' for RS question {question_number}")
                    
                    # Clean and normalize question type
                    raw_question_type = q_data.get('qtype', 'UNSTARRED').strip()
                    clean_question_type = self._clean_question_type(raw_question_type)
                    
                    # Extract member info (RS format is different)
                    member_name = q_data.get('name', '')
                    member_prefix = q_data.get('shri', '')
                    full_member_name = f"{member_prefix} {member_name}".strip()
                    
                    # Prepare master data for RS (handle null values properly)
                    master_data = {
                        'parent_institution': rs_institution,
                        'question_number': question_number,
                        'subjects': q_data.get('qtitle', ''),
                        'rajya_sabha_number': 'RS',  # Use 'RS' identifier
                        'lok_sabha_number': '',  # Empty for RS questions
                        'members': [{'name': full_member_name}] if full_member_name else [],
                        'ministry': q_data.get('min_name', ''),
                        'question_type': clean_question_type,
                        'date': question_date,
                        'session_number': session_number,
                        'questions_file_path': q_data.get('files') or '',  # Ensure not None
                        'questions_file_path_hindi': q_data.get('hindifiles') or '',  # Ensure not None
                        'question_text': q_data.get('qn_text', ''),  # RS provides question text
                        'answer_text': q_data.get('ans_text'),  # May be null
                        'answer_text_hindi': None,  # Not provided in RS API
                        'supplementary_type': False,  # RS API doesn't indicate this
                        'supplementary_questions': [],
                        'lok_sabha': rajya_sabha,
                        'session': session,
                        'raw_api_data': q_data,
                        'last_fetched': timezone.now()
                    }
                    
                    # Create or update master data (now includes question_type in constraint)
                    question_master, created = QuestionMasterData.objects.get_or_create(
                        parent_institution=rs_institution,
                        question_number=question_number,
                        rajya_sabha_number='RS',
                        session_number=session_number,
                        question_type=clean_question_type,  # Include question_type in unique constraint
                        defaults=master_data
                    )
                    
                    if created:
                        created_count += 1
                    else:
                        # Update existing record
                        for key, value in master_data.items():
                            if key not in ['parent_institution', 'question_number', 'rajya_sabha_number', 'session_number']:
                                setattr(question_master, key, value)
                        question_master.save()
                        updated_count += 1
            
            result = {
                'status': 'SUCCESS',
                'institution': 'rajya_sabha',
                'session_number': session_number,
                'total_available': total_record_size,
                'fetched': len(questions_data),
                'created': created_count,
                'updated': updated_count,
                'message': f'Successfully processed {len(questions_data)} questions for RS Session{session_number}'
            }
            
            logger.info(f"RS Questions fetch completed: {result}")
            return result
            
        except LokSabha.DoesNotExist:
            raise ValueError(f"Rajya Sabha record not found. Please fetch RS sessions first.")
        except Session.DoesNotExist:
            raise ValueError(f"Session {session_number} for Rajya Sabha not found. Please fetch RS sessions first.")
        except Exception as e:
            logger.error(f"Failed to fetch RS questions for Session{session_number}: {e}")
            raise
    
    def initialize_rs_master_data(self, force_update: bool = False) -> Dict:
        """
        Initialize Rajya Sabha master data - fetch sessions and all questions
        
        Args:
            force_update: If True, refetch data even if it exists
            
        Returns:
            Dict with initialization results
        """
        try:
            print(f"🏛️ Initializing Rajya Sabha Questions Master Data...")
            
            # Check if we already have RS data
            rs_institution = ParliamentInstitution.objects.filter(name='rajya_sabha').first()
            existing_sessions = Session.objects.filter(lok_sabha__number='RS').count() if rs_institution else 0
            existing_questions = QuestionMasterData.objects.filter(parent_institution__name='rajya_sabha').count() if rs_institution else 0
            
            if not force_update and existing_sessions > 0 and existing_questions > 0:
                print(f"📊 RS master data already exists: {existing_sessions} sessions, {existing_questions} questions")
                print(f"💡 Use force_update=True to refresh from server")
                
                return {
                    'status': 'ALREADY_EXISTS',
                    'sessions_count': existing_sessions,
                    'questions_count': existing_questions,
                    'message': 'RS master data already initialized. Use force_update=True to refresh.'
                }
            
            print(f"🚀 {'Updating' if force_update else 'Fetching'} RS master data from Parliament APIs...")
            
            # Step 1: Fetch and store all RS sessions
            print(f"📡 Step 1: Fetching Rajya Sabha sessions...")
            sessions_result = self.fetch_rajya_sabha_sessions()
            
            # Step 2: Fetch questions for current session (268) only for initialization
            print(f"📡 Step 2: Fetching questions for current RS session (268)...")
            questions_result = self.fetch_questions_for_session('268')
            
            result = {
                'status': 'SUCCESS',
                'sessions_result': sessions_result,
                'questions_result': questions_result,
                'total_sessions': Session.objects.filter(lok_sabha__number='RS').count(),
                'total_questions': QuestionMasterData.objects.filter(parent_institution__name='rajya_sabha').count(),
                'message': f'RS master data initialized successfully'
            }
            
            print(f"✅ RS master data initialization completed!")
            print(f"   📊 Sessions: {result['total_sessions']}")
            print(f"   📊 Questions: {result['total_questions']}")
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to initialize RS master data: {e}")
            raise
    
    def fetch_questions_for_recent_sessions(self, limit: int = 1) -> Dict:
        """
        Fetch questions for the most recent RS sessions (default: current session only)
        
        Args:
            limit: Number of recent sessions to process (default 1 for current session)
            
        Returns:
            Dict with overall statistics
        """
        try:
            # Get recent sessions (highest session numbers) - but RS sessions are numbered differently
            # Session 268 is current, but we should start from there and work backwards
            recent_sessions = Session.objects.filter(
                lok_sabha__number='RS'
            ).order_by('-session_number')[:limit]
            
            # If no sessions found or we want to test current session, use session 268
            if not recent_sessions or limit == 1:
                current_session = Session.objects.filter(
                    lok_sabha__number='RS',
                    session_number='268'
                ).first()
                
                if current_session:
                    recent_sessions = [current_session]
                else:
                    # Fallback to highest numbered session
                    recent_sessions = Session.objects.filter(
                        lok_sabha__number='RS'
                    ).order_by('-session_number')[:1]
            
            total_sessions = recent_sessions.count()
            processed_sessions = 0
            total_created = 0
            total_updated = 0
            errors = []
            
            print(f"📊 Processing {total_sessions} recent RS sessions for questions...")
            
            for session in recent_sessions:
                try:
                    print(f"   Processing RS Session{session.session_number}...")
                    result = self.fetch_questions_for_session(session.session_number)
                    
                    processed_sessions += 1
                    total_created += result.get('created', 0)
                    total_updated += result.get('updated', 0)
                    
                    print(f"      ✅ +{result.get('created', 0)} created, +{result.get('updated', 0)} updated")
                    
                    # Brief pause between requests
                    time.sleep(1)
                    
                except Exception as e:
                    error_msg = f"RS Session{session.session_number}: {str(e)}"
                    errors.append(error_msg)
                    logger.error(f"Failed to process RS session: {error_msg}")
                    print(f"      ❌ {error_msg}")
            
            result = {
                'status': 'SUCCESS' if not errors else 'PARTIAL_SUCCESS',
                'total_sessions': total_sessions,
                'processed_sessions': processed_sessions,
                'total_created': total_created,
                'total_updated': total_updated,
                'errors': errors,
                'message': f'RS questions fetch completed: {processed_sessions}/{total_sessions} sessions processed'
            }
            
            logger.info(f"RS questions fetch completed: {result}")
            return result
            
        except Exception as e:
            logger.error(f"Failed to fetch RS questions: {e}")
            raise
    
    def get_rs_statistics(self) -> Dict:
        """
        Get statistics about RS master questions data
        
        Returns:
            Dict with statistics
        """
        try:
            rs_institution = ParliamentInstitution.objects.get(name='rajya_sabha')
            total_questions = QuestionMasterData.objects.filter(parent_institution=rs_institution).count()
            
            # Group by question type
            by_question_type = {}
            for question_type, _ in QuestionMasterData.QUESTION_TYPES:
                count = QuestionMasterData.objects.filter(
                    parent_institution=rs_institution,
                    question_type=question_type
                ).count()
                by_question_type[question_type] = count
            
            # Processing status
            processed_count = QuestionMasterData.objects.filter(
                parent_institution=rs_institution,
                is_processed=True
            ).count()
            unprocessed_count = total_questions - processed_count
            
            # Questions with PDF URLs
            with_pdf_count = QuestionMasterData.objects.filter(
                parent_institution=rs_institution
            ).exclude(questions_file_path='').count()
            without_pdf_count = total_questions - with_pdf_count
            
            return {
                'institution': 'rajya_sabha',
                'total_questions': total_questions,
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
            
        except ParliamentInstitution.DoesNotExist:
            return {
                'institution': 'rajya_sabha',
                'total_questions': 0,
                'message': 'Rajya Sabha institution not found. Please initialize RS data first.'
            }
        except Exception as e:
            logger.error(f"Failed to get RS statistics: {e}")
            raise
    
    def _clean_question_type(self, raw_type: str) -> str:
        """
        Clean and normalize question type from RS API response
        
        Args:
            raw_type: Raw question type from RS API
            
        Returns:
            Cleaned question type that matches our model choices
        """
        if not raw_type:
            return 'UNSTARRED'  # Default for RS
        
        # Remove extra whitespace and normalize (RS API has trailing spaces!)
        cleaned_type = raw_type.strip().upper()
        
        # Map RS formats to our standard types (RS API uses trailing spaces)
        if cleaned_type in ['STARRED', 'STARRED QUESTION']:
            return 'STARRED'
        elif cleaned_type in ['UNSTARRED', 'UNSTARRED QUESTION']:
            return 'UNSTARRED'
        elif cleaned_type in ['SHORT_NOTICE', 'SHORT NOTICE', 'SHORT NOTICE QUESTION']:
            return 'SHORT_NOTICE'
        else:
            # Log unexpected types for debugging
            logger.warning(f"Unexpected RS question type '{raw_type}' (cleaned: '{cleaned_type}') -> defaulting to UNSTARRED")
            return 'UNSTARRED'
    
    def get_available_sessions_with_questions(self) -> List[Dict]:
        """
        Get list of available RS sessions that have questions data
        
        Returns:
            List of session info dicts with question counts
        """
        try:
            available_sessions = self.fetch_available_question_sessions()
            
            # Get current data from database for these sessions
            rs_institution = ParliamentInstitution.objects.get(name='rajya_sabha')
            session_stats = []
            
            for session_number in available_sessions[-10:]:  # Get last 10 sessions
                question_count = QuestionMasterData.objects.filter(
                    parent_institution=rs_institution,
                    session_number=session_number
                ).count()
                
                starred_count = QuestionMasterData.objects.filter(
                    parent_institution=rs_institution,
                    session_number=session_number,
                    question_type='STARRED'
                ).count()
                
                unstarred_count = QuestionMasterData.objects.filter(
                    parent_institution=rs_institution,
                    session_number=session_number,
                    question_type='UNSTARRED'
                ).count()
                
                with_pdf_count = QuestionMasterData.objects.filter(
                    parent_institution=rs_institution,
                    session_number=session_number
                ).exclude(questions_file_path='').count()
                
                session_stats.append({
                    'session_number': session_number,
                    'total_questions': question_count,
                    'starred_questions': starred_count,
                    'unstarred_questions': unstarred_count,
                    'questions_with_pdf': with_pdf_count,
                    'has_data': question_count > 0
                })
            
            return session_stats
            
        except Exception as e:
            logger.error(f"Failed to get available sessions with questions: {e}")
            return []
