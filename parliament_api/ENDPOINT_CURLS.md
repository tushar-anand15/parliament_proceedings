# Parliament API Endpoint Testing - CURL Commands

## Authentication
All requests require a token:
```bash
TOKEN="***REMOVED_SECRET***"
BASE_URL="http://localhost:8000"
```

## API Response Format - CONSISTENT STRUCTURE
Both LS and RS endpoints now return consistent format:
```json
{
  "status": "success",
  "data": {
    "questions": [...],
    "pagination": {...}
  },
  "message": "..."
}
```

## 1. Service Availability
```bash
curl -X GET "${BASE_URL}/api/" \
  -H "Authorization: Token ${TOKEN}"
```

## 2. Debate Endpoints

### Get Debate Statistics
```bash
curl -X GET "${BASE_URL}/api/debates/statistics/" \
  -H "Authorization: Token ${TOKEN}"
```

### Get Debate Scraping Status
```bash
curl -X GET "${BASE_URL}/api/debates/scraping-status/" \
  -H "Authorization: Token ${TOKEN}"
```

### Start Debate Scraping
```bash
curl -X POST "${BASE_URL}/api/debates/start-scraping/" \
  -H "Authorization: Token ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "loksabha_no": "18",
    "session_no": "V",
    "start_date": "2024-07-01",
    "end_date": "2024-07-02",
    "download_pdfs": true,
    "job_name": "Test Job"
  }'
```
**Response:** `{message, job_id, task_id, job_name, status, loksabha_no, session_no, ...}`

**Note:** Returns 400 error if there's already an active scraping job for the same LS/Session combination:
```json
{
  "error": "Another debate scraping job is already running for LS18 Session V",
  "active_job_id": 123
}
```
Solution: Wait for the job to complete, or use a different LS/Session combination.

### Check Debate Task Status
```bash
curl -X GET "${BASE_URL}/api/debates/task-status/TASK_ID/" \
  -H "Authorization: Token ${TOKEN}"
```
**Response:** `{task_id, status, ready, successful, failed, result/error, job}`

## 3. Lok Sabha Question Endpoints

### Get LS Download Statistics
```bash
curl -X GET "${BASE_URL}/api/questions/ls/download-statistics/" \
  -H "Authorization: Token ${TOKEN}"
```
**Response:** `{download_statistics, master_data_statistics, calculated_at}` or `{task_id, status, message}` if use_celery=true

### Get LS Question List
```bash
curl -X GET "${BASE_URL}/api/questions/ls/questions/?limit=10" \
  -H "Authorization: Token ${TOKEN}"
```
**Response:** Paginated list with `{results: [...], count, next, previous}`

### Get LS Master Data
```bash
curl -X GET "${BASE_URL}/api/questions/ls/master-data/" \
  -H "Authorization: Token ${TOKEN}"
```

### Process LS Question Queue
```bash
curl -X POST "${BASE_URL}/api/questions/ls/process-queue/" \
  -H "Authorization: Token ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "max_items": 5,
    "use_celery": true
  }'
```
**Response:** May contain `task_id` if using Celery

### LS Bulk Download
```bash
curl -X POST "${BASE_URL}/api/questions/ls/bulk-download/" \
  -H "Authorization: Token ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "question_ids": [1, 2, 3],
    "use_celery": true
  }'
```

### Check LS Task Status
```bash
curl -X GET "${BASE_URL}/api/questions/ls/task-status/TASK_ID/" \
  -H "Authorization: Token ${TOKEN}"
```

## 4. Rajya Sabha Question Endpoints

### Get RS Statistics
```bash
curl -X GET "${BASE_URL}/api/questions/rs/statistics/" \
  -H "Authorization: Token ${TOKEN}"
```
**Response:** `{status, data: {...}, message}`

### Get RS Master Data
```bash
curl -X GET "${BASE_URL}/api/questions/rs/master-data/" \
  -H "Authorization: Token ${TOKEN}"
```

### Get RS Master Data List
```bash
curl -X GET "${BASE_URL}/api/questions/rs/master-data/list/?session_number=268&limit=5" \
  -H "Authorization: Token ${TOKEN}"
```

### Start RS Scraping
```bash
curl -X POST "${BASE_URL}/api/questions/rs/scrape/" \
  -H "Authorization: Token ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "session_number": "268",
    "download_pdfs": true
  }'
```
**Response:** `{status, data: {task_id, session_number, download_pdfs}, message}`

### RS Bulk Download
```bash
curl -X POST "${BASE_URL}/api/questions/rs/bulk-download/" \
  -H "Authorization: Token ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "session_number": "268",
    "download_all_session": true
  }'
```
**Response:** `{status, data: {task_id, questions_queued, session_number}}`

### Check RS Task Status
```bash
curl -X GET "${BASE_URL}/api/questions/rs/task-status/TASK_ID/" \
  -H "Authorization: Token ${TOKEN}"
```

