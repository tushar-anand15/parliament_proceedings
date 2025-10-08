#!/bin/bash
#
# Test script for continuous_download.sh fixes
#

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_PATH="$PROJECT_ROOT/env"

echo -e "${BLUE}Testing continuous_download.sh fixes${NC}"
echo ""

# Test 1: Check if virtual environment exists
echo -e "${YELLOW}Test 1: Checking virtual environment...${NC}"
if [ -f "$VENV_PATH/bin/activate" ]; then
    echo -e "${GREEN}✓ Virtual environment found${NC}"
else
    echo -e "${RED}✗ Virtual environment not found at $VENV_PATH${NC}"
    exit 1
fi

# Test 2: Check if batch_download_and_monitor.py exists
echo -e "${YELLOW}Test 2: Checking batch_download_and_monitor.py...${NC}"
if [ -f "$SCRIPT_DIR/batch_download_and_monitor.py" ]; then
    echo -e "${GREEN}✓ batch_download_and_monitor.py found${NC}"
else
    echo -e "${RED}✗ batch_download_and_monitor.py not found${NC}"
    exit 1
fi

# Test 3: Check if redis module is available
echo -e "${YELLOW}Test 3: Checking redis Python module...${NC}"
if "$VENV_PATH/bin/python" -c "import redis" 2>/dev/null; then
    echo -e "${GREEN}✓ redis module available${NC}"
else
    echo -e "${RED}✗ redis module not found${NC}"
    echo -e "${YELLOW}Run: source $VENV_PATH/bin/activate && pip install redis${NC}"
    exit 1
fi

# Test 4: Check if requests module is available
echo -e "${YELLOW}Test 4: Checking requests Python module...${NC}"
if "$VENV_PATH/bin/python" -c "import requests" 2>/dev/null; then
    echo -e "${GREEN}✓ requests module available${NC}"
else
    echo -e "${RED}✗ requests module not found${NC}"
    exit 1
fi

# Test 5: Test statistics fetching
echo -e "${YELLOW}Test 5: Testing statistics fetching...${NC}"

# Source the get_statistics function
source "$SCRIPT_DIR/continuous_download.sh" 2>/dev/null

# Try to get statistics
STATS_OUTPUT=$(get_statistics 2>/tmp/test_stats_err.log)
STATS_EXIT_CODE=$?

if [ $STATS_EXIT_CODE -eq 0 ] && echo "$STATS_OUTPUT" | grep -q "TOTAL_PENDING"; then
    echo -e "${GREEN}✓ Statistics fetching works${NC}"
    
    # Parse and display some stats
    while IFS= read -r line; do
        if echo "$line" | grep -qE '^TOTAL_PENDING=[0-9]+$'; then
            eval "$line"
            echo "  Total pending items: ${TOTAL_PENDING}"
        fi
    done <<< "$STATS_OUTPUT"
else
    echo -e "${YELLOW}⚠ Statistics fetching returned exit code $STATS_EXIT_CODE${NC}"
    if [ -f /tmp/test_stats_err.log ]; then
        echo "  Error output:"
        cat /tmp/test_stats_err.log | sed 's/^/    /'
    fi
fi

# Test 6: Test queue checking
echo -e "${YELLOW}Test 6: Testing Celery queue check...${NC}"
QUEUE_SIZE=$("$VENV_PATH/bin/python" "$SCRIPT_DIR/batch_download_and_monitor.py" --check-queue 2>/dev/null | grep "pending" | grep -oE '[0-9,]+' | head -1 | tr -d ',')
if [ -n "$QUEUE_SIZE" ]; then
    echo -e "${GREEN}✓ Queue check works (Queue size: $QUEUE_SIZE)${NC}"
else
    echo -e "${YELLOW}⚠ Queue check via Python failed, trying redis-cli...${NC}"
    QUEUE_SIZE=$(redis-cli LLEN celery 2>/dev/null || echo "0")
    echo "  Queue size via redis-cli: $QUEUE_SIZE"
fi

echo ""
echo -e "${GREEN}All basic tests completed!${NC}"
echo ""
echo -e "${BLUE}To run the full continuous download script:${NC}"
echo -e "${YELLOW}  cd $SCRIPT_DIR${NC}"
echo -e "${YELLOW}  ./continuous_download.sh${NC}"
echo ""
echo -e "${BLUE}Or run in tmux:${NC}"
echo -e "${YELLOW}  tmux new -s download${NC}"
echo -e "${YELLOW}  cd $SCRIPT_DIR && ./continuous_download.sh${NC}"
