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
            default=5,
            help='Number of recent sessions for verbatim (0=all, default: 5)'
        )
        
        parser.add_argument(
            '--official-sessions',
            type=int,
            default=10,
            help='Number of recent sessions to analyze for official (default: 10)'
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
        
        self.stdout.write(self.style.SUCCESS('🏛️  Initializing RS Debates Master Data'))
        self.stdout.write('')
        
        service = RSDebateMasterDataService()
        
        if verbatim_only:
            # Only verbatim
            self.stdout.write(self.style.WARNING('📝 Initializing VERBATIM debates only...'))
            result = service.initialize_verbatim_master_data(
                force_update=force,
                max_workers=workers,
                recent_sessions_only=recent_sessions
            )
            
            self._print_verbatim_results(result)
            
        elif official_only:
            # Only official
            self.stdout.write(self.style.WARNING('📚 Initializing OFFICIAL debates only...'))
            result = service.initialize_official_master_data(
                force_update=force,
                recent_sessions_count=official_sessions
            )
            
            self._print_official_results(result)
            
        else:
            # Both (default)
            self.stdout.write(self.style.WARNING('📋 Initializing BOTH verbatim and official debates...'))
            result = service.initialize_complete_rs_master_data(
                force_update=force,
                verbatim_workers=workers,
                verbatim_recent_only=recent_sessions,
                official_recent_sessions=official_sessions
            )
            
            self._print_complete_results(result)
    
    def _print_verbatim_results(self, result: dict):
        """Print verbatim results"""
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('📝 VERBATIM DEBATES RESULTS:'))
        self.stdout.write(f"   Status: {result['status']}")
        self.stdout.write(f"   Sessions Processed: {result['sessions_processed']}")
        self.stdout.write(f"   Dates Processed: {result['dates_processed']}")
        self.stdout.write(f"   Debates Discovered: {result['debates_discovered']}")
        
        if result.get('errors'):
            self.stdout.write(self.style.ERROR(f"   Errors: {len(result['errors'])}"))
            for error in result['errors'][:5]:  # Show first 5 errors
                self.stdout.write(f"      • {error}")
        else:
            self.stdout.write(self.style.SUCCESS('   ✓ No errors'))
    
    def _print_official_results(self, result: dict):
        """Print official results"""
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('📚 OFFICIAL DEBATES RESULTS:'))
        self.stdout.write(f"   Status: {result['status']}")
        self.stdout.write(f"   Years Available: {result['years_available']} (1952-2024)")
        self.stdout.write(f"   Sessions Available: {result['sessions_available']}")
        self.stdout.write(f"   Total Debates: {result['total_debates']:,}")
        self.stdout.write(f"      • Part 1 (Q&A): {result['part1_debates']:,}")
        self.stdout.write(f"      • Part 2 (Other): {result['part2_debates']:,}")
        
        if result.get('recent_sessions'):
            self.stdout.write('')
            self.stdout.write('   Recent Sessions:')
            for session in result['recent_sessions'][:5]:
                self.stdout.write(f"      • Session {session['session_no']}: {session['debate_count']:,} debates")
        
        if result.get('errors'):
            self.stdout.write(self.style.ERROR(f"   Errors: {len(result['errors'])}"))
        else:
            self.stdout.write(self.style.SUCCESS('   ✓ No errors'))
    
    def _print_complete_results(self, result: dict):
        """Print complete results"""
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('='*60))
        self.stdout.write(self.style.SUCCESS('COMPLETE RS DEBATES MASTER DATA INITIALIZATION'))
        self.stdout.write(self.style.SUCCESS('='*60))
        
        # Verbatim section
        verbatim = result.get('verbatim', {})
        self._print_verbatim_results(verbatim)
        
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
