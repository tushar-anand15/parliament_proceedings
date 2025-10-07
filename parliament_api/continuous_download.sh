#!/bin/bash
#
# Intelligent Continuous Parliament PDF Download Script
# Automatically calculates pending downloads and adjusts batch sizes
#
# Usage:
#   ./continuous_download.sh
#   
# Or in tmux:
#   tmux new -s download
#   ./continuous_download.sh
#

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SUB_BATCH_SIZE=500        # Items per sub-batch (prevents queue overflow)
SUB_DELAY=5              # Seconds between sub-batches
MAJOR_DELAY=120          # Seconds between major batches
CYCLE_DELAY=300          # Seconds between full cycles (5 minutes)
MIN_PENDING_THRESHOLD=100  # Don't schedule if less than this pending
IDLE_CHECK_INTERVAL=600    # Check every 10 minutes when idle
DOWNLOAD_TYPE="all"      # all, ls, rs, or debates

# Logging
LOG_FILE="/var/log/parliament_api/continuous_download.log"
mkdir -p "$(dirname "$LOG_FILE")" 2>/dev/null || LOG_FILE="$SCRIPT_DIR/download.log"

log_message() {
    echo -e "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

# Trap Ctrl+C to exit gracefully
trap 'log_message "${RED}Script interrupted by user${NC}"; exit 0' INT TERM

# Get current statistics from the API
get_statistics() {
    python3 - <<'EOF'
import requests
import json
import sys
import time

BASE_URL = "https://api.opensansad.co.in"
TOKEN = "***REMOVED_SECRET***"
HEADERS = {
    "Authorization": f"Token {TOKEN}",
    "Content-Type": "application/json"
}

def fetch_with_retry(url, headers, max_retries=3, timeout=30):
    """Fetch URL with retry logic"""
    for attempt in range(max_retries):
        try:
            response = requests.get(url, headers=headers, timeout=timeout)
            response.raise_for_status()
            return response
        except (requests.RequestException, requests.Timeout) as e:
            if attempt < max_retries - 1:
                print(f"Attempt {attempt + 1} failed, retrying in 5s...", file=sys.stderr)
                time.sleep(5)
            else:
                raise e
    return None

def format_number(num):
    """Format number with thousands separator"""
    return f"{num:,}"

try:
    # Get debate statistics with retry
    debate_response = fetch_with_retry(
        f"{BASE_URL}/api/debates/statistics/",
        headers=HEADERS,
        timeout=30
    )
    debate_stats = debate_response.json()
    
    # Use the ACCURATE LS statistics endpoint
    ls_response = fetch_with_retry(
        f"{BASE_URL}/api/questions/ls/download-statistics/?use_celery=false",
        headers=HEADERS,
        timeout=30
    )
    ls_stats = ls_response.json()
    
    # Get RS question statistics with retry
    rs_response = fetch_with_retry(
        f"{BASE_URL}/api/questions/rs/statistics/",
        headers=HEADERS,
        timeout=30
    )
    rs_stats = rs_response.json()
    
    # Extract ACCURATE data - Use master_data_statistics for total count
    ls_total = ls_stats.get('master_data_statistics', {}).get('pdf_availability', {}).get('with_pdf', 0)
    ls_downloaded = ls_stats.get('download_statistics', {}).get('master_data', {}).get('pdfs_downloaded', 0)
    ls_pending = ls_total - ls_downloaded
    
    rs_data = rs_stats.get('data', {})
    rs_pdf_status = rs_data.get('pdf_download_status', {})
    rs_total = rs_pdf_status.get('questions_with_pdf_url', 0)
    rs_downloaded = rs_pdf_status.get('pdfs_downloaded', 0)
    rs_pending = rs_total - rs_downloaded
    
    debates_total = debate_stats.get('total_debates', 0)
    status_breakdown = debate_stats.get('status_breakdown', {})
    debates_downloaded = status_breakdown.get('completed', 0)
    debates_pending = status_breakdown.get('pending', 0)
    
    # Output in a format that bash can parse
    print(f"LS_TOTAL={ls_total}")
    print(f"LS_DOWNLOADED={ls_downloaded}")
    print(f"LS_PENDING={ls_pending}")
    print(f"RS_TOTAL={rs_total}")
    print(f"RS_DOWNLOADED={rs_downloaded}")
    print(f"RS_PENDING={rs_pending}")
    print(f"DEBATES_TOTAL={debates_total}")
    print(f"DEBATES_DOWNLOADED={debates_downloaded}")
    print(f"DEBATES_PENDING={debates_pending}")
    
    total_pending = ls_pending + rs_pending + debates_pending
    total_items = ls_total + rs_total + debates_total
    total_downloaded = ls_downloaded + rs_downloaded + debates_downloaded
    
    print(f"TOTAL_PENDING={total_pending}")
    print(f"TOTAL_ITEMS={total_items}")
    print(f"TOTAL_DOWNLOADED={total_downloaded}")
    
except Exception as e:
    print(f"ERROR: {e}", file=sys.stderr)
    sys.exit(1)
EOF
}

# Calculate optimal batch parameters based on pending items
calculate_batch_params() {
    local pending=$1
    local batch_size
    local num_batches
    
    if [ $pending -le 0 ]; then
        echo "0 0"
        return
    fi
    
    # BASE BATCH SIZE: 100,000 items (will be split into 500-item sub-batches)
    # This means 200 sub-batches of 500 items each per major batch
    local base_batch_size=100000
    
    # Determine batch size based on pending count
    if [ $pending -lt 1000 ]; then
        # Very small amount left - process all in one batch
        batch_size=$pending
        num_batches=1
    elif [ $pending -lt 10000 ]; then
        # Small amount - use 5000 item batches (10 sub-batches of 500)
        batch_size=5000
        num_batches=$(( (pending + batch_size - 1) / batch_size ))
    elif [ $pending -lt 100000 ]; then
        # Medium amount - use 25000 item batches (50 sub-batches of 500)
        batch_size=25000
        num_batches=$(( (pending + batch_size - 1) / batch_size ))
        # Cap at 10 batches
        if [ $num_batches -gt 10 ]; then
            num_batches=10
            batch_size=$(( (pending + num_batches - 1) / num_batches ))
        fi
    elif [ $pending -lt 500000 ]; then
        # Large amount - use 100,000 item batches (200 sub-batches of 500)
        batch_size=$base_batch_size
        num_batches=$(( (pending + batch_size - 1) / batch_size ))
        # Cap at 10 batches per cycle
        if [ $num_batches -gt 10 ]; then
            num_batches=10
            batch_size=$(( (pending + num_batches - 1) / num_batches ))
        fi
    else
        # Very large amount (500K+) - use max batch size
        batch_size=$base_batch_size
        num_batches=10  # 10 batches × 100K = 1M items per cycle
    fi
    
    echo "$batch_size $num_batches"
}

# Display configuration
echo -e "${BLUE}╔═══════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║     ${GREEN}INTELLIGENT CONTINUOUS PARLIAMENT PDF DOWNLOAD${BLUE}               ║${NC}"
echo -e "${BLUE}║     ${YELLOW}Automated Download Manager v2.0 with Progress Tracking${BLUE}       ║${NC}"
echo -e "${BLUE}╚═══════════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${GREEN}📋 Configuration:${NC}"
echo "  • Base batch size:     100,000 items (standard major batch)"
echo "  • Sub-batch size:      $SUB_BATCH_SIZE items (API request size)"
echo "  • Sub-batch delay:     ${SUB_DELAY}s between API calls"
echo "  • Major batch delay:   ${MAJOR_DELAY}s between major batches"
echo "  • Cycle delay:         ${CYCLE_DELAY}s between full cycles"
echo "  • Min threshold:       $MIN_PENDING_THRESHOLD items (idle below this)"
echo "  • Idle check:          Every ${IDLE_CHECK_INTERVAL}s when idle"
echo "  • Download type:       $DOWNLOAD_TYPE"
echo "  • Log file:            $LOG_FILE"
echo ""
echo -e "${YELLOW}🎯 Strategy:${NC}"
echo "  ✓ Fetches real-time statistics from API"
echo "  ✓ Uses accurate master_data counts (688K+ questions)"
echo "  ✓ Automatically calculates optimal batch sizes"
echo "  ✓ Random selection to avoid duplicate scheduling"
echo "  ✓ Visual progress bars with percentage tracking"
echo "  ✓ Smart idle mode when downloads complete"
echo ""
echo -e "${RED}⚡ Performance:${NC}"
echo "  • 16 concurrent Celery workers (2 workers × 8 processes)"
echo "  • Batch processing: 100K items = 200 sub-batches × 500 items"
echo "  • Processing capacity: ~5,000-10,000 PDFs per hour"
echo "  • Automatic retry on API timeouts with backoff"
echo ""
echo -e "${GREEN}Press Ctrl+C to stop gracefully${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════════════${NC}"
echo ""

# Main loop
CYCLE_NUM=1
START_TIME=$(date +%s)
CONSECUTIVE_IDLE_CYCLES=0

while true; do
    log_message "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    log_message "${GREEN}Starting Cycle #$CYCLE_NUM${NC}"
    
    # Calculate elapsed time
    CURRENT_TIME=$(date +%s)
    ELAPSED=$((CURRENT_TIME - START_TIME))
    HOURS=$((ELAPSED / 3600))
    MINUTES=$(((ELAPSED % 3600) / 60))
    SECONDS=$((ELAPSED % 60))
    
    log_message "Running time: ${HOURS}h ${MINUTES}m ${SECONDS}s"
    log_message ""
    
    # Get current statistics
    log_message "${YELLOW}Fetching current statistics...${NC}"
    STATS_OUTPUT=$(get_statistics 2>&1)
    
    if [ $? -ne 0 ]; then
        log_message "${RED}✗ Failed to fetch statistics${NC}"
        log_message "$STATS_OUTPUT"
        log_message "${YELLOW}Waiting ${CYCLE_DELAY}s before retry...${NC}"
        sleep $CYCLE_DELAY
        continue
    fi
    
    # Parse statistics
    eval "$STATS_OUTPUT"
    
    # Function to create progress bar
    create_progress_bar() {
        local current=$1
        local total=$2
        local width=30
        
        if [ $total -eq 0 ]; then
            echo "[No items]"
            return
        fi
        
        local percentage=$((current * 100 / total))
        local filled=$((current * width / total))
        local empty=$((width - filled))
        
        printf "["
        if [ $filled -gt 0 ]; then
            printf "%${filled}s" | tr ' ' '█'
        fi
        if [ $empty -gt 0 ]; then
            printf "%${empty}s" | tr ' ' '░'
        fi
        printf "] %3d%% (%s/%s)" $percentage \
            $(printf "%'d" $current) \
            $(printf "%'d" $total)
    }
    
    # Display statistics with progress bars
    log_message "${GREEN}═══ Current Download Status ════════════════════════════════════${NC}"
    log_message ""
    
    log_message "  ${BLUE}Lok Sabha Questions:${NC}"
    log_message "  $(create_progress_bar ${LS_DOWNLOADED:?} ${LS_TOTAL:?})"
    log_message "  ${YELLOW}↳ ${LS_PENDING:?} pending${NC}"
    log_message ""
    
    log_message "  ${BLUE}Rajya Sabha Questions:${NC}"
    log_message "  $(create_progress_bar ${RS_DOWNLOADED:?} ${RS_TOTAL:?})"
    log_message "  ${YELLOW}↳ ${RS_PENDING:?} pending${NC}"
    log_message ""
    
    log_message "  ${BLUE}Parliamentary Debates:${NC}"
    log_message "  $(create_progress_bar ${DEBATES_DOWNLOADED:?} ${DEBATES_TOTAL:?})"
    log_message "  ${YELLOW}↳ ${DEBATES_PENDING:?} pending${NC}"
    log_message ""
    
    PROGRESS_PCT=$((TOTAL_DOWNLOADED * 100 / TOTAL_ITEMS))
    log_message "  ${GREEN}━━━ Overall Progress ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    log_message "  $(create_progress_bar ${TOTAL_DOWNLOADED:?} ${TOTAL_ITEMS:?})"
    log_message ""
    
    # Check if there's work to do
    if [ ${TOTAL_PENDING:?} -lt $MIN_PENDING_THRESHOLD ]; then
        CONSECUTIVE_IDLE_CYCLES=$((CONSECUTIVE_IDLE_CYCLES + 1))
        log_message "${YELLOW}⏸ Only ${TOTAL_PENDING} items pending (below threshold of ${MIN_PENDING_THRESHOLD})${NC}"
        log_message "${YELLOW}Entering idle mode - will check again in ${IDLE_CHECK_INTERVAL}s${NC}"
        log_message "Consecutive idle cycles: $CONSECUTIVE_IDLE_CYCLES"
        
        if [ ${TOTAL_PENDING} -eq 0 ]; then
            log_message "${GREEN}✓ All downloads complete! 🎉${NC}"
            log_message "Total downloaded: ${TOTAL_DOWNLOADED}/${TOTAL_ITEMS}"
            log_message "Entering monitoring mode - checking for new items every ${IDLE_CHECK_INTERVAL}s"
        fi
        
        sleep $IDLE_CHECK_INTERVAL
        CYCLE_NUM=$((CYCLE_NUM + 1))
        continue
    fi
    
    # Reset idle counter if we have work
    if [ $CONSECUTIVE_IDLE_CYCLES -gt 0 ]; then
        log_message "${GREEN}Resuming active downloads${NC}"
        CONSECUTIVE_IDLE_CYCLES=0
    fi
    
    # Calculate optimal batch parameters
    read BATCH_SIZE NUM_BATCHES <<< $(calculate_batch_params ${TOTAL_PENDING:?})
    
    # Calculate how many sub-batches this will create
    SUB_BATCHES_PER_MAJOR=$((BATCH_SIZE / SUB_BATCH_SIZE))
    if [ $((BATCH_SIZE % SUB_BATCH_SIZE)) -ne 0 ]; then
        SUB_BATCHES_PER_MAJOR=$((SUB_BATCHES_PER_MAJOR + 1))
    fi
    TOTAL_SUB_BATCHES=$((SUB_BATCHES_PER_MAJOR * NUM_BATCHES))
    
    log_message "${BLUE}📊 Batch Calculation:${NC}"
    log_message "  Major batch size:      $(printf "%'d" $BATCH_SIZE) items"
    log_message "  Number of batches:     $NUM_BATCHES"
    log_message "  Sub-batches per major: $SUB_BATCHES_PER_MAJOR (${SUB_BATCH_SIZE} items each)"
    log_message "  Total sub-batches:     $TOTAL_SUB_BATCHES API calls"
    log_message "  Total to schedule:     $(printf "%'d" $((BATCH_SIZE * NUM_BATCHES))) items"
    log_message "  Estimated time:        ~$((TOTAL_SUB_BATCHES * SUB_DELAY / 60)) minutes"
    log_message ""
    
    # Run the batch download script
    if [ $BATCH_SIZE -gt 0 ] && [ $NUM_BATCHES -gt 0 ]; then
        python3 "$SCRIPT_DIR/batch_download_and_monitor.py" \
            --batches $NUM_BATCHES \
            --batch-size $BATCH_SIZE \
            --sub-batch-size $SUB_BATCH_SIZE \
            --sub-delay $SUB_DELAY \
            --delay $MAJOR_DELAY \
            --type $DOWNLOAD_TYPE
        
        EXIT_CODE=$?
        
        if [ $EXIT_CODE -eq 0 ]; then
            log_message "${GREEN}✓ Cycle #$CYCLE_NUM completed successfully${NC}"
        else
            log_message "${RED}✗ Cycle #$CYCLE_NUM exited with code $EXIT_CODE${NC}"
        fi
    else
        log_message "${YELLOW}⚠ No batches to schedule${NC}"
    fi
    
    log_message ""
    log_message "${YELLOW}Waiting ${CYCLE_DELAY}s before next cycle...${NC}"
    log_message "Next cycle will start at: $(date -d "+${CYCLE_DELAY} seconds" '+%Y-%m-%d %H:%M:%S')"
    log_message ""
    
    # Wait before next cycle
    sleep $CYCLE_DELAY
    
    CYCLE_NUM=$((CYCLE_NUM + 1))
done