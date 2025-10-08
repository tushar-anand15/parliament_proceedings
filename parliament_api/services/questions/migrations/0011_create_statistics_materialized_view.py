# Migration to create materialized view for fast statistics queries

from django.db import migrations


class Migration(migrations.Migration):
    
    dependencies = [
        ('questions', '0010_optimize_for_sequential_processing'),
    ]
    
    operations = [
        migrations.RunSQL(
            # Create materialized view for question statistics
            sql="""
            CREATE MATERIALIZED VIEW IF NOT EXISTS mv_question_statistics AS
            SELECT 
                parent_institution_id,
                COUNT(*) as total_questions,
                COUNT(CASE WHEN questions_file_path != '' THEN 1 END) as total_with_pdf,
                COUNT(CASE WHEN pdf_downloaded = true THEN 1 END) as downloaded,
                COUNT(CASE WHEN questions_file_path != '' AND pdf_downloaded = false THEN 1 END) as pending,
                COUNT(CASE WHEN question_type = 'STARRED' THEN 1 END) as starred,
                COUNT(CASE WHEN question_type = 'UNSTARRED' THEN 1 END) as unstarred,
                COUNT(CASE WHEN question_type = 'SHORT_NOTICE' THEN 1 END) as short_notice,
                -- Session-wise aggregates
                COUNT(DISTINCT lok_sabha_number) as unique_lok_sabhas,
                COUNT(DISTINCT session_number) as unique_sessions,
                -- Date range
                MIN(date) as earliest_date,
                MAX(date) as latest_date,
                -- Last update time
                NOW() as last_refreshed
            FROM questions_questionmasterdata
            GROUP BY parent_institution_id
            WITH DATA;
            
            -- Create unique index for concurrent refresh
            CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_question_stats_inst 
            ON mv_question_statistics (parent_institution_id);
            
            -- Create function for refreshing the view
            CREATE OR REPLACE FUNCTION refresh_question_statistics()
            RETURNS void AS $$
            BEGIN
                REFRESH MATERIALIZED VIEW CONCURRENTLY mv_question_statistics;
            END;
            $$ LANGUAGE plpgsql;
            
            -- Create a more detailed session-level materialized view
            CREATE MATERIALIZED VIEW IF NOT EXISTS mv_question_session_statistics AS
            SELECT 
                parent_institution_id,
                lok_sabha_number,
                session_number,
                COUNT(*) as total_questions,
                COUNT(CASE WHEN questions_file_path != '' THEN 1 END) as total_with_pdf,
                COUNT(CASE WHEN pdf_downloaded = true THEN 1 END) as downloaded,
                COUNT(CASE WHEN questions_file_path != '' AND pdf_downloaded = false THEN 1 END) as pending,
                COUNT(CASE WHEN question_type = 'STARRED' THEN 1 END) as starred,
                COUNT(CASE WHEN question_type = 'UNSTARRED' THEN 1 END) as unstarred
            FROM questions_questionmasterdata
            GROUP BY parent_institution_id, lok_sabha_number, session_number
            WITH DATA;
            
            -- Create index for session statistics
            CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_question_session_stats 
            ON mv_question_session_statistics (parent_institution_id, lok_sabha_number, session_number);
            """,
            
            # Reverse SQL - drop materialized views
            reverse_sql="""
            DROP MATERIALIZED VIEW IF EXISTS mv_question_session_statistics CASCADE;
            DROP MATERIALIZED VIEW IF EXISTS mv_question_statistics CASCADE;
            DROP FUNCTION IF EXISTS refresh_question_statistics() CASCADE;
            """,
        ),
    ]
