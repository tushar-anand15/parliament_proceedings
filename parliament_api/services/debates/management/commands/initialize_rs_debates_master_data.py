"""
Management command to initialize RS debates master data
Fetches metadata for both verbatim and official RS debates
"""

from django.core.management.base import BaseCommand
from services.debates.rs_debate_master_data_service import RSDebateMasterDataService
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Initialize RS debates master data (verbatim + official)'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force refresh data even if it exists'
        )
        
        parser.add_argument(
            '--verbatim-only',
            action='store_true',
            help='Initialize only verbatim debates'
        )
        
        parser.add_argument(
            '--official-only',
            action='store_true',
            help='Initialize only official debates'
        )
        
        parser.add_argument(
            '--workers',
            type=int,
            default=10,
            help='Number of parallel workers for verbatim debates (default: 10)'
        )
        
        parser.add_argument(
            '--recent-sessions',
            type=int,
            default=0,
            help='Number of recent sessions for verbatim (0=ALL 80 sessions, default: 0)'
        )
        
        parser.add_argument(
            '--official-sessions',
            type=int,
            default=0,
            help='Number of sessions for official (0=ALL 265 sessions with FULL metadata, default: 0)'
        )
        
        parser.add_argument(
            '--verbatim-batch-size',
            type=int,
            default=10,
            help='Number of sessions per batch for verbatim processing (default: 10)'
        )
        
        parser.add_argument(
            '--official-batch-size',
            type=int,
            default=5,
            help='Number of sessions per batch for official processing (default: 5)'
        )
    
    def handle(self, *args, **options):
        # Suppress INFO logs during initialization (only show WARNING and above)
        import logging
        logging.getLogger('services.debates.rs_debate_master_data_service').setLevel(logging.WARNING)
        force = options['force']
        verbatim_only = options['verbatim_only']
        official_only = options['official_only']
        workers = options['workers']
        recent_sessions = options['recent_sessions']
        official_sessions = options['official_sessions']
        verbatim_batch_size = options['verbatim_batch_size']
        official_batch_size = options['official_batch_size']
        
        self.stdout.write(self.style.SUCCESS('🏛️  Initializing RS Debates Master Data'))
        self.stdout.write('')
        
        service = RSDebateMasterDataService()
        
        if verbatim_only:
            # Only verbatim
            self.stdout.write(self.style.WARNING('📝 Initializing VERBATIM debates only...'))
            result = service.initialize_verbatim_master_data(
                force_update=force,
                max_workers=workers,
                recent_sessions_only=recent_sessions,
                batch_size=verbatim_batch_size
            )
            
            self._print_verbatim_results(result)
            
        elif official_only:
            # Only official
            self.stdout.write(self.style.WARNING('📚 Initializing OFFICIAL debates only...'))
            result = service.initialize_official_master_data(
                force_update=force,
                recent_sessions_count=official_sessions,
                batch_size=official_batch_size
            )
            
            self._print_official_results(result)
            
        else:
            # Both (default)
            self.stdout.write(self.style.WARNING('📋 Initializing BOTH verbatim and official debates...'))
            result = service.initialize_complete_rs_master_data(
                force_update=force,
                verbatim_workers=workers,
                verbatim_recent_only=recent_sessions,
                official_recent_sessions=official_sessions,
                verbatim_batch_size=verbatim_batch_size,
                official_batch_size=official_batch_size
            )
            
            self._print_complete_results(result)
    
    def _print_verbatim_results(self, result: dict):
        """Print verbatim results"""
        status = result.get('status', 'UNKNOWN')
        if status == 'SUCCESS':
            self.stdout.write(self.style.SUCCESS(f'✅ Verbatim initialization complete'))
        else:
            self.stdout.write(self.style.WARNING(f'⚠️ Verbatim initialization: {status}'))
        
        self.stdout.write(f"   Sessions processed: {result.get('sessions_processed', 0)}")
        self.stdout.write(f"   Dates processed: {result.get('dates_processed', 0)}")
        self.stdout.write(f"   Debates discovered: {result.get('debates_discovered', 0)}")
        self.stdout.write(f"   Master records created: {result.get('master_records_created', 0)}")
        self.stdout.write(f"   Master records updated: {result.get('master_records_updated', 0)}")
        
        errors = result.get('errors', [])
        if errors:
            self.stdout.write(self.style.WARNING(f'   Errors: {len(errors)}'))
            for error in errors[:5]:  # Show first 5 errors
                self.stdout.write(f'     - {error}')
    
    def _print_official_results(self, result: dict):
        """Print official results"""
        status = result.get('status', 'UNKNOWN')
        if status == 'SUCCESS':
            self.stdout.write(self.style.SUCCESS(f'✅ Official initialization complete'))
        else:
            self.stdout.write(self.style.WARNING(f'⚠️ Official initialization: {status}'))
        
        self.stdout.write(f"   Years available: {result.get('years_available', 0)}")
        self.stdout.write(f"   Sessions available: {result.get('sessions_available', 0)}")
        self.stdout.write(f"   Total debates: {result.get('total_debates', 0):,}")
        self.stdout.write(f"   Part 1 debates: {result.get('part1_debates', 0):,}")
        self.stdout.write(f"   Part 2 debates: {result.get('part2_debates', 0):,}")
        self.stdout.write(f"   Master records created: {result.get('master_records_created', 0)}")
        self.stdout.write(f"   Master records updated: {result.get('master_records_updated', 0)}")
        
        errors = result.get('errors', [])
        if errors:
            self.stdout.write(self.style.WARNING(f'   Errors: {len(errors)}'))
            for error in errors[:5]:  # Show first 5 errors
                self.stdout.write(f'     - {error}')
    
    def _print_complete_results(self, result: dict):
        """Print combined results"""
        status = result.get('status', 'UNKNOWN')
        if status == 'SUCCESS':
            self.stdout.write(self.style.SUCCESS(f'\n✅ Complete RS Debates initialization finished'))
        else:
            self.stdout.write(self.style.WARNING(f'\n⚠️ Complete RS Debates initialization: {status}'))
        
        # Verbatim results
        self.stdout.write(self.style.WARNING('\n📝 Verbatim Results:'))
        verbatim = result.get('verbatim', {})
        self.stdout.write(f"   Sessions: {verbatim.get('sessions_processed', 0)}")
        self.stdout.write(f"   Dates: {verbatim.get('dates_processed', 0)}")
        self.stdout.write(f"   Debates: {verbatim.get('debates_discovered', 0)}")
        self.stdout.write(f"   DB Records (new/updated): {verbatim.get('master_records_created', 0)}/{verbatim.get('master_records_updated', 0)}")
        
        # Official results
        self.stdout.write(self.style.WARNING('\n📚 Official Results:'))
        official = result.get('official', {})
        self.stdout.write(f"   Sessions: {official.get('sessions_available', 0)}")
        self.stdout.write(f"   Years: {official.get('years_available', 0)}")
        self.stdout.write(f"   Total debates: {official.get('total_debates', 0):,}")
        self.stdout.write(f"   DB Records (new/updated): {official.get('master_records_created', 0)}/{official.get('master_records_updated', 0)}")
        
        # Show aggregate errors
        all_errors = result.get('errors', [])
        if all_errors:
            self.stdout.write(self.style.WARNING(f'\n⚠️ Total errors: {len(all_errors)}'))
            for error in all_errors[:10]:  # Show first 10 errors
                self.stdout.write(f'   - {error}')
        
        # Show database totals
        from services.debates.models import DebateMasterData
        from services.questions.models import ParliamentInstitution
        
        try:
            rs_institution = ParliamentInstitution.objects.get(name='rajya_sabha')
            rs_debate_records = DebateMasterData.objects.filter(parent_institution=rs_institution).count()
            self.stdout.write(self.style.SUCCESS(f'\n📊 Database Summary:'))
            self.stdout.write(f'   Total RS Debate Master Records: {rs_debate_records}')
        except Exception as e:
            self.stdout.write(self.style.WARNING(f'   Could not fetch database summary: {e}'))
        
        # Official section
        official = result.get('official', {})
        self._print_official_results(official)
        
        # Summary
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('='*60))
        self.stdout.write(self.style.SUCCESS('SUMMARY'))
        self.stdout.write(self.style.SUCCESS('='*60))
        self.stdout.write(f"   Overall Status: {result['status']}")
        
        total_errors = len(result.get('errors', []))
        if total_errors > 0:
            self.stdout.write(self.style.ERROR(f"   Total Errors: {total_errors}"))
        else:
            self.stdout.write(self.style.SUCCESS('   ✅ No errors - All data initialized successfully!'))
        
        self.stdout.write('')
