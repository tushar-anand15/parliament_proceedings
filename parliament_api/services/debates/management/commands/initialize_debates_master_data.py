import sys
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from services.debates.debate_master_data_service import DebateMasterDataService
from services.debates.uncorrected_debate_master_data_service import UncorrectedDebateMasterDataService
from services.debates.models import DebateMasterData
from services.questions.models import Session, LokSabha


class Command(BaseCommand):
    help = 'Initialize debate master data (CORRECTED and UNCORRECTED) by fetching all available session dates from Parliament APIs'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--force-update',
            action='store_true',
            help='Force update even if master data already exists',
        )
        parser.add_argument(
            '--lok-sabha',
            type=str,
            help='Initialize data for specific Lok Sabha only (e.g., "18")',
        )
        parser.add_argument(
            '--session',
            type=str,
            help='Initialize data for specific session only (e.g., "5"). Must be used with --lok-sabha',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be done without actually doing it',
        )
        parser.add_argument(
            '--corrected-only',
            action='store_true',
            help='Initialize only CORRECTED debates (skip uncorrected)',
        )
        parser.add_argument(
            '--uncorrected-only',
            action='store_true',
            help='Initialize only UNCORRECTED debates (skip corrected)',
        )
    
    def handle(self, *args, **options):
        # Suppress INFO logs during initialization (only show WARNING and above)
        import logging
        logging.getLogger('services.debates.debate_master_data_service').setLevel(logging.WARNING)
        try:
            self.stdout.write(
                self.style.SUCCESS('🏛️ Parliament Debates Master Data Initialization')
            )
            self.stdout.write('=' * 60)
            
            # Validate arguments
            if options['session'] and not options['lok_sabha']:
                raise CommandError("--session option requires --lok-sabha to be specified")
            
            # Initialize service
            service = DebateMasterDataService()
            
            # Check current state
            existing_count = DebateMasterData.objects.count()
            total_sessions = Session.objects.count()
            
            self.stdout.write(f"📊 Current State:")
            self.stdout.write(f"   • Total Sessions in DB: {total_sessions}")
            self.stdout.write(f"   • Existing Debate Master Data: {existing_count}")
            
            if options['dry_run']:
                self.stdout.write(
                    self.style.WARNING('\n🔍 DRY RUN MODE - No changes will be made')
                )
            
            # Handle specific Lok Sabha/Session
            if options['lok_sabha']:
                if options['session']:
                    self._handle_specific_session(service, options)
                else:
                    self._handle_specific_lok_sabha(service, options)
            else:
                self._handle_all_sessions(service, options)
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'❌ Command failed: {str(e)}')
            )
            if options.get('verbosity', 1) >= 2:
                import traceback
                self.stdout.write(traceback.format_exc())
            sys.exit(1)
    
    def _handle_all_sessions(self, service, options):
        """Handle initialization for all sessions - BOTH corrected and uncorrected"""
        
        corrected_service = service  # DebateMasterDataService
        uncorrected_service = UncorrectedDebateMasterDataService()
        
        skip_corrected = options.get('uncorrected_only', False)
        skip_uncorrected = options.get('corrected_only', False)
        
        if not options['force_update']:
            existing_count = DebateMasterData.objects.count()
            if existing_count > 0:
                self.stdout.write(
                    self.style.WARNING(
                        f'\n⚠️  Debate master data already exists ({existing_count} records)'
                    )
                )
                self.stdout.write('Use --force-update to refresh from server')
                return
        
        if options['dry_run']:
            if not skip_corrected:
                self.stdout.write('\n🔍 Would initialize CORRECTED debate master data')
            if not skip_uncorrected:
                self.stdout.write('🔍 Would initialize UNCORRECTED debate master data')
            return
        
        # Initialize CORRECTED debates
        if not skip_corrected:
            self.stdout.write('\n🚀 PHASE 1: Initializing CORRECTED debate master data...')
            
            import io
            from contextlib import redirect_stdout
            
            with redirect_stdout(io.StringIO()) as f:
                corrected_result = corrected_service.initialize_debate_master_data(
                    force_update=options['force_update']
                )
            
            output = f.getvalue()
            for line in output.strip().split('\n'):
                if line.strip():
                    self.stdout.write(f'   {line}')
            
            self.stdout.write(self.style.SUCCESS('✅ CORRECTED debates master data initialized'))
        
        # Initialize UNCORRECTED debates
        if not skip_uncorrected:
            self.stdout.write('\n🚀 PHASE 2: Initializing UNCORRECTED debate master data (includes PDF URLs)...')
            
            try:
                uncorrected_result = uncorrected_service.fetch_uncorrected_master_data_for_all_sessions()
                
                self.stdout.write(f'\n📊 Uncorrected Debates Results:')
                self.stdout.write(f'   • Sessions processed: {uncorrected_result.get("processed_sessions", 0)}/{uncorrected_result.get("total_sessions", 0)}')
                self.stdout.write(f'   • Master data created: {uncorrected_result.get("total_created", 0)}')
                self.stdout.write(f'   • Master data updated: {uncorrected_result.get("total_updated", 0)}')
                self.stdout.write(f'   • Total dates: {uncorrected_result.get("total_dates", 0)}')
                self.stdout.write(f'   • Total PDF files: {uncorrected_result.get("total_pdf_files", 0)}')
                
                errors = uncorrected_result.get('errors', [])
                if errors:
                    self.stdout.write(f'   • Errors: {len(errors)}')
                    for error in errors[:3]:
                        self.stdout.write(f'     - {error}')
                    if len(errors) > 3:
                        self.stdout.write(f'     ... and {len(errors) - 3} more')
                
                self.stdout.write(self.style.SUCCESS('✅ UNCORRECTED debates master data initialized'))
                
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'❌ Uncorrected debates initialization failed: {e}'))
        
        self.stdout.write(self.style.SUCCESS('\n🎉 Debate master data initialization completed!'))
    
    def _handle_specific_lok_sabha(self, service, options):
        """Handle initialization for specific Lok Sabha"""
        
        lok_sabha_number = options['lok_sabha']
        
        try:
            from services.questions.models import LokSabha
            lok_sabha = LokSabha.objects.get(number=lok_sabha_number)
            sessions = Session.objects.filter(lok_sabha=lok_sabha)
            
            if not sessions.exists():
                raise CommandError(f"No sessions found for Lok Sabha {lok_sabha_number}")
            
            self.stdout.write(f'\n🎯 Processing Lok Sabha {lok_sabha_number} ({sessions.count()} sessions)')
            
            if options['dry_run']:
                for session in sessions:
                    self.stdout.write(f'   Would process: LS{lok_sabha_number} Session {session.session_number}')
                return
            
            processed = 0
            errors = []
            
            for session in sessions:
                try:
                    self.stdout.write(f'   Processing LS{lok_sabha_number} Session {session.session_number}...')
                    
                    result = service.fetch_debate_dates_for_session(
                        lok_sabha_number,
                        session.session_number
                    )
                    
                    dates_count = result.get('dates_count', 0)
                    self.stdout.write(
                        self.style.SUCCESS(f'     ✅ {dates_count} debate dates found')
                    )
                    processed += 1
                    
                except Exception as e:
                    error_msg = f'LS{lok_sabha_number} Session {session.session_number}: {str(e)}'
                    errors.append(error_msg)
                    self.stdout.write(
                        self.style.ERROR(f'     ❌ {error_msg}')
                    )
            
            # Print summary
            self.stdout.write(f'\n📊 Summary for Lok Sabha {lok_sabha_number}:')
            self.stdout.write(f'   • Processed: {processed}/{sessions.count()} sessions')
            if errors:
                self.stdout.write(f'   • Errors: {len(errors)}')
                for error in errors[:3]:  # Show first 3 errors
                    self.stdout.write(f'     - {error}')
                if len(errors) > 3:
                    self.stdout.write(f'     ... and {len(errors) - 3} more')
            
        except LokSabha.DoesNotExist:
            raise CommandError(f"Lok Sabha {lok_sabha_number} not found in database")
    
    def _handle_specific_session(self, service, options):
        """Handle initialization for specific session"""
        
        lok_sabha_number = options['lok_sabha']
        session_number = options['session']
        
        try:
            from services.questions.models import LokSabha
            lok_sabha = LokSabha.objects.get(number=lok_sabha_number)
            session = Session.objects.get(lok_sabha=lok_sabha, session_number=session_number)
            
            self.stdout.write(f'\n🎯 Processing LS{lok_sabha_number} Session {session_number}')
            
            if options['dry_run']:
                self.stdout.write(f'   Would process: LS{lok_sabha_number} Session {session_number}')
                return
            
            result = service.fetch_debate_dates_for_session(
                lok_sabha_number,
                session_number
            )
            
            dates_count = result.get('dates_count', 0)
            api_sources = result.get('api_sources_used', [])
            date_range = result.get('date_range', {})
            
            self.stdout.write(
                self.style.SUCCESS(f'✅ Successfully processed LS{lok_sabha_number} Session {session_number}')
            )
            self.stdout.write(f'   • Debate dates found: {dates_count}')
            self.stdout.write(f'   • Date range: {date_range.get("start", "N/A")} to {date_range.get("end", "N/A")}')
            self.stdout.write(f'   • API sources used: {", ".join(api_sources)}')
            self.stdout.write(f'   • Created new record: {"Yes" if result.get("created") else "No"}')
            
        except LokSabha.DoesNotExist:
            raise CommandError(f"Lok Sabha {lok_sabha_number} not found in database")
        except Session.DoesNotExist:
            raise CommandError(f"Session {session_number} not found for Lok Sabha {lok_sabha_number}")
    
    def _print_results(self, result):
        """Print initialization results"""
        
        status = result.get('status', 'UNKNOWN')
        
        if status == 'ALREADY_EXISTS':
            self.stdout.write(
                self.style.WARNING(f'\n⚠️  {result.get("message", "Already exists")}')
            )
            return
        
        self.stdout.write(f'\n📊 Initialization Results:')
        self.stdout.write(f'   • Status: {status}')
        
        if 'debate_result' in result:
            debate_result = result['debate_result']
            self.stdout.write(f'   • Sessions processed: {debate_result.get("processed_sessions", 0)}/{debate_result.get("total_sessions", 0)}')
            self.stdout.write(f'   • Master data created: {debate_result.get("total_created", 0)}')
            self.stdout.write(f'   • Master data updated: {debate_result.get("total_updated", 0)}')
            
            errors = debate_result.get('errors', [])
            if errors:
                self.stdout.write(f'   • Errors: {len(errors)}')
                # Show first few errors
                for error in errors[:3]:
                    self.stdout.write(f'     - {error}')
                if len(errors) > 3:
                    self.stdout.write(f'     ... and {len(errors) - 3} more')
        
        self.stdout.write(f'   • Total sessions in DB: {result.get("total_sessions", 0)}')
        self.stdout.write(f'   • Total debate metadata: {result.get("total_debate_metadata", 0)}')
        
        if status == 'SUCCESS':
            self.stdout.write(
                self.style.SUCCESS(f'\n🎉 {result.get("message", "Completed successfully")}')
            )
        elif status == 'PARTIAL_SUCCESS':
            self.stdout.write(
                self.style.WARNING(f'\n⚠️  {result.get("message", "Completed with some errors")}')
            )
        
        # Show usage examples
        self.stdout.write(f'\n💡 Next Steps:')
        self.stdout.write(f'   • View statistics: python manage.py shell -c "from services.debates.debate_master_data_service import DebateMasterDataService; print(DebateMasterDataService().get_debate_master_data_statistics())"')
        self.stdout.write(f'   • Start debate scraping: Use the debates API endpoints')
        self.stdout.write(f'   • Check admin panel: /admin/debates/debatemasterdata/')
