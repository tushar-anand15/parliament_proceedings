import sys
import os
import json
import logging
import uuid
import threading
import queue
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from django.utils import timezone
from django.db import transaction
from django.conf import settings

# Add the scraper directory to Python path to import direct_api_client
scraper_path = os.path.join(settings.BASE_DIR.parent, 'scraper')
if scraper_path not in sys.path:
    sys.path.append(scraper_path)

try:
    from direct_api_client import ParliamentAPI
except ImportError:
    logging.error("Could not import ParliamentAPI from direct_api_client")
    ParliamentAPI = None

from .models import ScrapingJob, ScrapingSession, ScrapingError, ScrapingConfig
from services.questions.models import Question, LokSabha, Session, Member, Ministry

logger = logging.getLogger(__name__)


class ParliamentQuestionsScraperService:
    """
    Service that integrates the direct_api_client with Django models
    to provide complete scraping functionality with database operations
    """
    
    def __init__(self, scraping_job: ScrapingJob = None):
        self.scraping_job = scraping_job
        self.api_client = ParliamentAPI() if ParliamentAPI else None
        self.config = ScrapingConfig.get_default()
        
        if not self.api_client:
            raise Exception("ParliamentAPI client not available")
    
    def start_scraping(self, 
                      loksabha_no: str, 
                      session_no: str = None,
                      job_name: str = None,
                      force_update: bool = False) -> ScrapingJob:
        """
        Start a scraping job for the specified Lok Sabha and session
        
        Args:
            loksabha_no: Lok Sabha number (e.g., "17")
            session_no: Session number (optional)
            job_name: Custom job name
            force_update: Force update existing records
        """
        
        # Create or get LokSabha
        lok_sabha, created = LokSabha.objects.get_or_create(
            number=loksabha_no,
            defaults={'is_current': loksabha_no == "17"}
        )
        
        # Create or get Session if specified
        session = None
        if session_no:
            session, created = Session.objects.get_or_create(
                lok_sabha=lok_sabha,
                session_number=session_no
            )
        
        # Create scraping job
        if not job_name:
            session_str = f" Session {session_no}" if session_no else ""
            job_name = f"Scrape {loksabha_no}th LS{session_str}"
        
        job = ScrapingJob.objects.create(
            name=job_name,
            description=f"Scraping questions from {loksabha_no}th Lok Sabha{' Session ' + session_no if session_no else ''}",
            job_type='specific_session' if session_no else 'full_scrape',
            batch_size=self.config.default_batch_size if self.config else 100,
            worker_count=self.config.default_workers if self.config else 5
        )
        
        # Add target Lok Sabha and Session
        job.target_lok_sabhas.add(lok_sabha)
        if session:
            job.target_sessions.add(session)
        
        self.scraping_job = job
        
        # Start the scraping process in background thread
        scraping_thread = threading.Thread(
            target=self._execute_scraping_with_error_handling,
            args=(loksabha_no, session_no, force_update),
            daemon=True
        )
        scraping_thread.start()
        
        return job
    
    def _execute_scraping_with_error_handling(self, loksabha_no: str, session_no: str = None, force_update: bool = False):
        """Wrapper for _execute_scraping that handles errors gracefully in background thread"""
        try:
            self._execute_scraping(loksabha_no, session_no, force_update)
        except Exception as e:
            logger.error(f"Background scraping failed: {e}")
            if self.scraping_job:
                self.scraping_job.fail_job(str(e))

    def _execute_scraping(self, loksabha_no: str, session_no: str = None, force_update: bool = False):
        """Execute the actual scraping process"""
        
        job = self.scraping_job
        job.start_job()
        
        try:
            # Get existing questions count
            existing_count = self._get_existing_questions_count(loksabha_no, session_no)
            
            # Fetch questions from API
            logger.info(f"Fetching questions from API for {loksabha_no}th Lok Sabha")
            
            filters = {'loksabha_no': loksabha_no}
            if session_no:
                filters['session_no'] = session_no
            
            # Get total count first
            sample_data = self.api_client.get_questions(start=0, rows=1, **filters)
            total_api_count = int(sample_data.get('rowsCount', 0)) if sample_data else 0
            
            logger.info(f"API reports {total_api_count} questions, DB has {existing_count} questions")
            
            # Update job with expected total
            job.total_questions_expected = total_api_count
            job.save()
            
            # Smart delta checking - only fetch what we need
            if not force_update:
                if existing_count >= total_api_count:
                    logger.info("Database already has all available questions, skipping scrape")
                    job.complete_job()
                    return
                elif existing_count > 0:
                    logger.info(f"Database has {existing_count} questions, API has {total_api_count}. Will fetch incrementally.")
                    # For incremental updates, we'll still fetch all and let the deduplication handle it
                    # This is safer than trying to fetch only newer records since API doesn't have reliable pagination by date
            
            # Use streaming batch processing instead of loading everything into memory
            logger.info(f"Starting streaming batch processing for {total_api_count} questions")
            self._process_questions_in_streaming_batches(loksabha_no, session_no, force_update, total_api_count)
            
            job.complete_job()
            logger.info(f"Scraping completed successfully. Processed {job.questions_processed} questions")
            
        except Exception as e:
            logger.error(f"Scraping failed: {e}")
            job.fail_job(str(e))
            raise
    
    def _get_existing_questions_count(self, loksabha_no: str, session_no: str = None) -> int:
        """Get count of existing questions in database"""
        queryset = Question.objects.filter(lok_sabha__number=loksabha_no)
        if session_no:
            queryset = queryset.filter(session__session_number=session_no)
        return queryset.count()
    
    def _process_questions_in_streaming_batches(self, 
                                               loksabha_no: str, 
                                               session_no: str = None,
                                               force_update: bool = False,
                                               total_count: int = 0):
        """
        Process questions using async producer-consumer pattern
        Producer: Fetches data from API continuously
        Consumer: Processes data to database continuously
        Both run simultaneously for maximum throughput
        """
        job = self.scraping_job
        batch_size = 10000  # 5x larger batches for aggressive processing
        
        # Create queue for producer-consumer communication
        question_queue = queue.Queue(maxsize=50)  # Max 50 batches in queue (50,000 questions)
        
        # Shared state between threads
        producer_finished = threading.Event()
        consumer_finished = threading.Event()
        error_occurred = threading.Event()
        
        logger.info(f"Starting async producer-consumer processing for {total_count} questions")
        
        def api_producer():
            """Producer: Continuously fetch batches from API and put in queue"""
            try:
                start = 0
                while start < total_count:
                    # Fetch batch from API
                    batch_data = self.api_client.get_questions(
                        start=start, 
                        rows=batch_size, 
                        loksabha_no=loksabha_no
                    )
                    
                    if not batch_data or 'records' not in batch_data:
                        logger.warning(f"No data in batch starting at {start}")
                        break
                    
                    batch_questions = batch_data['records']
                    if not batch_questions:
                        logger.info(f"API returned no more questions at position {start}")
                        break
                    
                    # Put batch in queue (this will block if queue is full)
                    logger.info(f"🔄 Producer: Fetched batch {start}-{start + len(batch_questions)} / {total_count}")
                    question_queue.put({
                        'questions': batch_questions,
                        'batch_start': start,
                        'batch_size': len(batch_questions)
                    })
                    
                    start += batch_size
                    
                    # Small delay to avoid overwhelming API
                    time.sleep(0.05)
                    
                    # Check if consumer reported error
                    if error_occurred.is_set():
                        logger.error("Producer stopping due to consumer error")
                        break
                        
                # Signal that producer is done
                question_queue.put(None)  # Sentinel value
                producer_finished.set()
                logger.info("🏁 Producer: Finished fetching all batches")
                
            except Exception as e:
                logger.error(f"Producer error: {e}")
                error_occurred.set()
                question_queue.put(None)  # Wake up consumer
        
        def db_consumer():
            """Consumer: Continuously take batches from queue and save to database"""
            try:
                total_processed = 0
                while True:
                    try:
                        # Get batch from queue (timeout to check for completion)
                        batch_data = question_queue.get(timeout=30)
                        
                        # Check for sentinel value (producer finished)
                        if batch_data is None:
                            logger.info("🏁 Consumer: Received completion signal")
                            break
                            
                        # Process this batch
                        questions = batch_data['questions']
                        batch_start = batch_data['batch_start']
                        
                        logger.info(f"💾 Consumer: Processing batch {batch_start} ({len(questions)} questions)")
                        
                        # Save to database
                        self._process_and_save_questions(questions, loksabha_no, session_no, force_update)
                        
                        total_processed += len(questions)
                        
                        # Mark task as done
                        question_queue.task_done()
                        
                        logger.info(f"✅ Consumer: Completed batch {batch_start} (Total processed: {total_processed})")
                        
                    except queue.Empty:
                        # Timeout waiting for data - check if producer is done
                        if producer_finished.is_set():
                            logger.info("Consumer: Producer finished and queue empty, stopping")
                            break
                        logger.info("Consumer: Waiting for more data...")
                        continue
                        
            except Exception as e:
                logger.error(f"Consumer error: {e}")
                error_occurred.set()
            finally:
                consumer_finished.set()
        
        # Start both threads
        producer_thread = threading.Thread(target=api_producer, name="API-Producer")
        consumer_thread = threading.Thread(target=db_consumer, name="DB-Consumer")
        
        logger.info("🚀 Starting producer and consumer threads")
        producer_thread.start()
        consumer_thread.start()
        
        # Wait for both threads to complete
        producer_thread.join()
        consumer_thread.join()
        
        # Check for errors
        if error_occurred.is_set():
            raise Exception("Error occurred during async processing")
            
        logger.info("🎉 Async producer-consumer processing completed successfully")
    
    def _process_and_save_questions(self, 
                                   api_questions: List[Dict], 
                                   loksabha_no: str, 
                                   session_no: str = None,
                                   force_update: bool = False):
        """Process API questions using BULK operations for maximum performance"""
        
        job = self.scraping_job
        lok_sabha = LokSabha.objects.get(number=loksabha_no)
        session = None
        
        if session_no:
            session = Session.objects.get(lok_sabha=lok_sabha, session_number=session_no)
        
        logger.info(f"🚀 BULK processing {len(api_questions)} questions")
        
        # Step 1: Extract all question data in parallel
        from concurrent.futures import ThreadPoolExecutor
        
        def extract_question_data(api_question):
            try:
                return self._extract_question_data(api_question, lok_sabha, session)
            except Exception as e:
                logger.error(f"Failed to extract data for question {api_question.get('resourceId', 'unknown')}: {e}")
                return None
        
        # Parallel data extraction
        with ThreadPoolExecutor(max_workers=4) as executor:
            question_data_list = list(executor.map(extract_question_data, api_questions))
        
        # Filter out failed extractions
        valid_data = [(api_q, q_data) for api_q, q_data in zip(api_questions, question_data_list) if q_data]
        
        if not valid_data:
            logger.error("No valid question data extracted")
            return
        
        logger.info(f"✅ Extracted {len(valid_data)} valid questions")
        
        # Step 2: BULK check for existing questions using resource IDs
        resource_ids = [q_data['api_resource_id'] for _, q_data in valid_data if q_data.get('api_resource_id')]
        
        existing_questions_map = {}
        if resource_ids:
            existing_questions = Question.objects.filter(api_resource_id__in=resource_ids).select_related('lok_sabha', 'session')
            existing_questions_map = {q.api_resource_id: q for q in existing_questions}
            logger.info(f"📋 Found {len(existing_questions_map)} existing questions")
        
        # Step 3: Separate new vs existing questions
        questions_to_create = []
        questions_to_update = []
        skipped_count = 0
        
        for api_question, question_data in valid_data:
            resource_id = question_data.get('api_resource_id')
            existing_question = existing_questions_map.get(resource_id) if resource_id else None
            
            if existing_question:
                if force_update:
                    # Prepare for bulk update
                    for key, value in question_data.items():
                        if key not in ['members', 'ministries']:
                            setattr(existing_question, key, value)
                    existing_question.last_scraped = timezone.now()
                    questions_to_update.append((existing_question, api_question))
                else:
                    skipped_count += 1
            else:
                # Prepare for bulk create
                question_data['question_id'] = str(uuid.uuid4())
                questions_to_create.append((Question(**question_data), api_question))
        
        # Step 4: BULK database operations with retry logic
        created_count = 0
        updated_count = 0
        failed_count = 0
        
        def execute_with_retry(operation_name, operation_func, max_retries=3):
            """Execute database operation with retry logic for database locks"""
            for attempt in range(max_retries):
                try:
                    return operation_func()
                except Exception as e:
                    if "database is locked" in str(e).lower() and attempt < max_retries - 1:
                        wait_time = (2 ** attempt) * 0.1  # Exponential backoff: 0.1s, 0.2s, 0.4s
                        logger.warning(f"Database locked during {operation_name}, retrying in {wait_time}s (attempt {attempt + 1}/{max_retries})")
                        time.sleep(wait_time)
                        continue
                    else:
                        logger.error(f"{operation_name} failed after {attempt + 1} attempts: {e}")
                        raise
        
        # Separate transactions for creates and updates to reduce lock time
        if questions_to_create:
            def bulk_create_operation():
                with transaction.atomic():
                    new_questions = [q for q, _ in questions_to_create]
                    Question.objects.bulk_create(new_questions, batch_size=200)  # Smaller batch size
                    return len(new_questions)
            
            created_count = execute_with_retry("bulk_create", bulk_create_operation)
            logger.info(f"💾 BULK created {created_count} questions")
            
            # Handle relationships separately to avoid long transactions
            for question, api_question in questions_to_create:
                try:
                    self._update_question_relationships(question, api_question)
                except Exception as e:
                    logger.error(f"Failed to update relationships for new question: {e}")
                    failed_count += 1
        
        if questions_to_update:
            def bulk_update_operation():
                with transaction.atomic():
                    existing_questions = [q for q, _ in questions_to_update]
                    Question.objects.bulk_update(existing_questions, [
                        'title', 'subject', 'question_text', 'answer_text',
                        'document_type', 'language', 'year', 'document_handle',
                        'pdf_files', 'minister_names', 'council_of_state_no',
                        'committee_name', 'assembly_no', 'debate', 'report_no',
                        'youtube_url', 'source', 'date', 'asked_date', 'status',
                        'session', 'last_scraped'
                    ], batch_size=200)  # Smaller batch size
                    return len(existing_questions)
            
            updated_count = execute_with_retry("bulk_update", bulk_update_operation)
            logger.info(f"🔄 BULK updated {updated_count} questions")
            
            # Handle relationships separately to avoid long transactions
            for question, api_question in questions_to_update:
                try:
                    self._update_question_relationships(question, api_question)
                except Exception as e:
                    logger.error(f"Failed to update relationships for existing question: {e}")
                    failed_count += 1
        
        # Update job counters
        job.questions_processed += len(api_questions)
        job.questions_created += created_count
        job.questions_updated += updated_count
        job.questions_failed += failed_count
        job.save()
        
        logger.info(f"🎯 BULK batch complete: {created_count} created, {updated_count} updated, "
                    f"{skipped_count} skipped, {failed_count} failed "
                    f"(Total processed: {job.questions_processed})")
    
    def _find_existing_question(self, api_question: Dict, lok_sabha: LokSabha, session: Session = None) -> Optional[Question]:
        """
        Find existing question using natural keys instead of relying on API IDs
        
        Uses combination of:
        - question_number
        - date  
        - lok_sabha
        - session (if available)
        - question_type
        """
        
        question_no = api_question.get('questionNo', '')
        question_type = api_question.get('questionType', '')
        
        # Parse date
        date = None
        if api_question.get('date'):
            try:
                date_str = api_question['date']
                for fmt in ['%Y-%m-%d', '%d-%b-%Y', '%d/%m/%Y']:
                    try:
                        date = datetime.strptime(date_str, fmt).date()
                        break
                    except ValueError:
                        continue
            except Exception:
                pass
        
        # Extract session from API question data if not provided
        question_session = session
        if not question_session and api_question.get('sessionNo'):
            session_no = api_question['sessionNo']
            try:
                question_session = Session.objects.get(
                    lok_sabha=lok_sabha,
                    session_number=session_no
                )
            except Session.DoesNotExist:
                # Session doesn't exist yet, will be created later
                pass
        
        # Build query to find existing question
        query_filters = {
            'lok_sabha': lok_sabha,
            'question_number': question_no,
            'question_type': question_type
        }
        
        # Add date filter if available
        if date:
            query_filters['date'] = date
            
        # Add session filter if available
        if question_session:
            query_filters['session'] = question_session
        
        # First try to find by API resource ID (most reliable)
        resource_id = api_question.get('resourceId', '')
        if resource_id:
            try:
                existing_question = Question.objects.filter(api_resource_id=resource_id).first()
                if existing_question:
                    logger.debug(f"Found existing question by resourceId: {resource_id}")
                    return existing_question
            except Exception as e:
                logger.warning(f"Error finding question by resourceId: {e}")
        
        # Fallback to natural key matching
        try:
            existing_question = Question.objects.filter(**query_filters).first()
            if existing_question:
                logger.debug(f"Found existing question by natural keys: {question_no} ({question_type}) from {date}")
            return existing_question
        except Exception as e:
            logger.warning(f"Error finding existing question: {e}")
            return None

    def _extract_question_data(self, api_question: Dict, lok_sabha: LokSabha, session: Session = None) -> Dict:
        """Extract question data from API response and format for Django model"""
        
        # Parse date
        date = None
        if api_question.get('date'):
            try:
                # Try different date formats
                date_str = api_question['date']
                for fmt in ['%d-%b-%Y', '%Y-%m-%d', '%d/%m/%Y']:
                    try:
                        date = datetime.strptime(date_str, fmt).date()
                        break
                    except ValueError:
                        continue
            except Exception as e:
                logger.warning(f"Could not parse date '{api_question.get('date')}': {e}")
        
        # Extract session from API question data if not provided
        question_session = session
        if not question_session and api_question.get('sessionNo'):
            session_no = api_question['sessionNo']
            question_session, created = Session.objects.get_or_create(
                lok_sabha=lok_sabha,
                session_number=session_no
            )
            if created:
                logger.debug(f"Created new session: {lok_sabha.number}th LS Session {session_no}")
        
        return {
            # question_id will be set as UUID when creating new records
            'api_resource_id': api_question.get('resourceId', ''),
            'question_number': api_question.get('questionNo', ''),
            'question_type': api_question.get('questionType', ''),
            'title': api_question.get('title', ''),
            'subject': api_question.get('subject', ''),
            'question_text': api_question.get('questionText', ''),
            'answer_text': api_question.get('answerText', ''),
            
            # API Metadata
            'document_type': api_question.get('type', ''),
            'language': api_question.get('language', ''),
            'year': api_question.get('year', ''),
            'document_handle': api_question.get('handle', ''),
            'pdf_files': api_question.get('files', []) if isinstance(api_question.get('files'), list) else [],
            'minister_names': api_question.get('ministerName', []) if isinstance(api_question.get('ministerName'), list) else [],
            
            # Additional metadata
            'council_of_state_no': api_question.get('councilOfStateNo', ''),
            'committee_name': api_question.get('committeeName', ''),
            'assembly_no': api_question.get('assemblyNo', ''),
            'debate': api_question.get('debate', ''),
            'report_no': api_question.get('reportNo', ''),
            'youtube_url': api_question.get('youtubeURL', ''),
            'source': api_question.get('source', ''),
            
            # Timestamps
            'date': date,
            'asked_date': date,  # Use same date for now
            'status': 'answered' if api_question.get('answerText') else 'active',
            'lok_sabha': lok_sabha,
            'session': question_session,
            'raw_api_data': api_question,
            'last_scraped': timezone.now()
        }
    
    def _update_question_relationships(self, question: Question, api_question: Dict):
        """Update question relationships (members, ministries)"""
        
        # Handle members
        members_data = api_question.get('members', [])
        if isinstance(members_data, str):
            members_data = [members_data]
        elif not isinstance(members_data, list):
            members_data = []
        
        for member_name in members_data:
            if member_name:
                member, created = Member.objects.get_or_create(
                    name=member_name.strip(),
                    defaults={'is_active': True}
                )
                question.members.add(member)
        
        # Handle ministries
        ministries_data = api_question.get('ministry', [])
        if isinstance(ministries_data, str):
            ministries_data = [ministries_data]
        elif not isinstance(ministries_data, list):
            ministries_data = []
        
        for ministry_name in ministries_data:
            if ministry_name:
                ministry, created = Ministry.objects.get_or_create(
                    name=ministry_name.strip(),
                    defaults={'is_active': True}
                )
                question.ministries.add(ministry)
    
    def get_scraping_status(self) -> Dict:
        """Get current scraping status"""
        
        if not self.scraping_job:
            return {'status': 'no_active_job'}
        
        return {
            'job_id': self.scraping_job.id,
            'status': self.scraping_job.status,
            'progress_percent': self.scraping_job.progress_percent,
            'questions_processed': self.scraping_job.questions_processed,
            'questions_created': self.scraping_job.questions_created,
            'questions_updated': self.scraping_job.questions_updated,
            'questions_failed': self.scraping_job.questions_failed,
            'total_expected': self.scraping_job.total_questions_expected,
            'started_at': self.scraping_job.started_at,
            'duration': str(self.scraping_job.duration) if self.scraping_job.duration else None
        }
    
    def check_for_updates(self, loksabha_no: str, session_no: str = None) -> Dict:
        """Check if there are new questions available on the API"""
        
        # Get current count in database
        db_count = self._get_existing_questions_count(loksabha_no, session_no)
        
        # Get count from API
        filters = {'loksabha_no': loksabha_no}
        if session_no:
            filters['session_no'] = session_no
        
        sample_data = self.api_client.get_questions(start=0, rows=1, **filters)
        api_count = int(sample_data.get('rowsCount', 0)) if sample_data else 0
        
        return {
            'loksabha_no': loksabha_no,
            'session_no': session_no,
            'database_count': db_count,
            'api_count': api_count,
            'new_questions_available': api_count > db_count,
            'difference': api_count - db_count
        }
    
    @classmethod
    def create_and_start_scraping(cls, 
                                 loksabha_no: str,
                                 session_no: str = None,
                                 job_name: str = None,
                                 force_update: bool = False) -> 'ParliamentQuestionsScraperService':
        """Convenience method to create service and start scraping"""
        
        service = cls()
        service.start_scraping(loksabha_no, session_no, job_name, force_update)
        return service 