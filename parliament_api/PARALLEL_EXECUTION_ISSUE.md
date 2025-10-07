# 🐛 PARALLEL EXECUTION ISSUE

## The Problem

When calling `/api/questions/ls/master-data/bulk-download/` with `limit: 50`:

### What You THINK Is Happening:
```
API Call → Creates 50 Individual Celery Tasks → 8 Workers Process in Parallel
          ✓ Task 1 (Worker 1)
          ✓ Task 2 (Worker 2)  
          ✓ Task 3 (Worker 3)
          ... (all 8 workers busy)
```

### What's ACTUALLY Happening:
```
API Call → Creates 1 Celery Task → Downloads 50 PDFs SEQUENTIALLY
          ✓ PDF 1 → PDF 2 → PDF 3 → ... → PDF 50 (one by one!)
          (Only 1 worker used, others sit idle)
```

## Root Cause

**File:** `services/questions/tasks.py`
**Line:** 381-495

The `bulk_download_question_pdfs_from_master_data_task` function does this:

```python
for i, master_data in enumerate(master_data_list, 1):
    # Download immediately to GCS (SEQUENTIALLY!)
    success = service.download_question_pdf(question, pdf_url)
```

This creates **ONE task** that processes all PDFs in a loop!

## The Solution Exists But Isn't Used!

**File:** `services/questions/tasks.py`
**Lines:** 95-194

There's a PROPER parallel implementation in `bulk_download_question_pdfs_task`:

```python
# Creates individual task signatures
for question_id in question_ids:
    download_tasks.append(
        download_question_pdf_task.si(question_id, pdf_url)
    )

# Dispatches ALL in parallel
job = group(download_tasks)
group_result = job.apply_async()
```

This dispatches each PDF as a separate task that workers can process in parallel!

## Why This Matters

**Current Performance:**
- 50 PDFs × 0.83s each = 41.5 seconds (sequential)
- Only 1 of 8 workers used = 12.5% efficiency

**With Parallel Execution:**
- 50 PDFs ÷ 8 workers = 6.25 PDFs per worker
- 6.25 × 0.83s = 5.2 seconds total!
- **8x faster!**

## Fix Required

The `bulk_download_question_pdfs_from_master_data_task` needs to be rewritten to:
1. Use `files.download_pdf_unified` task (the new unified one)
2. Create individual task signatures for each PDF
3. Dispatch using `celery.group()` for parallel execution


