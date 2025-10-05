from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.db import transaction
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import random
import logging
import sys
from services.questions.master_data_service import QuestionMasterDataService
from services.questions.rs_master_data_service import RajyaSabhaMasterDataService
from services.questions.models import QuestionMasterData, Session, LokSabha, ParliamentInstitution

logger = logging.getLogger(__name__)


def show_progress_bar(current, total, prefix='Progress', bar_length=40, suffix=''):
    """Show a progress bar in the terminal"""
    if total == 0:
        return
    
    percent = float(current) * 100 / total
    filled_length = int(bar_length * current // total)
    bar = '█' * filled_length + '░' * (bar_length - filled_length)
    
    # Use carriage return to overwrite the line
    sys.stdout.write(f'\r{prefix} [{bar}] {percent:.1f}% {suffix}')
    sys.stdout.flush()
    
    if current == total:
        sys.stdout.write('\n')
        sys.stdout.flush()


class Command(BaseCommand):
    help = 'Initialize questions master data from sansad.in API with parallel processing (supports both LS and RS)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force-update',
            action='store_true',
            help='Force update even if data already exists',
        )
        parser.add_argument(
            '--workers',
            type=int,
            default=10,
            help='Number of parallel workers (default: 10)',
        )
        parser.add_argument(
            '--recent-only',
            action='store_true',
            help='Only fetch recent Lok Sabhas (16-18)',
        )
        parser.add_argument(
            '--incremental-update',
            action='store_true',
            help='Only fetch sessions that have no questions in database',
        )
        parser.add_argument(
            '--timeout',
            type=int,
            default=500,
            help='API request timeout in seconds (default: 500)',
        )
        parser.add_argument(
            '--rs-only',
            action='store_true',
            help='Initialize only Rajya Sabha questions',
        )
        parser.add_argument(
            '--ls-only',
            action='store_true',
            help='Initialize only Lok Sabha questions',
        )
        parser.add_argument(
            '--test-coverage',
            action='store_true',
            help='Test 10 random questions from each available session after initialization',
        )

    def handle(self, *args, **options):
        # Suppress INFO logs during initialization (only show WARNING and above)
        logging.getLogger('services.questions.master_data_service').setLevel(logging.WARNING)
        logging.getLogger('services.questions.rs_master_data_service').setLevel(logging.WARNING)
        
        self.stdout.write(
            self.style.SUCCESS('🏛️ Parliament Questions Master Data - PARALLEL INITIALIZATION (LS + RS)')
        )
        self.stdout.write('=' * 80)
        
        force_update = options['force_update']
        workers = options['workers']
        recent_only = options['recent_only']
        incremental_update = options['incremental_update']
        timeout = options['timeout']
        rs_only = options['rs_only']
        ls_only = options['ls_only']
        test_coverage = options['test_coverage']
        
        try:
            # Initialize services
            ls_service = QuestionMasterDataService()
            rs_service = RajyaSabhaMasterDataService()
            
            # Check current state
            existing_sessions = Session.objects.count()
            existing_ls_questions = QuestionMasterData.objects.filter(parent_institution__name='lok_sabha').count()
            existing_rs_questions = QuestionMasterData.objects.filter(parent_institution__name='rajya_sabha').count()
            total_questions = existing_ls_questions + existing_rs_questions
            
            self.stdout.write(f"📊 Current state:")
            self.stdout.write(f"   Sessions in DB: {existing_sessions}")
            self.stdout.write(f"   LS Questions in DB: {existing_ls_questions:,}")
            self.stdout.write(f"   RS Questions in DB: {existing_rs_questions:,}")
            self.stdout.write(f"   Total Questions: {total_questions:,}")
            
            # Determine what to initialize
            if rs_only:
                self.stdout.write(f"\n🎯 RAJYA SABHA ONLY MODE")
                self._initialize_rs_data(rs_service, force_update, workers, timeout)
            elif ls_only:
                self.stdout.write(f"\n🎯 LOK SABHA ONLY MODE")
                self._initialize_ls_data(ls_service, force_update, workers, recent_only, incremental_update, timeout)
            else:
                self.stdout.write(f"\n🎯 FULL INITIALIZATION MODE (LS + RS)")
                
                # Initialize LS first
                if not ls_only:
                    self.stdout.write(f"\n📡 PHASE 1: Lok Sabha Initialization")
                    self._initialize_ls_data(ls_service, force_update, workers, recent_only, incremental_update, timeout)
                
                # Initialize RS second
                if not ls_only:
                    self.stdout.write(f"\n📡 PHASE 2: Rajya Sabha Initialization")
                    self._initialize_rs_data(rs_service, force_update, workers, timeout)
            
            # Test coverage if requested
            if test_coverage:
                self.stdout.write(f"\n🧪 PHASE 3: Coverage Testing")
                self._test_coverage_all_sessions()
            
            # Final statistics
            self._show_final_statistics_combined()
        
        except Exception as e:
            raise CommandError(f'Failed to initialize master data: {str(e)}')
    
    def _initialize_ls_data(self, ls_service, force_update, workers, recent_only, incremental_update, timeout):
        """Initialize Lok Sabha data (existing logic)"""
        # Step 1: Ensure sessions metadata is available
        self.stdout.write('\n📡 Step 1: Ensuring LS sessions metadata...')
        sessions_result = ls_service.fetch_lok_sabha_sessions()
        self.stdout.write(f"✅ LS Sessions metadata ready")
        
        # Step 2: Get sessions to process
        if recent_only:
            sessions_to_process = Session.objects.filter(
                lok_sabha__number__in=['16', '17', '18']
            ).order_by('lok_sabha__number', 'session_number')
            self.stdout.write(f'🎯 Processing RECENT LS sessions only: {sessions_to_process.count()} sessions')
        else:
            sessions_to_process = Session.objects.all().order_by('lok_sabha__number', 'session_number')
            self.stdout.write(f'🚀 Processing ALL LS sessions: {sessions_to_process.count()} sessions')
            
        # Filter for incremental update
        if incremental_update:
            sessions_without_questions = []
            for session in sessions_to_process:
                question_count = QuestionMasterData.objects.filter(
                    lok_sabha_number=session.lok_sabha.number,
                    session_number=session.session_number
                ).count()
                if question_count == 0:
                    sessions_without_questions.append(session)
            
            sessions_to_process = sessions_without_questions
            self.stdout.write(f'📈 INCREMENTAL UPDATE: {len(sessions_to_process)} LS sessions without questions')
        
        # Step 3: Parallel processing
        self.stdout.write(f'\n⚡ Step 3: LS Parallel processing with {workers} workers...')
        
        start_time = timezone.now()
        results = self._process_sessions_parallel(ls_service, list(sessions_to_process), workers, timeout)
        end_time = timezone.now()
        duration = (end_time - start_time).total_seconds()
        
        self.stdout.write(f'\n🎉 LS INITIALIZATION COMPLETED!')
        self.stdout.write(f'⏱️  Duration: {duration:.1f} seconds')
        self.stdout.write(f'📊 LS Results:')
        self.stdout.write(f'   Sessions processed: {results["processed_sessions"]}/{results["total_sessions"]}')
        self.stdout.write(f'   Questions created: {results["total_created"]:,}')
        self.stdout.write(f'   Questions updated: {results["total_updated"]:,}')
    
    def _initialize_rs_data(self, rs_service, force_update, workers, timeout):
        """Initialize Rajya Sabha data"""
        self.stdout.write('\n📡 RS Step 1: Getting available RS sessions with questions...')
        
        # Get available sessions from RS questions API
        available_sessions = rs_service.fetch_available_question_sessions()
        self.stdout.write(f'📊 Found {len(available_sessions)} RS sessions with questions: {min(available_sessions)}-{max(available_sessions)}')
        
        # Initialize RS sessions and institution
        rs_result = rs_service.fetch_rajya_sabha_sessions()
        self.stdout.write(f"✅ RS Sessions metadata ready")
        
        # Step 2: Process available sessions with questions
        self.stdout.write(f'\n⚡ RS Step 2: Processing {len(available_sessions)} RS sessions with questions...')
        
        start_time = timezone.now()
        
        # Process RS sessions in parallel
        rs_results = self._process_rs_sessions_parallel(rs_service, available_sessions, workers, timeout)
        
        end_time = timezone.now()
        duration = (end_time - start_time).total_seconds()
        
        self.stdout.write(f'\n🎉 RS INITIALIZATION COMPLETED!')
        self.stdout.write(f'⏱️  Duration: {duration:.1f} seconds')
        self.stdout.write(f'📊 RS Results:')
        self.stdout.write(f'   Sessions processed: {rs_results["processed_sessions"]}/{rs_results["total_sessions"]}')
        self.stdout.write(f'   Questions created: {rs_results["total_created"]:,}')
        self.stdout.write(f'   Questions updated: {rs_results["total_updated"]:,}')
        self.stdout.write(f'   Starred questions: {rs_results["starred_questions"]:,}')
        self.stdout.write(f'   Unstarred questions: {rs_results["unstarred_questions"]:,}')
    
    def _process_rs_sessions_parallel(self, rs_service, session_numbers, workers, timeout):
        """Process RS sessions in parallel"""
        results = {
            'total_sessions': len(session_numbers),
            'processed_sessions': 0,
            'total_created': 0,
            'total_updated': 0,
            'starred_questions': 0,
            'unstarred_questions': 0,
            'errors': []
        }
        
        self.stdout.write(f'🔥 Starting {workers} parallel workers for {len(session_numbers)} RS sessions...')
        
        # Process in parallel
        with ThreadPoolExecutor(max_workers=workers) as executor:
            # Submit all sessions for processing
            future_to_session = {}
            for session_number in session_numbers:
                future = executor.submit(self._process_single_rs_session, rs_service, session_number, timeout)
                future_to_session[future] = session_number
            
            # Collect results as they complete
            completed = 0
            start_time = time.time()
            
            for future in as_completed(future_to_session):
                session_number = future_to_session[future]
                completed += 1
                
                try:
                    session_result = future.result(timeout=timeout + 60)
                    results['processed_sessions'] += 1
                    results['total_created'] += session_result.get('created', 0)
                    results['total_updated'] += session_result.get('updated', 0)
                    
                    # Calculate time remaining
                    elapsed = time.time() - start_time
                    rate = completed / elapsed if elapsed > 0 else 0
                    remaining = (len(session_numbers) - completed) / rate if rate > 0 else 0
                    
                    # Show progress bar
                    show_progress_bar(
                        completed,
                        len(session_numbers),
                        prefix='   RS Sessions',
                        suffix=f'({results["total_created"]:,} created, {results["total_updated"]:,} updated) ~{remaining/60:.0f}min'
                    )
                    
                except Exception as e:
                    error_msg = f"RS Session{session_number}: {str(e)}"
                    results['errors'].append(error_msg)
                    
                    self.stdout.write(
                        f'❌ ({completed}/{len(session_numbers)}) RS Session{session_number}: {str(e)[:60]}...'
                    )
        
        # Get final counts
        rs_institution = ParliamentInstitution.objects.get(name='rajya_sabha')
        results['starred_questions'] = QuestionMasterData.objects.filter(
            parent_institution=rs_institution,
            question_type='STARRED'
        ).count()
        results['unstarred_questions'] = QuestionMasterData.objects.filter(
            parent_institution=rs_institution,
            question_type='UNSTARRED'
        ).count()
        
        return results
    
    def _process_single_rs_session(self, rs_service, session_number, timeout=500, max_retries=3):
        """Process a single RS session with retry logic and randomized delay"""
        for attempt in range(max_retries):
            try:
                # Add randomized delay (0.2-0.5 seconds) to avoid overwhelming API
                # Skip on retries since exponential backoff will handle it
                if attempt == 0:
                    from django.conf import settings
                    time.sleep(random.uniform(settings.API_REQUEST_DELAY_MIN, settings.API_REQUEST_DELAY_MAX))
                elif attempt > 0:
                    delay = min(2 ** attempt, 60)
                    time.sleep(delay)
                    logger.info(f"Retry {attempt + 1}/{max_retries} for RS Session{session_number} after {delay}s delay")
                
                result = rs_service.fetch_questions_for_session(session_number, timeout=timeout)
                return result
                    
            except Exception as e:
                logger.warning(f"Attempt {attempt + 1}/{max_retries} failed for RS Session{session_number}: {e}")
                
                if attempt == max_retries - 1:
                    logger.error(f"All {max_retries} attempts failed for RS Session{session_number}: {e}")
                    raise
    
    def _test_coverage_all_sessions(self):
        """Test 10 random questions from each available session (both LS and RS)"""
        from services.files.pdf_download_service import UnifiedPDFDownloadService
        from django.db.models import Count, Q
        
        self.stdout.write('🧪 Testing coverage: 10 random questions from each available session...')
        
        pdf_service = UnifiedPDFDownloadService()
        
        # Test LS sessions
        self.stdout.write('\n📊 Testing LS Sessions Coverage:')
        ls_sessions = QuestionMasterData.objects.filter(
            parent_institution__name='lok_sabha'
        ).values('lok_sabha_number', 'session_number').annotate(
            question_count=Count('id'),
            with_pdf_count=Count('id', filter=Q(questions_file_path__gt='')),
            starred_count=Count('id', filter=Q(question_type='STARRED')),
            unstarred_count=Count('id', filter=Q(question_type='UNSTARRED'))
        ).filter(question_count__gt=0).order_by('-lok_sabha_number', '-session_number')[:10]
        
        ls_total_tested = 0
        ls_total_accessible = 0
        
        for session_info in ls_sessions:
            ls_no = session_info['lok_sabha_number']
            session_no = session_info['session_number']
            
            # Get 10 random questions
            questions = QuestionMasterData.objects.filter(
                parent_institution__name='lok_sabha',
                lok_sabha_number=ls_no,
                session_number=session_no
            ).exclude(questions_file_path='').order_by('?')[:10]
            
            if questions:
                accessible_count = 0
                for question in questions:
                    result = pdf_service.test_pdf_accessibility(question.questions_file_path)
                    if result['accessible']:
                        accessible_count += 1
                
                ls_total_tested += len(questions)
                ls_total_accessible += accessible_count
                
                rate = (accessible_count / len(questions)) * 100
                self.stdout.write(f'   LS{ls_no} Session{session_no}: {accessible_count}/{len(questions)} accessible ({rate:.1f}%)')
        
        # Test RS sessions
        self.stdout.write('\n📊 Testing RS Sessions Coverage:')
        rs_sessions = QuestionMasterData.objects.filter(
            parent_institution__name='rajya_sabha'
        ).values('session_number').annotate(
            question_count=Count('id'),
            with_pdf_count=Count('id', filter=Q(questions_file_path__gt='')),
            starred_count=Count('id', filter=Q(question_type='STARRED')),
            unstarred_count=Count('id', filter=Q(question_type='UNSTARRED'))
        ).filter(question_count__gt=0).order_by('-session_number')[:10]
        
        rs_total_tested = 0
        rs_total_accessible = 0
        
        for session_info in rs_sessions:
            session_no = session_info['session_number']
            starred_count = session_info['starred_count']
            unstarred_count = session_info['unstarred_count']
            
            # Get 10 random questions
            rs_institution = ParliamentInstitution.objects.get(name='rajya_sabha')
            questions = QuestionMasterData.objects.filter(
                parent_institution=rs_institution,
                session_number=session_no
            ).exclude(questions_file_path='').order_by('?')[:10]
            
            if questions:
                accessible_count = 0
                for question in questions:
                    result = pdf_service.test_pdf_accessibility(question.questions_file_path)
                    if result['accessible']:
                        accessible_count += 1
                
                rs_total_tested += len(questions)
                rs_total_accessible += accessible_count
                
                rate = (accessible_count / len(questions)) * 100
                self.stdout.write(f'   RS Session{session_no}: {accessible_count}/{len(questions)} accessible ({rate:.1f}%) - {starred_count} starred, {unstarred_count} unstarred')
        
        # Overall coverage results
        total_tested = ls_total_tested + rs_total_tested
        total_accessible = ls_total_accessible + rs_total_accessible
        overall_rate = (total_accessible / max(total_tested, 1)) * 100
        
        self.stdout.write(f'\n📊 Overall Coverage Test Results:')
        self.stdout.write(f'   LS Questions tested: {ls_total_tested}, accessible: {ls_total_accessible}')
        self.stdout.write(f'   RS Questions tested: {rs_total_tested}, accessible: {rs_total_accessible}')
        self.stdout.write(f'   Total tested: {total_tested}, accessible: {total_accessible}')
        self.stdout.write(f'   Overall accessibility: {overall_rate:.1f}%')
        
        if overall_rate >= 80:
            self.stdout.write(self.style.SUCCESS('✅ Coverage test PASSED!'))
        else:
            self.stdout.write(self.style.WARNING(f'⚠️ Coverage test: {overall_rate:.1f}% accessibility'))
    
    def _initialize_rs_data(self, rs_service, force_update, workers, timeout):
        """Initialize Rajya Sabha data"""
        # Get available sessions
        available_sessions = rs_service.fetch_available_question_sessions()
        self.stdout.write(f'📊 Available RS sessions: {len(available_sessions)} (from {min(available_sessions)} to {max(available_sessions)})')
        
        # Initialize RS sessions metadata
        rs_sessions_result = rs_service.fetch_rajya_sabha_sessions()
        
        # Check existing RS data
        rs_institution = ParliamentInstitution.objects.filter(name='rajya_sabha').first()
        existing_rs_questions = QuestionMasterData.objects.filter(parent_institution=rs_institution).count() if rs_institution else 0
        
        if not force_update and existing_rs_questions > 1000:
            self.stdout.write(f'⚠️ RS data already exists: {existing_rs_questions:,} questions')
            self.stdout.write('Use --force-update to refresh RS data')
            return
        
        # Determine how many sessions to process
        if force_update:
            # Process ALL available sessions when force update is used
            sessions_to_process = available_sessions
            self.stdout.write(f'🚀 FORCE UPDATE: Processing ALL {len(sessions_to_process)} RS sessions: {min(sessions_to_process)}-{max(sessions_to_process)}')
        else:
            # Process recent sessions (last 10) for regular initialization
            sessions_to_process = available_sessions[-10:]
            self.stdout.write(f'🎯 Processing {len(sessions_to_process)} recent RS sessions: {min(sessions_to_process)}-{max(sessions_to_process)}')
            self.stdout.write('💡 Use --force-update to process ALL 87 available sessions')
        
        start_time = timezone.now()
        rs_results = self._process_rs_sessions_parallel(rs_service, sessions_to_process, workers, timeout)
        end_time = timezone.now()
        duration = (end_time - start_time).total_seconds()
        
        self.stdout.write(f'\n🎉 RS INITIALIZATION COMPLETED!')
        self.stdout.write(f'⏱️  Duration: {duration:.1f} seconds')
        self.stdout.write(f'📊 RS Results:')
        self.stdout.write(f'   Sessions processed: {rs_results["processed_sessions"]}/{rs_results["total_sessions"]}')
        self.stdout.write(f'   Questions created: {rs_results["total_created"]:,}')
        self.stdout.write(f'   Questions updated: {rs_results["total_updated"]:,}')
        self.stdout.write(f'   Starred questions: {rs_results["starred_questions"]:,}')
        self.stdout.write(f'   Unstarred questions: {rs_results["unstarred_questions"]:,}')
    
    def _process_sessions_parallel(self, service, sessions_list, workers, timeout=500):
        """Process sessions in parallel using ThreadPoolExecutor"""
        
        results = {
            'total_sessions': len(sessions_list),
            'processed_sessions': 0,
            'total_created': 0,
            'total_updated': 0,
            'errors': [],
            'successful_sessions': [],
            'failed_sessions': []
        }
        
        self.stdout.write(f'🔥 Starting {workers} parallel workers for {len(sessions_list)} sessions...')
        
        # Process in parallel
        with ThreadPoolExecutor(max_workers=workers) as executor:
            # Submit all sessions for processing
            future_to_session = {}
            for session in sessions_list:
                future = executor.submit(self._process_single_session, service, session, timeout)
                future_to_session[future] = session
            
            # Collect results as they complete
            completed = 0
            start_time = time.time()
            
            for future in as_completed(future_to_session):
                session = future_to_session[future]
                completed += 1
                
                try:
                    session_result = future.result(timeout=timeout + 60)  # Add buffer to future timeout
                    results['processed_sessions'] += 1
                    results['total_created'] += session_result.get('created', 0)
                    results['total_updated'] += session_result.get('updated', 0)
                    
                    api_source = session_result.get('api_source', 'unknown')
                    fetched = session_result.get('fetched', 0)
                    
                    # Calculate time remaining
                    elapsed = time.time() - start_time
                    rate = completed / elapsed if elapsed > 0 else 0
                    remaining = (len(sessions_list) - completed) / rate if rate > 0 else 0
                    
                    # Show progress bar
                    show_progress_bar(
                        completed,
                        len(sessions_list),
                        prefix='   Sessions',
                        suffix=f'({results["total_created"]:,} created, {results["total_updated"]:,} updated) ~{remaining/60:.0f}min'
                    )
                    
                    results['successful_sessions'].append({
                        'lok_sabha': session.lok_sabha.number,
                        'session': session.session_number,
                        'created': session_result['created'],
                        'updated': session_result['updated'],
                        'fetched': fetched,
                        'api_source': api_source
                    })
                    
                except Exception as e:
                    error_msg = f"LS{session.lok_sabha.number} Session{session.session_number}: {str(e)}"
                    results['errors'].append(error_msg)
                    results['failed_sessions'].append({
                        'lok_sabha': session.lok_sabha.number,
                        'session': session.session_number,
                        'error': str(e)
                    })
                    
                    self.stdout.write(
                        f'❌ ({completed}/{len(sessions_list)}) LS{session.lok_sabha.number} '
                        f'Session{session.session_number}: {str(e)[:60]}...'
                    )
        
        return results
    
    def _process_single_session(self, service, session, timeout=500, max_retries=3):
        """Process a single session with exponential backoff and randomized delay - called by parallel workers"""
        
        for attempt in range(max_retries):
            try:
                # Add randomized delay (0.2-0.5 seconds) to avoid overwhelming API
                # Skip on retries since exponential backoff will handle it
                if attempt == 0:
                    from django.conf import settings
                    time.sleep(random.uniform(settings.API_REQUEST_DELAY_MIN, settings.API_REQUEST_DELAY_MAX))
                elif attempt > 0:
                    # Exponential backoff delay
                    delay = min(2 ** attempt, 60)  # Cap at 60 seconds
                    time.sleep(delay)
                    logger.info(f"Retry {attempt + 1}/{max_retries} for LS{session.lok_sabha.number} Session{session.session_number} after {delay}s delay")
                
                # Call with timeout parameter
                result = service.fetch_questions_for_session(
                    session.lok_sabha.number,
                    session.session_number,
                    page_size=10000,
                    use_fallback=True,
                    timeout=timeout
                )
                return result
                    
            except Exception as e:
                logger.warning(f"Attempt {attempt + 1}/{max_retries} failed for LS{session.lok_sabha.number} Session{session.session_number}: {e}")
                
                if attempt == max_retries - 1:
                    # Final attempt failed
                    logger.error(f"All {max_retries} attempts failed for LS{session.lok_sabha.number} Session{session.session_number}: {e}")
                    raise
                
                # Continue to next attempt
                continue
    
    def _show_final_statistics_combined(self):
        """Show comprehensive final statistics for both LS and RS"""
        self.stdout.write('\n📈 FINAL MASTER DATA STATISTICS (LS + RS):')
        
        try:
            # Get fresh counts
            total_sessions = Session.objects.count()
            total_lok_sabhas = LokSabha.objects.count()
            
            # LS vs RS breakdown
            ls_questions = QuestionMasterData.objects.filter(parent_institution__name='lok_sabha').count()
            rs_questions = QuestionMasterData.objects.filter(parent_institution__name='rajya_sabha').count()
            total_questions = ls_questions + rs_questions
            
            self.stdout.write(f'📊 Database Totals:')
            self.stdout.write(f'   Lok Sabhas: {total_lok_sabhas}')
            self.stdout.write(f'   Sessions: {total_sessions}')
            self.stdout.write(f'   LS Questions: {ls_questions:,}')
            self.stdout.write(f'   RS Questions: {rs_questions:,}')
            self.stdout.write(f'   Total Questions: {total_questions:,}')
            
            # RS question type breakdown
            if rs_questions > 0:
                rs_institution = ParliamentInstitution.objects.get(name='rajya_sabha')
                rs_starred = QuestionMasterData.objects.filter(parent_institution=rs_institution, question_type='STARRED').count()
                rs_unstarred = QuestionMasterData.objects.filter(parent_institution=rs_institution, question_type='UNSTARRED').count()
                
                self.stdout.write(f'\n📈 RS Question Types:')
                self.stdout.write(f'   RS Starred: {rs_starred:,}')
                self.stdout.write(f'   RS Unstarred: {rs_unstarred:,}')
            
            # Questions by Lok Sabha (LS only)
            self.stdout.write(f'\n📈 LS Questions by Lok Sabha:')
            for ls in LokSabha.objects.filter(number__regex=r'^\d+$').order_by('number'):  # Only numeric LS numbers
                question_count = QuestionMasterData.objects.filter(lok_sabha_number=ls.number).count()
                if question_count > 0:
                    self.stdout.write(f'   LS{ls.number}: {question_count:,} questions')
            
            # PDF availability
            questions_with_pdf = QuestionMasterData.objects.exclude(questions_file_path='').count()
            questions_without_pdf = total_questions - questions_with_pdf
            
            self.stdout.write(f'\n📁 PDF Availability:')
            self.stdout.write(f'   Questions with PDFs: {questions_with_pdf:,}')
            self.stdout.write(f'   Questions without PDFs: {questions_without_pdf:,}')
            self.stdout.write(f'   PDF coverage: {(questions_with_pdf/max(total_questions,1)*100):.1f}%')
            
            # Usage examples
            self.stdout.write(f'\n💡 Usage Examples:')
            self.stdout.write(f'   # Test LS questions:')
            self.stdout.write(f'   python manage.py initialize_questions_master_data --ls-only --test-coverage')
            self.stdout.write(f'   # Test RS questions:')
            self.stdout.write(f'   python manage.py initialize_questions_master_data --rs-only --test-coverage')
            self.stdout.write(f'   # Test both with coverage:')
            self.stdout.write(f'   python manage.py initialize_questions_master_data --test-coverage')
            
        except Exception as e:
            self.stdout.write(
                self.style.WARNING(f"⚠️ Failed to get statistics: {str(e)}")
            )