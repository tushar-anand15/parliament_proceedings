# Rajya Sabha (RS) Debates API Documentation

## Overview
This document provides comprehensive documentation for the Rajya Sabha debates API flow, specifically for **Verbatim Debates**. This will serve as a reference for implementing RS debate scraping services.

---

## API Flow Summary

The RS debates scraping follows a 3-step hierarchical flow:

```
1. Fetch All RS Sessions → Session Numbers (189-268)
2. For Each Session → Fetch Session Dates → Sitting Dates
3. For Each Date → Fetch Debate Documents → PDF Files (by time slots)
```

---

## 1. Get All RS Sessions

### Endpoint
```
GET https://sansad.in/api_rs/debate/rs-session
```

### Headers
```http
Accept: application/json, text/plain, */*
Accept-Language: en-US,en;q=0.9
Connection: keep-alive
Referer: https://sansad.in/rs/debates/verbatim
Sec-Fetch-Dest: empty
Sec-Fetch-Mode: cors
Sec-Fetch-Site: same-origin
Sec-GPC: 1
User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36
sec-ch-ua: "Chromium";v="140", "Not=A?Brand";v="24", "Brave";v="140"
sec-ch-ua-mobile: ?0
sec-ch-ua-platform: "macOS"
```

### cURL Example
```bash
curl 'https://sansad.in/api_rs/debate/rs-session' \
  -H 'Accept: application/json, text/plain, */*' \
  -H 'Accept-Language: en-US,en;q=0.9' \
  -H 'Connection: keep-alive' \
  -H 'Referer: https://sansad.in/rs/debates/verbatim' \
  -H 'Sec-Fetch-Dest: empty' \
  -H 'Sec-Fetch-Mode: cors' \
  -H 'Sec-Fetch-Site: same-origin' \
  -H 'Sec-GPC: 1' \
  -H 'User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36' \
  -H 'sec-ch-ua: "Chromium";v="140", "Not=A?Brand";v="24", "Brave";v="140"' \
  -H 'sec-ch-ua-mobile: ?0' \
  -H 'sec-ch-ua-platform: "macOS"'
```

### Response Format
```json
[189, 190, 191, 192, 193, ..., 266, 267, 268]
```

### Response Details
- **Type**: Array of integers
- **Content**: List of Rajya Sabha session numbers
- **Range**: Sessions 189-268 (current as of Oct 2025)
- **Order**: Ascending order

### Key Points
- Simple array of session numbers
- No additional metadata in response
- Session numbers are continuous integers
- Latest session number indicates the most recent session

---

## 2. Get Session Dates

### Endpoint
```
GET https://rsdoc.nic.in/business/SessionDates?Sessionno={session_number}
```

### Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `Sessionno` | integer | Yes | RS Session number (e.g., 268) |

### Headers
```http
accept: application/json, text/plain, */*
accept-language: en-US,en;q=0.9
origin: https://sansad.in
priority: u=1, i
referer: https://sansad.in/
sec-ch-ua: "Chromium";v="140", "Not=A?Brand";v="24", "Brave";v="140"
sec-ch-ua-mobile: ?0
sec-ch-ua-platform: "macOS"
sec-fetch-dest: empty
sec-fetch-mode: cors
sec-fetch-site: cross-site
sec-gpc: 1
user-agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36
```

### cURL Example
```bash
curl 'https://rsdoc.nic.in/business/SessionDates?Sessionno=268' \
  -H 'accept: application/json, text/plain, */*' \
  -H 'accept-language: en-US,en;q=0.9' \
  -H 'origin: https://sansad.in' \
  -H 'priority: u=1, i' \
  -H 'referer: https://sansad.in/' \
  -H 'sec-ch-ua: "Chromium";v="140", "Not=A?Brand";v="24", "Brave";v="140"' \
  -H 'sec-ch-ua-mobile: ?0' \
  -H 'sec-ch-ua-platform: "macOS"' \
  -H 'sec-fetch-dest: empty' \
  -H 'sec-fetch-mode: cors' \
  -H 'sec-fetch-site: cross-site' \
  -H 'sec-gpc: 1' \
  -H 'user-agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36'
```

### Response Format
```json
[
  {
    "Id": 17165,
    "sessionNo": 268,
    "CrteatedBy": "NicLegislativeAdmin",
    "CreatedOn": "2025-07-03T18:51:02.8",
    "SittingDate": "2025-08-21T00:00:00",
    "LastEditedBy": "NicLegislativeAdmin",
    "LastEditedOn": "2025-07-03T18:51:02.8"
  },
  {
    "Id": 17164,
    "sessionNo": 268,
    "CrteatedBy": "NicLegislativeAdmin",
    "CreatedOn": "2025-07-03T18:51:02.8",
    "SittingDate": "2025-08-20T00:00:00",
    "LastEditedBy": "NicLegislativeAdmin",
    "LastEditedOn": "2025-07-03T18:51:02.8"
  }
  // ... more dates
]
```

### Response Fields
| Field | Type | Description |
|-------|------|-------------|
| `Id` | integer | Unique identifier for the sitting date record |
| `sessionNo` | integer | Session number (matches request parameter) |
| `CrteatedBy` | string | User who created the record (typically "NicLegislativeAdmin") |
| `CreatedOn` | datetime | Timestamp when record was created |
| `SittingDate` | datetime | The actual sitting date (ISO 8601 format) |
| `LastEditedBy` | string | User who last edited the record |
| `LastEditedOn` | datetime | Timestamp of last edit |

### Key Points
- **Different Domain**: Uses `rsdoc.nic.in` (not `sansad.in` or `eparlib.sansad.in`)
- **Cross-site Request**: Note the `sec-fetch-site: cross-site` header
- **Date Format**: Dates are in ISO 8601 format (`YYYY-MM-DDTHH:MM:SS`)
- **Order**: Typically returned in descending order (most recent first)
- **Metadata**: Includes creation and editing timestamps

---

## 3. Get Verbatim Debates (PDFs)

### Endpoint
```
GET https://rsdoc.nic.in/business/BusinessVerbatim?ses_no={session_number}&ses_dt={date}
```

### Parameters
| Parameter | Type | Required | Format | Description |
|-----------|------|----------|--------|-------------|
| `ses_no` | integer | Yes | `268` | RS Session number |
| `ses_dt` | string | Yes | `DD/MM/YYYY` | Session sitting date |

### Headers
```http
accept: application/json, text/plain, */*
accept-language: en-US,en;q=0.9
origin: https://sansad.in
priority: u=1, i
referer: https://sansad.in/
sec-ch-ua: "Chromium";v="140", "Not=A?Brand";v="24", "Brave";v="140"
sec-ch-ua-mobile: ?0
sec-ch-ua-platform: "macOS"
sec-fetch-dest: empty
sec-fetch-mode: cors
sec-fetch-site: cross-site
sec-gpc: 1
user-agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36
```

### cURL Example
```bash
curl 'https://rsdoc.nic.in/business/BusinessVerbatim?ses_no=268&ses_dt=21/07/2025' \
  -H 'accept: application/json, text/plain, */*' \
  -H 'accept-language: en-US,en;q=0.9' \
  -H 'origin: https://sansad.in' \
  -H 'priority: u=1, i' \
  -H 'referer: https://sansad.in/' \
  -H 'sec-ch-ua: "Chromium";v="140", "Not=A?Brand";v="24", "Brave";v="140"' \
  -H 'sec-ch-ua-mobile: ?0' \
  -H 'sec-ch-ua-platform: "macOS"' \
  -H 'sec-fetch-dest: empty' \
  -H 'sec-fetch-mode: cors' \
  -H 'sec-fetch-site: cross-site' \
  -H 'sec-gpc: 1' \
  -H 'user-agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36'
```

### Response Format
```json
[
  {
    "Id": 103392,
    "MenuId": 0,
    "Section": "Debates",
    "SubSection": "VerbatimDebates",
    "Type": null,
    "Description": null,
    "Ministry": null,
    "Metadata": null,
    "session": "268",
    "Name": "11-12.pdf",
    "FileType": "pdf",
    "FileLocation": "UploadedFiles/Debates/VerbatimDebates/268/2172025/1100-1200 Noon/",
    "FileUrl": "https://cms.rajyasabha.nic.in/UploadedFiles/Debates/VerbatimDebates/268/2172025/1100-1200 Noon//11-12.pdf",
    "FileVersion": 0,
    "FileSequence": 0,
    "FileStatus": null,
    "Language": "Verbatim",
    "IsArchived": false,
    "IsDownloadable": false,
    "IsPlayable": false,
    "CreatedOn": "2025-07-21T20:53:54.527",
    "CreatedBy": "f89256e4-e5bc-4fc1-a351-0719457ab931",
    "PublishedOn": "2025-07-21T20:54:18.587",
    "PublishedBy": "4433101d-05a0-41cb-b96e-131f525d8a4a",
    "ApprovedOn": "2025-07-21T20:54:18.587",
    "ApprovedBy": "4433101d-05a0-41cb-b96e-131f525d8a4a",
    "isApproved": true,
    "isPublished": true,
    "FileSize": 140212,
    "startDate": null,
    "endDate": null,
    "Tiltle": null,
    "selectedDate": "2025-07-21T00:00:00",
    "PublishDate": null,
    "Time": "11:00-12:00 Noon",
    "Time_H": "11:00-12:00 Noon",
    "ArchivedBy": null,
    "ArchivedOn": null,
    "SNo": null,
    "Subject": null,
    "Source": null,
    "PageNoFrom": null,
    "PageNoTo": null,
    "year": null,
    "EditedBy": null,
    "Version": null,
    "Item_Text": null,
    "HindiFileName": null,
    "HindiFilePath": null,
    "HindiFileType": null,
    "HindiFileSize": null
  }
  // ... more PDFs
]
```

### Response Fields (Core)
| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `Id` | integer | Unique document identifier | `103392` |
| `Section` | string | Document section category | `"Debates"` |
| `SubSection` | string | Document subsection | `"VerbatimDebates"` |
| `session` | string | Session number | `"268"` |
| `Name` | string | PDF filename | `"11-12.pdf"` |
| `FileType` | string | File type | `"pdf"` |
| `FileLocation` | string | Relative path on server | `"UploadedFiles/Debates/VerbatimDebates/268/2172025/1100-1200 Noon/"` |
| `FileUrl` | string | **Full download URL** | `"https://cms.rajyasabha.nic.in/UploadedFiles/..."` |
| `Language` | string | Debate type/language | `"Verbatim"` |
| `FileSize` | integer | File size in bytes | `140212` |
| `selectedDate` | datetime | Sitting date | `"2025-07-21T00:00:00"` |
| `Time` | string | **Time slot identifier** | `"11:00-12:00 Noon"` |
| `Time_H` | string | Time slot (Hindi/localized) | `"11:00-12:00 Noon"` |

### Response Fields (Status & Metadata)
| Field | Type | Description |
|-------|------|-------------|
| `isApproved` | boolean | Whether document is approved |
| `isPublished` | boolean | Whether document is published |
| `CreatedOn` | datetime | Document creation timestamp |
| `CreatedBy` | string | UUID of creator |
| `PublishedOn` | datetime | Publication timestamp |
| `PublishedBy` | string | UUID of publisher |
| `ApprovedOn` | datetime | Approval timestamp |
| `ApprovedBy` | string | UUID of approver |

### Time Slots Structure

RS debates are organized by time slots throughout the day:

| Time Slot | Description | Typical Content |
|-----------|-------------|-----------------|
| `11:00-12:00 Noon` | Morning session | Opening proceedings |
| `12:00-01:00 PM` | Question Hour (QH) | Parliamentary questions |
| `02:00-03:00 PM` | Afternoon session | Debates, discussions |
| `03:00-04:00 PM` | Mid-afternoon | Continued proceedings |
| `04:00-05:00 PM` | Late afternoon | Closing proceedings |
| `Index` | Index document | Session index/table of contents |
| `Full Day` | Complete compilation | All proceedings for the day |

### Key Points - Critical Implementation Details

#### 1. **Multiple PDFs Per Day**
- Unlike LS debates (single PDF per day), RS verbatim debates have **multiple PDFs per sitting date**
- Each PDF corresponds to a specific time slot
- Must handle array of documents for each date

#### 2. **Time Slot Organization**
- Documents are organized by hourly time slots
- Special documents: "Index" and "Full Day"
- Time slots are in `Time` field (English) and `Time_H` field (may contain Hindi)

#### 3. **Date Format Conversion Required**
- Session Dates API returns: `2025-08-21T00:00:00` (ISO 8601)
- Business Verbatim API expects: `21/08/2025` (DD/MM/YYYY)
- **Must convert dates before API call**

#### 4. **File URLs**
- Files are hosted on `cms.rajyasabha.nic.in` domain
- Full URL provided in `FileUrl` field
- Can be downloaded directly (no authentication required based on headers)

#### 5. **File Sizes**
- Typical hourly PDFs: 80-300 KB
- Full Day PDFs: 5-7 MB
- Index PDFs: ~80-90 KB

---

## Comparison: RS vs LS Debates

| Aspect | Rajya Sabha (RS) | Lok Sabha (LS) |
|--------|------------------|----------------|
| **Primary Domain** | `rsdoc.nic.in` | `eparlib.sansad.in` |
| **Session Endpoint** | `sansad.in/api_rs/debate/rs-session` | `sansad.in/api_ls/lok-sabha` |
| **PDFs per Day** | **Multiple** (by time slot) | Single |
| **Time Slots** | Yes (11-12, 12-1, 2-3, etc.) | No |
| **Date Format** | DD/MM/YYYY | DD/MM/YYYY |
| **PDF Host** | `cms.rajyasabha.nic.in` | `eparlib.sansad.in` |
| **Full Day PDF** | Yes (separate file) | N/A (single file only) |
| **Index PDF** | Yes | No |

---

## Implementation Considerations

### 1. Database Schema Extensions

**New Model: `RajyaSabhaSession`** (or reuse Session with institution flag)
```python
class RajyaSabhaSession(models.Model):
    session_number = models.IntegerField(unique=True)
    # ... session metadata
```

**Extend `Debate` Model** for RS:
```python
class Debate(models.Model):
    # Add new field
    time_slot = models.CharField(max_length=50, blank=True, null=True)
    # e.g., "11:00-12:00 Noon", "Full Day", "Index"
    
    # Update unique constraint to include time_slot for RS
    class Meta:
        unique_together = [
            'parent_institution', 
            'session', 
            'debate_date', 
            'debate_category',
            'time_slot'  # NEW: Critical for RS to avoid conflicts
        ]
```

### 2. Service Architecture

Create `RSDebateMasterDataService` similar to existing LS service:

```python
class RSDebateMasterDataService:
    def __init__(self):
        self.base_url = "https://sansad.in/api_rs"
        self.rsdoc_url = "https://rsdoc.nic.in/business"
        
    def fetch_rs_sessions(self) -> List[int]:
        """Fetch all RS session numbers"""
        # GET /debate/rs-session
        
    def fetch_session_dates(self, session_no: int) -> List[Dict]:
        """Fetch sitting dates for a session"""
        # GET /SessionDates?Sessionno={session_no}
        
    def fetch_verbatim_debates(self, session_no: int, date_str: str) -> List[Dict]:
        """Fetch verbatim debate PDFs for a specific date"""
        # GET /BusinessVerbatim?ses_no={session_no}&ses_dt={date}
        # Note: date_str must be in DD/MM/YYYY format
```

### 3. Date Conversion Helper

```python
def convert_date_for_api(iso_date_str: str) -> str:
    """
    Convert ISO date to DD/MM/YYYY format
    Input: "2025-08-21T00:00:00"
    Output: "21/08/2025"
    """
    from datetime import datetime
    dt = datetime.fromisoformat(iso_date_str.replace('Z', '+00:00'))
    return dt.strftime('%d/%m/%Y')
```

### 4. Scraping Strategy

**Option A: Store All Time Slots Separately**
- Each time slot = separate `Debate` record
- Pros: Granular tracking, easy to download specific slots
- Cons: More database records

**Option B: Store Full Day Only**
- Only download "Full Day" PDF
- Pros: Fewer records, complete coverage
- Cons: Less granular, larger files

**Recommendation**: Option A (store all) with flag to prioritize "Full Day" downloads

### 5. Celery Task Structure

```python
@shared_task
def scrape_rs_verbatim_debates(session_number: int, date_str: str):
    """
    Scrape all verbatim debates for a session date
    Handles multiple time slots per day
    """
    # 1. Fetch all PDFs for the date
    # 2. Create Debate record for each time slot
    # 3. Queue download tasks
    # 4. Handle "Full Day" vs individual slots
```

### 6. Error Handling

- **Empty Response**: Some dates may have no debates published yet
- **Missing Time Slots**: Not all time slots may be available
- **API Timeouts**: `rsdoc.nic.in` may be slower than `sansad.in`
- **Date Format Errors**: Critical to validate DD/MM/YYYY conversion

### 7. Rate Limiting

- RS API endpoints appear less rate-limited than LS
- Still recommend: 1-2 second delay between requests
- Batch session processing with ThreadPoolExecutor (max 5 workers)

---

## API Endpoint Quick Reference

```
# 1. Get Sessions
GET https://sansad.in/api_rs/debate/rs-session

# 2. Get Session Dates
GET https://rsdoc.nic.in/business/SessionDates?Sessionno={session_no}

# 3. Get Verbatim Debates
GET https://rsdoc.nic.in/business/BusinessVerbatim?ses_no={session_no}&ses_dt={DD/MM/YYYY}

# 4. Download PDF (from FileUrl field)
GET https://cms.rajyasabha.nic.in/UploadedFiles/Debates/VerbatimDebates/{session}/{date}/{time_slot}/{filename}.pdf
```

---

## Testing Commands

### Test Session List
```bash
curl 'https://sansad.in/api_rs/debate/rs-session' | python3 -m json.tool
```

### Test Session Dates (Session 268)
```bash
curl 'https://rsdoc.nic.in/business/SessionDates?Sessionno=268' \
  -H 'origin: https://sansad.in' \
  | python3 -m json.tool
```

### Test Verbatim Debates (Specific Date)
```bash
curl 'https://rsdoc.nic.in/business/BusinessVerbatim?ses_no=268&ses_dt=21/07/2025' \
  -H 'origin: https://sansad.in' \
  | python3 -m json.tool
```

### Test PDF Download
```bash
curl 'https://cms.rajyasabha.nic.in/UploadedFiles/Debates/VerbatimDebates/268/2172025/Full%20Day//Full%20Day%2021.07.pdf' \
  --output test_debate.pdf
```

---

## Next Steps for Implementation

1. **Create Database Models**
   - [ ] Extend `Debate` model with `time_slot` field
   - [ ] Add RS-specific constraints
   - [ ] Create migration

2. **Build RS Master Data Service**
   - [ ] Implement session fetching
   - [ ] Implement date fetching
   - [ ] Implement debate metadata fetching
   - [ ] Add date conversion utilities

3. **Build RS Scraper Service**
   - [ ] Handle multiple PDFs per date
   - [ ] Implement time slot logic
   - [ ] Download and store PDFs
   - [ ] Handle Full Day vs individual slots

4. **Create API Endpoints**
   - [ ] List RS sessions
   - [ ] List debates by session
   - [ ] Filter by time slot
   - [ ] Download status tracking

5. **Testing & Validation**
   - [ ] Test with recent sessions
   - [ ] Test with historical sessions
   - [ ] Validate date conversions
   - [ ] Test time slot handling

---

## Additional Resources

- **RS Debates Portal**: https://sansad.in/rs/debates/verbatim
- **CMS Domain**: https://cms.rajyasabha.nic.in/
- **API Domain**: https://rsdoc.nic.in/

---

## Notes & Observations

1. **API Stability**: RS APIs appear stable and well-maintained
2. **Cross-Origin**: Note that debate data comes from different domain (`rsdoc.nic.in`)
3. **No Authentication**: All endpoints are public, no authentication required
4. **Data Freshness**: Debates are typically published same day or next day
5. **Historical Data**: Full historical data available from Session 189 onwards
6. **Language**: Currently only English verbatim debates documented (Hindi variants may exist)

---

**Document Version**: 1.0  
**Last Updated**: October 5, 2025  
**Status**: Ready for Implementation - Verbatim Debates Only

**Next Update Will Include**: Other RS debate types (Synopsis, Corrected Debates, etc.)
