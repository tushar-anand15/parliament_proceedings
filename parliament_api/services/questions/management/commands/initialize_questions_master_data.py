from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.db import transaction
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import logging
from services.questions.master_data_service import QuestionMasterDataService
from services.questions.models import QuestionMasterData, Session, LokSabha

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Initialize questions master data from sansad.in API with parallel processing'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force-update',
            action='store_true',
            help='Force update even if data already exists',
        )
        parser.add_argument(
            '--workers',
            type=int,
            default=5,
            help='Number of parallel workers (default: 5)',
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

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.SUCCESS('🏛️ Parliament Questions Master Data - PARALLEL INITIALIZATION')
        )
        self.stdout.write('=' * 70)
        
        force_update = options['force_update']
        workers = options['workers']
        recent_only = options['recent_only']
        incremental_update = options['incremental_update']
        timeout = options['timeout']
        
        try:
            service = QuestionMasterDataService()
            
            # Check current state
            existing_sessions = Session.objects.count()
            existing_questions = QuestionMasterData.objects.count()
            
            self.stdout.write(f"📊 Current state:")
            self.stdout.write(f"   Sessions in DB: {existing_sessions}")
            self.stdout.write(f"   Questions in DB: {existing_questions:,}")
            
            if not force_update and not incremental_update and existing_sessions > 0 and existing_questions > 50000:
                self.stdout.write(
                    self.style.WARNING('⚠️ Substantial master data already exists!')
                )
                self.stdout.write('Use --force-update to refresh or --incremental-update to add missing sessions')
                return
            
            # Step 1: Ensure sessions metadata is available
            self.stdout.write('\n📡 Step 1: Ensuring sessions metadata...')
            sessions_result = service.fetch_lok_sabha_sessions()
            self.stdout.write(f"✅ Sessions metadata ready")
            
            # Step 2: Get sessions to process
            if recent_only:
                sessions_to_process = Session.objects.filter(
                    lok_sabha__number__in=['16', '17', '18']
                ).order_by('lok_sabha__number', 'session_number')
                self.stdout.write(f'🎯 Processing RECENT sessions only: {sessions_to_process.count()} sessions')
            else:
                sessions_to_process = Session.objects.all().order_by('lok_sabha__number', 'session_number')
                self.stdout.write(f'🚀 Processing ALL sessions: {sessions_to_process.count()} sessions')
            
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
                self.stdout.write(f'📈 INCREMENTAL UPDATE: {len(sessions_to_process)} sessions without questions')
            
            # Step 3: Parallel processing
            self.stdout.write(f'\n⚡ Step 3: Parallel processing with {workers} workers...')
            self.stdout.write('This will fetch ALL questions from ALL sessions in parallel!')
            
            start_time = timezone.now()
            
            # Process sessions in parallel
            results = self._process_sessions_parallel(service, list(sessions_to_process), workers, timeout)
            
            end_time = timezone.now()
            duration = (end_time - start_time).total_seconds()
            
            # Show results
            self.stdout.write(f'\n🎉 PARALLEL INITIALIZATION COMPLETED!')
            self.stdout.write(f'⏱️  Duration: {duration:.1f} seconds')
            self.stdout.write(f'📊 Results:')
            self.stdout.write(f'   Sessions processed: {results["processed_sessions"]}/{results["total_sessions"]}')
            self.stdout.write(f'   Questions created: {results["total_created"]:,}')
            self.stdout.write(f'   Questions updated: {results["total_updated"]:,}')
            self.stdout.write(f'   Errors: {len(results["errors"])}')
            
            if results['errors']:
                self.stdout.write(f'\n⚠️ Errors (first 10):')
                for error in results['errors'][:10]:
                    self.stdout.write(f'   • {error}')
                if len(results['errors']) > 10:
                    self.stdout.write(f'   ... and {len(results["errors"]) - 10} more errors')
            
            # Final statistics
            self._show_final_statistics(service)
        
        except Exception as e:
            raise CommandError(f'Failed to initialize master data: {str(e)}')
    
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
                    
                    self.stdout.write(
                        f'✅ ({completed}/{len(sessions_list)}) LS{session.lok_sabha.number} '
                        f'Session{session.session_number}: {session_result["created"]} created, '
                        f'{session_result["updated"]} updated, {fetched} fetched via {api_source} API'
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
        """Process a single session with exponential backoff - called by parallel workers"""
        
        for attempt in range(max_retries):
            try:
                # Exponential backoff delay
                if attempt > 0:
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
    
    def _show_final_statistics(self, service):
        """Show comprehensive final statistics"""
        self.stdout.write('\n📈 FINAL MASTER DATA STATISTICS:')
        
        try:
            # Get fresh counts
            total_questions = QuestionMasterData.objects.count()
            total_sessions = Session.objects.count()
            total_lok_sabhas = LokSabha.objects.count()
            
            self.stdout.write(f'📊 Database Totals:')
            self.stdout.write(f'   Lok Sabhas: {total_lok_sabhas}')
            self.stdout.write(f'   Sessions: {total_sessions}')
            self.stdout.write(f'   Questions: {total_questions:,}')
            
            # Questions by Lok Sabha
            self.stdout.write(f'\n📈 Questions by Lok Sabha:')
            for ls in LokSabha.objects.order_by('number'):
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
            
            # Sessions ready for testing
            sessions_with_questions = []
            for session in Session.objects.all():
                question_count = QuestionMasterData.objects.filter(
                    lok_sabha_number=session.lok_sabha.number,
                    session_number=session.session_number
                ).exclude(questions_file_path='').count()
                
                if question_count > 0:
                    sessions_with_questions.append({
                        'lok_sabha': session.lok_sabha.number,
                        'session': session.session_number,
                        'count': question_count
                    })
            
            self.stdout.write(f'\n🎯 Sessions Ready for Testing: {len(sessions_with_questions)}')
            
            # Show top sessions by question count
            top_sessions = sorted(sessions_with_questions, key=lambda x: x['count'], reverse=True)[:10]
            for session_info in top_sessions:
                self.stdout.write(
                    f'   LS{session_info["lok_sabha"]} Session{session_info["session"]}: '
                    f'{session_info["count"]:,} questions'
                )
            
            if len(sessions_with_questions) > 10:
                self.stdout.write(f'   ... and {len(sessions_with_questions) - 10} more sessions')
            
            self.stdout.write(f'\n💡 Usage Examples:')
            self.stdout.write(f'   # Test any session:')
            if top_sessions:
                top = top_sessions[0]
                self.stdout.write(f'   curl -X POST "http://localhost:8000/api/questions/sessions/" -H "Content-Type: application/json" -H "Authorization: Token YOUR_TOKEN" -d \'{{"lok_sabha_number": "{top["lok_sabha"]}", "session_number": "{top["session"]}", "question_count": 20, "download_pdfs": true}}\'')
            
        except Exception as e:
            self.stdout.write(
                self.style.WARNING(f"⚠️ Failed to get statistics: {str(e)}")
            )