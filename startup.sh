#!/bin/bash

# Parliament API Management Script
# Usage: ./startup.sh [start|stop|restart|status]
# Default: start

set -e  # Exit on any error

# Script mode
MODE=${1:-start}

# Colors for terminal output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
WHITE='\033[1;37m'
NC='\033[0m' # No Color

# Progress bar function
show_progress() {
    local current=$1
    local total=$2
    local desc=$3
    local percent=$((current * 100 / total))
    local filled=$((percent / 2))
    local empty=$((50 - filled))
    
    printf "\r${CYAN}[${desc}]${NC} ["
    printf "%${filled}s" | tr ' ' '█'
    printf "%${empty}s" | tr ' ' '░'
    printf "] ${percent}%%"
}

# Print colored messages
print_status() {
    echo -e "${GREEN}✓${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

print_info() {
    echo -e "${BLUE}ℹ${NC} $1"
}

print_header() {
    echo -e "\n${PURPLE}╔══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${PURPLE}║${NC} ${WHITE}$1${NC} ${PURPLE}║${NC}"
    echo -e "${PURPLE}╚══════════════════════════════════════════════════════════════╝${NC}\n"
}

# Check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Check if tmux session exists
tmux_session_exists() {
    tmux has-session -t "$1" 2>/dev/null
}

# Check if Redis is running
redis_running() {
    redis-cli ping >/dev/null 2>&1
}

# Check if PostgreSQL is running
postgres_running() {
    if command_exists pg_isready; then
        pg_isready >/dev/null 2>&1
    else
        # Fallback: try to connect
        psql -h localhost -U postgres -c '\q' >/dev/null 2>&1
    fi
}

# Check if port is in use
port_in_use() {
    if command_exists lsof; then
        lsof -i :$1 >/dev/null 2>&1
    elif command_exists netstat; then
        netstat -an | grep -q ":$1 " 2>/dev/null
    else
        # Fallback using /proc/net/tcp (Linux) or ss command
        if [ -f /proc/net/tcp ]; then
            grep -q ":$1 " /proc/net/tcp 2>/dev/null
        else
            # Last resort - try to connect to the port
            timeout 1 bash -c "cat < /dev/null > /dev/tcp/localhost/$1" 2>/dev/null
        fi
    fi
}

# Get service status
get_service_status() {
    local status=""
    
    if tmux_session_exists "parliament-redis"; then
        status="${status}redis:running "
    else
        status="${status}redis:stopped "
    fi
    
    if tmux_session_exists "parliament-celery"; then
        status="${status}celery:running "
    else
        status="${status}celery:stopped "
    fi
    
    if tmux_session_exists "parliament-flower"; then
        status="${status}flower:running "
    else
        status="${status}flower:stopped "
    fi
    
    if tmux_session_exists "parliament-api"; then
        status="${status}api:running"
    else
        status="${status}api:stopped"
    fi
    
    echo "$status"
}

# Kill existing tmux sessions
cleanup_sessions() {
    print_info "Cleaning up existing tmux sessions..."
    tmux kill-session -t "parliament-redis" 2>/dev/null || true
    tmux kill-session -t "parliament-celery" 2>/dev/null || true
    tmux kill-session -t "parliament-flower" 2>/dev/null || true
    tmux kill-session -t "parliament-api" 2>/dev/null || true
    
    # Kill any Redis processes
    pkill -f "redis-server" 2>/dev/null || true
    
    # Kill any Django processes on port 8000
    if port_in_use 8000; then
        if command_exists lsof; then
            lsof -ti:8000 | xargs kill -9 2>/dev/null || true
        else
            # Alternative method using netstat and ps
            for pid in $(netstat -tulpn 2>/dev/null | grep :8000 | awk '{print $7}' | cut -d'/' -f1); do
                kill -9 $pid 2>/dev/null || true
            done
        fi
    fi
    
    # Kill any Flower processes on port 5555
    if port_in_use 5555; then
        if command_exists lsof; then
            lsof -ti:5555 | xargs kill -9 2>/dev/null || true
        else
            # Alternative method using netstat and ps
            for pid in $(netstat -tulpn 2>/dev/null | grep :5555 | awk '{print $7}' | cut -d'/' -f1); do
                kill -9 $pid 2>/dev/null || true
            done
        fi
    fi
    
    print_status "Existing sessions and processes cleaned up"
}

# Show service status
show_status() {
    print_header "📊 Parliament API Status"
    
    local status=$(get_service_status)
    
    echo -e "${WHITE}Service Status:${NC}"
    
    if echo "$status" | grep -q "redis:running"; then
        echo -e "  ${GREEN}✓${NC} Redis Server     - Running (tmux: parliament-redis)"
    else
        echo -e "  ${RED}✗${NC} Redis Server     - Stopped"
    fi
    
    if echo "$status" | grep -q "celery:running"; then
        echo -e "  ${GREEN}✓${NC} Celery Worker    - Running (tmux: parliament-celery)"
    else
        echo -e "  ${RED}✗${NC} Celery Worker    - Stopped"
    fi
    
    if echo "$status" | grep -q "flower:running"; then
        echo -e "  ${GREEN}✓${NC} Celery Flower    - Running (tmux: parliament-flower)"
    else
        echo -e "  ${RED}✗${NC} Celery Flower    - Stopped"
    fi
    
    if echo "$status" | grep -q "api:running"; then
        echo -e "  ${GREEN}✓${NC} Django API       - Running (tmux: parliament-api)"
    else
        echo -e "  ${RED}✗${NC} Django API       - Stopped"
    fi
    
    echo -e "\n${WHITE}Database & Cache Status:${NC}"
    if postgres_running; then
        echo -e "  ${GREEN}✓${NC} PostgreSQL       - Running"
    else
        echo -e "  ${RED}✗${NC} PostgreSQL       - Not running"
    fi
    
    if redis_running; then
        echo -e "  ${GREEN}✓${NC} Redis Server     - Running"
    else
        echo -e "  ${RED}✗${NC} Redis Server     - Not running"
    fi
    
    echo -e "\n${WHITE}Port Status:${NC}"
    if port_in_use 5432; then
        echo -e "  ${GREEN}✓${NC} PostgreSQL 5432  - In use"
    else
        echo -e "  ${RED}✗${NC} PostgreSQL 5432  - Free"
    fi
    
    if port_in_use 6379; then
        echo -e "  ${GREEN}✓${NC} Redis Port 6379  - In use"
    else
        echo -e "  ${RED}✗${NC} Redis Port 6379  - Free"
    fi
    
    if port_in_use 8000; then
        echo -e "  ${GREEN}✓${NC} API Port 8000    - In use"
    else
        echo -e "  ${RED}✗${NC} API Port 8000    - Free"
    fi
    
    if port_in_use 5555; then
        echo -e "  ${GREEN}✓${NC} Flower Port 5555 - In use"
    else
        echo -e "  ${RED}✗${NC} Flower Port 5555 - Free"
    fi
    
    echo -e "\n${WHITE}Management Commands:${NC}"
    echo -e "  ${YELLOW}Start:${NC}            ./startup.sh start"
    echo -e "  ${YELLOW}Stop:${NC}             ./startup.sh stop"
    echo -e "  ${YELLOW}Restart:${NC}          ./startup.sh restart"
    echo -e "  ${YELLOW}Status:${NC}           ./startup.sh status"
    echo -e "  ${YELLOW}View logs:${NC}        tmux attach -t parliament-api"
}

# Stop all services
stop_services() {
    print_header "🛑 Stopping Parliament API Services"
    
    print_info "Stopping all services..."
    cleanup_sessions
    
    # Wait a moment for processes to fully stop
    sleep 2
    
    print_status "All services stopped"
    
    echo -e "\n${GREEN}✅ Parliament API services have been stopped${NC}\n"
}

# Restart services
restart_services() {
    print_header "🔄 Restarting Parliament API Services"
    
    print_info "Stopping existing services..."
    cleanup_sessions
    sleep 2
    
    print_info "Starting services..."
    start_services
}

# Start services function
start_services() {
    # Check if we're in the right directory
    if [ ! -f "parliament_api/manage.py" ]; then
        print_error "Please run this script from the parliament_proceedings directory"
        exit 1
    fi
    
    # Check required commands
    print_info "Checking system requirements..."
    show_progress 1 11 "Checking requirements"
    
    if ! command_exists python3; then
        print_error "Python 3 is required but not installed"
        exit 1
    fi
    
    if ! command_exists tmux; then
        print_error "tmux is required but not installed. Install with: brew install tmux"
        exit 1
    fi
    
    if ! command_exists redis-server; then
        print_warning "Redis server not found. Attempting to install..."
        if command_exists brew; then
            print_info "Installing Redis via Homebrew..."
            brew install redis
        elif command_exists apt-get; then
            print_info "Installing Redis via apt..."
            sudo apt-get update && sudo apt-get install -y redis-server
        elif command_exists yum; then
            print_info "Installing Redis via yum..."
            sudo yum install -y redis
        else
            print_error "Please install Redis manually: https://redis.io/download"
            print_info "Or install Homebrew: https://brew.sh"
            exit 1
        fi
    fi
    
    # Check PostgreSQL
    if ! command_exists psql; then
        print_warning "PostgreSQL not found. Attempting to install..."
        if command_exists brew; then
            print_info "Installing PostgreSQL via Homebrew..."
            brew install postgresql
            print_info "Starting PostgreSQL service..."
            brew services start postgresql
        elif command_exists apt-get; then
            print_info "Installing PostgreSQL via apt..."
            sudo apt-get update && sudo apt-get install -y postgresql postgresql-contrib
            sudo systemctl start postgresql
            sudo systemctl enable postgresql
        elif command_exists yum; then
            print_info "Installing PostgreSQL via yum..."
            sudo yum install -y postgresql postgresql-server postgresql-contrib
            sudo postgresql-setup initdb
            sudo systemctl start postgresql
            sudo systemctl enable postgresql
        else
            print_error "Please install PostgreSQL manually"
            exit 1
        fi
    fi
    
    show_progress 2 11 "Requirements checked"
    print_status "System requirements satisfied"
    
    # Set up virtual environment
    print_info "Setting up Python virtual environment..."
    show_progress 3 11 "Setting up venv"
    
    if [ ! -d "env" ]; then
        print_info "Creating virtual environment..."
        python3 -m venv env
        print_status "Virtual environment created"
    else
        print_status "Virtual environment already exists"
    fi
    
    # Activate virtual environment
    source env/bin/activate
    print_status "Virtual environment activated"
    print_info "Python path: $(which python)"
    print_info "Pip path: $(which pip)"
    
    # Upgrade pip
    print_info "Upgrading pip..."
    pip install --upgrade pip >/dev/null 2>&1
    show_progress 4 11 "Pip upgraded"
    
    # Install/update requirements
    print_info "Installing/updating Python packages..."
    cd parliament_api
    print_info "Installing packages from requirements.txt..."
    pip install -r requirements.txt
    show_progress 5 11 "Packages installed"
    print_status "Python packages installed/updated"
    
    # Setup PostgreSQL database and user
    print_info "Setting up PostgreSQL database..."
    
    # Load environment variables and export them
    if [ -f "../.env" ]; then
        set -a  # automatically export all variables
        source ../.env
        set +a  # stop auto-exporting
        print_status "Environment variables loaded from .env"
    fi
    
    # Create database and user if they don't exist
    DB_NAME=${DB_NAME:-parliament_api}
    DB_USER=${DB_USER:-parliament_user}
    DB_PASSWORD=${DB_PASSWORD:-***REMOVED_SECRET***}
    
    # Check for RESET_DB flag
    if [ -f ".reset_db_flag" ]; then
        print_warning "Database reset requested..."
        
        # Drop database if it exists
        if psql -lqt | cut -d \| -f 1 | grep -qw "$DB_NAME" 2>/dev/null; then
            print_info "Dropping existing database: $DB_NAME"
            psql postgres -c "DROP DATABASE IF EXISTS $DB_NAME;" 2>/dev/null || true
            print_status "Database dropped"
        fi
        
        # Remove reset flag
        rm -f ".reset_db_flag"
        print_status "Database reset flag cleared"
    fi
    
    # Check if database exists, create if not
    if ! psql -lqt | cut -d \| -f 1 | grep -qw "$DB_NAME" 2>/dev/null; then
        print_info "Creating PostgreSQL database and user..."
        
        # Create user and database
        psql postgres -c "CREATE USER $DB_USER WITH PASSWORD '$DB_PASSWORD';" 2>/dev/null || true
        psql postgres -c "ALTER USER $DB_USER CREATEDB;" 2>/dev/null || true
        psql postgres -c "CREATE DATABASE $DB_NAME OWNER $DB_USER;" 2>/dev/null || true
        psql postgres -c "GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;" 2>/dev/null || true
        
        print_status "PostgreSQL database and user created"
    else
        print_status "PostgreSQL database already exists"
    fi
    
    # Run Django migrations
    print_info "Running Django migrations..."
    python manage.py migrate >/dev/null 2>&1
    show_progress 6 11 "Migrations completed"
    print_status "Database migrations completed"
    
    # Create superuser if it doesn't exist
    print_info "Checking for superuser..."
    if ! python manage.py shell -c "from django.contrib.auth import get_user_model; User = get_user_model(); print('exists' if User.objects.filter(is_superuser=True).exists() else 'missing')" 2>/dev/null | grep -q "exists"; then
        print_info "Creating superuser (admin/admin)..."
        echo "from django.contrib.auth import get_user_model; User = get_user_model(); User.objects.create_superuser('admin', 'admin@example.com', 'admin')" | python manage.py shell >/dev/null 2>&1
        print_status "Superuser created (username: admin, password: admin)"
    else
        print_status "Superuser already exists"
    fi
    
    show_progress 7 11 "Django setup completed"
    
    # Setup Google Cloud Storage buckets
    print_info "Setting up Google Cloud Storage buckets..."
    
    # The environment variables are already loaded and exported from above
    # Now run Python with those variables
    python -c "
import sys
import os
import django
from google.cloud import storage
from google.api_core import exceptions as gcs_exceptions

# Explicitly set Django settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'parliament_api.settings')

# Setup Django
django.setup()

try:
    from django.conf import settings
    
    print(f'ℹ GCS Project: {settings.GCS_PROJECT_ID}')
    print(f'ℹ Debates Bucket: {settings.GCS_DEBATES_BUCKET}')
    print(f'ℹ Questions Bucket: {settings.GCS_QUESTIONS_BUCKET}')
    
    # Initialize client
    credentials_path = str(settings.GCS_CREDENTIALS_PATH)
    if os.path.exists(credentials_path):
        client = storage.Client.from_service_account_json(credentials_path)
    else:
        client = storage.Client(project=settings.GCS_PROJECT_ID)
    
    # Function to check and create bucket
    def ensure_bucket_exists(bucket_name):
        try:
            bucket = client.bucket(bucket_name)
            # Try to get bucket metadata to check if it exists
            try:
                bucket.reload()
                print(f'✓ Bucket exists: {bucket_name}')
                return True
            except gcs_exceptions.NotFound:
                # Bucket doesn't exist, create it
                print(f'⚠ Bucket does not exist, creating: {bucket_name}')
                bucket = client.create_bucket(bucket_name, location=settings.GCS_REGION)
                print(f'✓ Bucket created successfully: {bucket_name}')
                return True
            except gcs_exceptions.Forbidden:
                # Don't have permission to check, try to use it anyway
                print(f'⚠ Cannot verify bucket (permission denied), assuming exists: {bucket_name}')
                return True
        except gcs_exceptions.Forbidden as e:
            print(f'✗ Permission denied for bucket {bucket_name}: {str(e)}')
            return False
        except Exception as e:
            print(f'✗ Error with bucket {bucket_name}: {str(e)}')
            return False
    
    # Check/create both buckets
    debates_ok = ensure_bucket_exists(settings.GCS_DEBATES_BUCKET)
    questions_ok = ensure_bucket_exists(settings.GCS_QUESTIONS_BUCKET)
    
    if debates_ok and questions_ok:
        print('✓ GCS setup completed successfully')
        sys.exit(0)
    else:
        print('⚠ GCS setup completed with warnings - some buckets may not be accessible')
        sys.exit(0)
        
except Exception as e:
    print(f'✗ GCS setup failed: {e}')
    print('⚠️  Continuing without GCS - files will only be stored locally')
    import traceback
    traceback.print_exc()
    sys.exit(0)  # Don't fail startup if GCS isn't available
" 2>&1 | while read line; do
        if [[ $line == ✓* ]]; then
            print_status "${line#✓ }"
        elif [[ $line == ✗* ]]; then
            print_error "${line#✗ }"
        elif [[ $line == ⚠* ]]; then
            print_warning "${line#⚠ }"
        elif [[ $line == ℹ* ]]; then
            print_info "${line#ℹ }"
        else
            echo "   $line"
        fi
    done
    
    show_progress 7 11 "GCS setup completed"
    
    # Initialize master data tables if they don't exist
    print_info "Checking master data tables..."
    
    # Check if master data exists
    MASTER_DATA_EXISTS=$(python manage.py shell --no-startup -c "
from services.questions.models import QuestionMasterData, Session, LokSabha, ParliamentInstitution
from services.debates.models import DebateMasterData
import sys
import os
os.environ['DJANGO_COLORS'] = 'nocolor'

# Count LS sessions (sessions linked to LokSabha)
ls_sessions = Session.objects.filter(lok_sabha__isnull=False).count()

# Count RS sessions (for now, we'll count RS session numbers from questions/debates metadata)
# RS doesn't use the Session model the same way, so we count unique session numbers from data
rs_questions = QuestionMasterData.objects.filter(parent_institution__name='rajya_sabha').count() if ParliamentInstitution.objects.filter(name='rajya_sabha').exists() else 0
rs_sessions = QuestionMasterData.objects.filter(parent_institution__name='rajya_sabha').values('session_number').distinct().count() if ParliamentInstitution.objects.filter(name='rajya_sabha').exists() else 0

ls_questions = QuestionMasterData.objects.filter(parent_institution__name='lok_sabha').count() if ParliamentInstitution.objects.filter(name='lok_sabha').exists() else 0
ls_debates = DebateMasterData.objects.filter(parent_institution__name='lok_sabha').count() if ParliamentInstitution.objects.filter(name='lok_sabha').exists() else 0

print(f'{ls_sessions},{rs_sessions},{ls_questions},{rs_questions},{ls_debates}')
" 2>&1 | grep -E '^[0-9,]+$')
    
    IFS=',' read -r LS_SESSIONS RS_SESSIONS LS_QUESTIONS RS_QUESTIONS LS_DEBATES <<< "$MASTER_DATA_EXISTS"
    
    # Provide defaults if variables are empty
    LS_SESSIONS=${LS_SESSIONS:-0}
    RS_SESSIONS=${RS_SESSIONS:-0}
    LS_QUESTIONS=${LS_QUESTIONS:-0}
    RS_QUESTIONS=${RS_QUESTIONS:-0}
    LS_DEBATES=${LS_DEBATES:-0}
    
    # Check if we need to initialize any data
    NEEDS_INIT=false
    if [ "$LS_SESSIONS" -eq "0" ] || [ "$RS_SESSIONS" -eq "0" ] || [ "$LS_QUESTIONS" -eq "0" ] || [ "$RS_QUESTIONS" -eq "0" ] || [ "$LS_DEBATES" -eq "0" ]; then
        NEEDS_INIT=true
    fi
    
    if [ "$NEEDS_INIT" = true ]; then
        print_warning "Master data tables are incomplete, initializing missing data..."
        print_info "This will fetch data from Parliament APIs (may take 10-15 minutes)..."
        
        # Initialize questions master data (includes sessions, LS and RS questions)
        if [ "$LS_SESSIONS" -eq "0" ] || [ "$RS_SESSIONS" -eq "0" ] || [ "$LS_QUESTIONS" -eq "0" ] || [ "$RS_QUESTIONS" -eq "0" ]; then
            print_info "Initializing Questions Master Data (LS + RS)..."
            print_info "   Current state:"
            print_info "      • LS Sessions: $LS_SESSIONS"
            print_info "      • RS Sessions: $RS_SESSIONS"
            print_info "      • LS Questions: $LS_QUESTIONS"
            print_info "      • RS Questions: $RS_QUESTIONS"
            print_warning "   This will take 10-15 minutes - showing real-time progress..."
            echo ""
            
            # Fetch COMPLETE dataset with parallel workers - SHOW REAL-TIME OUTPUT
            python manage.py initialize_questions_master_data --workers 10 2>&1 | while IFS= read -r line; do
                echo "      $line"
            done
            
            print_status "Questions master data initialized (LS + RS)"
        fi
        
        # Initialize LS debates master data
        if [ "$LS_DEBATES" -eq "0" ]; then
            print_info "Initializing LS Debates Master Data..."
            print_warning "   Fetching debate dates from Parliament APIs..."
            echo ""
            
            python manage.py initialize_debates_master_data 2>&1 | while IFS= read -r line; do
                echo "      $line"
            done
            
            print_status "LS Debates master data initialized"
        fi
        
        # Initialize RS debates master data (NEW)
        print_info "Initializing RS Debates Master Data..."
        print_info "   This includes BOTH verbatim and official debates..."
        print_warning "   Processing recent 5 sessions (verbatim) + 10 sessions (official)..."
        echo ""
        
        python manage.py initialize_rs_debates_master_data --workers 10 --recent-sessions 5 --official-sessions 10 2>&1 | while IFS= read -r line; do
            echo "      $line"
        done
        
        print_status "RS Debates master data initialized"
        
        # Re-check counts after initialization
        FINAL_COUNT=$(python manage.py shell --no-startup -c "
from services.questions.models import QuestionMasterData, Session, ParliamentInstitution
from services.debates.models import DebateMasterData
import os
os.environ['DJANGO_COLORS'] = 'nocolor'

ls_sessions = Session.objects.filter(lok_sabha__isnull=False).count()
rs_sessions = QuestionMasterData.objects.filter(parent_institution__name='rajya_sabha').values('session_number').distinct().count() if ParliamentInstitution.objects.filter(name='rajya_sabha').exists() else 0

ls_questions = QuestionMasterData.objects.filter(parent_institution__name='lok_sabha').count() if ParliamentInstitution.objects.filter(name='lok_sabha').exists() else 0
rs_questions = QuestionMasterData.objects.filter(parent_institution__name='rajya_sabha').count() if ParliamentInstitution.objects.filter(name='rajya_sabha').exists() else 0

ls_debates = DebateMasterData.objects.filter(parent_institution__name='lok_sabha').count() if ParliamentInstitution.objects.filter(name='lok_sabha').exists() else 0

print(f'{ls_sessions},{rs_sessions},{ls_questions},{rs_questions},{ls_debates}')
" 2>&1 | grep -E '^[0-9,]+$')
        
        IFS=',' read -r FINAL_LS_SESSIONS FINAL_RS_SESSIONS FINAL_LS_QUESTIONS FINAL_RS_QUESTIONS FINAL_LS_DEBATES <<< "$FINAL_COUNT"
        print_status "Master data initialization completed"
        print_info "   • LS Sessions: ${FINAL_LS_SESSIONS:-0}"
        print_info "   • RS Sessions: ${FINAL_RS_SESSIONS:-0}"
        print_info "   • LS Questions: ${FINAL_LS_QUESTIONS:-0}"
        print_info "   • RS Questions: ${FINAL_RS_QUESTIONS:-0}"
        print_info "   • LS Debates: ${FINAL_LS_DEBATES:-0}"
        print_info "   • RS Debates: Metadata initialized (verbatim + official)"
    else
        print_status "Master data already initialized"
        print_info "   • LS Sessions: $LS_SESSIONS"
        print_info "   • RS Sessions: $RS_SESSIONS"
        print_info "   • LS Questions: $LS_QUESTIONS"
        print_info "   • RS Questions: $RS_QUESTIONS"
        print_info "   • LS Debates: $LS_DEBATES"
        print_info "   • RS Debates: Will be checked and initialized if needed"
        
        # Still run RS debates initialization to ensure it's up to date (idempotent)
        print_info "Checking RS Debates Master Data (quick check)..."
        python manage.py initialize_rs_debates_master_data --workers 10 --recent-sessions 2 --official-sessions 5 2>&1 | while IFS= read -r line; do
            # Only show summary lines (lines starting with special chars or containing key info)
            if [[ "$line" =~ ^[[:space:]]*(Status:|Sessions:|Dates:|Debates:|✓|✅|❌|⚠|ℹ|═|─) ]] || [[ "$line" =~ (RESULTS|SUMMARY|Complete) ]]; then
                echo "      $line"
            fi
        done
    fi
    
    show_progress 8 11 "Master data setup completed"
    
    # Check if services are already running
    local status=$(get_service_status)
    if echo "$status" | grep -q "redis:running\|celery:running\|api:running"; then
        print_warning "Some services are already running. Cleaning up first..."
        cleanup_sessions
        sleep 2
    fi
    
    # Ensure PostgreSQL is running
    print_info "Ensuring PostgreSQL is running..."
    if ! postgres_running; then
        print_info "Starting PostgreSQL service..."
        if command_exists brew; then
            brew services start postgresql
        elif command_exists systemctl; then
            sudo systemctl start postgresql
        else
            print_warning "Please start PostgreSQL manually"
        fi
        sleep 2
    fi
    print_status "PostgreSQL is running"
    
    # Start Redis in tmux session
    print_info "Starting Redis server..."
    tmux new-session -d -s "parliament-redis" -c "$(pwd)"
    tmux send-keys -t "parliament-redis" "redis-server" Enter
    sleep 2
    show_progress 9 11 "Redis started"
    print_status "Redis server started in tmux session 'parliament-redis'"
    
    # Start Celery worker in tmux session
    print_info "Starting Celery worker..."
    CELERY_CONCURRENCY=${CELERY_WORKER_CONCURRENCY:-8}
    tmux new-session -d -s "parliament-celery" -c "$(pwd)"
    tmux send-keys -t "parliament-celery" "source ../env/bin/activate && celery -A parliament_api worker --loglevel=info --concurrency=$CELERY_CONCURRENCY" Enter
    sleep 3
    show_progress 10 11 "Celery started"
    print_status "Celery worker started in tmux session 'parliament-celery' (concurrency: $CELERY_CONCURRENCY)"
    
    # Start Celery Flower monitoring
    print_info "Starting Celery Flower monitoring..."
    tmux new-session -d -s "parliament-flower" -c "$(pwd)"
    tmux send-keys -t "parliament-flower" "source ../env/bin/activate && celery -A parliament_api flower --port=5555" Enter
    sleep 2
    show_progress 10 11 "Flower started"
    print_status "Celery Flower started in tmux session 'parliament-flower'"
    
    # Start Django development server
    print_info "Starting Django development server..."
    tmux new-session -d -s "parliament-api" -c "$(pwd)"
    tmux send-keys -t "parliament-api" "source ../env/bin/activate && python manage.py runserver 0.0.0.0:8000" Enter
    sleep 3
    show_progress 11 11 "API started"
    print_status "Django server started in tmux session 'parliament-api'"
    
    # Final status
    print_header "🎉 Parliament API Successfully Started!"
    
    echo -e "${WHITE}Services Status:${NC}"
    echo -e "  ${GREEN}✓${NC} Redis Server     - tmux session: parliament-redis"
    echo -e "  ${GREEN}✓${NC} Celery Worker    - tmux session: parliament-celery"
    echo -e "  ${GREEN}✓${NC} Celery Flower    - tmux session: parliament-flower"
    echo -e "  ${GREEN}✓${NC} Django API       - tmux session: parliament-api"
    
    echo -e "\n${WHITE}Access Points:${NC}"
    echo -e "  ${CYAN}API Server:${NC}        http://localhost:8000"
    echo -e "  ${CYAN}API Docs:${NC}          http://localhost:8000/api/schema/swagger-ui/"
    echo -e "  ${CYAN}Admin Panel:${NC}       http://localhost:8000/admin/"
    echo -e "  ${CYAN}Celery Flower:${NC}     http://localhost:5555"
    echo -e "  ${CYAN}Redis Monitor:${NC}     redis-cli monitor"
    
    echo -e "\n${WHITE}Management Commands:${NC}"
    echo -e "  ${YELLOW}View logs:${NC}        tmux attach -t parliament-api"
    echo -e "  ${YELLOW}Stop all:${NC}         ./startup.sh stop"
    echo -e "  ${YELLOW}Restart:${NC}          ./startup.sh restart"
    echo -e "  ${YELLOW}Status:${NC}           ./startup.sh status"
    
    echo -e "\n${WHITE}Default Credentials:${NC}"
    echo -e "  ${YELLOW}Admin:${NC}            admin / admin"
    
    echo -e "\n${GREEN}🚀 Parliament API is ready to use!${NC}\n"
    
    # Optional: Attach to the API session
    read -p "Press Enter to attach to the API session (or Ctrl+C to exit)..."
    tmux attach -t parliament-api
}

# Main function with mode handling
main() {
    case $MODE in
        start)
            print_header "🏛️  Starting Parliament API"
            start_services
            ;;
        stop)
            stop_services
            ;;
        restart)
            restart_services
            ;;
        status)
            show_status
            ;;
        *)
            echo -e "${RED}Usage: $0 [start|stop|restart|status]${NC}"
            echo -e "${YELLOW}Default: start${NC}"
            exit 1
            ;;
    esac
}

# Handle script interruption
trap 'print_error "Operation interrupted"; exit 1' INT TERM

# Run main function
main "$@"
