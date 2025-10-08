# Database Optimization Plan for Parliament API

## Executive Summary
The Parliament API is experiencing severe performance degradation at scale with 1M+ records. This document identifies critical database design flaws and provides a comprehensive optimization strategy.

## Critical Issues Identified

### 1. **FATAL: Random Ordering (`order_by('?')`) at Scale**
**Severity: CRITICAL**
- **Location**: Multiple views using `order_by('?')` for "random" selection
  - `services/questions/master_data_service.py:1029`
  - `services/questions/views.py:808, 1178`
  - `services/debates/views.py:709`
- **Impact**: Forces PostgreSQL to:
  1. Fetch ALL matching rows from disk
  2. Apply RANDOM() to each row
  3. Sort entire result set
  4. Return limited results
- **Performance**: O(n log n) where n = total matching records (potentially 688K+)

### 2. **Missing Critical Indexes**
**Severity: HIGH**
- Compound indexes for frequently filtered columns are missing
- No covering indexes for statistics queries
- Missing indexes on foreign key relationships

### 3. **Inefficient Query Patterns**
**Severity: HIGH**
- Multiple COUNT queries without proper indexes
- Aggregations across large tables without partitioning
- No query result caching for statistics

### 4. **Database Design Issues**
**Severity: MEDIUM**
- Large JSON fields in hot tables
- No table partitioning for time-series data
- Missing database-level constraints

## Optimization Strategy

### Phase 1: Immediate Fixes (1-2 days)

#### 1.1 Replace Random Ordering
Create a new migration to add a random selection field:

```python
# migrations/0010_add_random_selection.py
from django.db import migrations, models
import random

class Migration(migrations.Migration):
    dependencies = [
        ('questions', '0009_questionmasterdata_metadata_hash'),
    ]
    
    operations = [
        # Add random selection field for efficient random ordering
        migrations.AddField(
            model_name='questionmasterdata',
            name='random_selection',
            field=models.FloatField(default=0, db_index=True),
        ),
        migrations.AddField(
            model_name='debate',
            name='random_selection',
            field=models.FloatField(default=0, db_index=True),
        ),
    ]
```

Update the service to use indexed random selection:

```python
# services/questions/master_data_service.py

def get_questions_for_download(self, ...):
    # ... existing code ...
    
    if pending_only:
        queryset = queryset.filter(pdf_downloaded=False)
    
    # REPLACE order_by('?') with efficient random selection
    import random
    random_threshold = random.random()
    
    # This uses the index on random_selection
    queryset = queryset.filter(
        random_selection__gte=random_threshold
    ).order_by('random_selection')
    
    # If we don't get enough results, wrap around
    if limit and queryset.count() < limit:
        remaining = limit - queryset.count()
        wrap_queryset = queryset.filter(
            random_selection__lt=random_threshold
        ).order_by('random_selection')[:remaining]
        queryset = list(queryset) + list(wrap_queryset)
    
    if limit:
        queryset = queryset[:limit]
```

#### 1.2 Add Critical Compound Indexes

```python
# migrations/0011_add_performance_indexes.py
from django.db import migrations, models

class Migration(migrations.Migration):
    operations = [
        # QuestionMasterData indexes
        migrations.AddIndex(
            model_name='questionmasterdata',
            index=models.Index(
                fields=['parent_institution', 'pdf_downloaded', 'questions_file_path'],
                name='idx_qmd_inst_pdf_status'
            ),
        ),
        migrations.AddIndex(
            model_name='questionmasterdata',
            index=models.Index(
                fields=['pdf_downloaded', '-date', 'random_selection'],
                name='idx_qmd_download_queue'
            ),
        ),
        migrations.AddIndex(
            model_name='questionmasterdata',
            index=models.Index(
                fields=['parent_institution', 'lok_sabha_number', 'session_number', 'pdf_downloaded'],
                name='idx_qmd_session_status'
            ),
        ),
        
        # Debate indexes
        migrations.AddIndex(
            model_name='debate',
            index=models.Index(
                fields=['parent_institution', 'status', '-debate_date'],
                name='idx_debate_inst_status'
            ),
        ),
        migrations.AddIndex(
            model_name='debate',
            index=models.Index(
                fields=['status', 'random_selection'],
                name='idx_debate_download_queue'
            ),
        ),
    ]
```

### Phase 2: Query Optimization (2-3 days)

#### 2.1 Implement Materialized Views for Statistics

```sql
-- Create materialized view for real-time statistics
CREATE MATERIALIZED VIEW mv_question_statistics AS
SELECT 
    parent_institution_id,
    COUNT(*) as total_questions,
    COUNT(CASE WHEN questions_file_path != '' THEN 1 END) as total_with_pdf,
    COUNT(CASE WHEN pdf_downloaded = true THEN 1 END) as downloaded,
    COUNT(CASE WHEN questions_file_path != '' AND pdf_downloaded = false THEN 1 END) as pending,
    COUNT(CASE WHEN question_type = 'STARRED' THEN 1 END) as starred,
    COUNT(CASE WHEN question_type = 'UNSTARRED' THEN 1 END) as unstarred
FROM questions_questionmasterdata
GROUP BY parent_institution_id
WITH DATA;

-- Create index on materialized view
CREATE UNIQUE INDEX ON mv_question_statistics (parent_institution_id);

-- Refresh strategy (run every 5 minutes via cron)
CREATE OR REPLACE FUNCTION refresh_question_statistics()
RETURNS void AS $$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY mv_question_statistics;
END;
$$ LANGUAGE plpgsql;
```

Update statistics view to use materialized view:

```python
# services/questions/fast_stats_view.py

class FastDownloadStatsView(APIView):
    def get(self, request):
        # Use raw SQL to query materialized view (instant response)
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    parent_institution_id,
                    total_with_pdf,
                    downloaded,
                    pending
                FROM mv_question_statistics
                WHERE parent_institution_id IN (
                    SELECT id FROM questions_parliamentinstitution 
                    WHERE name IN ('lok_sabha', 'rajya_sabha')
                )
            """)
            results = cursor.fetchall()
            
        # Format results...
```

#### 2.2 Implement Query Result Caching

```python
# services/cache_service.py
from django.core.cache import cache
from django.db.models import Count, Q
import hashlib
import json

class StatisticsCacheService:
    """Caching layer for expensive statistics queries"""
    
    CACHE_TTL = 300  # 5 minutes
    
    @classmethod
    def get_or_compute(cls, key: str, compute_func, ttl=None):
        """Get from cache or compute and cache"""
        cache_key = f"stats:{key}"
        result = cache.get(cache_key)
        
        if result is None:
            result = compute_func()
            cache.set(cache_key, result, ttl or cls.CACHE_TTL)
            
        return result
    
    @classmethod
    def invalidate_pattern(cls, pattern: str):
        """Invalidate all cache keys matching pattern"""
        cache.delete_pattern(f"stats:{pattern}*")
```

### Phase 3: Database Structure Optimization (1 week)

#### 3.1 Implement Table Partitioning

```sql
-- Partition QuestionMasterData by year
ALTER TABLE questions_questionmasterdata 
PARTITION BY RANGE (EXTRACT(YEAR FROM date));

CREATE TABLE questions_questionmasterdata_2024 
PARTITION OF questions_questionmasterdata 
FOR VALUES FROM (2024) TO (2025);

CREATE TABLE questions_questionmasterdata_2025 
PARTITION OF questions_questionmasterdata 
FOR VALUES FROM (2025) TO (2026);

-- Add partition for historical data
CREATE TABLE questions_questionmasterdata_historical 
PARTITION OF questions_questionmasterdata 
FOR VALUES FROM (1900) TO (2024);
```

#### 3.2 Optimize JSON Fields

```python
# migrations/0012_optimize_json_fields.py
from django.db import migrations, models

class Migration(migrations.Migration):
    operations = [
        # Move large JSON fields to separate table
        migrations.CreateModel(
            name='QuestionRawData',
            fields=[
                ('id', models.AutoField(primary_key=True)),
                ('question', models.OneToOneField('Question', on_delete=models.CASCADE)),
                ('raw_api_data', models.JSONField(default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
        ),
        migrations.RemoveField(
            model_name='question',
            name='raw_api_data',
        ),
    ]
```

### Phase 4: Advanced Optimizations (2 weeks)

#### 4.1 Implement Database Connection Pooling

```python
# settings.py
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        # ... existing config ...
        'OPTIONS': {
            'connect_timeout': 10,
            'options': '-c statement_timeout=30000',  # 30 seconds
        },
        'CONN_MAX_AGE': 600,
        'CONN_HEALTH_CHECKS': True,
        'ATOMIC_REQUESTS': False,  # Use explicit transactions
    }
}

# Use pgbouncer for connection pooling
# /etc/pgbouncer/pgbouncer.ini
"""
[databases]
parliament_api = host=localhost port=5432 dbname=parliament_api

[pgbouncer]
pool_mode = transaction
max_client_conn = 1000
default_pool_size = 25
"""
```

#### 4.2 Implement Read Replicas for Statistics

```python
# settings.py
DATABASES = {
    'default': {
        # ... primary database ...
    },
    'replica': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'parliament_api',
        'HOST': 'replica.parliament.db',
        # ... replica config ...
    }
}

DATABASE_ROUTERS = ['parliament_api.routers.ReadReplicaRouter']

# routers.py
class ReadReplicaRouter:
    def db_for_read(self, model, **hints):
        if 'statistics' in str(model._meta):
            return 'replica'
        return 'default'
```

## Implementation Timeline

### Week 1
- [ ] Day 1-2: Implement random selection field and replace order_by('?')
- [ ] Day 3-4: Add compound indexes
- [ ] Day 5: Deploy and monitor performance

### Week 2
- [ ] Day 1-2: Implement materialized views
- [ ] Day 3-4: Add caching layer
- [ ] Day 5: Performance testing

### Week 3
- [ ] Implement table partitioning
- [ ] Optimize JSON fields
- [ ] Setup monitoring

### Week 4
- [ ] Setup connection pooling
- [ ] Configure read replicas
- [ ] Final optimization and testing

## Performance Targets

### Current Performance
- Statistics endpoint: **45+ seconds** (timeout)
- Batch query (5000 items): **10-20 seconds**
- Random selection: **5-15 seconds**

### Target Performance
- Statistics endpoint: **< 100ms**
- Batch query (5000 items): **< 1 second**
- Random selection: **< 50ms**

## Monitoring and Maintenance

### Key Metrics to Track
1. Query execution time (p50, p95, p99)
2. Database connection pool utilization
3. Cache hit ratio
4. Index usage statistics
5. Table bloat percentage

### Maintenance Tasks
1. **Daily**: Refresh materialized views
2. **Weekly**: Analyze query performance
3. **Monthly**: Vacuum and analyze tables
4. **Quarterly**: Review and optimize indexes

## Quick Wins Script

Create this script for immediate performance improvement:

```python
# management/commands/optimize_database.py
from django.core.management.base import BaseCommand
from django.db import connection
import random

class Command(BaseCommand):
    help = 'Apply immediate database optimizations'
    
    def handle(self, *args, **options):
        with connection.cursor() as cursor:
            # 1. Add random selection values
            self.stdout.write("Adding random selection values...")
            cursor.execute("""
                UPDATE questions_questionmasterdata 
                SET random_selection = RANDOM() 
                WHERE random_selection = 0
            """)
            
            # 2. Create missing indexes
            self.stdout.write("Creating performance indexes...")
            cursor.execute("""
                CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_qmd_download_status 
                ON questions_questionmasterdata(pdf_downloaded, parent_institution_id) 
                WHERE questions_file_path != '';
            """)
            
            # 3. Update table statistics
            self.stdout.write("Updating table statistics...")
            cursor.execute("ANALYZE questions_questionmasterdata;")
            cursor.execute("ANALYZE debates_debate;")
            
            # 4. Create partial indexes for common queries
            cursor.execute("""
                CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_qmd_pending_downloads
                ON questions_questionmasterdata(random_selection)
                WHERE pdf_downloaded = FALSE AND questions_file_path != '';
            """)
            
        self.stdout.write(self.style.SUCCESS('Database optimization complete!'))
```

## Conclusion

The primary issue is the use of `order_by('?')` on large datasets, which causes PostgreSQL to load and sort hundreds of thousands of records. Combined with missing compound indexes and lack of query optimization, this creates a perfect storm of performance problems.

The proposed optimizations will reduce query times by **100-1000x**, making the API responsive even with millions of records. Start with Phase 1 for immediate relief, then progressively implement other phases for long-term scalability.
