#!/bin/bash
# Parliament API Deployment Script for opensansad.co.in
# This script handles the production deployment

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
DOMAIN="api.opensansad.co.in"
LOG_DIR="/var/log/parliament_api"

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

check_sudo() {
    if [ "$EUID" -ne 0 ]; then
        log_error "This script must be run with sudo"
        exit 1
    fi
}

log_step() {
    echo -e "\n${BLUE}==>${NC} $1\n"
}

check_prerequisites() {
    log_step "Checking prerequisites..."
    
    # Check if PostgreSQL is running
    if systemctl is-active --quiet postgresql 2>/dev/null; then
        log_info "PostgreSQL is running"
    else
        log_warn "PostgreSQL may not be running as systemd service (might be ok)"
    fi
    
    # Check if Redis is running
    if redis-cli ping >/dev/null 2>&1; then
        log_info "Redis is running"
    else
        log_warn "Redis is not responding"
    fi
    
    log_info "Prerequisites check passed"
}

install_system_packages() {
    log_step "Installing system packages..."
    
    if ! command -v nginx >/dev/null 2>&1; then
        log_info "Installing Nginx..."
        apt-get update
        apt-get install -y nginx
    else
        log_info "Nginx already installed"
    fi
    
    if ! command -v certbot >/dev/null 2>&1; then
        log_info "Installing Certbot..."
        apt-get install -y certbot python3-certbot-nginx
    else
        log_info "Certbot already installed"
    fi
}

install_dependencies() {
    log_step "Installing Python dependencies..."
    cd "$APP_DIR"
    sudo -u $APP_USER $VENV_DIR/bin/pip install --upgrade pip
    sudo -u $APP_USER $VENV_DIR/bin/pip install -r requirements.txt
}

run_migrations() {
    log_info "Running database migrations..."
    cd "$APP_DIR"
    sudo -u $APP_USER $VENV_DIR/bin/python manage.py migrate --noinput
}

collect_static() {
    log_step "Collecting static files..."
    cd "$APP_DIR"
    sudo -u $APP_USER $VENV_DIR/bin/python manage.py collectstatic --noinput --clear
}

setup_log_directory() {
    log_step "Setting up log directory..."
    
    if [ ! -d "$LOG_DIR" ]; then
        mkdir -p "$LOG_DIR"
        chown $APP_USER:$APP_USER "$LOG_DIR"
        log_info "Created log directory: $LOG_DIR"
    else
        log_info "Log directory already exists"
    fi
}

install_systemd_services() {
    log_step "Installing systemd services..."
    
    # Copy service files
    cp "$APP_DIR/deployment/systemd/"*.service /etc/systemd/system/
    systemctl daemon-reload
    log_info "Systemd service files copied"
    
    # Enable and start services
    if ! systemctl is-enabled parliament-api-daphne >/dev/null 2>&1; then
        systemctl enable parliament-api-daphne
        log_info "Enabled parliament-api-daphne"
    fi
    
    # Enable dual Celery workers for 2x performance
    if ! systemctl is-enabled parliament-celery-worker-1 >/dev/null 2>&1; then
        systemctl enable parliament-celery-worker-1
        log_info "Enabled parliament-celery-worker-1 (8 concurrent workers)"
    fi
    
    if ! systemctl is-enabled parliament-celery-worker-2 >/dev/null 2>&1; then
        systemctl enable parliament-celery-worker-2
        log_info "Enabled parliament-celery-worker-2 (8 concurrent workers)"
    fi
    
    # Keep legacy worker disabled (use worker-1 and worker-2 instead)
    if systemctl is-enabled parliament-celery-worker >/dev/null 2>&1; then
        systemctl disable parliament-celery-worker
        log_info "Disabled legacy parliament-celery-worker (using dual workers instead)"
    fi
    
    if ! systemctl is-enabled parliament-celery-beat >/dev/null 2>&1; then
        systemctl enable parliament-celery-beat
        log_info "Enabled parliament-celery-beat"
    fi
    
    if ! systemctl is-enabled parliament-flower >/dev/null 2>&1; then
        systemctl enable parliament-flower
        log_info "Enabled parliament-flower"
    fi
}

setup_nginx() {
    log_step "Setting up Nginx..."
    
    # Check if SSL certificates exist
    if [ ! -d "/etc/letsencrypt/live/$DOMAIN" ]; then
        log_info "SSL certificates don't exist yet - creating HTTP-only config first"
        
        # Create temporary HTTP-only nginx config
        cat > /etc/nginx/sites-available/opensansad-api <<'NGINX_CONF'
# Temporary HTTP-only configuration for opensansad.co.in
# SSL will be added by certbot

upstream parliament_api {
    server 127.0.0.1:8000 fail_timeout=30s max_fails=3;
    keepalive 32;
}

server {
    listen 80;
    listen [::]:80;
    server_name api.opensansad.co.in;
    
    # Logging
    access_log /var/log/nginx/parliament_api_access.log combined;
    error_log /var/log/nginx/parliament_api_error.log warn;
    
    # Max upload size
    client_max_body_size 10M;
    
    # Static files
    location /static/ {
        alias /home/tusharanand/parliament_proceedings/parliament_api/staticfiles/;
        expires 1y;
        add_header Cache-Control "public, immutable";
        access_log off;
    }
    
    # Media files
    location /media/ {
        alias /home/tusharanand/parliament_proceedings/parliament_api/media/;
        expires 1h;
        add_header Cache-Control "public";
    }
    
    # Health check
    location /health/ {
        proxy_pass http://parliament_api;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        access_log off;
    }
    
    # All other requests
    location / {
        proxy_pass http://parliament_api;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120;
    }
}
NGINX_CONF
    else
        log_info "SSL certificates exist - using full SSL config"
        cp "$APP_DIR/deployment/nginx/parliament-api.conf" /etc/nginx/sites-available/opensansad-api
    fi
    
    # Enable site
    if [ ! -L /etc/nginx/sites-enabled/opensansad-api ]; then
        ln -s /etc/nginx/sites-available/opensansad-api /etc/nginx/sites-enabled/
        log_info "Nginx site enabled"
    else
        log_info "Nginx site already enabled"
    fi
    
    # Test configuration
    if nginx -t 2>&1 | grep -q "successful"; then
        log_info "Nginx configuration is valid"
    else
        log_error "Nginx configuration test failed!"
        nginx -t
        exit 1
    fi
    
    # Reload nginx
    systemctl reload nginx || systemctl start nginx
    log_info "Nginx reloaded"
}

stop_tmux_services() {
    log_step "Stopping tmux services..."
    
    cd /home/tusharanand/parliament_proceedings
    if [ -f "./startup.sh" ]; then
        sudo -u $APP_USER ./startup.sh stop || true
        log_info "Stopped tmux services"
    fi
    
    sleep 3
}

restart_services() {
    log_step "Starting systemd services..."
    
    # Stop legacy worker if running
    if systemctl is-active parliament-celery-worker >/dev/null 2>&1; then
        systemctl stop parliament-celery-worker
        log_info "Stopped legacy Celery worker"
    fi
    
    # Start main application
    systemctl restart parliament-api-daphne
    log_info "Started Daphne service"
    
    # Start dual Celery workers (16 total concurrent workers)
    systemctl restart parliament-celery-worker-1
    log_info "Started Celery worker 1 (8 concurrent workers)"
    
    systemctl restart parliament-celery-worker-2
    log_info "Started Celery worker 2 (8 concurrent workers)"
    
    # Start Celery beat
    systemctl restart parliament-celery-beat
    log_info "Started Celery beat"
    
    # Start Flower monitoring
    systemctl restart parliament-flower
    log_info "Started Flower monitoring"
    
    # Reload Nginx
    systemctl reload nginx
    log_info "Reloaded Nginx"
}

setup_ssl() {
    log_step "Setting up SSL certificate..."
    
    # Check if certificate already exists
    if [ -d "/etc/letsencrypt/live/$DOMAIN" ]; then
        log_info "SSL certificate already exists for $DOMAIN"
        
        # Update to full SSL config if not already
        log_info "Updating to full SSL configuration..."
        cp "$APP_DIR/deployment/nginx/parliament-api.conf" /etc/nginx/sites-available/opensansad-api
        
        if nginx -t 2>&1 | grep -q "successful"; then
            systemctl reload nginx
            log_info "Nginx updated with SSL configuration"
        fi
        return
    fi
    
    # Check if DNS is resolving
    log_info "Checking DNS resolution for $DOMAIN..."
    DNS_IP=$(dig +short $DOMAIN | head -1)
    
    if [ -z "$DNS_IP" ]; then
        log_warn "DNS is not resolving yet for $DOMAIN"
        log_warn "Please wait for DNS propagation and run this script again"
        log_info "You can check DNS with: dig $DOMAIN"
        log_info "API is accessible via HTTP at: http://$DOMAIN"
        return
    elif [ "$DNS_IP" != "34.180.6.36" ]; then
        log_warn "DNS is resolving to $DNS_IP instead of 34.180.6.36"
        log_warn "Current DNS: $DNS_IP"
        read -p "Continue with SSL setup anyway? (y/n) " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            log_info "Skipping SSL setup. Run this script again later."
            log_info "API is accessible via HTTP at: http://$DOMAIN"
            return
        fi
    else
        log_info "DNS correctly resolving to 34.180.6.36"
    fi
    
    log_info "Obtaining SSL certificate from Let's Encrypt..."
    if certbot --nginx -d $DOMAIN --non-interactive --agree-tos --email tusharanand1594@gmail.com --redirect; then
        log_info "SSL certificate installed successfully"
        
        # Now copy the full SSL config
        log_info "Updating to full SSL configuration..."
        cp "$APP_DIR/deployment/nginx/parliament-api.conf" /etc/nginx/sites-available/opensansad-api
        
        if nginx -t 2>&1 | grep -q "successful"; then
            systemctl reload nginx
            log_info "Nginx configuration updated"
        fi
    else
        log_warn "SSL certificate installation failed"
        log_warn "API is still accessible via HTTP at: http://$DOMAIN"
        log_info "Run this script again after DNS propagates"
    fi
}

check_health() {
    log_step "Checking application health..."
    sleep 5  # Wait for services to start
    
    # Check if application is responding
    if curl -s -f http://localhost:8000/health/ > /dev/null; then
        log_info "✓ Application is healthy!"
        log_info "✓ Local health check: http://localhost:8000/health/"
    else
        log_error "Application health check failed!"
        log_error "Check logs: sudo journalctl -u parliament-api-daphne -n 50"
        exit 1
    fi
}

print_summary() {
    log_step "🎉 Deployment Complete!"
    
    echo -e "${GREEN}════════════════════════════════════════════════════════${NC}"
    echo -e "${GREEN}Services Status:${NC}"
    echo -e "  ✓ Django API (Daphne) - Running on port 8000"
    echo -e "  ✓ Celery Worker 1     - 8 concurrent workers"
    echo -e "  ✓ Celery Worker 2     - 8 concurrent workers (16 total)"
    echo -e "  ✓ Celery Beat         - Scheduling tasks"
    echo -e "  ✓ Flower              - Monitoring on port 5555"
    echo -e "  ✓ Nginx               - Reverse proxy"
    echo ""
    echo -e "${GREEN}Access Points:${NC}"
    if [ -d "/etc/letsencrypt/live/$DOMAIN" ]; then
        echo -e "  🌐 API: ${BLUE}https://$DOMAIN${NC}"
        echo -e "  📚 Docs: ${BLUE}https://$DOMAIN/api/docs/${NC}"
        echo -e "  👑 Admin: ${BLUE}https://$DOMAIN/admin/${NC}"
    else
        echo -e "  🌐 API: ${BLUE}http://$DOMAIN${NC} (HTTP only - SSL pending)"
        echo -e "  📚 Docs: ${BLUE}http://$DOMAIN/api/docs/${NC}"
        echo -e "  👑 Admin: ${BLUE}http://$DOMAIN/admin/${NC}"
    fi
    echo ""
    echo -e "${GREEN}Useful Commands:${NC}"
    echo -e "  Check status:        ${YELLOW}sudo systemctl status parliament-api-daphne${NC}"
    echo -e "  View logs:           ${YELLOW}sudo journalctl -u parliament-api-daphne -f${NC}"
    echo -e "  Restart API:         ${YELLOW}sudo systemctl restart parliament-api-daphne${NC}"
    echo -e "  Restart Workers:     ${YELLOW}sudo systemctl restart parliament-celery-worker-{1,2}${NC}"
    echo -e "  Worker 1 logs:       ${YELLOW}tail -f /var/log/parliament_api/celery-worker-1.log${NC}"
    echo -e "  Worker 2 logs:       ${YELLOW}tail -f /var/log/parliament_api/celery-worker-2.log${NC}"
    echo -e "  Flower dashboard:    ${YELLOW}http://localhost:5555/flower/${NC}"
    echo ""
    echo -e "${GREEN}════════════════════════════════════════════════════════${NC}"
}

# Main deployment flow
main() {
    echo -e "${BLUE}"
    echo "╔════════════════════════════════════════════════════════╗"
    echo "║  Parliament API Deployment - opensansad.co.in         ║"
    echo "╚════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
    
    check_sudo
    check_prerequisites
    install_system_packages
    install_dependencies
    run_migrations
    collect_static
    setup_log_directory
    install_systemd_services
    setup_nginx
    stop_tmux_services
    restart_services
    check_health
    setup_ssl
    print_summary
}

# Run main function
main "$@"


