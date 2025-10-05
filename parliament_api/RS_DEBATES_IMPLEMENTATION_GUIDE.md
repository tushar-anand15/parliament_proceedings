# RS Debates Implementation Guide

Quick reference for implementing RS debates service based on API documentation.

## Quick Start Checklist

- [ ] Extend Debate model with `time_slot` field
- [ ] Create migration for model changes
- [ ] Implement `RSDebateMasterDataService`
- [ ] Implement `RSDebateScraperService`
- [ ] Create Celery tasks for RS debates
- [ ] Add API endpoints for RS debates
- [ ] Test with recent session data

---

## 1. Model Changes

### Add to `services/debates/models.py`

```python
class Debate(models.Model):
    # ... existing fields ...
    
    # NEW FIELD for RS debates
    time_slot = models.CharField(
        max_length=50, 
        blank=True, 
        null=True,
        help_text='Time slot for RS debates (e.g., "11:00-12:00 Noon", "Full Day")'
    )
    
    class Meta:
        unique_together = [
            'parent_institution',
            'lok_sabha',  # For LS
            'session', 
            'debate_date', 
            'debate_category',
            'language',
            'time_slot'  # NEW: Allows multiple PDFs per day for RS
        ]
```

### Migration Command
```bash
cd parliament_api
python manage.py makemigrations debates
python manage.py migrate debates
```

---

## 2. Create RS Master Data Service

### File: `services/debates/rs_debate_master_data_service.py`

```python
import requests
import logging
from datetime import datetime
from typing import List, Dict, Optional
from django.utils import timezone
from django.db import transaction

logger = logging.getLogger(__name__)


class RSDebateMasterDataService:
    """Service for fetching RS debate metadata"""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Origin': 'https://sansad.in',
            'Referer': 'https://sansad.in/',
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
            'sec-fetch-site': 'cross-site',
            'sec-fetch-mode': 'cors',
            'sec-fetch-dest': 'empty'
        })
        
        self.api_rs_base = "https://sansad.in/api_rs"
        self.rsdoc_base = "https://rsdoc.nic.in/business"
        
    def fetch_all_rs_sessions(self) -> List[int]:
        """
        Fetch all RS session numbers
        Returns: [189, 190, 191, ..., 268]
        """
        try:
            url = f"{self.api_rs_base}/debate/rs-session"
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            
            sessions = response.json()
            logger.info(f"✅ Fetched {len(sessions)} RS sessions")
            return sessions
            
        except Exception as e:
            logger.error(f"❌ Error fetching RS sessions: {e}")
            return []
    
    def fetch_session_dates(self, session_no: int) -> List[Dict]:
        """
        Fetch sitting dates for an RS session
        
        Returns list of dicts with structure:
        {
            "Id": 17165,
            "sessionNo": 268,
            "SittingDate": "2025-08-21T00:00:00",
            "CreatedOn": "2025-07-03T18:51:02.8",
            ...
        }
        """
        try:
            url = f"{self.rsdoc_base}/SessionDates"
            params = {'Sessionno': session_no}
            
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()
            
            dates = response.json()
            logger.info(f"✅ Session {session_no}: {len(dates)} sitting dates")
            return dates
            
        except Exception as e:
            logger.error(f"❌ Error fetching dates for session {session_no}: {e}")
            return []
    
    def fetch_verbatim_debates(self, session_no: int, date_str: str) -> List[Dict]:
        """
        Fetch verbatim debate PDFs for a specific date
        
        Args:
            session_no: RS session number (e.g., 268)
            date_str: Date in DD/MM/YYYY format (e.g., "21/07/2025")
            
        Returns list of dicts with PDF metadata including:
        - FileUrl: Direct download URL
        - Time: Time slot (e.g., "11:00-12:00 Noon")
        - FileSize: Size in bytes
        - Name: Filename
        """
        try:
            url = f"{self.rsdoc_base}/BusinessVerbatim"
            params = {
                'ses_no': session_no,
                'ses_dt': date_str
            }
            
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()
            
            debates = response.json()
            logger.info(f"✅ Session {session_no}, Date {date_str}: {len(debates)} PDFs")
            return debates
            
        except Exception as e:
            logger.error(f"❌ Error fetching debates for {session_no}/{date_str}: {e}")
            return []
    
    @staticmethod
    def convert_iso_to_dd_mm_yyyy(iso_date_str: str) -> str:
        """
        Convert ISO date to DD/MM/YYYY format
        Input: "2025-08-21T00:00:00"
        Output: "21/08/2025"
        """
        try:
            # Handle both with and without timezone
            if 'T' in iso_date_str:
                dt = datetime.fromisoformat(iso_date_str.replace('Z', '+00:00'))
            else:
                dt = datetime.fromisoformat(iso_date_str)
            
            return dt.strftime('%d/%m/%Y')
        except Exception as e:
            logger.error(f"Date conversion error: {e}")
            return ""
    
    def initialize_rs_debate_master_data(self, force_update: bool = False) -> Dict:
        """
        Initialize RS debate master data
        Fetches all sessions, dates, and debate metadata
        """
        result = {
            'status': 'SUCCESS',
            'sessions_processed': 0,
            'dates_processed': 0,
            'debates_discovered': 0,
            'errors': []
        }
        
        try:
            # Step 1: Get all sessions
            logger.info("🏛️  Step 1: Fetching RS sessions...")
            sessions = self.fetch_all_rs_sessions()
            
            if not sessions:
                result['status'] = 'ERROR'
                result['errors'].append('No sessions fetched')
                return result
            
            # Step 2: For each session, get dates and debates
            for session_no in sessions[-5:]:  # Start with last 5 sessions for testing
                logger.info(f"📅 Processing Session {session_no}...")
                
                # Get sitting dates
                dates = self.fetch_session_dates(session_no)
                result['sessions_processed'] += 1
                
                for date_obj in dates[:3]:  # Limit to 3 dates per session for testing
                    sitting_date = date_obj.get('SittingDate', '')
                    date_str = self.convert_iso_to_dd_mm_yyyy(sitting_date)
                    
                    if not date_str:
                        continue
                    
                    # Get debate PDFs for this date
                    debates = self.fetch_verbatim_debates(session_no, date_str)
                    result['dates_processed'] += 1
                    result['debates_discovered'] += len(debates)
                    
                    logger.info(f"   📄 {date_str}: {len(debates)} PDFs")
            
            return result
            
        except Exception as e:
            logger.error(f"❌ Error in initialization: {e}")
            result['status'] = 'ERROR'
            result['errors'].append(str(e))
            return result
```

---

## 3. Create RS Scraper Service

### File: `services/debates/rs_debate_scraper_service.py`

```python
import logging
import uuid
from typing import Dict, List, Optional
from datetime import datetime
from django.utils import timezone
from django.db import transaction

from .models import Debate, DebateMasterData
from .rs_debate_master_data_service import RSDebateMasterDataService
from services.files.pdf_download_service import PDFDownloadService
from services.questions.models import Session, ParliamentInstitution

logger = logging.getLogger(__name__)


class RSDebateScraperService:
    """Service for scraping RS verbatim debates"""
    
    def __init__(self):
        self.master_service = RSDebateMasterDataService()
        self.pdf_service = PDFDownloadService()
        
    def scrape_verbatim_debates_for_date(
        self, 
        session_no: int, 
        sitting_date: str,
        session_obj: Session = None
    ) -> Dict:
        """
        Scrape all verbatim debates for a specific date
        
        Args:
            session_no: RS session number
            sitting_date: Date in DD/MM/YYYY format
            session_obj: Optional Session model instance
            
        Returns:
            Dict with scraping results
        """
        result = {
            'status': 'SUCCESS',
            'session_no': session_no,
            'date': sitting_date,
            'debates_created': 0,
            'debates_updated': 0,
            'errors': []
        }
        
        try:
            # Fetch debate metadata from API
            debates_data = self.master_service.fetch_verbatim_debates(
                session_no, 
                sitting_date
            )
            
            if not debates_data:
                logger.warning(f"No debates found for session {session_no}, date {sitting_date}")
                result['status'] = 'NO_DATA'
                return result
            
            # Get RS institution
            rs_institution = ParliamentInstitution.objects.filter(
                name='Rajya Sabha'
            ).first()
            
            if not rs_institution:
                result['status'] = 'ERROR'
                result['errors'].append('Rajya Sabha institution not found in database')
                return result
            
            # Convert date for database storage
            debate_date = datetime.strptime(sitting_date, '%d/%m/%Y').date()
            
            # Process each debate PDF (time slot)
            for debate_item in debates_data:
                try:
                    # Extract fields
                    file_url = debate_item.get('FileUrl', '')
                    time_slot = debate_item.get('Time', '')
                    file_name = debate_item.get('Name', '')
                    file_size = debate_item.get('FileSize', 0)
                    
                    if not file_url:
                        continue
                    
                    # Create or update Debate record
                    debate, created = Debate.objects.update_or_create(
                        parent_institution=rs_institution,
                        session=session_obj,
                        debate_date=debate_date,
                        debate_category='verbatim',
                        time_slot=time_slot,
                        defaults={
                            'debate_id': str(uuid.uuid4()),
                            'pdf_url': file_url,
                            'file_size': file_size,
                            'raw_api_data': debate_item,
                            'status': 'pending',
                            'language': 'en',
                            'debate_type': 'verbatim'
                        }
                    )
                    
                    if created:
                        result['debates_created'] += 1
                        logger.info(f"✅ Created debate: {debate_date} - {time_slot}")
                    else:
                        result['debates_updated'] += 1
                        logger.info(f"🔄 Updated debate: {debate_date} - {time_slot}")
                    
                except Exception as e:
                    error_msg = f"Error processing debate {file_name}: {e}"
                    logger.error(error_msg)
                    result['errors'].append(error_msg)
            
            return result
            
        except Exception as e:
            logger.error(f"❌ Error scraping debates: {e}")
            result['status'] = 'ERROR'
            result['errors'].append(str(e))
            return result
    
    def download_debate_pdf(self, debate_id: str) -> Dict:
        """
        Download PDF for a specific debate
        
        Args:
            debate_id: Debate UUID
            
        Returns:
            Dict with download result
        """
        try:
            debate = Debate.objects.get(debate_id=debate_id)
            
            if not debate.pdf_url:
                return {
                    'status': 'ERROR',
                    'message': 'No PDF URL available'
                }
            
            # Update status
            debate.status = 'downloading'
            debate.download_attempts += 1
            debate.last_download_attempt = timezone.now()
            debate.save()
            
            # Download PDF using existing service
            download_result = self.pdf_service.download_pdf(
                url=debate.pdf_url,
                filename=f"rs_debate_{debate.debate_date}_{debate.time_slot}.pdf"
            )
            
            if download_result['status'] == 'SUCCESS':
                # Update debate with file reference
                debate.status = 'completed'
                debate.pdf_file = download_result.get('file_obj')
                debate.save()
                
                return {
                    'status': 'SUCCESS',
                    'debate_id': debate_id,
                    'file_path': download_result.get('file_path')
                }
            else:
                debate.status = 'failed'
                debate.error_message = download_result.get('error', '')
                debate.save()
                
                return {
                    'status': 'FAILED',
                    'debate_id': debate_id,
                    'error': download_result.get('error')
                }
                
        except Debate.DoesNotExist:
            return {
                'status': 'ERROR',
                'message': f'Debate {debate_id} not found'
            }
        except Exception as e:
            logger.error(f"Error downloading debate {debate_id}: {e}")
            return {
                'status': 'ERROR',
                'message': str(e)
            }
```

---

## 4. Celery Tasks

### Add to `services/debates/tasks.py`

```python
from celery import shared_task
from .rs_debate_scraper_service import RSDebateScraperService
from .rs_debate_master_data_service import RSDebateMasterDataService
import logging

logger = logging.getLogger(__name__)


@shared_task(name='scrape_rs_verbatim_debates_for_session')
def scrape_rs_verbatim_debates_for_session(session_no: int):
    """
    Scrape all verbatim debates for an RS session
    """
    try:
        logger.info(f"🚀 Starting RS verbatim debate scraping for session {session_no}")
        
        master_service = RSDebateMasterDataService()
        scraper_service = RSDebateScraperService()
        
        # Get session dates
        dates = master_service.fetch_session_dates(session_no)
        
        results = {
            'session_no': session_no,
            'total_dates': len(dates),
            'processed': 0,
            'errors': []
        }
        
        for date_obj in dates:
            sitting_date = date_obj.get('SittingDate', '')
            date_str = master_service.convert_iso_to_dd_mm_yyyy(sitting_date)
            
            if not date_str:
                continue
            
            # Scrape debates for this date
            result = scraper_service.scrape_verbatim_debates_for_date(
                session_no, 
                date_str
            )
            
            results['processed'] += 1
            
            if result['status'] == 'ERROR':
                results['errors'].extend(result.get('errors', []))
        
        logger.info(f"✅ Completed RS session {session_no} scraping")
        return results
        
    except Exception as e:
        logger.error(f"❌ Error in RS session scraping task: {e}")
        return {
            'status': 'ERROR',
            'error': str(e)
        }


@shared_task(name='download_rs_debate_pdf')
def download_rs_debate_pdf(debate_id: str):
    """
    Download PDF for a specific RS debate
    """
    try:
        scraper_service = RSDebateScraperService()
        result = scraper_service.download_debate_pdf(debate_id)
        return result
        
    except Exception as e:
        logger.error(f"❌ Error downloading RS debate {debate_id}: {e}")
        return {
            'status': 'ERROR',
            'error': str(e)
        }
```

---

## 5. Management Command

### File: `services/debates/management/commands/initialize_rs_debates.py`

```python
from django.core.management.base import BaseCommand
from services.debates.rs_debate_master_data_service import RSDebateMasterDataService
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Initialize RS debates master data'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force refresh data even if it exists'
        )
        
        parser.add_argument(
            '--session',
            type=int,
            help='Specific session number to process'
        )
    
    def handle(self, *args, **options):
        force = options['force']
        session_no = options.get('session')
        
        self.stdout.write(self.style.SUCCESS('🏛️  Initializing RS Debates Master Data'))
        
        service = RSDebateMasterDataService()
        
        if session_no:
            # Process specific session
            self.stdout.write(f"Processing session {session_no}...")
            dates = service.fetch_session_dates(session_no)
            
            for date_obj in dates:
                sitting_date = date_obj.get('SittingDate')
                date_str = service.convert_iso_to_dd_mm_yyyy(sitting_date)
                
                debates = service.fetch_verbatim_debates(session_no, date_str)
                self.stdout.write(f"  📅 {date_str}: {len(debates)} PDFs")
        else:
            # Initialize all
            result = service.initialize_rs_debate_master_data(force_update=force)
            
            self.stdout.write(self.style.SUCCESS(
                f"✅ Completed!\n"
                f"   Sessions: {result['sessions_processed']}\n"
                f"   Dates: {result['dates_processed']}\n"
                f"   Debates: {result['debates_discovered']}\n"
            ))
            
            if result.get('errors'):
                self.stdout.write(self.style.ERROR(f"Errors: {len(result['errors'])}"))
```

---

## 6. Testing Commands

### Test Master Data Service
```bash
cd parliament_api

# Initialize RS debates (test mode - last 5 sessions)
python manage.py initialize_rs_debates

# Force refresh specific session
python manage.py initialize_rs_debates --session 268 --force
```

### Test in Django Shell
```python
python manage.py shell

from services.debates.rs_debate_master_data_service import RSDebateMasterDataService

service = RSDebateMasterDataService()

# Test 1: Get all sessions
sessions = service.fetch_all_rs_sessions()
print(f"Sessions: {len(sessions)} - Latest: {sessions[-1]}")

# Test 2: Get dates for session 268
dates = service.fetch_session_dates(268)
print(f"Session 268 has {len(dates)} sitting dates")

# Test 3: Get debates for specific date
debates = service.fetch_verbatim_debates(268, "21/07/2025")
print(f"Found {len(debates)} PDFs for 21/07/2025")

# Show time slots
for d in debates:
    print(f"  - {d['Time']}: {d['Name']} ({d['FileSize']} bytes)")
```

---

## 7. API Endpoints (Views)

### Add to `services/debates/views.py`

```python
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from .rs_debate_master_data_service import RSDebateMasterDataService
from .rs_debate_scraper_service import RSDebateScraperService

@api_view(['GET'])
def rs_sessions_list(request):
    """Get all RS session numbers"""
    try:
        service = RSDebateMasterDataService()
        sessions = service.fetch_all_rs_sessions()
        
        return Response({
            'status': 'success',
            'count': len(sessions),
            'sessions': sessions
        })
    except Exception as e:
        return Response({
            'status': 'error',
            'message': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
def rs_session_dates(request, session_no):
    """Get sitting dates for an RS session"""
    try:
        service = RSDebateMasterDataService()
        dates = service.fetch_session_dates(session_no)
        
        return Response({
            'status': 'success',
            'session_no': session_no,
            'count': len(dates),
            'dates': dates
        })
    except Exception as e:
        return Response({
            'status': 'error',
            'message': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
def rs_verbatim_debates(request, session_no):
    """Get verbatim debates for a session and date"""
    date_str = request.query_params.get('date')  # Format: DD/MM/YYYY
    
    if not date_str:
        return Response({
            'status': 'error',
            'message': 'Date parameter required (format: DD/MM/YYYY)'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        service = RSDebateMasterDataService()
        debates = service.fetch_verbatim_debates(session_no, date_str)
        
        return Response({
            'status': 'success',
            'session_no': session_no,
            'date': date_str,
            'count': len(debates),
            'debates': debates
        })
    except Exception as e:
        return Response({
            'status': 'error',
            'message': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
```

### Add to `services/debates/urls.py`

```python
from django.urls import path
from . import views

urlpatterns = [
    # ... existing LS endpoints ...
    
    # RS Verbatim Debates
    path('rs/sessions/', views.rs_sessions_list, name='rs_sessions_list'),
    path('rs/sessions/<int:session_no>/dates/', views.rs_session_dates, name='rs_session_dates'),
    path('rs/sessions/<int:session_no>/debates/', views.rs_verbatim_debates, name='rs_verbatim_debates'),
]
```

---

## 8. Quick Test Curl Commands

```bash
# Test RS sessions endpoint
curl http://localhost:8000/api/debates/rs/sessions/

# Test session dates
curl http://localhost:8000/api/debates/rs/sessions/268/dates/

# Test verbatim debates for specific date
curl "http://localhost:8000/api/debates/rs/sessions/268/debates/?date=21/07/2025"
```

---

## Common Pitfalls & Solutions

### 1. Date Format Issues
**Problem**: API returns ISO format but expects DD/MM/YYYY
**Solution**: Always use `convert_iso_to_dd_mm_yyyy()` helper

### 2. Unique Constraint Violations
**Problem**: Multiple PDFs for same date
**Solution**: Include `time_slot` in unique_together constraint

### 3. Missing Institution
**Problem**: Rajya Sabha institution not in database
**Solution**: Create it first or ensure initialization

### 4. Cross-Origin Issues
**Problem**: API calls blocked
**Solution**: Include proper headers (Origin, Referer)

### 5. Large Response Sizes
**Problem**: Full Day PDFs are 5-7 MB
**Solution**: Implement chunked downloads or streaming

---

## Next Steps

1. Test with recent sessions (265-268)
2. Validate all time slots are captured
3. Test PDF download functionality
4. Add error recovery mechanisms
5. Implement progress tracking
6. Add admin interface for monitoring
7. Document other RS debate types (Synopsis, etc.)

---

# RS OFFICIAL DEBATES (Part 1 & Part 2)

## Overview

RS Official Debates use a completely different API architecture from Verbatim Debates. This is a REST API with advanced search/browse capabilities that provides access to:
- **Part 1**: Question and Answer (640,638 records)
- **Part 2**: Other than Question and Answer (97,360 records)

Total records: **~738,000** debates from 1952-2024 across sessions 166-265.

---

## API Architecture

### Base URL
```
https://rsdebate.nic.in/restv3
```

### Key Endpoints

| Endpoint | Purpose |
|----------|---------|
| `/field/browse` | Browse/aggregate by specific field (year, session, type, etc.) |
| `/fetch/all` | Fetch actual debate records with filtering and pagination |

---

## 1. Browse by Field (Metadata Discovery)

### Endpoint
```
GET https://rsdebate.nic.in/restv3/field/browse
```

### Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `field` | string | Yes | Field to browse (year, sessionNo, type, date, ministry, etc.) |
| `start` | int | No | Pagination start (default: 0) |
| `rows` | int | No | Number of results (default: 10) |
| `collectionId` | string | Yes | Collection filter: `(1,2)` for both parts |

### Available Fields to Browse

| Field | Description | Use Case |
|-------|-------------|----------|
| `year` | Years with debates | Get all available years (1952-2024) |
| `sessionNo` | Session numbers | Get all sessions (166-265) |
| `type` | Debate types | Part 1 vs Part 2 |
| `date` | Specific dates | Browse by date |
| `ministry` | Government ministries | Filter by ministry |
| `ministerName` | Minister names | Find debates by minister |
| `questionerName` | MP names | Find debates by questioner |
| `debateTitleSubject` | Debate subjects | Browse by topic |
| `title` | Debate titles | Common debate titles |
| `questionType` | Question types | Starred, Unstarred, Short notice |

### Example 1: Get All Years

```bash
curl 'https://rsdebate.nic.in/restv3/field/browse?field=year&start=0&rows=200&collectionId=(1,2)' \
  -H 'Accept: application/json, text/plain, */*' \
  -H 'Origin: https://sansad.in' \
  -H 'Referer: https://sansad.in/'
```

**Response:**
```json
{
  "rowsCount": "73",
  "message": "OK",
  "statusCode": "200",
  "records": [
    {"name": "2024", "count": "4573"},
    {"name": "2023", "count": "11003"},
    {"name": "2022", "count": "11210"},
    ...
    {"name": "1952", "count": "940"}
  ]
}
```

### Example 2: Get All Sessions

```bash
curl 'https://rsdebate.nic.in/restv3/field/browse?field=sessionNo&start=0&rows=100&collectionId=(1,2)' \
  -H 'Accept: application/json, text/plain, */*' \
  -H 'Origin: https://sansad.in'
```

**Response:**
```json
{
  "rowsCount": "265",
  "records": [
    {"name": "265", "count": "3109"},
    {"name": "264", "count": "7134"},
    ...
    {"name": "166", "count": "2145"}
  ]
}
```

### Example 3: Get Debate Types

```bash
curl 'https://rsdebate.nic.in/restv3/field/browse?field=type&start=0&rows=100&collectionId=(1,2)' \
  -H 'Accept: application/json, text/plain, */*' \
  -H 'Origin: https://sansad.in'
```

**Response:**
```json
{
  "rowsCount": "2",
  "records": [
    {"name": "Part 1(Question and Answer)", "count": "640638"},
    {"name": "Part 2(Other than Question and Answer)", "count": "97360"}
  ]
}
```

---

## 2. Fetch Debate Records

### Endpoint
```
GET https://rsdebate.nic.in/restv3/fetch/all
```

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `start` | int | Yes | Pagination offset (0-based) |
| `rows` | int | Yes | Number of records to fetch (max recommended: 50) |
| `collectionId` | string | Yes | `(1,2)` for both Part 1 & 2 |
| `order` | string | No | Sort order: `all_desc` or `all_asc` |
| `year` | int | No | Filter by specific year |
| `sessionNo` | int | No | Filter by session number |
| `type` | string | No | Filter by type |
| `date` | string | No | Filter by date (YYYY-MM-DD) |
| `ministry` | string | No | Filter by ministry name |
| `bucketFields` | string | No | Comma-separated fields for aggregation |

### Example 1: Fetch Recent Debates (Paginated)

```bash
curl 'https://rsdebate.nic.in/restv3/fetch/all?start=0&rows=50&order=all_desc&collectionId=(1,2)' \
  -H 'Accept: application/json, text/plain, */*' \
  -H 'Origin: https://sansad.in' \
  -H 'Referer: https://sansad.in/'
```

### Example 2: Filter by Year (2024)

```bash
curl 'https://rsdebate.nic.in/restv3/fetch/all?start=0&rows=50&year=2024&order=all_desc&collectionId=(1,2)' \
  -H 'Accept: application/json, text/plain, */*' \
  -H 'Origin: https://sansad.in'
```

### Example 3: Filter by Session (265)

```bash
curl 'https://rsdebate.nic.in/restv3/fetch/all?start=0&rows=50&sessionNo=265&order=all_desc&collectionId=(1,2)' \
  -H 'Accept: application/json, text/plain, */*' \
  -H 'Origin: https://sansad.in'
```

### Response Structure

```json
{
  "rowsCount": "738000",
  "message": "OK",
  "statusCode": "200",
  "start": "0",
  "rows": "50",
  "timeTaken": "37ms",
  "records": [
    {
      "title": "DISCONTINUATION OF SENIOR CITIZEN CONCESSION",
      "debateTitleSubject": "WRITTEN ANSWERS TO UNSTARRED QUESTIONS",
      "date": "2024-08-09",
      "type": "Part 1(Question and Answer)",
      "sessionNo": "265",
      "questionNo": "2189",
      "questionType": "Unstarred",
      "resourceId": "749152",
      "year": "2024",
      "pageNoFromTo": "314-314",
      "handle": "123456789/748709",
      "members": [],
      "questionerName": ["PHULO DEVI NETAM", "RAJANI ASHOKRAO PATIL"],
      "ministerName": ["ASHWINI VAISHNAW"],
      "ministry": ["ELECTRONICS AND INFORMATION TECHNOLOGY", "RAILWAYS"],
      "files": ["https://rsdebate.nic.in/bitstream/123456789/748709/1/PQ_265_09082024_U2189_p314_p314.pdf"]
    }
  ]
}
```

### Response Fields

#### Core Fields
| Field | Type | Description |
|-------|------|-------------|
| `title` | string | Debate/question title |
| `debateTitleSubject` | string | Subject category |
| `date` | string | Date (YYYY-MM-DD) |
| `type` | string | Part 1 or Part 2 |
| `sessionNo` | string | RS session number |
| `year` | string | Year |
| `resourceId` | string | Unique resource ID |
| `handle` | string | Handle for bitstream |
| `pageNoFromTo` | string | Page range (e.g., "314-314") |

#### Question-Specific Fields (Part 1)
| Field | Type | Description |
|-------|------|-------------|
| `questionNo` | string | Question number |
| `questionType` | string | Starred, Unstarred, Short notice |
| `questionerName` | array | Names of MPs who asked |
| `ministerName` | array | Ministers who answered |
| `ministry` | array | Ministries involved |

#### File Fields
| Field | Type | Description |
|-------|------|-------------|
| `files` | array | **Direct PDF download URLs** |
| `language` | array | Languages available |

---

## Implementation Strategy for Official Debates

### Service Architecture

```python
class RSOfficialDebateService:
    """Service for RS Official Debates (Part 1 & Part 2)"""
    
    def __init__(self):
        self.base_url = "https://rsdebate.nic.in/restv3"
        self.session = requests.Session()
        self.session.headers.update({
            'Accept': 'application/json, text/plain, */*',
            'Origin': 'https://sansad.in',
            'Referer': 'https://sansad.in/',
            'User-Agent': 'Mozilla/5.0 ...'
        })
    
    def browse_years(self) -> List[Dict]:
        """Get all available years with debate counts"""
        url = f"{self.base_url}/field/browse"
        params = {
            'field': 'year',
            'start': 0,
            'rows': 200,
            'collectionId': '(1,2)'
        }
        response = self.session.get(url, params=params)
        return response.json()['records']
    
    def browse_sessions(self) -> List[Dict]:
        """Get all available sessions with debate counts"""
        url = f"{self.base_url}/field/browse"
        params = {
            'field': 'sessionNo',
            'start': 0,
            'rows': 300,
            'collectionId': '(1,2)'
        }
        response = self.session.get(url, params=params)
        return response.json()['records']
    
    def fetch_debates(
        self, 
        start: int = 0, 
        rows: int = 50,
        year: Optional[int] = None,
        session_no: Optional[int] = None,
        date: Optional[str] = None
    ) -> Dict:
        """
        Fetch official debates with optional filters
        
        Args:
            start: Pagination offset
            rows: Number of records
            year: Filter by year (e.g., 2024)
            session_no: Filter by session (e.g., 265)
            date: Filter by date (YYYY-MM-DD)
        """
        url = f"{self.base_url}/fetch/all"
        params = {
            'start': start,
            'rows': rows,
            'order': 'all_desc',
            'collectionId': '(1,2)'
        }
        
        if year:
            params['year'] = year
        if session_no:
            params['sessionNo'] = session_no
        if date:
            params['date'] = date
        
        response = self.session.get(url, params=params)
        return response.json()
    
    def fetch_all_debates_for_session(self, session_no: int) -> List[Dict]:
        """
        Fetch all debates for a specific session (with pagination)
        """
        all_records = []
        start = 0
        rows_per_page = 50
        
        while True:
            result = self.fetch_debates(
                start=start,
                rows=rows_per_page,
                session_no=session_no
            )
            
            records = result.get('records', [])
            if not records:
                break
            
            all_records.extend(records)
            start += rows_per_page
            
            # Check if we've fetched all
            total = int(result.get('rowsCount', 0))
            if start >= total:
                break
        
        return all_records
```

---

## Database Model for Official Debates

### Option 1: Extend Existing Debate Model

```python
class Debate(models.Model):
    # ... existing fields ...
    
    # NEW FIELDS for Official Debates
    question_number = models.CharField(max_length=20, blank=True, null=True)
    question_type = models.CharField(max_length=50, blank=True, null=True)
    # Starred, Unstarred, Short notice
    
    questioners = models.JSONField(default=list, blank=True)
    # List of MP names who asked question
    
    ministers = models.JSONField(default=list, blank=True)
    # List of minister names who answered
    
    ministries = models.JSONField(default=list, blank=True)
    # List of ministries involved
    
    page_range = models.CharField(max_length=50, blank=True, null=True)
    # e.g., "314-314" or "326-328"
    
    resource_id = models.CharField(max_length=50, blank=True, null=True, unique=True)
    # Unique ID from API
    
    handle = models.CharField(max_length=100, blank=True, null=True)
    # Handle for bitstream URL
```

### Option 2: Create Separate Model (Recommended)

```python
class RSOfficialDebate(models.Model):
    """Model for RS Official Debates (Part 1 & Part 2)"""
    
    # Unique identifiers
    resource_id = models.CharField(max_length=50, unique=True)
    handle = models.CharField(max_length=100)
    
    # Session information
    session_number = models.CharField(max_length=10)
    debate_date = models.DateField()
    year = models.IntegerField()
    
    # Debate classification
    debate_type = models.CharField(max_length=50)
    # "Part 1(Question and Answer)" or "Part 2(Other than Question and Answer)"
    
    title = models.CharField(max_length=500)
    subject = models.CharField(max_length=500)
    
    # Question fields (Part 1 only)
    question_number = models.CharField(max_length=20, blank=True)
    question_type = models.CharField(max_length=50, blank=True)
    # Starred, Unstarred, Short notice
    
    # People involved
    questioners = models.JSONField(default=list)
    ministers = models.JSONField(default=list)
    ministries = models.JSONField(default=list)
    members = models.JSONField(default=list)
    
    # Document info
    page_range = models.CharField(max_length=50)
    pdf_urls = models.JSONField(default=list)
    
    # Status
    status = models.CharField(max_length=20, default='pending')
    pdf_downloaded = models.BooleanField(default=False)
    
    # Raw data
    raw_api_data = models.JSONField(default=dict)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['session_number', 'debate_date', 'question_number', 'debate_type']
        ordering = ['-debate_date', 'question_number']
        indexes = [
            models.Index(fields=['session_number', 'debate_date']),
            models.Index(fields=['year']),
            models.Index(fields=['debate_type']),
            models.Index(fields=['resource_id']),
        ]
```

---

## Scraping Strategy

### Approach 1: Year-by-Year (Historical)

```python
def scrape_by_year(year: int):
    """Scrape all debates for a specific year"""
    service = RSOfficialDebateService()
    
    # Get total count for year
    result = service.fetch_debates(start=0, rows=1, year=year)
    total = int(result['rowsCount'])
    
    print(f"Year {year}: {total} records to fetch")
    
    # Paginate through all records
    start = 0
    batch_size = 50
    
    while start < total:
        debates = service.fetch_debates(
            start=start,
            rows=batch_size,
            year=year
        )
        
        # Process and save debates
        for record in debates['records']:
            save_official_debate(record)
        
        start += batch_size
        time.sleep(1)  # Rate limiting
```

### Approach 2: Session-by-Session (Recommended)

```python
def scrape_by_session(session_no: int):
    """Scrape all debates for a specific session"""
    service = RSOfficialDebateService()
    debates = service.fetch_all_debates_for_session(session_no)
    
    print(f"Session {session_no}: {len(debates)} records")
    
    for record in debates:
        save_official_debate(record)
```

### Approach 3: Incremental (Recent Data)

```python
def scrape_recent_debates(days: int = 30):
    """Scrape debates from last N days"""
    service = RSOfficialDebateService()
    
    from datetime import datetime, timedelta
    cutoff_date = datetime.now() - timedelta(days=days)
    
    start = 0
    batch_size = 50
    
    while True:
        result = service.fetch_debates(start=start, rows=batch_size)
        records = result['records']
        
        if not records:
            break
        
        for record in records:
            debate_date = datetime.strptime(record['date'], '%Y-%m-%d')
            
            if debate_date < cutoff_date:
                # Reached cutoff, stop
                return
            
            save_official_debate(record)
        
        start += batch_size
```

---

## Key Differences: Official vs Verbatim Debates

| Aspect | Official Debates | Verbatim Debates |
|--------|------------------|------------------|
| **API Type** | REST with search/filter | Simple endpoints |
| **Total Records** | 738,000 | ~10-20 per session |
| **Granularity** | Individual questions/debates | Hourly time slots |
| **Date Range** | 1952-2024 | 2025 onwards (recent) |
| **PDF Structure** | 1 PDF per question | Multiple PDFs per day |
| **API Domain** | `rsdebate.nic.in` | `rsdoc.nic.in` |
| **Pagination** | Required (large dataset) | Not needed |
| **Filtering** | Rich (year, session, ministry, etc.) | Basic (session, date) |
| **Content Type** | Q&A + General debates | Proceedings transcripts |

---

## Testing Validation Results

✅ **Pagination Works**: Tested `start=50,100` with different `rows` values  
✅ **Year Filter Works**: Tested `year=2024` returns 4,573 records  
✅ **Session Filter**: Tested `sessionNo=268` returns 0 (no data yet - future session)  
✅ **Session Range**: Sessions 166-265 available (100 sessions)  
✅ **Total Records**: 738,000 debates spanning 73 years  
✅ **PDF URLs**: Direct download links in `files[]` array  

---

## Implementation Priority

1. **Phase 1**: Implement browse/metadata endpoints
2. **Phase 2**: Implement fetch with filtering
3. **Phase 3**: Create database model (separate table recommended)
4. **Phase 4**: Implement year-by-year scraper
5. **Phase 5**: Add pagination and batch processing
6. **Phase 6**: PDF download integration

---

## API Rate Limiting Notes

- Response times: 1-37ms (very fast)
- No obvious rate limits observed
- Recommend: 1 second delay between batch requests
- Batch size: 50 records per request (optimal)
- Large datasets: Use background Celery tasks

---

**Ready to implement! Start with Step 1 (Model Changes) and work through sequentially.**
