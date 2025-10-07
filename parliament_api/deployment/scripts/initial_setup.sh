#!/bin/bash
# Parliament API Initial Setup Script
# This script sets up the Parliament API application from scratch

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
APP_NAME="parliament_api"
APP_USER="tusharanand"
APP_DIR="/home/tusharanand/parliament_proceedings/parliament_api"
VENV_DIR="/home/tusharanand/parliament_proceedings/env"
LOG_DIR="/var/log/parliament_api"
PYTHON_VERSION="python3.11"  # Adjust as needed

# Functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_step() {
    echo -e "\n${BLUE}==>${NC} $1\n"
}

check_root() {
    if [ "$EUID" -ne 0 ]; then
        log_error "This script must be run as root"
        exit 1
    fi
}

install_system_dependencies() {
    log_step "Installing system dependencies..."
    
    apt-get update
    apt-get install -y \
        python3.11 \
        python3.11-venv \
        python3-pip \
        postgresql \
        postgresql-contrib \
        redis-server \
        nginx \
        git \
        curl \
        supervisor \
        build-essential \
        libpq-dev \
        python3-dev \
        certbot \
        python3-certbot-nginx
    
    log_info "System dependencies installed"
}

create_directories() {
    log_step "Creating application directories..."
    
    mkdir -p "$APP_DIR"
    mkdir -p "$LOG_DIR"
    mkdir -p "$APP_DIR/media"
    mkdir -p "$APP_DIR/staticfiles"
    mkdir -p "$APP_DIR/logs"
    
    chown -R $APP_USER:$APP_USER "$APP_DIR"
    chown -R $APP_USER:$APP_USER "$LOG_DIR"
    
    log_info "Directories created"
}

setup_python_environment() {
    log_step "Setting up Python virtual environment..."
    
    cd "$APP_DIR"
    sudo -u $APP_USER $PYTHON_VERSION -m venv "$VENV_DIR"
    sudo -u $APP_USER $VENV_DIR/bin/pip install --upgrade pip wheel setuptools
    
    log_info "Python environment ready"
}

setup_database() {
    log_step "Setting up PostgreSQL database..."
    
    # Check if database already exists
    if sudo -u postgres psql -lqt | cut -d \| -f 1 | grep -qw parliament_api; then
        log_warn "Database already exists, skipping creation"
    else
        sudo -u postgres psql <<EOF
CREATE DATABASE parliament_api;
CREATE USER parliament_user WITH PASSWORD 'CHANGE_THIS_PASSWORD';
ALTER ROLE parliament_user SET client_encoding TO 'utf8';
ALTER ROLE parliament_user SET default_transaction_isolation TO 'read committed';
ALTER ROLE parliament_user SET timezone TO 'UTC';
GRANT ALL PRIVILEGES ON DATABASE parliament_api TO parliament_user;
ALTER DATABASE parliament_api OWNER TO parliament_user;
EOF
        log_info "Database created"
    fi
}

setup_redis() {
    log_step "Configuring Redis..."
    
    systemctl enable redis-server
    systemctl start redis-server
    
    log_info "Redis configured"
}

copy_source_code() {
    log_step "Copying source code..."
    
    # This assumes you're running from the parliament_api directory
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
    
    if [ -d "$SCRIPT_DIR/parliament_api" ]; then
        log_info "Copying files from $SCRIPT_DIR to $APP_DIR"
        rsync -av --exclude='*.pyc' --exclude='__pycache__' --exclude='.git' \
            --exclude='venv' --exclude='*.log' "$SCRIPT_DIR/" "$APP_DIR/"
        chown -R $APP_USER:$APP_USER "$APP_DIR"
    else
        log_error "Cannot find source code. Please run this script from the project root."
        exit 1
    fi
}

install_python_dependencies() {
    log_step "Installing Python dependencies..."
    
    cd "$APP_DIR"
    sudo -u $APP_USER $VENV_DIR/bin/pip install -r requirements.txt
    
    log_info "Python dependencies installed"
}

setup_environment_file() {
    log_step "Setting up environment file..."
    
    if [ ! -f "$APP_DIR/.env" ]; then
        if [ -f "$APP_DIR/.env.example" ]; then
            cp "$APP_DIR/.env.example" "$APP_DIR/.env"
            chown $APP_USER:$APP_USER "$APP_DIR/.env"
            chmod 600 "$APP_DIR/.env"
            log_warn "Please edit $APP_DIR/.env and configure your environment variables!"
            log_warn "After editing .env, run: python manage.py migrate && python manage.py collectstatic"
        else
            log_error ".env.example not found. Please create .env manually"
        fi
    else
        log_info ".env file already exists"
    fi
}

install_systemd_services() {
    log_step "Installing systemd services..."
    
    if [ -d "$APP_DIR/deployment/systemd" ]; then
        cp "$APP_DIR/deployment/systemd/"*.service /etc/systemd/system/
        systemctl daemon-reload
        
        log_info "Systemd services installed. Enable them with:"
        log_info "  systemctl enable parliament-api-daphne"
        log_info "  systemctl enable parliament-celery-worker"
        log_info "  systemctl enable parliament-celery-beat"
    else
        log_warn "Systemd service files not found"
    fi
}

setup_nginx() {
    log_step "Setting up Nginx..."
    
    if [ -f "$APP_DIR/deployment/nginx/parliament-api.conf" ]; then
        cp "$APP_DIR/deployment/nginx/parliament-api.conf" /etc/nginx/sites-available/parliament-api
        
        log_warn "Please edit /etc/nginx/sites-available/parliament-api and update:"
        log_warn "  - server_name (domain)"
        log_warn "  - SSL certificate paths"
        log_info "Then enable with: ln -s /etc/nginx/sites-available/parliament-api /etc/nginx/sites-enabled/"
        log_info "And test with: nginx -t && systemctl reload nginx"
    else
        log_warn "Nginx config not found"
    fi
}

print_next_steps() {
    log_step "Setup Complete! Next Steps:"
    
    echo -e "${YELLOW}1. Configure Environment:${NC}"
    echo "   - Edit $APP_DIR/.env with your settings"
    echo "   - Update SECRET_KEY, database passwords, GCS credentials, etc."
    echo ""
    echo -e "${YELLOW}2. Run Migrations:${NC}"
    echo "   cd $APP_DIR"
    echo "   $VENV_DIR/bin/python manage.py migrate"
    echo "   $VENV_DIR/bin/python manage.py collectstatic"
    echo ""
    echo -e "${YELLOW}3. Create Superuser:${NC}"
    echo "   $VENV_DIR/bin/python manage.py createsuperuser"
    echo ""
    echo -e "${YELLOW}4. Configure Nginx:${NC}"
    echo "   - Edit /etc/nginx/sites-available/parliament-api"
    echo "   - Update domain and SSL settings"
    echo "   - Enable: ln -s /etc/nginx/sites-available/parliament-api /etc/nginx/sites-enabled/"
    echo "   - Test: nginx -t"
    echo ""
    echo -e "${YELLOW}5. Setup SSL:${NC}"
    echo "   certbot --nginx -d your-domain.com"
    echo ""
    echo -e "${YELLOW}6. Start Services:${NC}"
    echo "   systemctl enable parliament-api-daphne"
    echo "   systemctl start parliament-api-daphne"
    echo "   systemctl enable parliament-celery-worker"
    echo "   systemctl start parliament-celery-worker"
    echo "   systemctl enable parliament-celery-beat"
    echo "   systemctl start parliament-celery-beat"
    echo "   systemctl reload nginx"
    echo ""
    echo -e "${GREEN}Setup completed successfully!${NC}"
}

# Main setup flow
main() {
    log_info "Starting Parliament API initial setup..."
    
    check_root
    install_system_dependencies
    create_directories
    setup_python_environment
    setup_database
    setup_redis
    copy_source_code
    install_python_dependencies
    setup_environment_file
    install_systemd_services
    setup_nginx
    print_next_steps
}

# Run main function
main "$@"


