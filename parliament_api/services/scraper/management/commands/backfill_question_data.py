from django.core.management.base import BaseCommand
from django.db import transaction
from services.questions.models import Question, Session, LokSabha
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Backfill existing questions with new fields from raw_api_data'
    
    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Show what would be updated without making changes')
        parser.add_argument('--limit', type=int, help='Limit number of questions to process')
    
    def handle(self, *args, **options):
        dry_run = options.get('dry_run', False)
        limit = options.get('limit')
        
        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN MODE - No changes will be made"))
        
        # Get questions that have raw_api_data but missing new fields
        queryset = Question.objects.filter(
            raw_api_data__isnull=False
        ).exclude(
            api_resource_id__isnull=False,
            api_resource_id__gt=''
        )
        
        if limit:
            queryset = queryset[:limit]
        
        total_questions = queryset.count()
        self.stdout.write(f"Found {total_questions} questions to backfill")
        
        if total_questions == 0:
            self.stdout.write(self.style.SUCCESS("No questions need backfilling"))
            return
        
        updated_count = 0
        session_created_count = 0
        
        for i, question in enumerate(queryset, 1):
            try:
                with transaction.atomic():
                    api_data = question.raw_api_data
                    if not api_data:
                        continue
                    
                    # Extract and update fields
                    updates = {}
                    
                    # API Resource ID
                    if api_data.get('resourceId'):
                        updates['api_resource_id'] = api_data['resourceId']
                    
                    # Document metadata
                    if api_data.get('type'):
                        updates['document_type'] = api_data['type']
                    if api_data.get('language'):
                        updates['language'] = api_data['language']
                    if api_data.get('year'):
                        updates['year'] = str(api_data['year'])
                    if api_data.get('handle'):
                        updates['document_handle'] = api_data['handle']
                    
                    # PDF files
                    if api_data.get('files') and isinstance(api_data['files'], list):
                        updates['pdf_files'] = api_data['files']
                    
                    # Minister names
                    if api_data.get('ministerName') and isinstance(api_data['ministerName'], list):
                        updates['minister_names'] = api_data['ministerName']
                    
                    # Additional metadata
                    if api_data.get('councilOfStateNo'):
                        updates['council_of_state_no'] = api_data['councilOfStateNo']
                    if api_data.get('committeeName'):
                        updates['committee_name'] = api_data['committeeName']
                    if api_data.get('assemblyNo'):
                        updates['assembly_no'] = api_data['assemblyNo']
                    if api_data.get('debate'):
                        updates['debate'] = api_data['debate']
                    if api_data.get('reportNo'):
                        updates['report_no'] = api_data['reportNo']
                    if api_data.get('youtubeURL'):
                        updates['youtube_url'] = api_data['youtubeURL']
                    if api_data.get('source'):
                        updates['source'] = api_data['source']
                    
                    # Handle session if missing
                    if not question.session and api_data.get('sessionNo'):
                        session_no = api_data['sessionNo']
                        try:
                            session, created = Session.objects.get_or_create(
                                lok_sabha=question.lok_sabha,
                                session_number=session_no
                            )
                            if created:
                                session_created_count += 1
                                if not dry_run:
                                    self.stdout.write(f"Created session: {question.lok_sabha}th LS Session {session_no}")
                            updates['session'] = session
                        except Exception as e:
                            self.stdout.write(self.style.ERROR(f"Error creating session for question {question.id}: {e}"))
                    
                    # Apply updates
                    if updates and not dry_run:
                        for field, value in updates.items():
                            setattr(question, field, value)
                        question.save(update_fields=list(updates.keys()))
                        updated_count += 1
                    elif updates and dry_run:
                        updated_count += 1
                        if i <= 5:  # Show first 5 as examples
                            self.stdout.write(f"Would update Q{question.question_number}: {list(updates.keys())}")
                    
                    # Progress update
                    if i % 1000 == 0:
                        self.stdout.write(f"Processed {i}/{total_questions} questions...")
                        
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Error processing question {question.id}: {e}"))
        
        if dry_run:
            self.stdout.write(self.style.SUCCESS(
                f"DRY RUN COMPLETE: Would update {updated_count} questions and create {session_created_count} sessions"
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                f"BACKFILL COMPLETE: Updated {updated_count} questions and created {session_created_count} sessions"
            )) 