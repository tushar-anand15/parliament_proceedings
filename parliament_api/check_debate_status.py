#!/usr/bin/env python3
"""Check the error details for failed scraping jobs"""

import os
import sys
import django

# Django setup
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'parliament_api.settings')
django.setup()

from services.scraper.models import ScrapingJob, ScrapingError

# Get latest debate scraping job
latest_job = ScrapingJob.objects.filter(
    job_type='debates'
).order_by('-created_at').first()

if not latest_job:
    print("No debate scraping jobs found")
    exit(0)

print(f"📋 Latest Debate Scraping Job: #{latest_job.id}")
print(f"   Name: {latest_job.name}")
print(f"   Status: {latest_job.status}")
print(f"   Created: {latest_job.created_at}")
if latest_job.error_message:
    print(f"   Error: {latest_job.error_message}")
    
    # Get all errors for this job
    errors = ScrapingError.objects.filter(
        scraping_job=latest_job
    ).order_by('-occurred_at')[:5]
    
    if errors:
        print(f"\n❌ Errors for job #{latest_job.id}:")
        for error in errors:
            print(f"\n   Error ID: {error.id}")
            print(f"   Type: {error.error_type}")
            print(f"   Message: {error.error_message}")
            print(f"   Stack Trace: {error.stack_trace[:200] if error.stack_trace else 'None'}")
            print(f"   Question ID: {error.question_id}")
            print(f"   Occurred at: {error.occurred_at}")

# Also check Django logs
log_file = '/Users/tusharanand/Desktop/parliament_proceedings/parliament_api/logs/parliament.log'
if os.path.exists(log_file):
    print("\n📜 Recent Log Entries:")
    print("-" * 60)
    with open(log_file, 'r') as f:
        lines = f.readlines()
        # Get last 50 lines
        recent_lines = lines[-50:] if len(lines) > 50 else lines
        
        # Filter for debate-related errors
        for line in recent_lines:
            if 'debate' in line.lower() or 'error' in line.lower():
                print(line.strip())
