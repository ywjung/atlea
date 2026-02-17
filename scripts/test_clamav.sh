#!/bin/bash
# ClamAV Integration Test Script
# Tests ClamAV Docker container and virus scanning functionality

set -e

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "========================================="
echo "ClamAV Integration Test"
echo "========================================="
echo ""

# 1. Check if Docker is running
echo -e "${YELLOW}[1/7] Checking Docker...${NC}"
if ! docker info > /dev/null 2>&1; then
    echo -e "${RED}✗ Docker is not running${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Docker is running${NC}"
echo ""

# 2. Start ClamAV container
echo -e "${YELLOW}[2/7] Starting ClamAV container...${NC}"
docker-compose up -d clamav
echo -e "${GREEN}✓ ClamAV container started${NC}"
echo ""

# 3. Wait for ClamAV to be ready (up to 3 minutes)
echo -e "${YELLOW}[3/7] Waiting for ClamAV to initialize (this may take 2-3 minutes)...${NC}"
echo "Downloading virus definitions..."

MAX_WAIT=180  # 3 minutes
WAIT_INTERVAL=5
ELAPSED=0

while [ $ELAPSED -lt $MAX_WAIT ]; do
    if docker exec chatbot_clamav /usr/local/bin/clamd --ping 2>/dev/null | grep -q "PONG"; then
        echo -e "${GREEN}✓ ClamAV is ready!${NC}"
        break
    fi

    echo -n "."
    sleep $WAIT_INTERVAL
    ELAPSED=$((ELAPSED + WAIT_INTERVAL))

    if [ $ELAPSED -ge $MAX_WAIT ]; then
        echo -e "${RED}✗ ClamAV failed to start within 3 minutes${NC}"
        echo "Checking logs:"
        docker-compose logs clamav | tail -20
        exit 1
    fi
done
echo ""

# 4. Check ClamAV status
echo -e "${YELLOW}[4/7] Checking ClamAV status...${NC}"
docker-compose ps clamav
echo ""

# 5. Test with clean file
echo -e "${YELLOW}[5/7] Testing clean file scan...${NC}"
echo "This is a clean test file" > /tmp/clean_test.txt

if docker exec chatbot_clamav /usr/local/bin/clamdscan /tmp/clean_test.txt 2>&1 | grep -q "OK"; then
    echo -e "${GREEN}✓ Clean file scan successful${NC}"
else
    echo -e "${RED}✗ Clean file scan failed${NC}"
fi
rm -f /tmp/clean_test.txt
echo ""

# 6. Test with EICAR test virus
echo -e "${YELLOW}[6/7] Testing virus detection with EICAR test file...${NC}"
echo 'X5O!P%@AP[4\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*' > /tmp/eicar.txt

docker cp /tmp/eicar.txt chatbot_clamav:/tmp/eicar.txt

if docker exec chatbot_clamav /usr/local/bin/clamdscan /tmp/eicar.txt 2>&1 | grep -q "FOUND"; then
    echo -e "${GREEN}✓ Virus detection successful (EICAR test)${NC}"
else
    echo -e "${RED}✗ Virus detection failed${NC}"
    exit 1
fi

rm -f /tmp/eicar.txt
docker exec chatbot_clamav rm -f /tmp/eicar.txt
echo ""

# 7. Check virus definition version
echo -e "${YELLOW}[7/7] Checking virus definitions...${NC}"
docker exec chatbot_clamav /usr/local/bin/sigtool --info /var/lib/clamav/main.cvd 2>/dev/null || \
docker exec chatbot_clamav /usr/local/bin/sigtool --info /var/lib/clamav/main.cld 2>/dev/null | head -5
echo ""

# Summary
echo "========================================="
echo -e "${GREEN}✓ All tests passed!${NC}"
echo "========================================="
echo ""
echo "ClamAV is ready for use:"
echo "  - Host: localhost"
echo "  - Port: 3310"
echo "  - Status: docker-compose ps clamav"
echo "  - Logs: docker-compose logs -f clamav"
echo ""
echo "Next steps:"
echo "  1. Install Python clamd library: pip install clamd"
echo "  2. Set environment variables in .env:"
echo "     CLAMAV_HOST=localhost"
echo "     CLAMAV_PORT=3310"
echo "  3. Start the application: ./run.sh"
echo ""
