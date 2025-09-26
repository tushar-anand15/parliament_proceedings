from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from services.debates.debate_scraper_service import DebateScraperService
from services.debates.models import Debate


class Command(BaseCommand):
    help = 'Scrape parliamentary debates from the API'

    def add_arguments(self, parser):
        parser.add_argument(
            '--loksabha',
            type=str,
            required=True,
            help='Lok Sabha number (e.g., "18")'
        )
        parser.add_argument(
            '--session',
            type=str,
            required=True,
            help='Session number (e.g., "V")'
        )
        parser.add_argument(
            '--start-date',
            type=str,
            help='Start date in YYYY-MM-DD format'
        )
        parser.add_argument(
            '--end-date',
            type=str,
            help='End date in YYYY-MM-DD format'
        )
        parser.add_argument(
            '--no-download',
            action='store_true',
            help='Skip PDF downloads (only fetch metadata)'
        )
        parser.add_argument(
            '--stats',
            action='store_true',
            help='Show debate statistics'
        )
        parser.add_argument(
            '--download-pending',
            action='store_true',
            help='Download all pending debate PDFs'
        )

    def handle(self, *args, **options):
        loksabha_no = options['loksabha']
        session_no = options['session']
        start_date = options['start_date']
        end_date = options['end_date']
        no_download = options['no_download']
        show_stats = options['stats']
        download_pending = options['download_pending']

        self.stdout.write(
            self.style.SUCCESS(f'🏛️ Parliament Debates Scraper')
        )

        try:
            service = DebateScraperService()

            # Show statistics if requested
            if show_stats:
                self._show_debate_stats(service, loksabha_no, session_no)
                return

            # Download pending PDFs if requested
            if download_pending:
                self._download_pending_pdfs(service)
                return

            # Start scraping
            self.stdout.write(f'Target: {loksabha_no}th Lok Sabha Session {session_no}')
            if start_date:
                self.stdout.write(f'Start Date: {start_date}')
            if end_date:
                self.stdout.write(f'End Date: {end_date}')
            self.stdout.write(f'Download PDFs: {"No" if no_download else "Yes"}')

            self.stdout.write(f'\n🚀 Starting debate scraping process...')
            
            start_time = timezone.now()
            job = service.start_debate_scraping(
                loksabha_no=loksabha_no,
                session_no=session_no,
                start_date=start_date,
                end_date=end_date,
                download_pdfs=not no_download
            )
            
            self.stdout.write(
                self.style.SUCCESS(f'\n✅ Scraping job started successfully!')
            )
            self.stdout.write(f'   Job ID: {job.id}')
            self.stdout.write(f'   Status: {job.status}')
            self.stdout.write(f'   Note: Job is running in background. Check status with --stats')

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'\n❌ Scraping failed: {str(e)}')
            )
            raise CommandError(f'Scraping failed: {str(e)}')

    def _show_debate_stats(self, service, loksabha_no=None, session_no=None):
        """Show detailed debate statistics"""
        stats = service.get_debate_statistics(loksabha_no, session_no)
        
        self.stdout.write(f'\n📈 Debate Statistics:')
        self.stdout.write(f'   Total Debates: {stats["total_debates"]}')
        self.stdout.write(f'   Downloaded: {stats["downloaded_debates"]} ({stats["download_percentage"]}%)')
        self.stdout.write(f'   Pending: {stats["pending_debates"]}')
        self.stdout.write(f'   Failed: {stats["failed_debates"]}')
        
        if stats['date_range']['earliest_date']:
            self.stdout.write(f'\n   Date Range:')
            self.stdout.write(f'      From: {stats["date_range"]["earliest_date"]}')
            self.stdout.write(f'      To: {stats["date_range"]["latest_date"]}')
        
        self.stdout.write(f'\n   Storage:')
        self.stdout.write(f'      Total Size: {stats["total_size_mb"]} MB')
        self.stdout.write(f'      Average Size: {stats["average_size_mb"]} MB per debate')

    def _download_pending_pdfs(self, service):
        """Download all pending PDFs"""
        pending_debates = Debate.objects.filter(
            status='pending',
            pdf_url__isnull=False
        ).exclude(pdf_url='')
        
        count = pending_debates.count()
        
        if count == 0:
            self.stdout.write(self.style.WARNING('No pending debates to download'))
            return
        
        self.stdout.write(f'\n📥 Found {count} pending debates to download')
        
        for i, debate in enumerate(pending_debates, 1):
            self.stdout.write(f'\nDownloading {i}/{count}: {debate.debate_id}')
            
            success = service.download_debate_pdf(debate)
            
            if success:
                self.stdout.write(self.style.SUCCESS(f'   ✅ Downloaded successfully ({debate.file_size_mb} MB)'))
            else:
                self.stdout.write(self.style.ERROR(f'   ❌ Download failed: {debate.error_message}'))
        
        self.stdout.write(f'\n✅ Download process completed')
