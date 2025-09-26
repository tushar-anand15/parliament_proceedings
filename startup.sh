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
    
    echo -e "\n${WHITE}Port Status:${NC}"
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
    
    # Check if services are already running
    local status=$(get_service_status)
    if echo "$status" | grep -q "redis:running\|celery:running\|api:running"; then
        print_warning "Some services are already running. Cleaning up first..."
        cleanup_sessions
        sleep 2
    fi
    
    # Start Redis in tmux session
    print_info "Starting Redis server..."
    tmux new-session -d -s "parliament-redis" -c "$(pwd)"
    tmux send-keys -t "parliament-redis" "redis-server" Enter
    sleep 2
    show_progress 8 11 "Redis started"
    print_status "Redis server started in tmux session 'parliament-redis'"
    
    # Start Celery worker in tmux session
    print_info "Starting Celery worker..."
    tmux new-session -d -s "parliament-celery" -c "$(pwd)"
    tmux send-keys -t "parliament-celery" "source ../env/bin/activate && celery -A parliament_api worker --loglevel=info" Enter
    sleep 3
    show_progress 8 11 "Celery started"
    print_status "Celery worker started in tmux session 'parliament-celery'"
    
    # Start Celery Flower monitoring
    print_info "Starting Celery Flower monitoring..."
    tmux new-session -d -s "parliament-flower" -c "$(pwd)"
    tmux send-keys -t "parliament-flower" "source ../env/bin/activate && celery -A parliament_api flower --port=5555" Enter
    sleep 2
    show_progress 9 11 "Flower started"
    print_status "Celery Flower started in tmux session 'parliament-flower'"
    
    # Start Django development server
    print_info "Starting Django development server..."
    tmux new-session -d -s "parliament-api" -c "$(pwd)"
    tmux send-keys -t "parliament-api" "source ../env/bin/activate && python manage.py runserver 0.0.0.0:8000" Enter
    sleep 3
    show_progress 10 11 "API started"
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
