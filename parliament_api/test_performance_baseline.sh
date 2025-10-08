#!/bin/bash
#
# Performance Baseline Testing Script
# Run this BEFORE and AFTER applying database optimizations
#

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
BASE_URL="https://api.opensansad.co.in/api"
TOKEN="***REMOVED_SECRET***"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}    Performance Baseline Testing${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo -e "${YELLOW}Testing Date:${NC} $(date)"
echo ""

# Function to test endpoint and measure time
test_endpoint() {
    local endpoint=$1
    local description=$2
    
    echo -e "${YELLOW}Testing:${NC} $description"
    echo -e "${YELLOW}Endpoint:${NC} $endpoint"
    
    # Run the request and capture time
    start_time=$(date +%s%N)
    
    response=$(curl -s -w "\n%{http_code}" -X GET \
        -H "Authorization: Token $TOKEN" \
        -H "Content-Type: application/json" \
        "$BASE_URL$endpoint" 2>/dev/null)
    
    end_time=$(date +%s%N)
    
    # Extract HTTP status code (last line)
    http_code=$(echo "$response" | tail -1)
    
    # Calculate elapsed time in milliseconds
    elapsed_ms=$(( (end_time - start_time) / 1000000 ))
    # Calculate seconds with decimal (using integer math for compatibility)
    elapsed_s_int=$((elapsed_ms / 1000))
    elapsed_s_dec=$((elapsed_ms % 1000))
    elapsed_s="${elapsed_s_int}.${elapsed_s_dec}"
    
    # Color code the result
    if [ "$http_code" = "200" ]; then
        echo -e "${GREEN}✓ Status: $http_code${NC}"
        echo -e "${GREEN}✓ Time: ${elapsed_s}s (${elapsed_ms}ms)${NC}"
    elif [ "$http_code" = "503" ] || [ "$http_code" = "500" ]; then
        echo -e "${RED}✗ Status: $http_code (Error/Timeout)${NC}"
        echo -e "${RED}✗ Time: ${elapsed_s}s (${elapsed_ms}ms)${NC}"
    else
        echo -e "${YELLOW}⚠ Status: $http_code${NC}"
        echo -e "${YELLOW}⚠ Time: ${elapsed_s}s (${elapsed_ms}ms)${NC}"
    fi
    
    echo "---"
    echo ""
    
    # Return time in milliseconds for summary
    echo "$elapsed_ms" >> /tmp/perf_times.txt
}

# Clean up previous test
rm -f /tmp/perf_times.txt

echo -e "${BLUE}=== 1. Question Statistics Tests ===${NC}"
echo ""

test_endpoint "/questions/fast-stats/" "Fast Stats Endpoint (Current)"
test_endpoint "/questions/optimized-stats/" "Materialized View Stats (New)"
test_endpoint "/questions/ls/download-statistics/" "Download Statistics"

echo -e "${BLUE}=== 2. Debate Statistics Tests ===${NC}"
echo ""

test_endpoint "/debates/download-stats/" "Debate Download Stats"
test_endpoint "/questions/optimized-stats/debates/" "Debate Materialized View Stats (New)"

echo -e "${BLUE}=== 3. Heavy Query Tests ===${NC}"
echo ""

# Test a filtered query
test_endpoint "/questions/ls/master-data/list/?lok_sabha_number=17&session_number=1&limit=100" "Filtered Master Data Query"

# Test RS statistics
test_endpoint "/questions/rs/statistics/" "RS Question Statistics"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}    Performance Summary${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

if [ -f /tmp/perf_times.txt ]; then
    # Calculate statistics
    total_time=0
    count=0
    max_time=0
    min_time=999999999
    
    while IFS= read -r time_ms; do
        total_time=$((total_time + time_ms))
        count=$((count + 1))
        
        if [ "$time_ms" -gt "$max_time" ]; then
            max_time=$time_ms
        fi
        
        if [ "$time_ms" -lt "$min_time" ]; then
            min_time=$time_ms
        fi
    done < /tmp/perf_times.txt
    
    if [ $count -gt 0 ]; then
        avg_time=$((total_time / count))
        
        echo -e "${YELLOW}Total Endpoints Tested:${NC} $count"
        echo -e "${YELLOW}Average Response Time:${NC} ${avg_time}ms"
        echo -e "${YELLOW}Fastest Response:${NC} ${min_time}ms"
        echo -e "${YELLOW}Slowest Response:${NC} ${max_time}ms"
        echo ""
        
        # Performance rating
        if [ $avg_time -lt 500 ]; then
            echo -e "${GREEN}🎯 Performance: EXCELLENT (<500ms avg)${NC}"
        elif [ $avg_time -lt 2000 ]; then
            echo -e "${GREEN}✓ Performance: GOOD (<2s avg)${NC}"
        elif [ $avg_time -lt 5000 ]; then
            echo -e "${YELLOW}⚠ Performance: NEEDS IMPROVEMENT (<5s avg)${NC}"
        else
            echo -e "${RED}✗ Performance: CRITICAL (>5s avg)${NC}"
        fi
    fi
    
    rm -f /tmp/perf_times.txt
fi

echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}    Recommendations${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo "1. Run database migrations to add indexes and materialized views:"
echo -e "   ${YELLOW}python manage.py migrate questions${NC}"
echo -e "   ${YELLOW}python manage.py migrate debates${NC}"
echo ""
echo "2. Refresh materialized views after migration:"
echo -e "   ${YELLOW}curl -X POST -H 'Authorization: Token $TOKEN' $BASE_URL/questions/optimized-stats/refresh/${NC}"
echo ""
echo "3. For continuous monitoring, schedule materialized view refresh:"
echo -e "   ${YELLOW}Add to crontab: */5 * * * * psql -d parliament_api -c 'REFRESH MATERIALIZED VIEW CONCURRENTLY mv_question_statistics;'${NC}"
echo ""
echo "4. Monitor slow queries in PostgreSQL:"
echo -e "   ${YELLOW}psql -d parliament_api -c 'SELECT * FROM pg_stat_statements ORDER BY total_time DESC LIMIT 10;'${NC}"
echo ""
