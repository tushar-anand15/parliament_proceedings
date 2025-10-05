#!/bin/bash
# Reset Parliament API Database
# This script will drop the current database and trigger a fresh setup on next startup

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${YELLOW}⚠️  DATABASE RESET WARNING${NC}"
echo "This will:"
echo "  1. Drop the entire parliament_api database"
echo "  2. Delete all Redis data (dump.rdb)"
echo "  3. Trigger fresh setup on next startup"
echo ""
echo "All your data will be LOST, including:"
echo "  - All downloaded questions and debates"
echo "  - All master data tables"
echo "  - All user accounts and authentication tokens"
echo "  - All task history"
echo ""

read -p "Are you ABSOLUTELY sure you want to continue? (type 'yes' to confirm): " confirm

if [ "$confirm" != "yes" ]; then
    echo -e "${GREEN}✓${NC} Database reset cancelled"
    exit 0
fi

echo ""
echo -e "${YELLOW}Starting database reset...${NC}"

# Load environment variables
if [ -f ".env" ]; then
    export $(grep -v '^#' .env | xargs)
fi

DB_NAME=${DB_NAME:-parliament_api}
DB_USER=${DB_USER:-parliament_user}

# Stop all services first
echo -e "${YELLOW}1.${NC} Stopping all services..."
./startup.sh stop 2>/dev/null || true

# Drop database
echo -e "${YELLOW}2.${NC} Dropping database: $DB_NAME"
psql postgres -c "DROP DATABASE IF EXISTS $DB_NAME;" 2>/dev/null || {
    echo -e "${RED}✗${NC} Failed to drop database. Make sure PostgreSQL is running."
    exit 1
}

# Delete Redis data
echo -e "${YELLOW}3.${NC} Deleting Redis data..."
rm -f parliament_api/dump.rdb
rm -f dump.rdb

# Create reset flag for startup script
echo -e "${YELLOW}4.${NC} Creating reset flag..."
cd parliament_api
touch .reset_db_flag
cd ..

echo ""
echo -e "${GREEN}✅ Database reset complete!${NC}"
echo ""
echo "Next steps:"
echo "  1. Start the services: ./startup.sh start"
echo "  2. The startup script will:"
echo "     - Create fresh database"
echo "     - Run migrations"
echo "     - Create admin user"
echo "     - Initialize GCS buckets"
echo "     - Populate master data tables (5-10 minutes)"
echo "     - Start all services"
echo ""
echo "Note: Master data initialization will fetch from Parliament APIs"
echo "      and may take 5-10 minutes depending on your connection."


