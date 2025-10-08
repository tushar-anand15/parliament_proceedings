# Migration for optimizing sequential batch processing for debates

from django.db import migrations, models


class Migration(migrations.Migration):
    
    dependencies = [
        ('debates', '0010_add_debate_category_to_unique_constraint'),
    ]
    
    operations = [
        # Critical compound indexes for efficient sequential querying
        
        # Index for pending downloads query
        migrations.AddIndex(
            model_name='debate',
            index=models.Index(
                fields=['status', 'debate_date'],
                name='idx_debate_status_date',
            ),
        ),
        
        # Compound index for institution + status + date
        migrations.AddIndex(
            model_name='debate',
            index=models.Index(
                fields=['parent_institution', 'status', 'debate_date'],
                name='idx_debate_inst_status_date',
            ),
        ),
        
        # Index for session-based queries with status
        migrations.AddIndex(
            model_name='debate',
            index=models.Index(
                fields=['lok_sabha', 'session', 'status', 'debate_date'],
                name='idx_debate_session_sequential',
            ),
        ),
        
        # Create materialized view for debate statistics
        migrations.RunSQL(
            sql="""
            CREATE MATERIALIZED VIEW IF NOT EXISTS mv_debate_statistics AS
            SELECT 
                parent_institution_id,
                COUNT(*) as total_debates,
                COUNT(CASE WHEN status = 'completed' THEN 1 END) as completed,
                COUNT(CASE WHEN status = 'pending' THEN 1 END) as pending,
                COUNT(CASE WHEN status = 'downloading' THEN 1 END) as downloading,
                COUNT(CASE WHEN status = 'failed' THEN 1 END) as failed,
                COUNT(CASE WHEN status = 'not_available' THEN 1 END) as not_available,
                -- Category breakdown
                COUNT(CASE WHEN debate_category = 'uncorrected' THEN 1 END) as uncorrected,
                COUNT(CASE WHEN debate_category = 'corrected' THEN 1 END) as corrected,
                COUNT(CASE WHEN debate_category = 'synopsis' THEN 1 END) as synopsis,
                COUNT(CASE WHEN debate_category = 'verbatim' THEN 1 END) as verbatim,
                -- Date range
                MIN(debate_date) as earliest_date,
                MAX(debate_date) as latest_date,
                -- Last update
                NOW() as last_refreshed
            FROM debates_debate
            GROUP BY parent_institution_id
            WITH DATA;
            
            -- Create unique index for concurrent refresh
            CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_debate_stats_inst 
            ON mv_debate_statistics (parent_institution_id);
            
            -- Create function for refreshing the view
            CREATE OR REPLACE FUNCTION refresh_debate_statistics()
            RETURNS void AS $$
            BEGIN
                REFRESH MATERIALIZED VIEW CONCURRENTLY mv_debate_statistics;
            END;
            $$ LANGUAGE plpgsql;
            """,
            
            reverse_sql="""
            DROP MATERIALIZED VIEW IF EXISTS mv_debate_statistics CASCADE;
            DROP FUNCTION IF EXISTS refresh_debate_statistics() CASCADE;
            """,
        ),
    ]
