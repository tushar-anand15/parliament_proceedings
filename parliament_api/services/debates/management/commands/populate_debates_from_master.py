"""
Management command to populate individual Debate records from DebateMasterData
This makes individual debate days queryable in the Data Explorer
"""
from django.core.management.base import BaseCommand
from services.debates.populate_debates_from_master import DebatePopulationService
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Populate individual Debate records from DebateMasterData (makes debate days queryable)'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force update existing debate records'
        )
        parser.add_argument(
            '--institution',
            type=str,
            choices=['lok_sabha', 'rajya_sabha'],
            help='Process only specific institution'
        )
        parser.add_argument(
            '--lok-sabha',
            type=str,
            help='Process only specific Lok Sabha number (e.g., "18")'
        )
        parser.add_argument(
            '--session',
            type=str,
            help='Process only specific session number'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be done without making changes'
        )
    
    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('🏛️  Populating Debate Records from Master Data'))
        self.stdout.write('=' * 70)
        
        service = DebatePopulationService()
        
        # Show current status first
        self.stdout.write('\n📊 Current Status:')
        status = service.get_population_status()
        
        self.stdout.write('\n  Lok Sabha:')
        self.stdout.write(f'    • Master Sessions: {status["lok_sabha"]["master_sessions"]}')
        self.stdout.write(f'    • Available Dates: {status["lok_sabha"]["available_dates"]}')
        self.stdout.write(f'    • Debate Records: {status["lok_sabha"]["debate_records"]}')
        self.stdout.write(f'    • Population: {status["lok_sabha"]["population_percentage"]}%')
        
        self.stdout.write('\n  Rajya Sabha:')
        self.stdout.write(f'    • Master Sessions: {status["rajya_sabha"]["master_sessions"]}')
        self.stdout.write(f'    • Available Dates: {status["rajya_sabha"]["available_dates"]}')
        self.stdout.write(f'    • Debate Records: {status["rajya_sabha"]["debate_records"]}')
        self.stdout.write(f'    • Population: {status["rajya_sabha"]["population_percentage"]}%')
        
        if options['dry_run']:
            self.stdout.write(self.style.WARNING('\n🔍 DRY RUN MODE - No changes will be made'))
            self.stdout.write(f'\nWould create approximately:')
            ls_to_create = status['lok_sabha']['available_dates'] - status['lok_sabha']['debate_records']
            rs_to_create = status['rajya_sabha']['available_dates'] - status['rajya_sabha']['debate_records']
            self.stdout.write(f'  • LS Debate records: {ls_to_create}')
            self.stdout.write(f'  • RS Debate records: {rs_to_create}')
            self.stdout.write(f'  • Total: {ls_to_create + rs_to_create}')
            return
        
        # Run population
        self.stdout.write('\n🚀 Starting population...\n')
        
        result = service.populate_debates_from_master_data(
            force=options['force'],
            institution=options.get('institution'),
            lok_sabha=options.get('lok_sabha'),
            session=options.get('session')
        )
        
        # Print results
        self.stdout.write('\n📊 Population Results:')
        stats = result['statistics']
        self.stdout.write(f'  • Master records processed: {stats["master_records_processed"]}')
        self.stdout.write(f'  • Debates created: {stats["debates_created"]:,}')
        self.stdout.write(f'  • Debates updated: {stats["debates_updated"]:,}')
        self.stdout.write(f'  • Debates skipped: {stats["debates_skipped"]:,}')
        
        if stats['errors']:
            self.stdout.write(self.style.WARNING(f'\n⚠️  Errors encountered: {len(stats["errors"])}'))
            for error in stats['errors'][:5]:
                self.stdout.write(f'    - {error}')
            if len(stats['errors']) > 5:
                self.stdout.write(f'    ... and {len(stats["errors"]) - 5} more')
        
        # Show new status
        self.stdout.write('\n📊 Updated Status:')
        new_status = service.get_population_status()
        
        self.stdout.write('\n  Lok Sabha:')
        self.stdout.write(f'    • Debate Records: {new_status["lok_sabha"]["debate_records"]} ({new_status["lok_sabha"]["population_percentage"]}%)')
        
        self.stdout.write('\n  Rajya Sabha:')
        self.stdout.write(f'    • Debate Records: {new_status["rajya_sabha"]["debate_records"]} ({new_status["rajya_sabha"]["population_percentage"]}%)')
        
        if result['status'] == 'SUCCESS':
            self.stdout.write(self.style.SUCCESS('\n✅ Population completed successfully!'))
        else:
            self.stdout.write(self.style.WARNING('\n⚠️  Population completed with some errors'))
        
        self.stdout.write('\n💡 Next Steps:')
        self.stdout.write('  • View debates in Data Explorer: http://localhost:8000/api/docs/')
        self.stdout.write('  • Test endpoint: curl http://localhost:8000/api/explorer/ls/debates/?limit=10')
        self.stdout.write('  • Start downloading PDFs using the debate scraper')
        self.stdout.write('')
