# Parliament API - Production Deployment Guide

This guide provides comprehensive instructions for deploying the Parliament API to a production environment with security, scalability, and monitoring.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Security Checklist](#security-checklist)
3. [Initial Setup](#initial-setup)
4. [Configuration](#configuration)
5. [Deployment Options](#deployment-options)
6. [Post-Deployment](#post-deployment)
7. [Monitoring & Maintenance](#monitoring--maintenance)
8. [Troubleshooting](#troubleshooting)

---

## Prerequisites

### System Requirements

- **OS**: Ubuntu 22.04 LTS or newer (recommended)
- **Python**: 3.11+
- **PostgreSQL**: 14+
- **Redis**: 6.0+
- **Nginx**: 1.18+
- **RAM**: Minimum 4GB, Recommended 8GB+
- **Storage**: Minimum 20GB SSD

### Required Accounts & Services

- Domain name with DNS access
- Google Cloud Storage account (for file storage)
- SSL certificate (Let's Encrypt recommended)
- (Optional) Sentry account for error tracking

---

## Security Checklist

Before deploying to production, ensure you complete these security steps:

### ✅ Must-Do Items

- [ ] Generate a new `SECRET_KEY` (never use the default!)
  ```bash
  python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
  ```
- [ ] Set `DEBUG=false` in `.env`
- [ ] Update `ALLOWED_HOSTS` with your actual domain(s)
- [ ] Change all default passwords (database, admin, etc.)
- [ ] Configure proper CORS origins (remove wildcards)
- [ ] Enable HTTPS and set security headers
- [ ] Configure firewall rules (ufw/iptables)
- [ ] Set up regular database backups
- [ ] Enable Fail2Ban for SSH protection
- [ ] Restrict admin panel access by IP (optional but recommended)
- [ ] Review and update GCS bucket permissions
- [ ] Set up proper file permissions (600 for .env, etc.)

### ✅ Recommended Items

- [ ] Set up Sentry for error tracking
- [ ] Configure email notifications
- [ ] Set up application monitoring
- [ ] Enable database connection pooling
- [ ] Configure log rotation
- [ ] Set up automated backups
- [ ] Create staging environment
- [ ] Document disaster recovery procedures

---

## Initial Setup

### Option 1: Automated Setup (Recommended)

```bash
# Clone or copy your application to the server
cd /path/to/parliament_api

# Run the initial setup script as root
sudo bash deployment/scripts/initial_setup.sh
```

This script will:
- Install system dependencies
- Create necessary directories
- Set up Python environment
- Configure PostgreSQL and Redis
- Install systemd services
- Set up Nginx configuration template

### Option 2: Manual Setup

#### 1. Install System Dependencies

```bash
sudo apt-get update
sudo apt-get install -y \
    python3.11 python3.11-venv python3-pip \
    postgresql postgresql-contrib \
    redis-server nginx git curl \
    build-essential libpq-dev python3-dev \
    certbot python3-certbot-nginx
```

#### 2. Create Application Directory

```bash
sudo mkdir -p /opt/parliament_api
sudo chown www-data:www-data /opt/parliament_api
sudo mkdir -p /var/log/parliament_api
sudo chown www-data:www-data /var/log/parliament_api
```

#### 3. Set Up Python Environment

```bash
cd /opt/parliament_api
sudo -u www-data python3.11 -m venv venv
sudo -u www-data venv/bin/pip install --upgrade pip wheel
```

#### 4. Configure PostgreSQL

```bash
sudo -u postgres psql <<EOF
CREATE DATABASE parliament_api;
CREATE USER parliament_user WITH PASSWORD 'your_secure_password';
ALTER ROLE parliament_user SET client_encoding TO 'utf8';
ALTER ROLE parliament_user SET default_transaction_isolation TO 'read committed';
ALTER ROLE parliament_user SET timezone TO 'UTC';
GRANT ALL PRIVILEGES ON DATABASE parliament_api TO parliament_user;
ALTER DATABASE parliament_api OWNER TO parliament_user;
EOF
```

#### 5. Copy Application Files

```bash
# Copy your application files to /opt/parliament_api
sudo rsync -av /path/to/source/ /opt/parliament_api/
sudo chown -R www-data:www-data /opt/parliament_api
```

#### 6. Install Python Dependencies

```bash
cd /opt/parliament_api
sudo -u www-data venv/bin/pip install -r requirements.txt
```

---

## Configuration

### 1. Environment Variables

Copy and configure the environment file:

```bash
cd /opt/parliament_api
sudo cp .env.example .env
sudo chown www-data:www-data .env
sudo chmod 600 .env
```

Edit `/opt/parliament_api/.env` with production values:

```bash
# CRITICAL: Update these values for production!

# Django Settings
SECRET_KEY='your-generated-secret-key-here'
DEBUG=false
ALLOWED_HOSTS=api.yourdomain.com,yourdomain.com

# Frontend URL (for CORS)
FRONTEND_URL=https://yourdomain.com
CORS_ALLOWED_ORIGINS=https://yourdomain.com,https://www.yourdomain.com

# Proxy Settings (if behind nginx/cloudflare)
USE_X_FORWARDED_HOST=true
SECURE_PROXY_SSL_HEADER=true

# Database
DB_NAME=parliament_api
DB_USER=parliament_user
DB_PASSWORD=your_secure_database_password
DB_HOST=localhost
DB_PORT=5432

# Redis & Celery
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0

# Google Cloud Storage
GCS_PROJECT_ID=your-project-id
GCS_CREDENTIALS_PATH=/opt/parliament_api/gcs-credentials.json
GCS_DEBATES_BUCKET=your-debates-bucket
GCS_QUESTIONS_BUCKET=your-questions-bucket

# Security Features
SECURE_SSL_REDIRECT=true
SESSION_COOKIE_SECURE=true
CSRF_COOKIE_SECURE=true
SECURE_HSTS_SECONDS=31536000

# Admin User
DJANGO_SUPERUSER_USERNAME=admin
DJANGO_SUPERUSER_EMAIL=admin@yourdomain.com
DJANGO_SUPERUSER_PASSWORD=your-secure-admin-password

# Optional: Sentry Error Tracking
SENTRY_DSN=https://your-sentry-dsn

# Optional: Email Configuration
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=true
EMAIL_HOST_USER=your-email@gmail.com
EMAIL_HOST_PASSWORD=your-app-password
```

### 2. Google Cloud Storage Setup

```bash
# Upload your GCS credentials
sudo cp /local/path/to/gcs-credentials.json /opt/parliament_api/
sudo chown www-data:www-data /opt/parliament_api/gcs-credentials.json
sudo chmod 600 /opt/parliament_api/gcs-credentials.json
```

### 3. Run Database Migrations

```bash
cd /opt/parliament_api
sudo -u www-data venv/bin/python manage.py migrate
```

### 4. Collect Static Files

```bash
sudo -u www-data venv/bin/python manage.py collectstatic --noinput
```

### 5. Create Superuser

```bash
sudo -u www-data venv/bin/python manage.py createsuperuser
```

---

## Deployment Options

### Option A: Daphne (ASGI) - Recommended for Django 5.x

Daphne is the recommended ASGI server for modern Django applications.

#### Install Systemd Service

```bash
sudo cp deployment/systemd/parliament-api-daphne.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable parliament-api-daphne
sudo systemctl start parliament-api-daphne
```

#### Check Status

```bash
sudo systemctl status parliament-api-daphne
sudo journalctl -u parliament-api-daphne -f
```

### Option B: Gunicorn (WSGI) - Traditional Approach

If you prefer Gunicorn:

```bash
sudo cp deployment/systemd/parliament-api-gunicorn.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable parliament-api-gunicorn
sudo systemctl start parliament-api-gunicorn
```

### Celery Workers

```bash
# Install and start Celery worker
sudo cp deployment/systemd/parliament-celery-worker.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable parliament-celery-worker
sudo systemctl start parliament-celery-worker

# Install and start Celery beat (scheduler)
sudo cp deployment/systemd/parliament-celery-beat.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable parliament-celery-beat
sudo systemctl start parliament-celery-beat

# Optional: Flower (Celery monitoring)
sudo cp deployment/systemd/parliament-flower.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable parliament-flower
sudo systemctl start parliament-flower
```

### Nginx Configuration

#### 1. Copy Configuration

```bash
sudo cp deployment/nginx/parliament-api.conf /etc/nginx/sites-available/parliament-api
```

#### 2. Edit Configuration

```bash
sudo nano /etc/nginx/sites-available/parliament-api
```

Update these values:
- `server_name` → your domain
- SSL certificate paths (if not using Let's Encrypt)
- IP restrictions for admin panel (optional)

#### 3. Enable Site

```bash
sudo ln -s /etc/nginx/sites-available/parliament-api /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

#### 4. Set Up SSL with Let's Encrypt

```bash
sudo certbot --nginx -d api.yourdomain.com
```

Follow the prompts to configure SSL.

---

## Post-Deployment

### 1. Test the Application

```bash
# Test health endpoint
curl https://api.yourdomain.com/health/

# Expected response:
# {"status":"healthy","service":"parliament_api"}

# Test API root
curl https://api.yourdomain.com/api/

# Test detailed health checks
curl https://api.yourdomain.com/ht/
```

### 2. Configure Firewall

```bash
sudo ufw allow 22/tcp    # SSH
sudo ufw allow 80/tcp    # HTTP
sudo ufw allow 443/tcp   # HTTPS
sudo ufw enable
```

### 3. Set Up Log Rotation

Create `/etc/logrotate.d/parliament_api`:

```
/var/log/parliament_api/*.log {
    daily
    rotate 14
    compress
    delaycompress
    notifempty
    create 0640 www-data www-data
    sharedscripts
    postrotate
        systemctl reload parliament-api-daphne
    endscript
}
```

### 4. Set Up Database Backups

Create backup script `/usr/local/bin/backup-parliament-db.sh`:

```bash
#!/bin/bash
BACKUP_DIR="/var/backups/parliament_api"
DATE=$(date +%Y%m%d_%H%M%S)

mkdir -p $BACKUP_DIR

pg_dump -U parliament_user parliament_api | gzip > \
    $BACKUP_DIR/parliament_api_$DATE.sql.gz

# Keep only last 7 days of backups
find $BACKUP_DIR -name "*.sql.gz" -mtime +7 -delete
```

Make executable and add to crontab:

```bash
sudo chmod +x /usr/local/bin/backup-parliament-db.sh
sudo crontab -e

# Add this line for daily backups at 2 AM
0 2 * * * /usr/local/bin/backup-parliament-db.sh
```

---

## Monitoring & Maintenance

### Service Status

```bash
# Check all services
sudo systemctl status parliament-api-daphne
sudo systemctl status parliament-celery-worker
sudo systemctl status parliament-celery-beat
sudo systemctl status nginx
sudo systemctl status postgresql
sudo systemctl status redis
```

### View Logs

```bash
# Application logs
sudo tail -f /var/log/parliament_api/daphne.log
sudo tail -f /var/log/parliament_api/celery-worker.log

# Django application logs
sudo tail -f /opt/parliament_api/logs/parliament.log

# Nginx logs
sudo tail -f /var/log/nginx/parliament_api_access.log
sudo tail -f /var/log/nginx/parliament_api_error.log

# Systemd journal
sudo journalctl -u parliament-api-daphne -f
```

### Flower (Celery Monitoring)

If you enabled Flower:

```bash
# Access via SSH tunnel
ssh -L 5555:localhost:5555 user@your-server

# Then open in browser: http://localhost:5555/flower/
```

### Update Deployment

```bash
# Use the deployment script
sudo bash /opt/parliament_api/deployment/scripts/deploy.sh
```

Or manually:

```bash
cd /opt/parliament_api
sudo -u www-data git pull origin main
sudo -u www-data venv/bin/pip install -r requirements.txt
sudo -u www-data venv/bin/python manage.py migrate
sudo -u www-data venv/bin/python manage.py collectstatic --noinput
sudo systemctl restart parliament-api-daphne
sudo systemctl restart parliament-celery-worker
```

---

## Troubleshooting

### Application Won't Start

```bash
# Check logs
sudo journalctl -u parliament-api-daphne -n 100

# Check if port 8000 is in use
sudo lsof -i :8000

# Test configuration
cd /opt/parliament_api
sudo -u www-data venv/bin/python manage.py check --deploy
```

### Database Connection Issues

```bash
# Test PostgreSQL connection
sudo -u postgres psql -U parliament_user -d parliament_api

# Check PostgreSQL logs
sudo tail -f /var/log/postgresql/postgresql-*.log
```

### Redis Connection Issues

```bash
# Test Redis connection
redis-cli ping

# Check Redis status
sudo systemctl status redis
```

### Celery Tasks Not Running

```bash
# Check Celery worker status
sudo systemctl status parliament-celery-worker

# Monitor Celery logs
sudo tail -f /var/log/parliament_api/celery-worker.log

# Check Redis for pending tasks
redis-cli
> KEYS celery*
```

### 502 Bad Gateway

Usually means the application server is down:

```bash
# Check if Daphne/Gunicorn is running
sudo systemctl status parliament-api-daphne

# Check if application port is accessible
curl http://localhost:8000/health/

# Restart application
sudo systemctl restart parliament-api-daphne
```

### Static Files Not Loading

```bash
# Re-collect static files
cd /opt/parliament_api
sudo -u www-data venv/bin/python manage.py collectstatic --clear --noinput

# Check permissions
ls -la /opt/parliament_api/staticfiles/

# Check Nginx configuration
sudo nginx -t
```

---

## Security Best Practices

### 1. Regular Updates

```bash
# Update system packages
sudo apt-get update && sudo apt-get upgrade

# Update Python packages
cd /opt/parliament_api
sudo -u www-data venv/bin/pip list --outdated
```

### 2. Monitor Failed Login Attempts

```bash
# Check Axes (failed login tracking)
cd /opt/parliament_api
sudo -u www-data venv/bin/python manage.py axes_list_attempts
```

### 3. Review Nginx Access Logs

```bash
# Most accessed endpoints
sudo awk '{print $7}' /var/log/nginx/parliament_api_access.log | sort | uniq -c | sort -rn | head -20

# Top IP addresses
sudo awk '{print $1}' /var/log/nginx/parliament_api_access.log | sort | uniq -c | sort -rn | head -20
```

### 4. Database Maintenance

```bash
# Run VACUUM ANALYZE monthly
sudo -u postgres psql -d parliament_api -c "VACUUM ANALYZE;"
```

---

## Additional Resources

- [Django Deployment Checklist](https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/)
- [Daphne Documentation](https://github.com/django/daphne)
- [Nginx Security Headers](https://securityheaders.com/)
- [Let's Encrypt](https://letsencrypt.org/)
- [Celery Production Checklist](https://docs.celeryq.dev/en/stable/userguide/deployment.html)

---

## Support

For issues or questions:
- Check application logs first
- Review this deployment guide
- Check the project documentation
- Open an issue on the project repository

---

**Last Updated**: October 2025  
**Version**: 1.0.0


