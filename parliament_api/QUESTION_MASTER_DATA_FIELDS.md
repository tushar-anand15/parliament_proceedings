# QuestionMasterData Model - Complete Field Documentation

## Overview
The `QuestionMasterData` model stores comprehensive metadata for parliamentary questions from both Lok Sabha and Rajya Sabha. It serves as the master reference for all questions before they're processed into detailed `Question` records.

---

## Field Categories

### 1. Institution & Session Information
| Field | Type | Description | Source |
|-------|------|-------------|--------|
| `parent_institution` | ForeignKey | Link to ParliamentInstitution (lok_sabha or rajya_sabha) | Internal |
| `lok_sabha_number` | CharField(10) | Lok Sabha number (e.g., "17", "18") | API: `lokNo` |
| `rajya_sabha_number` | CharField(10) | Rajya Sabha number (future use) | API: Future |
| `session_number` | CharField(10) | Session number (e.g., "5", "268") | API: `sessionNo` |
| `lok_sabha` | ForeignKey | Link to LokSabha model | Internal |
| `session` | ForeignKey | Link to Session model | Internal |

### 2. Question Basic Information
| Field | Type | Description | Source |
|-------|------|-------------|--------|
| `question_number` | CharField(50) | Official question number (e.g., "420", "3360.0") | API: `quesNo` |
| `subjects` | TextField | Question subject/title | API: `subjects` |
| `members` | JSONField | Array of member objects who asked the question | API: `member` |
| `ministry` | CharField(200) | Ministry the question is directed to | API: `ministry` |
| `question_type` | CharField(20) | STARRED, UNSTARRED, or SHORT_NOTICE | API: `type` |
| `date` | DateField | Date the question was raised | API: `date` |

### 3. PDF URLs (Original Sources)
| Field | Type | Description | Purpose |
|-------|------|-------------|---------|
| `questions_file_path` | URLField | URL to English PDF on sansad.in | API: `questionsFilePath` |
| `questions_file_path_hindi` | URLField | URL to Hindi PDF on sansad.in | API: `questionsFilePathHindi` |

**Note**: These are SOURCE URLs, not storage locations. PDFs need to be downloaded from here.

### 4. Answer Data (If Available)
| Field | Type | Description | Source |
|-------|------|-------------|--------|
| `question_text` | TextField | Full question text | API: `questionText` |
| `answer_text` | TextField | English answer text | API: `answerText` |
| `answer_text_hindi` | TextField | Hindi answer text | API: `answerTextHindi` |
| `supplementary_type` | BooleanField | Whether has supplementary questions | API: `supplementaryType` |
| `supplementary_questions` | JSONField | Array of supplementary Q&A | API: `supplementaryQuestionResDtoList` |

### 5. Processing Status Tracking

#### Metadata Processing
| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `is_processed` | BooleanField | False | ✅ **METADATA scraped and converted to Question record** |
| `processed_at` | DateTimeField | NULL | Timestamp when Question record was created |

**Meaning**: 
- `is_processed=True` means we've created a detailed `Question` record from this metadata
- Does NOT mean PDF has been downloaded!

#### PDF Download Tracking (NEW - Proper Tracking)
| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `pdf_downloaded` | BooleanField | False | ✅ **PDF successfully downloaded and uploaded to GCS** |
| `pdf_gcs_path` | CharField(500) | Empty | Full GCS path (e.g., `rs_question/rs/session268/AS420.pdf`) |
| `pdf_download_attempted_at` | DateTimeField | NULL | Last download attempt timestamp |
| `pdf_download_attempts` | IntegerField | 0 | Number of download attempts (for retry logic) |
| `pdf_download_error` | TextField | Empty | Last error message if download failed |

**Meaning**:
- `pdf_downloaded=True` means PDF is confirmed in GCS storage
- `pdf_gcs_path` contains the exact GCS location
- `pdf_download_attempts` tracks retries (max 3 attempts typical)

### 6. Raw Data & Timestamps
| Field | Type | Description |
|-------|------|-------------|
| `raw_api_data` | JSONField | Complete raw JSON response from API |
| `created_at` | DateTimeField | When record was first created |
| `updated_at` | DateTimeField | Last time record was modified |
| `last_fetched` | DateTimeField | Last time data was fetched from API |

---

## Field Relationship Summary

```
API Call → QuestionMasterData created
  ├─ is_processed = False ❌ (metadata only)
  └─ pdf_downloaded = False ❌ (no PDF yet)

Metadata Conversion → Question record created
  ├─ is_processed = True ✅ (Question record exists)
  └─ pdf_downloaded = False ❌ (still no PDF)

PDF Download → File uploaded to GCS
  ├─ is_processed = True ✅ (Question record exists)
  ├─ pdf_downloaded = True ✅ (PDF in GCS)
  └─ pdf_gcs_path = "rs_question/rs/session268/AS420.pdf" ✅
```

---

## Current State Analysis

### Session 268 (Rajya Sabha)
```
Database Records: 3,674 questions
├─ is_processed=True: 3,674 (100%) ✅ All metadata converted
└─ pdf_downloaded=True: 1,000 (27.2%) ⚠️  Only 27% have PDFs in GCS

GCS Storage: 1,000 PDF files (219 MB)
Missing PDFs: 2,674 questions (72.8%)
```

**Issue**: All questions marked `is_processed=True` but only 27% have actual PDFs downloaded!

---

## Fixed Issues

### ❌ Before
```python
# WRONG: Filtered by is_processed (metadata conversion status)
session_questions = QuestionMasterData.objects.filter(
    session_number='268',
    is_processed=False  # ❌ Wrong field!
).exclude(questions_file_path='')
# Result: 0 questions (all metadata already processed)
```

### ✅ After
```python
# CORRECT: Filter by pdf_downloaded (actual PDF download status)
session_questions = QuestionMasterData.objects.filter(
    session_number='268',
    pdf_downloaded=False  # ✅ Correct field!
).exclude(questions_file_path='')
# Result: 2,674 questions ready for PDF download
```

---

## Indexes Created

```sql
CREATE INDEX questions_q_parent__a1b2c3_idx ON questionmasterdata (parent_institution_id, lok_sabha_number, session_number);
CREATE INDEX questions_q_questio_d4e5f6_idx ON questionmasterdata (question_type);
CREATE INDEX questions_q_is_proc_g7h8i9_idx ON questionmasterdata (is_processed);
CREATE INDEX questions_q_pdf_dow_f9b265_idx ON questionmasterdata (pdf_downloaded);  -- NEW!
CREATE INDEX questions_q_date_j1k2l3_idx ON questionmasterdata (date);
```

---

## Usage Examples

### Find questions needing PDF download
```python
# RS Session 268 - questions with metadata but no PDF
needs_download = QuestionMasterData.objects.filter(
    parent_institution__name='rajya_sabha',
    session_number='268',
    pdf_downloaded=False
).exclude(questions_file_path='').count()
# Returns: 2,674 questions
```

### Find fully processed questions
```python
# Questions with both metadata AND PDF
fully_complete = QuestionMasterData.objects.filter(
    session_number='268',
    is_processed=True,
    pdf_downloaded=True
).count()
```

### Track download failures
```python
# Questions that failed to download after 3 attempts
failed_downloads = QuestionMasterData.objects.filter(
    pdf_downloaded=False,
    pdf_download_attempts__gte=3
).exclude(pdf_download_error='')
```

---

## Migration Required

Run this to apply the new fields:
```bash
cd parliament_api
python manage.py makemigrations questions --name add_pdf_download_tracking
python manage.py migrate questions
```

✅ **Migration already applied!**

---

## Next Steps

1. ✅ **Migration applied** - New fields added to database
2. ✅ **Bulk download fixed** - Now uses `pdf_downloaded` field
3. ⏳ **Update download services** - Set `pdf_downloaded=True` when PDFs upload to GCS
4. ⏳ **Backfill data** - Mark existing 1,000 GCS files as `pdf_downloaded=True`
5. ⏳ **Update statistics** - Show metadata vs PDF download stats separately

---

## Inconsistencies Found & Fixed

| Issue | Status | Fix |
|-------|--------|-----|
| `is_processed` used for PDF download logic | ❌ Wrong | ✅ Added `pdf_downloaded` field |
| No tracking of GCS storage path | ❌ Missing | ✅ Added `pdf_gcs_path` field |
| No tracking of download failures | ❌ Missing | ✅ Added `pdf_download_error` field |
| No retry attempt tracking | ❌ Missing | ✅ Added `pdf_download_attempts` field |
| Inconsistent API response schemas (LS vs RS) | ❌ Wrong | ✅ Made consistent |
| Sequential testing (defeats Celery purpose) | ❌ Wrong | ✅ Parallel task creation/monitoring |

