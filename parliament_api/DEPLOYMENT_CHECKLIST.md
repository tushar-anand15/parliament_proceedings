# 🚀 Parliament API - Complete Deployment Checklist

**Domain:** `yourdomain.com`  
**Backend Server:** Separate server for API  
**Frontend Server:** Separate server for web app  
**Date Prepared:** October 6, 2025

---

## 📋 Overview

You have:
- ✅ Backend API (Django) ready to deploy
- ✅ Domain name registered
- ⚠️ **Frontend**: No frontend code in this repository
- ⚠️ **Backend**: Needs configuration

---

## 🎯 DEPLOYMENT PLAN

### Recommended Architecture

```
Domain Setup:
├── api.yourdomain.com     → Backend API Server (Django)
├── yourdomain.com         → Frontend Server (React/Next.js/etc.)
└── www.yourdomain.com     → Redirect to yourdomain.com
```

---

## 🔧 BACKEND SERVER CONFIGURATION (API)

### ✅ **Step 1: Domain & DNS Configuration**

Configure your DNS records:

| Type  | Name    | Value                    | TTL  |
|-------|---------|--------------------------|------|
| A     | api     | [BACKEND_SERVER_IP]      | 3600 |
| A     | @       | [FRONTEND_SERVER_IP]     | 3600 |
| CNAME | www     | yourdomain.com           | 3600 |

**Action Required:**
- [ ] Get your backend server IP address
- [ ] Get your frontend server IP address
- [ ] Add DNS records in your domain registrar's control panel
- [ ] Wait 1-24 hours for DNS propagation (check with `dig api.yourdomain.com`)

---

### ✅ **Step 2: Backend Server - System Setup**

**Prerequisites:**
- [ ] Ubuntu 22.04+ server with root access
- [ ] Minimum 4GB RAM (8GB recommended)
- [ ] 20GB+ SSD storage
- [ ] Open ports: 22 (SSH), 80 (HTTP), 443 (HTTPS)

**Install System Dependencies:**

```bash
# Update system
sudo apt-get update && sudo apt-get upgrade -y

# Install dependencies
sudo apt-get install -y \
    python3.11 python3.11-venv python3-pip \
    postgresql postgresql-contrib \
    redis-server nginx git curl \
    build-essential libpq-dev python3-dev \
    certbot python3-certbot-nginx
```

**Action Required:**
- [ ] SSH into your backend server
- [ ] Run the above commands
- [ ] Verify: `python3.11 --version`, `psql --version`, `redis-cli --version`

---

### ✅ **Step 3: Backend - Database Setup**

```bash
# Create PostgreSQL database and user
sudo -u postgres psql <<EOF
CREATE DATABASE parliament_api;
CREATE USER parliament_user WITH PASSWORD 'YOUR_SECURE_PASSWORD_HERE';
ALTER ROLE parliament_user SET client_encoding TO 'utf8';
ALTER ROLE parliament_user SET default_transaction_isolation TO 'read committed';
ALTER ROLE parliament_user SET timezone TO 'UTC';
GRANT ALL PRIVILEGES ON DATABASE parliament_api TO parliament_user;
ALTER DATABASE parliament_api OWNER TO parliament_user;
\q
EOF
```

**Action Required:**
- [ ] Run the above commands
- [ ] Save your database password securely
- [ ] Test connection: `psql -U parliament_user -d parliament_api -h localhost`

---

### ✅ **Step 4: Backend - Google Cloud Storage Setup**

**You already have GCS credentials in your repo, but verify:**

```bash
# Check if credentials file exists
ls -la parliament-process-90c920ce4243.json
```

**Action Required:**
- [ ] Verify you have GCS credentials JSON file
- [ ] Confirm your GCS project ID: ____________________
- [ ] Confirm your GCS buckets exist:
  - Debates bucket name: ____________________
  - Questions bucket name: ____________________
- [ ] Verify bucket permissions (Storage Object Admin role)

---

### ✅ **Step 5: Backend - Copy Application Code**

```bash
# Create application directory
sudo mkdir -p /opt/parliament_api
sudo chown $USER:$USER /opt/parliament_api

# Copy your code (from local machine or git)
# Option A: From your local machine
rsync -avz --exclude='*.pyc' --exclude='__pycache__' --exclude='.git' \
    --exclude='venv' --exclude='env' --exclude='*.log' \
    /path/to/local/parliament_api/ your-server:/opt/parliament_api/

# Option B: From git repository
git clone <your-repo-url> /opt/parliament_api
```

**Action Required:**
- [ ] Copy application code to `/opt/parliament_api`
- [ ] Copy GCS credentials: `sudo cp parliament-process-*.json /opt/parliament_api/gcs-credentials.json`
- [ ] Set ownership: `sudo chown -R www-data:www-data /opt/parliament_api`

---

### ✅ **Step 6: Backend - Create .env File**

```bash
# Copy the example file
cd /opt/parliament_api
sudo cp .env.example .env
sudo chown www-data:www-data .env
sudo chmod 600 .env

# Edit the .env file
sudo nano .env
```

**CRITICAL: Update these values in .env:**

```bash
# Generate a new SECRET_KEY
python3 -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
# Copy the output and paste in .env

# Update these values:
SECRET_KEY=<paste-generated-key-here>
DEBUG=false
ALLOWED_HOSTS=api.yourdomain.com,yourdomain.com
FRONTEND_URL=https://yourdomain.com
CORS_ALLOWED_ORIGINS=https://yourdomain.com,https://www.yourdomain.com
CSRF_TRUSTED_ORIGINS=https://yourdomain.com,https://api.yourdomain.com

# Database
DB_PASSWORD=<your-secure-database-password>

# GCS (update with your actual values)
GCS_PROJECT_ID=<your-project-id>
GCS_DEBATES_BUCKET=<your-debates-bucket>
GCS_QUESTIONS_BUCKET=<your-questions-bucket>

# Admin
ADMIN_PASSWORD=<your-admin-password>
DJANGO_SUPERUSER_PASSWORD=<your-admin-password>
ADMIN_EMAIL=admin@yourdomain.com
```

**Action Required:**
- [ ] Generate new SECRET_KEY
- [ ] Update all YOUR_* placeholders in .env
- [ ] Replace `yourdomain.com` with your actual domain
- [ ] Save and exit

---

### ✅ **Step 7: Backend - Python Environment & Dependencies**

```bash
cd /opt/parliament_api

# Create virtual environment
sudo -u www-data python3.11 -m venv venv

# Install dependencies
sudo -u www-data venv/bin/pip install --upgrade pip wheel
sudo -u www-data venv/bin/pip install -r requirements.txt

# Run migrations
sudo -u www-data venv/bin/python manage.py migrate

# Create superuser
sudo -u www-data venv/bin/python manage.py createsuperuser --noinput

# Collect static files
sudo -u www-data venv/bin/python manage.py collectstatic --noinput

# Create log directories
sudo mkdir -p /var/log/parliament_api
sudo chown www-data:www-data /var/log/parliament_api
```

**Action Required:**
- [ ] Run all commands above
- [ ] Verify no errors during migration
- [ ] Confirm static files are collected

---

### ✅ **Step 8: Backend - Systemd Services**

```bash
# Copy systemd service files
sudo cp deployment/systemd/*.service /etc/systemd/system/
sudo systemctl daemon-reload

# Enable services
sudo systemctl enable parliament-api-daphne
sudo systemctl enable parliament-celery-worker
sudo systemctl enable parliament-celery-beat
sudo systemctl enable redis-server

# Start services
sudo systemctl start redis-server
sudo systemctl start parliament-api-daphne
sudo systemctl start parliament-celery-worker
sudo systemctl start parliament-celery-beat

# Check status
sudo systemctl status parliament-api-daphne
sudo systemctl status parliament-celery-worker
sudo systemctl status redis-server
```

**Action Required:**
- [ ] Start all services
- [ ] Verify services are running: `sudo systemctl status parliament-api-daphne`
- [ ] Check logs if any service fails: `sudo journalctl -u parliament-api-daphne -n 50`

---

### ✅ **Step 9: Backend - Nginx Configuration**

```bash
# Copy nginx config
sudo cp deployment/nginx/parliament-api.conf /etc/nginx/sites-available/parliament-api

# Edit the config to update domain
sudo nano /etc/nginx/sites-available/parliament-api

# Find and replace all instances of:
#   api.yourdomain.com → api.youractual domain.com
```

**BEFORE enabling SSL, test HTTP first:**

```bash
# Enable site (HTTP only for now)
sudo ln -s /etc/nginx/sites-available/parliament-api /etc/nginx/sites-enabled/

# Test configuration
sudo nginx -t

# Reload nginx
sudo systemctl reload nginx
```

**Test HTTP access:**
```bash
curl http://api.yourdomain.com/health/
# Should return: {"status":"healthy","service":"parliament_api"}
```

**Action Required:**
- [ ] Update nginx config with your domain
- [ ] Enable nginx site
- [ ] Test with curl (HTTP)
- [ ] Verify health endpoint returns 200 OK

---

### ✅ **Step 10: Backend - SSL Certificate (Let's Encrypt)**

**IMPORTANT: DNS must be pointing to your server first!**

```bash
# Verify DNS is working
dig api.yourdomain.com
ping api.yourdomain.com

# Install SSL certificate
sudo certbot --nginx -d api.yourdomain.com

# Follow the prompts:
# - Enter email address
# - Agree to terms
# - Choose to redirect HTTP to HTTPS (option 2)

# Test SSL renewal (dry-run)
sudo certbot renew --dry-run
```

**Action Required:**
- [ ] Verify DNS is propagated
- [ ] Run certbot and follow prompts
- [ ] Test HTTPS: `curl https://api.yourdomain.com/health/`
- [ ] Verify SSL: Visit https://www.ssllabs.com/ssltest/ and test your domain

---

### ✅ **Step 11: Backend - Firewall Configuration**

```bash
# Configure UFW firewall
sudo ufw allow 22/tcp      # SSH
sudo ufw allow 80/tcp      # HTTP
sudo ufw allow 443/tcp     # HTTPS
sudo ufw enable

# Check status
sudo ufw status
```

**Action Required:**
- [ ] Configure firewall
- [ ] Verify you can still SSH into server
- [ ] Test HTTPS access from browser

---

### ✅ **Step 12: Backend - Initialize Data (Optional)**

```bash
# Initialize parliamentary master data
cd /opt/parliament_api
sudo -u www-data venv/bin/python manage.py initialize_questions_master_data

# Check database
sudo -u www-data venv/bin/python manage.py shell
>>> from services.questions.models import LokSabhaMaster
>>> print(LokSabhaMaster.objects.count())
>>> exit()
```

**Action Required:**
- [ ] Decide if you want to initialize data now or later
- [ ] If now, run the command above (can take 5-10 minutes)

---

## 🌐 FRONTEND SERVER CONFIGURATION

### ⚠️ **ISSUE: No Frontend Code Found**

**Your repository contains only the backend API.** You need to:

1. **Option A: You Have Frontend Elsewhere**
   - Deploy your existing frontend to the frontend server
   - Update frontend API URL to `https://api.yourdomain.com`
   - Configure CORS (already done in backend .env)

2. **Option B: Build Frontend from Scratch**
   - Use the `FRONTEND_INTEGRATION_GUIDE.md` as API documentation
   - Build React/Next.js/Vue frontend
   - Implement authentication flow (register/login)
   - Use the Data Explorer endpoints for queries

3. **Option C: Use API Directly**
   - Skip frontend for now
   - Use the Swagger UI: `https://api.yourdomain.com/api/docs/`
   - Test with Postman/curl
   - Build frontend later

---

### ✅ **Frontend Setup Checklist** (if you have frontend code)

**On your frontend server:**

```bash
# Example for Next.js/React
# Install Node.js
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt-get install -y nodejs

# Copy frontend code
mkdir -p /opt/frontend
# Copy your frontend files here

# Install dependencies
cd /opt/frontend
npm install

# Set environment variables
cat > .env.production <<EOF
NEXT_PUBLIC_API_URL=https://api.yourdomain.com
NEXT_PUBLIC_API_BASE_URL=https://api.yourdomain.com/api
EOF

# Build
npm run build

# Configure PM2 or systemd to run the app
npm install -g pm2
pm2 start npm --name "frontend" -- start
pm2 save
pm2 startup
```

**Frontend Nginx Config:**

```nginx
server {
    listen 80;
    server_name yourdomain.com www.yourdomain.com;
    
    location / {
        proxy_pass http://localhost:3000;  # or your frontend port
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
    }
}
```

**Then setup SSL:**
```bash
sudo certbot --nginx -d yourdomain.com -d www.yourdomain.com
```

**Action Required:**
- [ ] Deploy frontend code (if you have it)
- [ ] Configure environment variables with API URL
- [ ] Setup nginx reverse proxy
- [ ] Install SSL certificate
- [ ] Test frontend can reach API

---

## 🔒 SECURITY CHECKLIST

### ✅ **Post-Deployment Security**

**Backend Server:**
- [ ] Changed all default passwords
- [ ] SECRET_KEY is unique and secure
- [ ] DEBUG=false in production
- [ ] SSL/HTTPS is working
- [ ] Firewall is configured (ports 22, 80, 443 only)
- [ ] .env file permissions are 600
- [ ] Database password is strong
- [ ] Admin password is strong
- [ ] Regular backups configured (see below)

**Frontend Server (if separate):**
- [ ] SSL/HTTPS is working
- [ ] Firewall configured
- [ ] API URL uses HTTPS

**General:**
- [ ] DNS records are correct
- [ ] CORS is properly configured
- [ ] Rate limiting is enabled
- [ ] Failed login tracking (Axes) is active

---

## 💾 BACKUP CONFIGURATION

**Set up automated database backups:**

```bash
# Create backup script
sudo nano /usr/local/bin/backup-parliament-db.sh
```

```bash
#!/bin/bash
BACKUP_DIR="/var/backups/parliament_api"
DATE=$(date +%Y%m%d_%H%M%S)
mkdir -p $BACKUP_DIR

# Backup database
PGPASSWORD="your_db_password" pg_dump -U parliament_user -h localhost parliament_api | \
    gzip > $BACKUP_DIR/parliament_api_$DATE.sql.gz

# Keep only last 7 days
find $BACKUP_DIR -name "*.sql.gz" -mtime +7 -delete
```

```bash
# Make executable
sudo chmod +x /usr/local/bin/backup-parliament-db.sh

# Add to cron (daily at 2 AM)
sudo crontab -e
# Add this line:
0 2 * * * /usr/local/bin/backup-parliament-db.sh
```

**Action Required:**
- [ ] Create backup script
- [ ] Update with your database password
- [ ] Test: `sudo /usr/local/bin/backup-parliament-db.sh`
- [ ] Add to cron

---

## 🧪 TESTING CHECKLIST

### ✅ **Backend API Tests**

```bash
# 1. Health Check
curl https://api.yourdomain.com/health/
# Expected: {"status":"healthy","service":"parliament_api"}

# 2. API Documentation
# Visit: https://api.yourdomain.com/api/docs/
# Should show Swagger UI

# 3. Register User
curl -X POST https://api.yourdomain.com/api/auth/register/ \
  -H "Content-Type: application/json" \
  -d '{
    "username": "testuser",
    "email": "test@example.com",
    "password": "TestPass123!",
    "first_name": "Test",
    "last_name": "User",
    "user_type": "citizen"
  }'

# 4. Login
curl -X POST https://api.yourdomain.com/api/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{
    "username": "testuser",
    "password": "TestPass123!"
  }'
# Save the token from response

# 5. Test Authenticated Endpoint
curl -X GET https://api.yourdomain.com/api/explorer/metadata/ \
  -H "Authorization: Token ***REMOVED_SECRET***"
```

**Action Required:**
- [ ] All health checks pass
- [ ] Swagger UI loads
- [ ] Can register user
- [ ] Can login and get token
- [ ] Authenticated endpoints work
- [ ] CORS works from frontend domain

---

## 📊 MONITORING

### ✅ **Service Monitoring**

```bash
# Check all services
sudo systemctl status parliament-api-daphne
sudo systemctl status parliament-celery-worker
sudo systemctl status parliament-celery-beat
sudo systemctl status nginx
sudo systemctl status postgresql
sudo systemctl status redis

# Check logs
sudo tail -f /var/log/parliament_api/daphne.log
sudo tail -f /var/log/parliament_api/celery-worker.log
sudo tail -f /var/log/nginx/parliament_api_access.log
sudo tail -f /var/log/nginx/parliament_api_error.log
```

**Optional: Flower (Celery Monitor)**

Access via SSH tunnel:
```bash
# From your local machine
ssh -L 5555:localhost:5555 user@your-backend-server

# Then visit: http://localhost:5555/flower/
```

**Action Required:**
- [ ] All services running
- [ ] No errors in logs
- [ ] Set up monitoring/alerting (optional)

---

## 📝 REMAINING CONFIGURATION SUMMARY

### ❌ **MISSING / NEEDS CONFIGURATION:**

1. **Backend Server:**
   - [ ] .env file doesn't exist - needs to be created from .env.example
   - [ ] Domain name needs to be configured in .env and nginx
   - [ ] SSL certificates need to be installed
   - [ ] GCS bucket names need to be confirmed
   - [ ] Database needs to be created
   - [ ] Services need to be started

2. **Frontend:**
   - [ ] **No frontend code in this repository**
   - [ ] Need to deploy frontend separately
   - [ ] Need to point to API: `https://api.yourdomain.com`

3. **DNS:**
   - [ ] A records need to be created
   - [ ] DNS propagation (1-24 hours)

4. **Security:**
   - [ ] Generate new SECRET_KEY
   - [ ] Set strong passwords
   - [ ] Configure backups

---

## 🎯 QUICK START DEPLOYMENT (Backend Only)

**If you just want to get the backend API running quickly:**

```bash
# 1. DNS: Point api.yourdomain.com to your server IP

# 2. On your server, run the automated setup script:
cd /path/to/parliament_api
sudo bash deployment/scripts/initial_setup.sh

# 3. Edit .env file:
sudo nano /opt/parliament_api/.env
# Update: SECRET_KEY, domain, passwords, GCS settings

# 4. Run migrations:
cd /opt/parliament_api
sudo -u www-data venv/bin/python manage.py migrate
sudo -u www-data venv/bin/python manage.py collectstatic --noinput

# 5. Start services:
sudo systemctl start parliament-api-daphne
sudo systemctl start parliament-celery-worker

# 6. Configure nginx and SSL:
sudo nano /etc/nginx/sites-available/parliament-api  # Update domain
sudo ln -s /etc/nginx/sites-available/parliament-api /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d api.yourdomain.com

# 7. Test:
curl https://api.yourdomain.com/health/
```

---

## 📚 DOCUMENTATION REFERENCES

- **Backend Deployment:** `DEPLOYMENT_GUIDE.md`
- **Frontend Integration:** `FRONTEND_INTEGRATION_GUIDE.md`
- **Data Explorer:** `DATA_EXPLORER_IMPLEMENTATION.md`
- **API Documentation:** https://api.yourdomain.com/api/docs/ (after deployment)

---

## ✅ COMPLETION CHECKLIST

### Backend (API Server)
- [ ] DNS configured (api.yourdomain.com → server IP)
- [ ] System dependencies installed
- [ ] PostgreSQL database created
- [ ] Redis installed and running
- [ ] Application code deployed to `/opt/parliament_api`
- [ ] .env file created and configured
- [ ] Python virtual environment created
- [ ] Dependencies installed
- [ ] Migrations run successfully
- [ ] Static files collected
- [ ] Systemd services installed and running
- [ ] Nginx configured
- [ ] SSL certificate installed
- [ ] Firewall configured
- [ ] Backups configured
- [ ] Health checks pass
- [ ] API accessible at https://api.yourdomain.com

### Frontend (Web Server)
- [ ] DNS configured (yourdomain.com → server IP)
- [ ] Frontend code deployed
- [ ] Environment variables configured (API_URL)
- [ ] Frontend builds successfully
- [ ] Nginx configured
- [ ] SSL certificate installed
- [ ] Can communicate with API
- [ ] Authentication flow works

### Final Verification
- [ ] Register test user
- [ ] Login and receive token
- [ ] Make authenticated API calls
- [ ] CORS works from frontend domain
- [ ] All services running
- [ ] No errors in logs
- [ ] Backups working
- [ ] Monitoring setup

---

## 🆘 TROUBLESHOOTING

See `DEPLOYMENT_GUIDE.md` section "Troubleshooting" for common issues.

**Quick checks:**
```bash
# Service status
sudo systemctl status parliament-api-daphne

# Check logs
sudo journalctl -u parliament-api-daphne -n 100

# Test database connection
sudo -u postgres psql -U parliament_user -d parliament_api

# Test Redis
redis-cli ping

# Check port 8000
sudo lsof -i :8000
```

---

**Good luck with your deployment! 🚀**

Replace all instances of `yourdomain.com` with your actual domain name.
