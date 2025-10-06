# Parliament API - Frontend Integration Guide

**Version:** 1.0.0  
**Last Updated:** October 6, 2025  
**Base URL (Development):** `http://localhost:8000`

---

## 🔒 Security Overview

**IMPORTANT:** This API requires authentication for ALL data endpoints. Users must:
1. Register for an account
2. Login to receive an authentication token
3. Include the token in all subsequent requests

Only the following endpoints are public (no auth required):
- `POST /api/auth/register/` - User registration
- `POST /api/auth/login/` - User login
- `GET /api/debates/health/` - Health check

---

## 📚 Table of Contents

1. [Authentication](#authentication)
2. [API Structure](#api-structure)
3. [Core Endpoints](#core-endpoints)
4. [Data Explorer](#data-explorer) **⭐ NEW**
5. [Response Formats](#response-formats)
6. [Error Handling](#error-handling)
7. [Code Examples](#code-examples)
8. [Best Practices](#best-practices)
9. [Rate Limiting & Quotas](#rate-limiting--quotas)

---

## 🔐 Authentication

### Registration Flow

**Endpoint:** `POST /api/auth/register/`

**Request Body:**
```json
{
  "username": "researcher123",
  "email": "researcher@example.com",
  "password": "SecurePassword123!",
  "first_name": "John",
  "last_name": "Doe",
  "user_type": "citizen",
  "organization": "Research Institute"
}
```

**Response (201 Created):**
```json
{
  "message": "User registered successfully",
  "token": "9944b09199c62bcf9418ad846dd0e4bbdfc6ee4b",
  "user_id": 42,
  "username": "researcher123"
}
```

### Login Flow

**Endpoint:** `POST /api/auth/login/`

**Request Body:**
```json
{
  "username": "researcher123",
  "password": "SecurePassword123!"
}
```

**Response (200 OK):**
```json
{
  "token": "9944b09199c62bcf9418ad846dd0e4bbdfc6ee4b"
}
```

### Using the Token

Include the token in the `Authorization` header for all authenticated requests:

```
Authorization: Token 9944b09199c62bcf9418ad846dd0e4bbdfc6ee4b
```

### Logout

**Endpoint:** `POST /api/auth/logout/`  
**Headers:** `Authorization: Token <your-token>`

**Response (200 OK):**
```json
{
  "message": "Successfully logged out"
}
```

---

## 🏗️ API Structure

### Base URL Structure

```
/api/
├── /auth/              # Authentication & user management
├── /questions/         # Parliamentary questions
│   ├── /ls/           # Lok Sabha questions
│   └── /rs/           # Rajya Sabha questions
├── /debates/          # Parliamentary debates
├── /explorer/         # ⭐ Data Explorer (NEW) - High-performance filtered data access
│   ├── /ls/           # Lok Sabha data explorer
│   │   ├── /questions/    # LS Questions Explorer
│   │   └── /debates/      # LS Debates Explorer
│   ├── /rs/           # Rajya Sabha data explorer
│   │   ├── /questions/    # RS Questions Explorer
│   │   └── /debates/      # RS Debates Explorer
│   └── /metadata/     # Filter metadata & statistics
├── /scraper/          # Scraping jobs & status
├── /files/            # File downloads & management
├── /ai/               # AI analysis services
└── /docs/             # API documentation (Swagger UI)
```

### Interactive Documentation

- **Swagger UI:** `http://localhost:8000/api/docs/`
- **ReDoc:** `http://localhost:8000/api/redoc/`
- **OpenAPI Schema:** `http://localhost:8000/api/schema/`

---

## 📡 Core Endpoints

### 1. Parliamentary Questions (Lok Sabha)

#### List Questions
```http
GET /api/questions/ls/questions/?lok_sabha=18&session_number=5&limit=50
Authorization: Token <your-token>
```

**Query Parameters:**
- `lok_sabha` - Lok Sabha number (e.g., 15, 16, 17, 18)
- `session_number` - Session number
- `question_type` - Filter by type (STARRED, UNSTARRED)
- `search` - Search in question text
- `limit` - Number of results (default: 50)

**Response:**
```json
{
  "status": "success",
  "data": {
    "questions": [
      {
        "id": 123,
        "question_id": "uuid-here",
        "question_number": "1234",
        "title": "Question title",
        "question_type": "STARRED",
        "lok_sabha": "18",
        "session": "5",
        "members": ["Member Name"],
        "ministries": ["Ministry Name"],
        "date": "2024-10-06",
        "status": "answered",
        "has_answer": true,
        "pdf_files": ["https://url-to-pdf"]
      }
    ],
    "pagination": {
      "total": 5000,
      "limit": 50,
      "returned": 50
    }
  }
}
```

#### Get Question Details
```http
GET /api/questions/ls/questions/{id}/
Authorization: Token <your-token>
```

#### Question Statistics
```http
GET /api/questions/ls/stats/
Authorization: Token <your-token>
```

**Response:**
```json
{
  "statistics": {
    "total_questions": 50000,
    "total_lok_sabhas": 4,
    "total_sessions": 50,
    "total_members": 543,
    "total_ministries": 50
  }
}
```

#### List Available Sessions
```http
GET /api/questions/ls/sessions/
Authorization: Token <your-token>
```

**Response:**
```json
{
  "status": "SUCCESS",
  "total_sessions": 45,
  "sessions": [
    {
      "lok_sabha_number": "18",
      "session_number": "5",
      "total_questions": 2500,
      "starred_questions": 800,
      "unstarred_questions": 1700,
      "session_dates": ["2024-07-01", "2024-08-15"]
    }
  ]
}
```

### 2. Parliamentary Questions (Rajya Sabha)

#### List RS Questions
```http
GET /api/questions/rs/master-data/list/?session_number=268&limit=100
Authorization: Token <your-token>
```

**Query Parameters:**
- `session_number` - RS session number
- `question_type` - STARRED or UNSTARRED
- `ministry` - Filter by ministry
- `has_pdf` - Filter by PDF availability (true/false)
- `limit` - Results per page (default: 100)
- `offset` - Pagination offset

**Response:**
```json
{
  "status": "success",
  "data": {
    "questions": [
      {
        "id": 456,
        "question_number": "567",
        "subjects": "Question subject",
        "question_type": "STARRED",
        "ministry": "Ministry of Health",
        "session_number": "268",
        "date": "2024-10-01",
        "has_pdf": true,
        "pdf_url": "https://url",
        "members": ["RS Member"]
      }
    ],
    "pagination": {
      "total": 1500,
      "limit": 100,
      "offset": 0,
      "has_next": true
    }
  }
}
```

#### RS Statistics
```http
GET /api/questions/rs/statistics/
Authorization: Token <your-token>
```

### 3. Parliamentary Debates

#### List Debates
```http
GET /api/debates/?loksabha=18&session=5&status=completed
Authorization: Token <your-token>
```

**Query Parameters:**
- `loksabha` - Lok Sabha number
- `session` - Session number
- `status` - pending, completed, failed
- `start_date` - Filter from date (YYYY-MM-DD)
- `end_date` - Filter to date (YYYY-MM-DD)

**Response:**
```json
{
  "debates": [
    {
      "id": 789,
      "debate_id": "debate-uuid",
      "lok_sabha": "18",
      "session": "5",
      "debate_date": "2024-10-01",
      "debate_type": "text_of_debate",
      "language": "en",
      "status": "completed",
      "pdf_url": "https://url",
      "is_downloaded": true,
      "file_size_mb": 15.5,
      "page_count": 250
    }
  ],
  "total_count": 500
}
```

#### Get Debate Details
```http
GET /api/debates/{id}/
Authorization: Token <your-token>
```

#### Debate Statistics
```http
GET /api/debates/statistics/?loksabha=18
Authorization: Token <your-token>
```

**Response:**
```json
{
  "total_debates": 500,
  "status_breakdown": {
    "completed": 450,
    "pending": 30,
    "failed": 20
  },
  "loksabha_breakdown": [...],
  "session_breakdown": [...],
  "date_range": {
    "earliest_date": "2019-06-01",
    "latest_date": "2024-10-06"
  },
  "file_statistics": {
    "total_size_mb": 7500.50,
    "average_size_mb": 15.0
  }
}
```

#### Search Debates
```http
GET /api/debates/search/?year=2024&month=10&status=completed
Authorization: Token <your-token>
```

#### Discover Available Sessions
```http
GET /api/debates/discover-sessions/
Authorization: Token <your-token>
```

**Response:**
```json
{
  "total_sessions": 50,
  "sessions": [
    {
      "loksabha_no": "18",
      "session_no": "5",
      "api_source": "modern_api",
      "date_count": 45,
      "dates": ["2024-07-01", "2024-08-15"]
    }
  ],
  "lok_sabha_range": {
    "min": 15,
    "max": 18
  }
}
```

---

## 🚀 Data Explorer

### Overview

The **Data Explorer** is a high-performance API designed specifically for building data dashboards and explorers. It provides blazing-fast filtered access to all parliamentary data with advanced features:

✅ **Production-Grade Performance**: Optimized queries with count caching  
✅ **Advanced Filtering**: Multiple simultaneous filters  
✅ **Multi-field Sorting**: Sort by any relevant field  
✅ **Efficient Pagination**: Handle datasets of 50,000+ records  
✅ **Search Functionality**: Full-text search across multiple fields  
✅ **Rich Metadata**: Dynamic filter options for building UIs  

**Base URL**: `/api/explorer/`

---

### 1. Lok Sabha Questions Explorer

**Endpoint**: `GET /api/explorer/ls/questions/`

#### Advanced Filtering Example
```bash
GET /api/explorer/ls/questions/?lok_sabha=18&session=5&question_type=STARRED&ministry=Health&has_pdf=true&date_from=2024-01-01&date_to=2024-12-31&search=covid&sort_by=date&order=desc&limit=100&offset=0
Authorization: Token <your-token>
```

#### Query Parameters

| Parameter | Type | Description | Example |
|-----------|------|-------------|---------|
| `lok_sabha` | string | Lok Sabha number | `18` |
| `session` | string | Session number | `5` |
| `question_type` | string | STARRED, UNSTARRED, SHORT_NOTICE | `STARRED` |
| `ministry` | string | Ministry filter (partial match) | `Health` |
| `has_pdf` | boolean | Has PDF available | `true` |
| `has_answer` | boolean | Has answer text | `true` |
| `is_processed` | boolean | Is processed | `true` |
| `pdf_downloaded` | boolean | PDF downloaded to storage | `true` |
| `date_from` | date | Start date (YYYY-MM-DD) | `2024-01-01` |
| `date_to` | date | End date (YYYY-MM-DD) | `2024-12-31` |
| `search` | string | Search in subjects, ministry | `covid` |
| `sort_by` | string | Sort field: date, question_number, ministry, question_type, created_at | `date` |
| `order` | string | Sort order: asc, desc | `desc` |
| `limit` | integer | Records per page (max 500) | `100` |
| `offset` | integer | Starting position | `0` |

#### Response
```json
{
  "status": "success",
  "data": {
    "questions": [
      {
        "id": 12345,
        "question_number": "420",
        "subjects": "COVID-19 Vaccination Programme in Rural Areas",
        "question_type": "STARRED",
        "ministry": "Ministry of Health and Family Welfare",
        "date": "2024-07-15",
        "lok_sabha": "18",
        "session": "5",
        "member_names": ["Shri Ramesh Kumar", "Smt. Priya Sharma"],
        "has_pdf": true,
        "has_answer": true,
        "is_processed": true,
        "pdf_downloaded": true,
        "created_at": "2024-07-01T10:30:00Z",
        "updated_at": "2024-07-15T14:20:00Z"
      }
    ],
    "pagination": {
      "total": 5000,
      "limit": 100,
      "offset": 0,
      "returned": 100,
      "has_next": true,
      "has_previous": false,
      "next_offset": 100,
      "previous_offset": null
    }
  },
  "applied_filters": {
    "lok_sabha": "18",
    "session": "5",
    "question_type": "STARRED",
    "ministry": "Health",
    "has_pdf": "true",
    "date_from": "2024-01-01",
    "date_to": "2024-12-31",
    "search": "covid",
    "sort_by": "date",
    "order": "desc"
  }
}
```

---

### 2. Rajya Sabha Questions Explorer

**Endpoint**: `GET /api/explorer/rs/questions/`

Same as LS Questions Explorer but without `lok_sabha` parameter.

**Example**:
```bash
GET /api/explorer/rs/questions/?session=268&question_type=UNSTARRED&has_answer=true&limit=100
Authorization: Token <your-token>
```

---

### 3. Lok Sabha Debates Explorer

**Endpoint**: `GET /api/explorer/ls/debates/`

**Important**: Individual debate records must be created first by running:
```bash
python manage.py populate_debates_from_master
```
This command creates individual debate day records (~1,712 for LS, ~2,429 for RS) from session-level metadata, making them queryable in the explorer. PDF downloads will update these records with file information.

#### Query Parameters

| Parameter | Type | Description | Example |
|-----------|------|-------------|---------|
| `lok_sabha` | string | Lok Sabha number | `18` |
| `session` | string | Session number | `5` |
| `debate_category` | string | corrected, uncorrected | `corrected` |
| `status` | string | pending, completed, failed, not_available | `pending` |
| `date_from` | date | Start date (YYYY-MM-DD) | `2024-01-01` |
| `date_to` | date | End date (YYYY-MM-DD) | `2024-12-31` |
| `sort_by` | string | debate_date, created_at, updated_at, status | `debate_date` |
| `order` | string | asc, desc | `desc` |
| `limit` | integer | Records per page (max 500) | `100` |
| `offset` | integer | Starting position | `0` |

**Example**:
```bash
GET /api/explorer/ls/debates/?lok_sabha=18&session=5&status=pending&sort_by=debate_date&order=desc&limit=100
Authorization: Token <your-token>
```

**Response**:
```json
{
  "status": "success",
  "data": {
    "debates": [
      {
        "id": 1523,
        "debate_id": "18_5_20240721_corrected",
        "debate_date": "2024-07-21",
        "debate_type": "text_of_debate",
        "debate_category": "corrected",
        "language": "en",
        "time_slot": null,
        "lok_sabha": "18",
        "session": "5",
        "status": "pending",
        "is_downloaded": false,
        "file_size_mb": null,
        "page_count": null,
        "download_attempts": 0,
        "created_at": "2024-10-06T10:00:00Z",
        "updated_at": "2024-10-06T10:00:00Z"
      }
    ],
    "pagination": {
      "total": 1712,
      "limit": 100,
      "offset": 0,
      "returned": 100,
      "has_next": true,
      "has_previous": false,
      "next_offset": 100,
      "previous_offset": null
    }
  },
  "applied_filters": {
    "lok_sabha": "18",
    "session": "5",
    "status": "pending",
    "sort_by": "debate_date",
    "order": "desc"
  }
}
```

**Status Values**:
- `pending`: Debate day identified, PDF download not started
- `downloading`: PDF download in progress
- `completed`: PDF downloaded successfully
- `failed`: PDF download failed
- `not_available`: No PDF available for this date

---

### 4. Rajya Sabha Debates Explorer

**Endpoint**: `GET /api/explorer/rs/debates/`

**Important**: Individual debate records must be created first by running:
```bash
python manage.py populate_debates_from_master
```

#### Query Parameters

| Parameter | Type | Description | Example |
|-----------|------|-------------|---------|
| `session` | string | Session number | `268` |
| `debate_category` | string | corrected, verbatim, official_qa, official_other, official | `corrected` |
| `status` | string | pending, completed, failed, not_available | `pending` |
| `date_from` | date | Start date (YYYY-MM-DD) | `2024-01-01` |
| `date_to` | date | End date (YYYY-MM-DD) | `2024-12-31` |
| `sort_by` | string | debate_date, created_at, updated_at, status | `debate_date` |
| `order` | string | asc, desc | `desc` |
| `limit` | integer | Records per page (max 500) | `100` |
| `offset` | integer | Starting position | `0` |

**Example**:
```bash
GET /api/explorer/rs/debates/?session=268&status=pending&sort_by=debate_date&order=desc&limit=100
Authorization: Token <your-token>
```

**Response**:
```json
{
  "status": "success",
  "data": {
    "debates": [
      {
        "id": 2850,
        "debate_id": "rs_268_20250821_corrected",
        "debate_date": "2025-08-21",
        "debate_type": "text_of_debate",
        "debate_category": "corrected",
        "language": "en",
        "time_slot": null,
        "session": "268",
        "status": "pending",
        "is_downloaded": false,
        "file_size_mb": null,
        "page_count": null,
        "download_attempts": 0,
        "created_at": "2024-10-06T10:00:00Z",
        "updated_at": "2024-10-06T10:00:00Z"
      }
    ],
    "pagination": {
      "total": 2429,
      "limit": 100,
      "offset": 0,
      "returned": 100,
      "has_next": true,
      "has_previous": false,
      "next_offset": 100,
      "previous_offset": null
    }
  },
  "applied_filters": {
    "session": "268",
    "status": "pending",
    "sort_by": "debate_date",
    "order": "desc"
  }
}
```

---

### 5. Get Filter Metadata

#### Questions Metadata

**Endpoint**: `GET /api/explorer/metadata/questions/?institution=lok_sabha`

Returns all available filter options and statistics for building filter UIs.

**Response**:
```json
{
  "status": "success",
  "institution": "lok_sabha",
  "metadata": {
    "lok_sabhas": ["18", "17", "16", "15"],
    "sessions": ["9", "8", "7", "6", "5"],
    "ministries": [
      "Ministry of Health and Family Welfare",
      "Ministry of Home Affairs",
      "Ministry of Finance"
    ],
    "question_types": ["STARRED", "UNSTARRED", "SHORT_NOTICE"],
    "date_range": {
      "min": "2019-06-01",
      "max": "2024-12-31"
    }
  },
  "statistics": {
    "total_questions": 50000,
    "with_pdf": 45000,
    "with_answer": 42000,
    "processed": 38000,
    "pdf_downloaded": 35000
  }
}
```

#### Debates Metadata

**Endpoint**: `GET /api/explorer/metadata/debates/?institution=lok_sabha`

**Response** (after running `populate_debates_from_master`):
```json
{
  "status": "success",
  "institution": "lok_sabha",
  "metadata": {
    "lok_sabhas": ["18", "17", "16", "15", "14", "13"],
    "sessions": ["9", "8", "7", "6", "5", "4", "3", "2", "1"],
    "debate_categories": ["corrected", "uncorrected"],
    "statuses": ["pending", "downloading", "completed", "failed", "not_available"],
    "date_range": {
      "min": "1999-10-20",
      "max": "2025-08-21"
    }
  },
  "statistics": {
    "total_debates": 1712,
    "completed": 0,
    "pending": 1712,
    "failed": 0,
    "not_available": 0
  }
}
```

**For Rajya Sabha**:
```bash
GET /api/explorer/metadata/debates/?institution=rajya_sabha
```

**Response**:
```json
{
  "status": "success",
  "institution": "rajya_sabha",
  "metadata": {
    "sessions": ["268", "267", "266", "265", "264", "..."],
    "debate_categories": ["corrected"],
    "statuses": ["pending", "downloading", "completed", "failed", "not_available"],
    "date_range": {
      "min": "1950-05-13",
      "max": "2025-08-21"
    }
  },
  "statistics": {
    "total_debates": 2429,
    "completed": 0,
    "pending": 2429,
    "failed": 0,
    "not_available": 0
  }
}
```

---

### 6. Get Individual Record Details

#### Question Detail
```bash
GET /api/explorer/ls/questions/{id}/
GET /api/explorer/rs/questions/{id}/
Authorization: Token <your-token>
```

Returns full details including question text, answer text, supplementary questions, PDF URLs, etc.

#### Debate Detail
```bash
GET /api/explorer/ls/debates/{id}/
GET /api/explorer/rs/debates/{id}/
Authorization: Token <your-token>
```

Returns full debate details including debate date, status, download information, PDF URL, file size, page count, and error messages (if any).

---

### Data Explorer Performance Features

#### 1. Count Caching
- Total record counts cached for 5 minutes
- Eliminates expensive COUNT queries on large datasets
- Dramatically improves pagination performance

#### 2. Metadata Caching
- Filter metadata cached for 1 hour
- Reduces database load for dropdown population
- Updates automatically when cache expires

#### 3. Query Optimization
- Uses `select_related()` for foreign keys
- Proper database indexing on filtered fields
- Efficient queryset slicing for pagination

#### 4. Scalability
- Supports up to 500 records per page
- Handles datasets with 50,000+ records efficiently
- Response times: 50-150ms for most queries

---

### 4. File Downloads

#### Get File Download URL
```http
GET /api/files/download/{file_id}/
Authorization: Token <your-token>
```

**Response:**
```json
{
  "download_url": "https://storage.googleapis.com/presigned-url",
  "expires_at": "2024-10-06T13:00:00Z",
  "file_name": "question_1234.pdf",
  "file_size": 524288,
  "storage_type": "gcs"
}
```

#### List Files
```http
GET /api/files/documents/
Authorization: Token <your-token>
```

#### File Statistics
```http
GET /api/files/stats/
Authorization: Token <your-token>
```

### 5. Scraping Status & Jobs

#### Check Scraping Status
```http
GET /api/scraper/status/
Authorization: Token <your-token>
```

**Response:**
```json
{
  "active_jobs": [
    {
      "id": 42,
      "name": "Scrape LS18 Session 5",
      "job_type": "questions",
      "status": "running",
      "progress_percent": 65,
      "questions_processed": 3250,
      "questions_created": 3000,
      "started_at": "2024-10-06T10:00:00Z"
    }
  ],
  "latest_job": {...},
  "system_status": "operational"
}
```

#### Database Statistics
```http
GET /api/scraper/database-stats/
Authorization: Token <your-token>
```

**Response:**
```json
{
  "total_statistics": {
    "total_questions": 50000,
    "answered_questions": 45000,
    "recent_questions_scraped": 500
  },
  "loksabha_breakdown": [...],
  "session_breakdown": [...],
  "data_richness": {
    "pdf_coverage_percentage": 95.5
  }
}
```

### 6. User Profile

#### Get Profile
```http
GET /api/auth/profile/
Authorization: Token <your-token>
```

**Response:**
```json
{
  "user": {
    "id": 42,
    "username": "researcher123",
    "email": "researcher@example.com",
    "first_name": "John",
    "last_name": "Doe"
  },
  "profile": {
    "user_type": "citizen",
    "organization": "Research Institute",
    "subscription_tier": "free",
    "api_calls_today": 150,
    "daily_api_limit": 1000,
    "downloads_this_month": 50,
    "monthly_download_limit": 500
  }
}
```

---

## 📋 Response Formats

### Success Response Pattern
```json
{
  "status": "success",
  "data": {
    // Response data here
  },
  "message": "Operation completed successfully"
}
```

### Pagination Pattern
```json
{
  "data": [...],
  "pagination": {
    "total": 5000,
    "limit": 50,
    "offset": 0,
    "returned": 50,
    "has_next": true,
    "has_previous": false
  }
}
```

---

## ⚠️ Error Handling

### HTTP Status Codes

| Code | Meaning | Description |
|------|---------|-------------|
| 200 | OK | Request successful |
| 201 | Created | Resource created |
| 400 | Bad Request | Invalid parameters |
| 401 | Unauthorized | Missing or invalid token |
| 403 | Forbidden | Insufficient permissions |
| 404 | Not Found | Resource not found |
| 429 | Too Many Requests | Rate limit exceeded |
| 500 | Internal Server Error | Server error |

### Error Response Format
```json
{
  "error": "Error message here",
  "detail": "Detailed error information",
  "status": "error"
}
```

### Common Error Scenarios

#### 1. Missing Authentication Token
```json
{
  "detail": "Authentication credentials were not provided."
}
```

#### 2. Invalid Token
```json
{
  "detail": "Invalid token."
}
```

#### 3. Rate Limit Exceeded
```json
{
  "error": "Rate limit exceeded",
  "detail": "You have exceeded your daily API limit of 1000 requests."
}
```

---

## 💻 Code Examples

### React/TypeScript Example

```typescript
import axios, { AxiosInstance } from 'axios';

class ParliamentAPI {
  private api: AxiosInstance;
  private token: string | null = null;

  constructor(baseURL: string = 'http://localhost:8000') {
    this.api = axios.create({
      baseURL: baseURL + '/api',
      headers: {
        'Content-Type': 'application/json',
      },
    });

    // Add token to requests if available
    this.api.interceptors.request.use((config) => {
      if (this.token) {
        config.headers.Authorization = `Token ${this.token}`;
      }
      return config;
    });

    // Handle auth errors
    this.api.interceptors.response.use(
      (response) => response,
      (error) => {
        if (error.response?.status === 401) {
          this.handleAuthError();
        }
        return Promise.reject(error);
      }
    );

    // Load token from localStorage
    this.loadToken();
  }

  private loadToken() {
    this.token = localStorage.getItem('parliament_api_token');
  }

  private saveToken(token: string) {
    this.token = token;
    localStorage.setItem('parliament_api_token', token);
  }

  private clearToken() {
    this.token = null;
    localStorage.removeItem('parliament_api_token');
  }

  private handleAuthError() {
    this.clearToken();
    // Redirect to login page
    window.location.href = '/login';
  }

  // Authentication Methods
  async register(userData: {
    username: string;
    email: string;
    password: string;
    first_name?: string;
    last_name?: string;
  }) {
    const response = await this.api.post('/auth/register/', userData);
    this.saveToken(response.data.token);
    return response.data;
  }

  async login(username: string, password: string) {
    const response = await this.api.post('/auth/login/', {
      username,
      password,
    });
    this.saveToken(response.data.token);
    return response.data;
  }

  async logout() {
    try {
      await this.api.post('/auth/logout/');
    } finally {
      this.clearToken();
    }
  }

  async getProfile() {
    const response = await this.api.get('/auth/profile/');
    return response.data;
  }

  // Questions Methods
  async getQuestions(params: {
    lok_sabha?: string;
    session_number?: string;
    question_type?: 'STARRED' | 'UNSTARRED';
    limit?: number;
    search?: string;
  }) {
    const response = await this.api.get('/questions/ls/questions/', { params });
    return response.data;
  }

  async getQuestion(id: number) {
    const response = await this.api.get(`/questions/ls/questions/${id}/`);
    return response.data;
  }

  async getQuestionStats() {
    const response = await this.api.get('/questions/ls/stats/');
    return response.data;
  }

  async getAvailableSessions() {
    const response = await this.api.get('/questions/ls/sessions/');
    return response.data;
  }

  // Debates Methods
  async getDebates(params: {
    loksabha?: string;
    session?: string;
    status?: 'pending' | 'completed' | 'failed';
    start_date?: string;
    end_date?: string;
  }) {
    const response = await this.api.get('/debates/', { params });
    return response.data;
  }

  async getDebate(id: number) {
    const response = await this.api.get(`/debates/${id}/`);
    return response.data;
  }

  async getDebateStatistics(params?: { loksabha?: string }) {
    const response = await this.api.get('/debates/statistics/', { params });
    return response.data;
  }

  async searchDebates(params: {
    year?: number;
    month?: number;
    status?: string;
  }) {
    const response = await this.api.get('/debates/search/', { params });
    return response.data;
  }

  // File Methods
  async getFileDownloadURL(fileId: number) {
    const response = await this.api.get(`/files/download/${fileId}/`);
    return response.data;
  }

  // Scraper Methods
  async getScrapingStatus() {
    const response = await this.api.get('/scraper/status/');
    return response.data;
  }

  async getDatabaseStats() {
    const response = await this.api.get('/scraper/database-stats/');
    return response.data;
  }

  // Check if user is authenticated
  isAuthenticated(): boolean {
    return this.token !== null;
  }
}

// Export singleton instance
export const parliamentAPI = new ParliamentAPI();

// React Hook Example
export function useParliamentAPI() {
  return parliamentAPI;
}
```

### Usage in React Component

```typescript
import React, { useEffect, useState } from 'react';
import { useParliamentAPI } from './api/parliament';

interface Question {
  id: number;
  question_number: string;
  title: string;
  question_type: string;
  date: string;
}

export function QuestionsListPage() {
  const api = useParliamentAPI();
  const [questions, setQuestions] = useState<Question[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadQuestions();
  }, []);

  async function loadQuestions() {
    try {
      setLoading(true);
      const data = await api.getQuestions({
        lok_sabha: '18',
        session_number: '5',
        limit: 50,
      });
      setQuestions(data.data.questions);
    } catch (err: any) {
      setError(err.response?.data?.error || 'Failed to load questions');
    } finally {
      setLoading(false);
    }
  }

  if (loading) return <div>Loading...</div>;
  if (error) return <div>Error: {error}</div>;

  return (
    <div>
      <h1>Parliamentary Questions</h1>
      <ul>
        {questions.map((q) => (
          <li key={q.id}>
            {q.question_number}: {q.title}
          </li>
        ))}
      </ul>
    </div>
  );
}
```

### Vue.js Example

```typescript
// api/parliament.ts
import axios from 'axios';

const api = axios.create({
  baseURL: 'http://localhost:8000/api',
  headers: {
    'Content-Type': 'application/json',
  },
});

// Request interceptor
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('parliament_token');
  if (token) {
    config.headers.Authorization = `Token ${token}`;
  }
  return config;
});

// Response interceptor
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('parliament_token');
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

export default api;

// composables/useAuth.ts
import { ref, computed } from 'vue';
import api from '@/api/parliament';

const token = ref(localStorage.getItem('parliament_token'));
const user = ref(null);

export function useAuth() {
  const isAuthenticated = computed(() => !!token.value);

  async function login(username: string, password: string) {
    const response = await api.post('/auth/login/', { username, password });
    token.value = response.data.token;
    localStorage.setItem('parliament_token', response.data.token);
    await fetchProfile();
  }

  async function logout() {
    await api.post('/auth/logout/');
    token.value = null;
    user.value = null;
    localStorage.removeItem('parliament_token');
  }

  async function fetchProfile() {
    const response = await api.get('/auth/profile/');
    user.value = response.data;
  }

  return {
    isAuthenticated,
    user,
    login,
    logout,
    fetchProfile,
  };
}
```

### Python Example

```python
import requests
from typing import Optional, Dict, Any

class ParliamentAPIClient:
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = f"{base_url}/api"
        self.token: Optional[str] = None
        self.session = requests.Session()
        self.session.headers.update({
            'Content-Type': 'application/json'
        })
    
    def _update_auth_header(self):
        if self.token:
            self.session.headers.update({
                'Authorization': f'Token {self.token}'
            })
    
    def register(self, username: str, email: str, password: str, **kwargs) -> Dict[str, Any]:
        """Register a new user"""
        data = {
            'username': username,
            'email': email,
            'password': password,
            **kwargs
        }
        response = self.session.post(f"{self.base_url}/auth/register/", json=data)
        response.raise_for_status()
        result = response.json()
        self.token = result['token']
        self._update_auth_header()
        return result
    
    def login(self, username: str, password: str) -> str:
        """Login and get authentication token"""
        response = self.session.post(
            f"{self.base_url}/auth/login/",
            json={'username': username, 'password': password}
        )
        response.raise_for_status()
        self.token = response.json()['token']
        self._update_auth_header()
        return self.token
    
    def logout(self):
        """Logout and clear token"""
        if self.token:
            self.session.post(f"{self.base_url}/auth/logout/")
            self.token = None
            self.session.headers.pop('Authorization', None)
    
    def get_questions(self, **params) -> Dict[str, Any]:
        """Get list of parliamentary questions"""
        response = self.session.get(
            f"{self.base_url}/questions/ls/questions/",
            params=params
        )
        response.raise_for_status()
        return response.json()
    
    def get_debates(self, **params) -> Dict[str, Any]:
        """Get list of debates"""
        response = self.session.get(
            f"{self.base_url}/debates/",
            params=params
        )
        response.raise_for_status()
        return response.json()
    
    def get_scraping_status(self) -> Dict[str, Any]:
        """Get current scraping status"""
        response = self.session.get(f"{self.base_url}/scraper/status/")
        response.raise_for_status()
        return response.json()

# Usage Example
if __name__ == "__main__":
    client = ParliamentAPIClient()
    
    # Login
    client.login("researcher123", "SecurePassword123!")
    
    # Get questions
    questions = client.get_questions(lok_sabha="18", session_number="5", limit=10)
    print(f"Found {len(questions['data']['questions'])} questions")
    
    # Get debates
    debates = client.get_debates(loksabha="18", session="5")
    print(f"Found {len(debates['debates'])} debates")
    
    # Logout
    client.logout()
```

---

## 🎯 Best Practices

### 1. Token Management

```typescript
// ✅ Good: Store token securely
localStorage.setItem('token', token);

// ❌ Bad: Don't expose token in URLs
const url = `/api/data?token=${token}`; // NEVER DO THIS

// ✅ Good: Always use headers
headers: { 'Authorization': `Token ${token}` }
```

### 2. Error Handling

```typescript
// ✅ Good: Handle all error scenarios
try {
  const data = await api.getQuestions();
} catch (error) {
  if (error.response?.status === 401) {
    // Handle authentication error
    redirectToLogin();
  } else if (error.response?.status === 429) {
    // Handle rate limit
    showRateLimitError();
  } else {
    // Handle other errors
    showGenericError(error.message);
  }
}
```

### 3. Pagination

```typescript
// ✅ Good: Implement pagination for large datasets
async function loadAllQuestions() {
  let offset = 0;
  const limit = 100;
  const allQuestions = [];
  
  while (true) {
    const response = await api.get('/questions/ls/questions/', {
      params: { limit, offset }
    });
    
    allQuestions.push(...response.data.questions);
    
    if (!response.pagination.has_next) break;
    offset += limit;
  }
  
  return allQuestions;
}
```

### 4. Caching

```typescript
// ✅ Good: Cache frequently accessed data
const cache = new Map();

async function getQuestionWithCache(id: number) {
  if (cache.has(id)) {
    return cache.get(id);
  }
  
  const question = await api.getQuestion(id);
  cache.set(id, question);
  return question;
}
```

### 5. Request Debouncing

```typescript
// ✅ Good: Debounce search requests
import { debounce } from 'lodash';

const debouncedSearch = debounce(async (query: string) => {
  const results = await api.getQuestions({ search: query });
  setSearchResults(results);
}, 300);
```

---

## 📊 Rate Limiting & Quotas

### Default Limits (Per User)

| Resource | Limit | Period |
|----------|-------|--------|
| API Requests | 1,000 | Daily |
| PDF Downloads | 500 | Monthly |
| Concurrent Requests | 10 | Simultaneous |

### Checking Your Limits

```typescript
const profile = await api.getProfile();
console.log(`Used: ${profile.profile.api_calls_today}/${profile.profile.daily_api_limit}`);
console.log(`Downloads: ${profile.profile.downloads_this_month}/${profile.profile.monthly_download_limit}`);
```

### Handling Rate Limits

```typescript
// Implement exponential backoff
async function retryWithBackoff(fn: Function, maxRetries = 3) {
  for (let i = 0; i < maxRetries; i++) {
    try {
      return await fn();
    } catch (error) {
      if (error.response?.status === 429 && i < maxRetries - 1) {
        const delay = Math.pow(2, i) * 1000;
        await new Promise(resolve => setTimeout(resolve, delay));
      } else {
        throw error;
      }
    }
  }
}
```

---

## 🔍 Advanced Features

### Filtering Examples

```typescript
// Complex filtering
const results = await api.getQuestions({
  lok_sabha: '18',
  session_number: '5',
  question_type: 'STARRED',
  search: 'healthcare',
  limit: 50
});

// Date range filtering for debates
const debates = await api.getDebates({
  loksabha: '18',
  start_date: '2024-01-01',
  end_date: '2024-12-31',
  status: 'completed'
});
```

### Bulk Operations

```typescript
// Download multiple questions
async function bulkDownloadQuestions(questionIds: number[]) {
  const downloads = await Promise.all(
    questionIds.map(id => api.getQuestion(id))
  );
  return downloads;
}
```

---

## 🛠️ Troubleshooting

### Common Issues

#### 1. CORS Errors
```
Error: Access to XMLHttpRequest has been blocked by CORS policy
```
**Solution:** Make sure your frontend URL is in the allowed CORS origins. Contact admin to add your domain.

#### 2. Token Expiration
**Solution:** Implement token refresh logic or handle 401 errors by redirecting to login.

#### 3. Rate Limit Exceeded
```json
{"error": "Rate limit exceeded"}
```
**Solution:** Implement request throttling and caching.

---

## 📞 Support & Resources

- **API Documentation:** http://localhost:8000/api/docs/
- **GitHub Issues:** [Your repository URL]
- **Email Support:** support@parliamentapi.com

---

## 📝 Changelog

### Version 1.0.0 (2025-10-06)
- Initial release
- Authentication system with Token-based auth
- Complete Lok Sabha & Rajya Sabha questions API
- Debates API with full search capabilities
- File download management with GCS integration
- Comprehensive scraping and statistics endpoints

---

## 📜 License

This API is licensed under [Your License]. See LICENSE file for details.

---

**Happy Coding! 🎉**
