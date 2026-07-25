# Parliament API - Monitoring Guide

This guide explains how to monitor the deployed Parliament API backend, tasks, and downloads.

## Table of Contents
1. [Monitoring Overview](#monitoring-overview)
2. [Accessing Flower (Celery Monitoring)](#accessing-flower-celery-monitoring)
3. [API Health Checks](#api-health-checks)
4. [Monitoring Logs](#monitoring-logs)
5. [Database Monitoring](#database-monitoring)
6. [Task Status Endpoints](#task-status-endpoints)

---

## Monitoring Overview

Your Parliament API is deployed at:
- **API Base URL**: `https://api.opensansad.co.in`
- **Flower (Celery Monitoring)**: `https://api.opensansad.co.in/flower/` (access via SSH tunnel)
- **Admin Panel**: `https://api.opensansad.co.in/admin/`

---

## Accessing Flower (Celery Monitoring)

Flower is the web-based monitoring tool for Celery tasks. It's currently restricted to localhost for security.

### Option 1: SSH Tunnel (Recommended)

Create an SSH tunnel from your local machine:

```bash
# Replace 'tusharanand' with your SSH username
# Replace 'api.opensansad.co.in' or use the server IP address
ssh -L 5555:localhost:5555 tusharanand@api.opensansad.co.in

# Keep this terminal open and access Flower at:
# http://localhost:5555/flower/
```

Then open in your browser: **http://localhost:5555/flower/**

### Option 2: Temporarily Allow Your IP (Less Secure)

Edit the nginx configuration to allow your IP address:

```bash
# SSH into the server
sudo nano /etc/nginx/sites-available/parliament-api

# Find the Flower location block (around line 183) and add your IP:
location /flower/ {
    allow 127.0.0.1;
    allow YOUR_IP_ADDRESS;  # Add your IP here
    deny all;
    
    proxy_pass http://127.0.0.1:5555/flower/;
    ...
}

# Reload nginx
sudo nginx -t
sudo systemctl reload nginx
```

Then access: **https://api.opensansad.co.in/flower/**

**Remember to remove your IP when done for security!**

### What to Monitor in Flower

In Flower, you can:
- **Tasks**: View all running, queued, and completed tasks
- **Workers**: See active Celery workers and their status
- **Monitor**: Real-time task execution graphs
- **Broker**: Redis queue statistics
- **Task Details**: Click on any task to see:
  - Arguments passed
  - Status (PENDING, STARTED, SUCCESS, FAILURE)
  - Runtime
  - Result or error traceback
  - Retry information

---

## API Health Checks

### Basic Health Check

```bash
curl https://api.opensansad.co.in/health/
```

Expected response:
```json
{
  "status": "healthy",
  "service": "parliament_api"
}
```

### Detailed Health Check

```bash
curl https://api.opensansad.co.in/ht/
```

This checks:
- Database connectivity
- Redis connectivity
- Disk space
- Memory usage

### API Root

```bash
TOKEN="YOUR_TOKEN"
curl -H "Authorization: Token ${TOKEN}" https://api.opensansad.co.in/api/
```

---

## Monitoring Logs

### View Real-time Application Logs

SSH into the server and use these commands:

#### Daphne (Django Application) Logs
```bash
# Real-time logs
sudo tail -f /var/log/parliament_api/daphne.log

# Or using journalctl
sudo journalctl -u parliament-api-daphne -f
```

#### Celery Worker Logs
```bash
# Real-time logs
sudo tail -f /var/log/parliament_api/celery-worker.log

# Or using journalctl
sudo journalctl -u parliament-celery-worker -f
```

#### Celery Beat (Scheduler) Logs
```bash
sudo tail -f /var/log/parliament_api/celery-beat.log

# Or using journalctl
sudo journalctl -u parliament-celery-beat -f
```

#### Flower Logs
```bash
sudo tail -f /var/log/parliament_api/flower.log
```

#### Django Application Logs
```bash
sudo tail -f /opt/parliament_api/logs/parliament.log
```

#### Nginx Access Logs
```bash
# See all API requests
sudo tail -f /var/log/nginx/parliament_api_access.log

# See errors
sudo tail -f /var/log/nginx/parliament_api_error.log
```

### Filtering Logs

```bash
# Show only errors
sudo grep -i error /var/log/parliament_api/celery-worker.log

# Show logs for specific task
sudo grep "download_question_pdf" /var/log/parliament_api/celery-worker.log

# Show recent failed tasks
sudo grep -i "FAILED" /var/log/parliament_api/celery-worker.log | tail -20

# Monitor PDF downloads
sudo grep "Downloading PDF" /var/log/parliament_api/celery-worker.log -A 2
```

---

## Database Monitoring

### Check Database Status

```bash
# SSH into server
sudo -u postgres psql

# Connect to database
\c parliament_api

# Check table sizes
SELECT 
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
FROM pg_tables
WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC
LIMIT 10;

# Check question counts
SELECT COUNT(*) FROM questions_question;

# Check debate counts
SELECT COUNT(*) FROM debates_debate;

# Check master data counts
SELECT COUNT(*) FROM questions_questionmasterdata;

# Exit
\q
```

### Use the Built-in Monitoring Script

```bash
cd /opt/parliament_api
sudo -u www-data venv/bin/python monitor_db.py
```

This shows:
- Question statistics
- Debate statistics
- Download progress
- Storage usage

---

## Task Status Endpoints

Use these API endpoints to check task status programmatically:

### LS Question Task Status

```bash
TOKEN="YOUR_TOKEN"
TASK_ID="your-task-id-here"

curl -H "Authorization: Token ${TOKEN}" \
  https://api.opensansad.co.in/api/questions/ls/task-status/${TASK_ID}/
```

### RS Question Task Status

```bash
curl -H "Authorization: Token ${TOKEN}" \
  https://api.opensansad.co.in/api/questions/rs/task-status/${TASK_ID}/
```

### Debate Task Status

```bash
curl -H "Authorization: Token ${TOKEN}" \
  https://api.opensansad.co.in/api/debates/task-status/${TASK_ID}/
```

### Check Debate Scraping Status

```bash
curl -H "Authorization: Token ${TOKEN}" \
  https://api.opensansad.co.in/api/debates/scraping-status/
```

Response includes:
- Active jobs
- Completed jobs
- Failed jobs
- Current task status

---

## Statistics Endpoints

### LS Question Statistics

```bash
curl -H "Authorization: Token ${TOKEN}" \
  https://api.opensansad.co.in/api/questions/ls/download-statistics/
```

### RS Question Statistics

```bash
curl -H "Authorization: Token ${TOKEN}" \
  https://api.opensansad.co.in/api/questions/rs/statistics/
```

### Debate Statistics

```bash
curl -H "Authorization: Token ${TOKEN}" \
  https://api.opensansad.co.in/api/debates/statistics/
```

Response includes:
- Total debates in database
- Downloaded vs pending
- Breakdown by session
- Failed downloads
- Storage usage

---

## Service Status

Check if all services are running:

```bash
# SSH into server
ssh tusharanand@api.opensansad.co.in

# Check all services
sudo systemctl status parliament-api-daphne
sudo systemctl status parliament-celery-worker
sudo systemctl status parliament-celery-beat
sudo systemctl status parliament-flower
sudo systemctl status redis
sudo systemctl status postgresql
sudo systemctl status nginx

# Quick status of all at once
sudo systemctl status parliament-api-daphne parliament-celery-worker parliament-celery-beat parliament-flower redis postgresql nginx
```

### Restart Services if Needed

```bash
# Restart Django app
sudo systemctl restart parliament-api-daphne

# Restart Celery worker
sudo systemctl restart parliament-celery-worker

# Restart Celery beat
sudo systemctl restart parliament-celery-beat

# Restart Flower
sudo systemctl restart parliament-flower

# Restart all Parliament API services
sudo systemctl restart parliament-api-daphne parliament-celery-worker parliament-celery-beat parliament-flower
```

---

## Redis Monitoring

Check Redis for task queues:

```bash
# SSH into server and connect to Redis
redis-cli

# Check queue lengths
LLEN celery
LLEN celery:pdf_download

# See all keys
KEYS celery*

# Get info about Redis
INFO

# Exit
exit
```

---

## Google Cloud Storage Monitoring

Check if PDFs are being uploaded to GCS:

```bash
# Using gsutil (if installed on server)
gsutil ls gs://your-debates-bucket/
gsutil ls gs://your-questions-bucket/

# Check bucket size
gsutil du -sh gs://your-debates-bucket/
gsutil du -sh gs://your-questions-bucket/
```

---

## Common Issues and Solutions

### Issue: Tasks Not Running

**Check:**
1. Is Celery worker running? `sudo systemctl status parliament-celery-worker`
2. Is Redis running? `sudo systemctl status redis`
3. Check worker logs: `sudo journalctl -u parliament-celery-worker -n 50`

**Solution:**
```bash
sudo systemctl restart parliament-celery-worker
sudo systemctl restart redis
```

### Issue: PDFs Not Downloading

**Check:**
1. Task status in Flower
2. Worker logs for errors: `sudo grep "download.*pdf" /var/log/parliament_api/celery-worker.log -i`
3. Network connectivity from server

**Debug:**
```bash
# Test network from server
curl -I https://sansad.in
curl -I https://eparlib.nic.in
```

### Issue: High Memory Usage

**Check:**
```bash
# Memory usage
free -h

# Top processes
top

# Celery worker memory
ps aux | grep celery
```

**Solution:**
```bash
# Restart Celery worker to clear memory
sudo systemctl restart parliament-celery-worker
```

---

## Performance Monitoring

### Monitor API Response Times

```bash
# Watch nginx access logs for slow requests
sudo tail -f /var/log/nginx/parliament_api_access.log | grep -v "/health/"

# Analyze response times
sudo awk '{print $NF}' /var/log/nginx/parliament_api_access.log | sort -n | tail -20
```

### Monitor Download Rates

```bash
# Count PDFs downloaded in last hour
sudo grep "PDF.*downloaded successfully" /var/log/parliament_api/celery-worker.log | grep "$(date +%Y-%m-%d\ %H)" | wc -l

# Count failed downloads in last hour
sudo grep "Failed to download PDF" /var/log/parliament_api/celery-worker.log | grep "$(date +%Y-%m-%d\ %H)" | wc -l
```

---

## Automated Monitoring Script

Create a simple monitoring script:

```bash
#!/bin/bash
# Save as /usr/local/bin/check-parliament-api.sh

echo "=== Parliament API Status ==="
echo ""

echo "Services:"
systemctl is-active parliament-api-daphne
systemctl is-active parliament-celery-worker
systemctl is-active redis

echo ""
echo "Recent Errors (last 10):"
journalctl -u parliament-celery-worker --since "10 minutes ago" | grep -i error | tail -10

echo ""
echo "Active Tasks:"
redis-cli LLEN celery

echo ""
echo "Disk Usage:"
df -h /opt/parliament_api
```

Make it executable:
```bash
sudo chmod +x /usr/local/bin/check-parliament-api.sh
```

Run it:
```bash
sudo /usr/local/bin/check-parliament-api.sh
```

---

## Quick Reference Commands

```bash
# View running tasks in Flower
# → Open SSH tunnel first, then browse to http://localhost:5555/flower/

# Check if services are running
sudo systemctl status parliament-api-daphne parliament-celery-worker parliament-celery-beat

# View live logs
sudo tail -f /var/log/parliament_api/celery-worker.log

# Check task queue
redis-cli LLEN celery

# Restart everything
sudo systemctl restart parliament-api-daphne parliament-celery-worker parliament-celery-beat

# Test API health
curl https://api.opensansad.co.in/health/

# Get statistics
curl -H "Authorization: Token YOUR_TOKEN" \
  https://api.opensansad.co.in/api/debates/statistics/
```

---

**Last Updated**: October 2025


