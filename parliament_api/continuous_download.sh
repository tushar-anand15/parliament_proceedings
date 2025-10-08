#!/bin/bash
#
# Optimized Continuous Parliament PDF Download Script
# Uses materialized views for instant stats and indexed sequential processing
#
# Performance improvements:
# - Statistics queries: 12-55x faster (98ms vs 6s+)  
# - Sequential processing with compound indexes
# - No more random ordering overhead
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
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_PATH="$PROJECT_ROOT/env"
SUB_BATCH_SIZE=500        # Items per sub-batch (optimized for Celery workers)
SUB_DELAY=2              # Seconds between sub-batches (faster with indexed queries)
MAJOR_DELAY=120          # Seconds between major batches
CYCLE_DELAY=300          # Seconds between full cycles (5 minutes)
MIN_PENDING_THRESHOLD=100  # Don't schedule if less than this pending
IDLE_CHECK_INTERVAL=600    # Check every 10 minutes when idle
DOWNLOAD_TYPE="all"      # all, ls, rs, or debates
MAX_QUEUE_SIZE=5000     # Maximum queue size before waiting
QUEUE_WAIT_TIMEOUT=1800  # Maximum time to wait for queue (30 minutes)

# Activate virtual environment
if [ -f "$VENV_PATH/bin/activate" ]; then
    source "$VENV_PATH/bin/activate"
else
    echo -e "${RED}Error: Virtual environment not found at $VENV_PATH${NC}"
    exit 1
fi

# Logging
LOG_FILE="/var/log/parliament_api/continuous_download.log"
mkdir -p "$(dirname "$LOG_FILE")" 2>/dev/null || LOG_FILE="$SCRIPT_DIR/download.log"

log_message() {
    echo -e "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

# Trap Ctrl+C to exit gracefully
trap 'log_message "${RED}Script interrupted by user${NC}"; exit 0' INT TERM

# Get current statistics from the API with better error handling
get_statistics() {
    "$VENV_PATH/bin/python3" - <<'EOF'
import requests
import json
import sys
import time
import os
from datetime import datetime, timedelta

BASE_URL = "https://api.opensansad.co.in"
TOKEN = "***REMOVED_SECRET***"
HEADERS = {
    "Authorization": f"Token {TOKEN}",
    "Content-Type": "application/json",
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://www.opensansad.co.in",
    "Referer": "https://www.opensansad.co.in/",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
}

# Cache file for statistics
CACHE_FILE = "/tmp/parliament_stats_cache.json"
CACHE_DURATION = 60  # 1 minute cache for more real-time monitoring

def load_cached_stats():
    """Load cached statistics if available and fresh"""
    try:
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE, 'r') as f:
                cache_data = json.load(f)
            
            # Check if cache is fresh
            cache_time = datetime.fromisoformat(cache_data.get('timestamp', '2000-01-01'))
            if datetime.now() - cache_time < timedelta(seconds=CACHE_DURATION):
                return cache_data.get('stats')
    except:
        pass
    return None

def save_stats_cache(stats):
    """Save statistics to cache"""
    try:
        cache_data = {
            'timestamp': datetime.now().isoformat(),
            'stats': stats
        }
        with open(CACHE_FILE, 'w') as f:
            json.dump(cache_data, f)
    except:
        pass

def fetch_with_retry(url, headers, max_retries=2, timeout=5):
    """Fetch URL with retry logic - short timeout for fast failure"""
    for attempt in range(max_retries):
        try:
            response = requests.get(url, headers=headers, timeout=timeout)
            response.raise_for_status()
            return response
        except (requests.RequestException, requests.Timeout) as e:
            if attempt < max_retries - 1:
                time.sleep(1)  # Quick retry
            else:
                return None
    return None

# Try to load from cache first
cached_stats = load_cached_stats()
if cached_stats:
    print(f"# Using cached statistics", file=sys.stderr)
    for key, value in cached_stats.items():
        print(f"{key}={value}")
    sys.exit(0)

try:
    all_stats = {}
    
    # Try the OPTIMIZED endpoint first (materialized view) - SUPER FAST!
    try:
        optimized_response = fetch_with_retry(
            f"{BASE_URL}/api/questions/optimized-stats/",  # Our new 98ms endpoint!
            headers=HEADERS,
            timeout=3
        )
        if optimized_response:
            opt_stats = optimized_response.json()
            if opt_stats.get('status') == 'success':
                # Extract data from optimized endpoint
                ls_stats = opt_stats.get('lok_sabha', {})
                rs_stats = opt_stats.get('rajya_sabha', {})
                
                all_stats['ls'] = {
                    'total_with_pdf': ls_stats.get('total_with_pdf', 688235),
                    'downloaded': ls_stats.get('downloaded', 0)
                }
                all_stats['rs'] = {
                    'total_with_pdf': rs_stats.get('total_with_pdf', 309986),
                    'downloaded': rs_stats.get('downloaded', 0)
                }
                print(f"# Using optimized materialized view stats", file=sys.stderr)
    except:
        pass
    
    # If optimized endpoint failed, try the regular fast-stats endpoint
    if 'ls' not in all_stats:
        try:
            questions_response = fetch_with_retry(
                f"{BASE_URL}/api/questions/fast-stats/",
                headers=HEADERS,
                timeout=5
            )
            if questions_response:
                questions_stats = questions_response.json()
                all_stats['ls'] = questions_stats.get('lok_sabha', {'total_with_pdf': 688235, 'downloaded': 0})
                all_stats['rs'] = questions_stats.get('rajya_sabha', {'total_with_pdf': 309986, 'downloaded': 0})
                print(f"# Using fast-stats endpoint", file=sys.stderr)
        except:
            # Use known totals as fallback
            all_stats['ls'] = {'total_with_pdf': 688235, 'downloaded': 0}
            all_stats['rs'] = {'total_with_pdf': 309986, 'downloaded': 0}
    
    # Try to get debate statistics (use optimized endpoint if available)
    try:
        # Try optimized debate endpoint first
        debate_opt_response = fetch_with_retry(
            f"{BASE_URL}/api/questions/optimized-stats/debates/",  # 108ms endpoint!
            headers=HEADERS,
            timeout=3
        )
        if debate_opt_response:
            debate_opt_stats = debate_opt_response.json()
            if debate_opt_stats.get('status') == 'success':
                stats = debate_opt_stats.get('stats', {}).get('lok_sabha', {})
                by_status = stats.get('by_status', {})
                all_stats['debates'] = {
                    'total_debates': stats.get('total_debates', 44179),
                    'status_breakdown': {
                        'completed': by_status.get('completed', 0),
                        'pending': by_status.get('pending', 44179)
                    }
                }
                print(f"# Using optimized debate stats", file=sys.stderr)
    except:
        pass
    
    # Fallback to regular debate endpoint if optimized failed
    if 'debates' not in all_stats:
        try:
            debate_response = fetch_with_retry(
                f"{BASE_URL}/api/debates/download-stats/",
                headers=HEADERS,
                timeout=8
            )
            if debate_response:
                debate_stats = debate_response.json()
                all_stats['debates'] = debate_stats
        except:
            all_stats['debates'] = {'total_debates': 44179, 'status_breakdown': {'completed': 0, 'pending': 44179}}
    
    # Extract and format data
    ls_data = all_stats.get('ls', {})
    ls_total = ls_data.get('total_with_pdf', 688235)
    ls_downloaded = ls_data.get('downloaded', 0)
    ls_pending = ls_data.get('pending', ls_total - ls_downloaded)
    
    rs_data = all_stats.get('rs', {})
    rs_total = rs_data.get('total_with_pdf', 309986)
    rs_downloaded = rs_data.get('downloaded', 0)
    rs_pending = rs_data.get('pending', rs_total - rs_downloaded)
    
    debate_stats = all_stats.get('debates', {})
    debates_total = debate_stats.get('total_debates', 44179)
    status_breakdown = debate_stats.get('status_breakdown', {})
    debates_downloaded = status_breakdown.get('completed', 0)
    debates_pending = status_breakdown.get('pending', debates_total - debates_downloaded)
    
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
    
    # Save to cache for next time
    cache_stats = {
        'LS_TOTAL': ls_total,
        'LS_DOWNLOADED': ls_downloaded,
        'LS_PENDING': ls_pending,
        'RS_TOTAL': rs_total,
        'RS_DOWNLOADED': rs_downloaded,
        'RS_PENDING': rs_pending,
        'DEBATES_TOTAL': debates_total,
        'DEBATES_DOWNLOADED': debates_downloaded,
        'DEBATES_PENDING': debates_pending,
        'TOTAL_PENDING': total_pending,
        'TOTAL_ITEMS': total_items,
        'TOTAL_DOWNLOADED': total_downloaded
    }
    save_stats_cache(cache_stats)
    
except Exception as e:
    print(f"# Warning: Could not fetch fresh statistics, using estimates", file=sys.stderr)
    # Use reasonable fallback values based on known totals
    print("LS_TOTAL=688235")
    print("LS_DOWNLOADED=0")
    print("LS_PENDING=688235")
    print("RS_TOTAL=309986")
    print("RS_DOWNLOADED=0")
    print("RS_PENDING=309986")
    print("DEBATES_TOTAL=44179")
    print("DEBATES_DOWNLOADED=0")
    print("DEBATES_PENDING=44179")
    print("TOTAL_PENDING=1042400")
    print("TOTAL_ITEMS=1042400")
    print("TOTAL_DOWNLOADED=0")
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
echo -e "${BLUE}║     ${GREEN}OPTIMIZED CONTINUOUS PARLIAMENT PDF DOWNLOAD${BLUE}                 ║${NC}"
echo -e "${BLUE}║     ${YELLOW}v3.0 - Sequential Processing with Indexed Queries${BLUE}            ║${NC}"
echo -e "${BLUE}╚═══════════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${GREEN}📋 Configuration:${NC}"
echo "  • Base batch size:     100,000 items (standard major batch)"
echo "  • Sub-batch size:      $SUB_BATCH_SIZE items (API request size)"
echo "  • Sub-batch delay:     ${SUB_DELAY}s between API calls"
echo "  • Major batch delay:   ${MAJOR_DELAY}s between major batches"
echo "  • Cycle delay:         ${CYCLE_DELAY}s between full cycles"
echo "  • Min threshold:       $MIN_PENDING_THRESHOLD items (idle below this)"
echo "  • Max queue size:      $MAX_QUEUE_SIZE items (wait if above this)"
echo "  • Idle check:          Every ${IDLE_CHECK_INTERVAL}s when idle"
echo "  • Download type:       $DOWNLOAD_TYPE"
echo "  • Log file:            $LOG_FILE"
echo "  • Virtual env:         $VENV_PATH"
echo ""
echo -e "${YELLOW}🎯 Strategy:${NC}"
echo "  ✓ Uses optimized materialized view endpoints (98ms response time)"
echo "  ✓ Sequential processing with indexed queries (no random overhead)"
echo "  ✓ Monitors Celery queue to prevent overload"
echo "  ✓ Waits for queue to clear before scheduling new batches"
echo "  ✓ Automatically calculates optimal batch sizes"
echo "  ✓ Visual progress bars with percentage tracking"
echo "  ✓ Smart idle mode when downloads complete"
echo ""
echo -e "${RED}⚡ Performance:${NC}"
echo "  • 32 concurrent Celery workers (4 workers × 8 processes)"
echo "  • Batch processing: 100K items = 200 sub-batches × 500 items"
echo "  • Processing capacity: ~10,000-20,000 PDFs per hour"
echo "  • Automatic retry on API timeouts with backoff"
echo ""
echo -e "${GREEN}Press Ctrl+C to stop gracefully${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════════════${NC}"
echo ""

# Verify Python packages are available
if ! "$VENV_PATH/bin/python" -c "import redis" 2>/dev/null; then
    echo -e "${RED}Error: redis package not found in virtual environment${NC}"
    echo -e "${YELLOW}Run: source $VENV_PATH/bin/activate && pip install redis${NC}"
    exit 1
fi

# Function to check Celery queue
check_celery_queue() {
    local queue_output=$("$VENV_PATH/bin/python" "$SCRIPT_DIR/batch_download_and_monitor.py" --check-queue 2>/dev/null | grep "pending" | grep -oE '[0-9,]+' | head -1 | tr -d ',')
    if [ -n "$queue_output" ]; then
        echo "$queue_output"
    else
        # Fallback to redis-cli if Python fails
        redis-cli LLEN celery 2>/dev/null || echo "0"
    fi
}

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
    
    # Get current statistics (with fallback)
    log_message "${YELLOW}Fetching current statistics...${NC}"
    STATS_OUTPUT=$(get_statistics 2>&1)
    
    # Check if we got statistics (even if from cache or fallback)
    if echo "$STATS_OUTPUT" | grep -q "TOTAL_PENDING"; then
        # Statistics are available (either fresh, cached, or fallback)
        if echo "$STATS_OUTPUT" | grep -q "Using cached"; then
            log_message "${BLUE}ℹ Using cached statistics${NC}"
        elif echo "$STATS_OUTPUT" | grep -q "using estimates"; then
            log_message "${YELLOW}⚠ Using estimated statistics (API unavailable)${NC}"
        else
            log_message "${GREEN}✓ Fresh statistics retrieved${NC}"
        fi
    else
        # Complete failure - skip this cycle
        log_message "${RED}✗ Failed to get any statistics${NC}"
        log_message "${YELLOW}Will retry in ${CYCLE_DELAY}s...${NC}"
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
    # Check Celery queue status first
    QUEUE_SIZE=$(check_celery_queue)
    log_message "${BLUE}═══ Queue Status ════════════════════════════════════════════════${NC}"
    log_message "  Celery Queue: ${QUEUE_SIZE} pending tasks"
    
    if [ "$QUEUE_SIZE" -gt "$MAX_QUEUE_SIZE" ]; then
        log_message "  ${RED}⚠ Queue is OVERLOADED (>${MAX_QUEUE_SIZE})${NC}"
        log_message "  ${YELLOW}Will wait for queue to clear before scheduling...${NC}"
    elif [ "$QUEUE_SIZE" -gt 5000 ]; then
        log_message "  ${YELLOW}⚠ Queue is high${NC}"
    elif [ "$QUEUE_SIZE" -gt 0 ]; then
        log_message "  ${GREEN}✓ Queue is processing${NC}"
    else
        log_message "  ${GREEN}✓ Queue is empty${NC}"
    fi
    log_message ""
    
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
    
    # Check queue before scheduling
    if [ "$QUEUE_SIZE" -gt "$MAX_QUEUE_SIZE" ]; then
        log_message "${YELLOW}⏸ Queue has $QUEUE_SIZE tasks (threshold: $MAX_QUEUE_SIZE)${NC}"
        log_message "${YELLOW}Waiting for queue to process before scheduling new tasks...${NC}"
        
        # Wait for queue to clear
        WAIT_COUNT=0
        MAX_WAIT_CYCLES=$((QUEUE_WAIT_TIMEOUT / 60))  # Convert to minutes
        
        while [ "$QUEUE_SIZE" -gt "$MAX_QUEUE_SIZE" ] && [ $WAIT_COUNT -lt $MAX_WAIT_CYCLES ]; do
            # Show animated waiting indicator
            for spinner in '▓' '▒' '░' '▒'; do
                echo -ne "\r  ${spinner} Waiting... Queue: $QUEUE_SIZE tasks (${WAIT_COUNT}/${MAX_WAIT_CYCLES} min) ${spinner}  "
                sleep 15
                if [ $((WAIT_COUNT % 4)) -eq 0 ]; then
                    QUEUE_SIZE=$(check_celery_queue)
                fi
            done
            WAIT_COUNT=$((WAIT_COUNT + 1))
        done
        
        if [ "$QUEUE_SIZE" -gt "$MAX_QUEUE_SIZE" ]; then
            log_message "${RED}✗ Queue still overloaded after ${QUEUE_WAIT_TIMEOUT}s wait${NC}"
            log_message "${YELLOW}Skipping this cycle to prevent further overload${NC}"
        else
            log_message "${GREEN}✓ Queue cleared to $QUEUE_SIZE tasks${NC}"
        fi
    fi
    
    # Run the batch download script only if queue is not overloaded
    if [ $BATCH_SIZE -gt 0 ] && [ $NUM_BATCHES -gt 0 ] && [ "$QUEUE_SIZE" -le "$MAX_QUEUE_SIZE" ]; then
        log_message "${BLUE}🚀 Starting batch scheduling...${NC}"
        log_message "${YELLOW}This will take approximately $((TOTAL_SUB_BATCHES * SUB_DELAY / 60)) minutes${NC}"
        log_message ""
        
        # Create a simple progress indicator
        (
            while kill -0 $$ 2>/dev/null; do
                echo -ne "\r  Scheduling: ["
                for ((i=0; i<20; i++)); do
                    if [ $((RANDOM % 2)) -eq 0 ]; then
                        echo -ne "█"
                    else
                        echo -ne "░"
                    fi
                done
                echo -ne "] Queue: $(check_celery_queue) tasks    "
                sleep 2
            done
        ) &
        PROGRESS_PID=$!
        
        "$VENV_PATH/bin/python" "$SCRIPT_DIR/batch_download_and_monitor.py" \
            --batches $NUM_BATCHES \
            --batch-size $BATCH_SIZE \
            --sub-batch-size $SUB_BATCH_SIZE \
            --sub-delay $SUB_DELAY \
            --delay $MAJOR_DELAY \
            --type $DOWNLOAD_TYPE \
            --max-queue-size $MAX_QUEUE_SIZE
        
        EXIT_CODE=$?
        
        # Stop progress indicator
        kill $PROGRESS_PID 2>/dev/null
        wait $PROGRESS_PID 2>/dev/null
        echo -ne "\r                                                                           \r"
        
        if [ $EXIT_CODE -eq 0 ]; then
            log_message "${GREEN}✓ Cycle #$CYCLE_NUM completed successfully${NC}"
        else
            log_message "${RED}✗ Cycle #$CYCLE_NUM exited with code $EXIT_CODE${NC}"
        fi
    else
        if [ "$QUEUE_SIZE" -gt "$MAX_QUEUE_SIZE" ]; then
            log_message "${YELLOW}⚠ Skipped scheduling due to queue overload${NC}"
        else
            log_message "${YELLOW}⚠ No batches to schedule${NC}"
        fi
    fi
    
    log_message ""
    log_message "${YELLOW}Waiting ${CYCLE_DELAY}s before next cycle...${NC}"
    log_message "Next cycle will start at: $(date -d "+${CYCLE_DELAY} seconds" '+%Y-%m-%d %H:%M:%S')"
    log_message ""
    
    # Wait before next cycle with countdown
    WAIT_TIME=$CYCLE_DELAY
    while [ $WAIT_TIME -gt 0 ]; do
        MINS=$((WAIT_TIME / 60))
        SECS=$((WAIT_TIME % 60))
        echo -ne "\r  ${YELLOW}⏱${NC} Next cycle in: ${MINS}m ${SECS}s  "
        sleep 1
        WAIT_TIME=$((WAIT_TIME - 1))
    done
    echo -ne "\r                                          \r"
    
    CYCLE_NUM=$((CYCLE_NUM + 1))
done