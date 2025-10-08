# Migration for optimizing sequential batch processing and statistics
# Creates compound indexes using raw SQL for better performance

from django.db import migrations


class Migration(migrations.Migration):
    
    atomic = False  # Required for CREATE INDEX CONCURRENTLY
    
    dependencies = [
        ('questions', '0009_questionmasterdata_metadata_hash'),
    ]
    
    operations = [
        migrations.RunSQL(
            # Create compound indexes for efficient querying
            sql="""
            -- Index for pending downloads query (most important for batch processing)
            CREATE INDEX IF NOT EXISTS idx_qmd_pending_sequential 
            ON questions_questionmasterdata(pdf_downloaded, date, question_number)
            WHERE questions_file_path != '';
            
            -- Compound index for institution + download status
            CREATE INDEX IF NOT EXISTS idx_qmd_inst_pdf_date 
            ON questions_questionmasterdata(parent_institution_id, pdf_downloaded, date);
            
            -- Index for session-based batch queries
            CREATE INDEX IF NOT EXISTS idx_qmd_session_batch 
            ON questions_questionmasterdata(lok_sabha_number, session_number, pdf_downloaded, date);
            
            -- Index for statistics queries (covering index)
            CREATE INDEX IF NOT EXISTS idx_qmd_stats_covering 
            ON questions_questionmasterdata(parent_institution_id, pdf_downloaded, question_type)
            INCLUDE (questions_file_path);
            
            -- Additional index for the most common query pattern
            CREATE INDEX IF NOT EXISTS idx_qmd_inst_pdf_filter
            ON questions_questionmasterdata(parent_institution_id, pdf_downloaded)
            WHERE questions_file_path != '';
            """,
            
            # Reverse SQL - drop indexes
            reverse_sql="""
            DROP INDEX IF EXISTS idx_qmd_pending_sequential;
            DROP INDEX IF EXISTS idx_qmd_inst_pdf_date;
            DROP INDEX IF EXISTS idx_qmd_session_batch;
            DROP INDEX IF EXISTS idx_qmd_stats_covering;
            DROP INDEX IF EXISTS idx_qmd_inst_pdf_filter;
            """,
        ),
    ]
