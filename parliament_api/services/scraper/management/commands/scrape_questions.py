from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from services.scraper.scraper_service import ParliamentQuestionsScraperService
from services.questions.models import Question, LokSabha


class Command(BaseCommand):
    help = 'Scrape parliamentary questions from the API'

    def add_arguments(self, parser):
        parser.add_argument(
            '--loksabha',
            type=str,
            default='17',
            help='Lok Sabha number to scrape (default: 17)'
        )
        parser.add_argument(
            '--session',
            type=str,
            help='Session number to scrape (optional)'
        )
        parser.add_argument(
            '--force-update',
            action='store_true',
            help='Force update existing records'
        )
        parser.add_argument(
            '--check-only',
            action='store_true',
            help='Only check for updates, do not scrape'
        )
        parser.add_argument(
            '--stats',
            action='store_true',
            help='Show database statistics'
        )

    def handle(self, *args, **options):
        loksabha_no = options['loksabha']
        session_no = options['session']
        force_update = options['force_update']
        check_only = options['check_only']
        show_stats = options['stats']

        self.stdout.write(
            self.style.SUCCESS(f'🏛️ Parliament Questions Scraper')
        )
        self.stdout.write(f'Target: {loksabha_no}th Lok Sabha' + 
                         (f' Session {session_no}' if session_no else ''))

        try:
            service = ParliamentQuestionsScraperService()

            # Show statistics if requested
            if show_stats:
                self._show_database_stats()
                return

            # Check for updates
            update_info = service.check_for_updates(loksabha_no, session_no)
            
            self.stdout.write(f'\n📊 Update Check Results:')
            self.stdout.write(f'   Database: {update_info["database_count"]} questions')
            self.stdout.write(f'   API:      {update_info["api_count"]} questions')
            self.stdout.write(f'   Difference: {update_info["difference"]} new questions')
            
            if update_info['new_questions_available']:
                self.stdout.write(
                    self.style.WARNING(f'   ⚠️ New questions available!')
                )
            else:
                self.stdout.write(
                    self.style.SUCCESS(f'   ✅ Database is up to date')
                )

            # If only checking, return here
            if check_only:
                return

            # Start scraping if new questions are available or force update is requested
            if update_info['new_questions_available'] or force_update:
                self.stdout.write(f'\n🚀 Starting scraping process...')
                
                start_time = timezone.now()
                job = service.start_scraping(
                    loksabha_no=loksabha_no,
                    session_no=session_no,
                    force_update=force_update
                )
                end_time = timezone.now()
                
                duration = end_time - start_time
                
                self.stdout.write(
                    self.style.SUCCESS(f'\n✅ Scraping completed successfully!')
                )
                self.stdout.write(f'   Job ID: {job.id}')
                self.stdout.write(f'   Status: {job.status}')
                self.stdout.write(f'   Questions processed: {job.questions_processed}')
                self.stdout.write(f'   Questions created: {job.questions_created}')
                self.stdout.write(f'   Questions updated: {job.questions_updated}')
                self.stdout.write(f'   Questions failed: {job.questions_failed}')
                self.stdout.write(f'   Duration: {duration.total_seconds():.2f} seconds')
                
            else:
                self.stdout.write(f'\n⏭️ No scraping needed - database is already up to date')
                self.stdout.write(f'   Use --force-update to update existing records')

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'\n❌ Scraping failed: {str(e)}')
            )
            raise CommandError(f'Scraping failed: {str(e)}')

    def _show_database_stats(self):
        """Show detailed database statistics"""
        total_questions = Question.objects.count()
        
        self.stdout.write(f'\n📈 Database Statistics:')
        self.stdout.write(f'   Total Questions: {total_questions}')
        
        # Questions by Lok Sabha
        self.stdout.write(f'\n   By Lok Sabha:')
        for loksabha in LokSabha.objects.all().order_by('-number'):
            count = Question.objects.filter(lok_sabha=loksabha).count()
            if count > 0:
                current_marker = ' (current)' if loksabha.is_current else ''
                self.stdout.write(f'      {loksabha.number}th LS: {count} questions{current_marker}')
        
        # Questions by type
        from django.db.models import Count
        type_stats = Question.objects.values('question_type').annotate(
            count=Count('id')
        ).order_by('-count')
        
        if type_stats:
            self.stdout.write(f'\n   By Question Type:')
            for stat in type_stats:
                self.stdout.write(f'      {stat["question_type"]}: {stat["count"]}')
        
        # Recent activity
        from datetime import timedelta
        week_ago = timezone.now() - timedelta(days=7)
        recent_count = Question.objects.filter(last_scraped__gte=week_ago).count()
        
        self.stdout.write(f'\n   Recent Activity:')
        self.stdout.write(f'      Questions scraped in last 7 days: {recent_count}') 