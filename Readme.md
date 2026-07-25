# Parliament Proceedings API

A comprehensive REST API for accessing Indian Parliamentary data including questions, debates, and related proceedings from sansad.in. This project makes Parliamentary data freely accessible through a modern API with advanced features like bulk downloads, async processing, and cloud storage integration.

## Features

- **Complete Parliamentary Data Coverage**: Questions and answers across all Lok Sabha sessions
- **RESTful API**: Modern REST endpoints with comprehensive documentation
- **Async Processing**: Celery-based task queue for heavy operations
- **Cloud Storage**: Google Cloud Storage integration for PDF management
- **Bulk Operations**: Efficient bulk downloads and batch processing
- **Real-time Monitoring**: Celery Flower for task monitoring
- **Authentication**: JWT-based API authentication
- **Auto Documentation**: Swagger/OpenAPI documentation
- **Database Migrations**: Automated database schema management
- **Production Ready**: Gunicorn, Redis, PostgreSQL stack

## API Endpoints

### Questions API (`/api/questions/`)
- `GET /` - List all questions with filtering and pagination
- `GET /{id}/` - Retrieve specific question details
- `GET /stats/` - Question statistics and summaries
- `GET /master-data/` - Parliamentary metadata (Lok Sabhas, sessions)
- `GET /master-data/list/` - List master data with filtering
- `POST /master-data/bulk-download/` - Bulk download questions
- `GET /sessions/` - Session-based question data
- `GET /sessions/summary/` - Session summaries
- `POST /bulk-download/` - Async bulk download tasks
- `GET /task-status/{task_id}/` - Check async task status
- `GET /download-statistics/` - Download operation statistics
- `POST /populate/` - Populate questions data

### Debates API (`/api/debates/`)
- `GET /` - List debates with filtering
- `GET /{id}/` - Retrieve specific debate
- `GET /health/` - Health check endpoint
- `POST /start-scraping/` - Start debate scraping
- `GET /scraping-status/` - Check scraping status
- `GET /statistics/` - Debate statistics
- `GET /discover-sessions/` - Discover available sessions
- `GET /search/` - Search debates
- `POST /bulk-download/` - Bulk download debates
- `GET /download-queue/` - Download queue status

### Files API (`/api/files/`)
- `GET /documents/` - List document files
- `POST /upload/` - Upload documents
- `GET /download/{file_id}/` - Download specific file
- `GET /preview/{file_id}/` - Preview file content
- `POST /bulk-download/` - Bulk file downloads
- `POST /batch-download/` - Batch download operations
- `GET /batch-status/{batch_id}/` - Check batch status
- `POST /queue/add/` - Add files to download queue
- `POST /queue/process/` - Process download queue
- `GET /stats/` - File statistics
- `GET /storage-info/` - Storage information

### Scraper API (`/api/scraper/`)
- `GET /jobs/` - List scraping jobs
- `POST /start/` - Start scraping operation
- `POST /stop/` - Stop scraping
- `GET /status/` - Current scraping status
- `GET /jobs/latest/` - Latest scraping job
- `GET /data/stats/` - Scraped data statistics
- `POST /data/validate/` - Validate scraped data
- `GET /check-updates/` - Check for new data
- `GET /database-stats/` - Database statistics

### AI Service API (`/api/ai/`)
- `POST /analyze/text/` - Analyze text content
- `POST /analyze/document/` - Analyze documents
- `POST /summarize/text/` - Text summarization
- `POST /summarize/question/` - Question summarization
- `POST /classify/topic/` - Topic classification
- `POST /process/question/` - Process questions with AI
- `POST /extract/keywords/` - Extract keywords
- `POST /extract/entities/` - Extract named entities

### Authentication API (`/api/auth/`)
- `POST /token/` - Obtain JWT token
- `POST /token/refresh/` - Refresh JWT token
- `POST /token/verify/` - Verify JWT token

## Directory Structure

```
parliament_proceedings/
├── parliament_api/                 # Main Django application
│   ├── parliament_api/            # Project settings
│   │   ├── settings.py            # Django configuration
│   │   ├── urls.py               # URL routing
│   │   ├── celery.py             # Celery configuration
│   │   └── wsgi.py               # WSGI application
│   ├── services/                  # Microservice-style apps
│   │   ├── questions/            # Questions API service
│   │   │   ├── models.py         # Question data models
│   │   │   ├── views.py          # API endpoints
│   │   │   ├── tasks.py          # Celery tasks
│   │   │   ├── master_data_service.py  # Master data fetching
│   │   │   ├── question_download_service.py  # PDF downloads
│   │   │   └── management/commands/  # Django commands
│   │   ├── debates/              # Debates API service
│   │   ├── files/                # File management service
│   │   ├── scraper/              # Web scraping service
│   │   ├── ai_service/           # AI processing service
│   │   ├── cloud_storage/        # GCS integration
│   │   └── user_auth/            # Authentication service
│   ├── media/                    # Local file storage
│   ├── logs/                     # Application logs
│   └── manage.py                 # Django management script
├── scraper/                      # Legacy scraping tools
├── eci_scraper/                  # Election Commission scraper
├── env/                          # Python virtual environment
├── startup.sh                    # Service management script
└── parliament-process-*.json     # GCS service account key
```

## Migration and Setup

### Prerequisites
- Python 3.8+
- PostgreSQL 12+
- Redis 6+
- tmux (for service management)

### Quick Setup (New Server)

1. **Clone and Setup Environment**
```bash
git clone <repository-url>
cd parliament_proceedings
chmod +x startup.sh
```

2. **Automated Setup**
```bash
./startup.sh start
```

The startup script automatically:
- Creates Python virtual environment
- Installs all dependencies
- Sets up PostgreSQL database and user
- Runs Django migrations
- Creates superuser account
- Starts all services (Redis, Celery, Django, Flower)

3. **Manual Setup (if needed)**
```bash
# Create virtual environment
python3 -m venv env
source env/bin/activate

# Install dependencies
cd parliament_api
pip install -r requirements.txt

# Setup database
createdb parliament_api
python manage.py migrate

# Create superuser
python manage.py createsuperuser

# Initialize master data
python manage.py initialize_questions_master_data

# Start services manually
redis-server &
celery -A parliament_api worker --loglevel=info &
celery -A parliament_api flower &
python manage.py runserver 0.0.0.0:8000
```

### Service Management

```bash
# Start all services
./startup.sh start

# Stop all services  
./startup.sh stop

# Restart services
./startup.sh restart

# Check status
./startup.sh status

# View logs
tmux attach -t parliament-api
```

### Environment Configuration

Create `.env` file in project root:
```bash
# Database
DB_NAME=parliament_api
DB_USER=parliament_user
DB_PASSWORD=YOUR_TOKEN
DB_HOST=localhost
DB_PORT=5432

# Redis
REDIS_URL=redis://localhost:6379/0

# Google Cloud Storage (optional)
GCS_PROJECT_ID=your-project-id
GCS_BUCKET_NAME=your-bucket-name
GCS_CREDENTIALS_PATH=./parliament-process-*.json

# Django
SECRET_KEY=your-secret-key
DEBUG=False
ALLOWED_HOSTS=localhost,127.0.0.1,your-domain.com

# Celery
CELERY_WORKER_CONCURRENCY=8
```

### Access Points

- **API Server**: http://localhost:8000
- **API Documentation**: http://localhost:8000/api/docs/
- **Admin Panel**: http://localhost:8000/admin/
- **Celery Flower**: http://localhost:5555
- **Default Credentials**: admin / admin

## Data Migration to Google Cloud

### Option 1: Database Dump and Restore
```bash
# Export local database
pg_dump parliament_api > parliament_data.sql

# On GCloud instance
psql parliament_api < parliament_data.sql
```

### Option 2: Django Data Fixtures
```bash
# Export data as fixtures
python manage.py dumpdata > parliament_data.json

# On GCloud instance
python manage.py loaddata parliament_data.json
```

### Option 3: Fresh Setup (Recommended)
For a clean GCloud deployment:
1. Run fresh setup on GCloud instance
2. Initialize master data: `python manage.py initialize_questions_master_data`
3. Use bulk download APIs to populate data as needed
4. Clean up and organize GCS buckets for optimal performance

This approach ensures clean data structure and optimal performance on the new infrastructure.

## Contributing

This project is open source and contributions are welcome. The data remains free and accessible to all.

## License

Open source - Parliamentary data belongs to the public.
