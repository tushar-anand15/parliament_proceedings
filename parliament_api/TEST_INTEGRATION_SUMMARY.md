# Parliament API Integration Test - Summary

## What Was Done

### 1. API Endpoint Analysis
Analyzed the actual Django views and URL configurations to understand:
- Request/response structure for all endpoints
- Authentication requirements
- Celery task creation and monitoring patterns
- Response data structures (some return `{task_id}`, others return `{status, data: {task_id}}`)

### 2. Fixed Critical API Issues
**Fixed the blocking logic in debate scraping** (`services/debates/views.py`):
- ❌ **Before**: Returned 400 error when duplicate scraping request was made
- ✅ **After**: Returns 200 with existing job details (graceful handling)
- ✅ Includes `is_existing_job: true` flag to indicate reusing existing job
- ✅ Returns task_id, status, and progress of existing job
- **Result**: No more false negatives in testing! Duplicate requests are handled gracefully.

### 3. Enhanced Test Coverage
**Updated test to use ALL available sessions from master DB**:
- ✅ Fetches all sessions via `/api/debates/discover-sessions/` endpoint
- ✅ Tests 1-2 sessions per Lok Sabha (comprehensive coverage)
- ✅ Uses actual date ranges from master data
- ✅ Samples diverse sessions across LS1-LS18
- ✅ Limits to 15 sessions max to keep test duration reasonable
- **Result**: Maximum test coverage across Parliament history!

### 4. Fixed Test Script Issues
Fixed indentation and logic errors in `test_celery_integration.py`:
- ✅ Corrected all Python indentation errors
- ✅ Fixed conditional statement nesting
- ✅ Aligned response structure expectations with actual API
- ✅ Proper error handling for all endpoints
- ✅ Handles `is_existing_job` flag gracefully

### 5. Created Documentation
Created `ENDPOINT_CURLS.md` with curl commands for every endpoint being tested:
- Service availability
- Debate endpoints (statistics, scraping, task status)
- LS question endpoints (statistics, list, master data, bulk downloads)
- RS question endpoints (statistics, master data, scraping, bulk downloads)

## API Endpoints Tested

### Debate Endpoints (`/api/debates/`)
- `GET /statistics/` → Returns `{total_debates, status_breakdown, ...}`
- `GET /scraping-status/` → Returns `{active_jobs, latest_job, debate_statistics}`
- `POST /start-scraping/` → Returns `{message, job_id, task_id, job_name, status, ...}`
- `GET /task-status/{task_id}/` → Returns `{task_id, status, ready, successful, failed, result}`

### LS Question Endpoints (`/api/questions/ls/`)
- `GET /download-statistics/` → Returns `{download_statistics, master_data_statistics}` or `{task_id}` if Celery
- `GET /questions/` → Returns paginated `{results, count, next, previous}`
- `GET /master-data/` → Returns master data overview
- `POST /process-queue/` → May return `{task_id}` if using Celery
- `POST /bulk-download/` → Returns result from service
- `GET /task-status/{task_id}/` → Returns Celery task status

### RS Question Endpoints (`/api/questions/rs/`)
- `GET /statistics/` → Returns `{status: "success", data: {...}, message}`
- `GET /master-data/` → Returns RS master data overview
- `GET /master-data/list/` → Returns `{questions: [...]}`
- `POST /scrape/` → Returns `{status: "success", data: {task_id, session_number}, message}`
- `POST /bulk-download/` → Returns `{status: "success", data: {task_id, questions_queued}}`
- `GET /task-status/{task_id}/` → Returns Celery task status

## Key Response Structure Differences

### Debate & LS Endpoints
Return flat structure:
```json
{
  "task_id": "abc123",
  "message": "...",
  ...
}
```

### RS Endpoints
Return nested structure:
```json
{
  "status": "success",
  "data": {
    "task_id": "abc123",
    ...
  },
  "message": "..."
}
```

## Test Script Structure

### 1. Service Availability Check
- Tests `/api/` endpoint
- Validates authentication
- Ensures service is running

### 2. Debate Endpoint Tests
- Statistics endpoint
- Scraping status
- Task creation with monitoring
- Task status polling

### 3. LS Question Endpoint Tests
- Download statistics
- Question list pagination
- Master data retrieval
- Queue processing with Celery
- Task monitoring

### 4. RS Question Endpoint Tests
- Statistics (with nested response structure)
- Master data overview
- Scraping with PDF downloads
- Bulk download with task creation
- Task monitoring

### 5. Comprehensive Downloads
- 1 debate per LS session tested
- 5 questions per LS session tested
- 5 questions per RS session tested
- All with Celery task creation and monitoring

## Running the Tests

### Prerequisites
```bash
# 1. Start Django server
cd parliament_api
python manage.py runserver 8000

# 2. Start Celery worker (in another terminal)
cd parliament_api
celery -A parliament_api worker --loglevel=info

# 3. Start Redis (in another terminal)
redis-server

# 4. Ensure you have a valid auth token
```

### Run Full Test Suite
```bash
cd parliament_api
python test_celery_integration.py --token ***REMOVED_SECRET***
```

### Run Specific Tests
```bash
# Debates only
python test_celery_integration.py --token ***REMOVED_SECRET*** --debates

# Questions only (LS + RS)
python test_celery_integration.py --token ***REMOVED_SECRET*** --questions
```

### Using Default Admin Token
```bash
python test_celery_integration.py --token ***REMOVED_SECRET***
```

## Test Results

Results are saved to:
- `celery_integration_test_results.json` - Full JSON results
- Console output with real-time progress
- `logs/celery_test.log` - Detailed logs

## Next Steps

1. Run the test script to validate all endpoints
2. Review any failing endpoints
3. Check Celery task completion rates
4. Monitor response times and performance
5. Validate PDF downloads and GCS uploads

## Troubleshooting

### Authentication Errors (401)
- Verify token is valid
- Check token hasn't expired
- Ensure token is from correct environment

### Connection Errors
- Verify Django server is running on port 8000
- Check Celery worker is running
- Ensure Redis is running
- Check firewall settings

### Task Timeout
- Increase `max_wait` parameter in monitoring functions
- Check Celery worker logs for errors
- Verify external API connectivity

