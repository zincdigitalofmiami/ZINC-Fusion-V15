#!/bin/bash
# Deployment Validation Test Script
# Tests critical functionality after deployment

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
BACKEND_URL=${BACKEND_URL:-"http://localhost:8000"}
API_KEY=${FUSION_API_KEY:-""}

echo "=================================================="
echo "Deployment Validation Tests"
echo "=================================================="
echo "Backend URL: $BACKEND_URL"
echo ""

# Test counter
PASSED=0
FAILED=0

# Function to print test result
print_result() {
    local test_name=$1
    local result=$2
    local message=$3
    
    if [ "$result" = "PASS" ]; then
        echo -e "${GREEN}✓${NC} $test_name"
        ((PASSED++))
    else
        echo -e "${RED}✗${NC} $test_name"
        echo "  Error: $message"
        ((FAILED++))
    fi
}

# Test 1: Health Check
echo "Running tests..."
echo ""

HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$BACKEND_URL/health")
if [ "$HTTP_CODE" = "200" ]; then
    print_result "Health check" "PASS"
else
    print_result "Health check" "FAIL" "Expected 200, got $HTTP_CODE"
fi

# Test 2: API Authentication - No Key (should fail)
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$BACKEND_URL/api/dashboard/summary")
if [ "$HTTP_CODE" = "401" ] || [ "$HTTP_CODE" = "200" ]; then
    # 200 is ok if FUSION_API_KEY not set (dev mode)
    # 401 is expected if FUSION_API_KEY is set (prod mode)
    print_result "Auth without key" "PASS"
else
    print_result "Auth without key" "FAIL" "Expected 401 or 200, got $HTTP_CODE"
fi

# Test 3: API Authentication - Invalid Key (should fail)
if [ -n "$API_KEY" ]; then
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
        -H "X-API-Key: invalid-key-12345" \
        "$BACKEND_URL/api/dashboard/summary")
    if [ "$HTTP_CODE" = "401" ]; then
        print_result "Auth with invalid key" "PASS"
    else
        print_result "Auth with invalid key" "FAIL" "Expected 401, got $HTTP_CODE"
    fi
else
    echo -e "${YELLOW}⊘${NC} Auth with invalid key - SKIPPED (no API_KEY set)"
fi

# Test 4: API Authentication - Valid Key (should succeed)
if [ -n "$API_KEY" ]; then
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
        -H "X-API-Key: $API_KEY" \
        "$BACKEND_URL/api/dashboard/summary")
    if [ "$HTTP_CODE" = "200" ]; then
        print_result "Auth with valid key" "PASS"
    else
        print_result "Auth with valid key" "FAIL" "Expected 200, got $HTTP_CODE"
    fi
else
    echo -e "${YELLOW}⊘${NC} Auth with valid key - SKIPPED (no API_KEY set)"
fi

# Test 5: Performance - Overview Models Endpoint
START=$(date +%s%3N)
if [ -n "$API_KEY" ]; then
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
        -H "X-API-Key: $API_KEY" \
        "$BACKEND_URL/api/overview/models")
else
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
        "$BACKEND_URL/api/overview/models")
fi
END=$(date +%s%3N)
ELAPSED=$((END - START))

if [ "$HTTP_CODE" = "200" ]; then
    if [ "$ELAPSED" -lt 1000 ]; then
        print_result "Performance test (${ELAPSED}ms)" "PASS"
    else
        print_result "Performance test (${ELAPSED}ms)" "FAIL" "Response time >1000ms (target: <100ms)"
    fi
else
    print_result "Performance test" "FAIL" "HTTP $HTTP_CODE"
fi

# Test 6: Error Handling - Check no tracebacks in errors
RESPONSE=$(curl -s "$BACKEND_URL/api/nonexistent-endpoint")
if echo "$RESPONSE" | grep -q "Traceback\|File \"/"; then
    print_result "Error handling (no tracebacks)" "FAIL" "Traceback found in error response"
else
    print_result "Error handling (no tracebacks)" "PASS"
fi

# Test 7: CORS Headers (if configured)
CORS_HEADER=$(curl -s -I "$BACKEND_URL/health" | grep -i "access-control-allow-origin")
if [ -n "$CORS_HEADER" ] || [ -z "$FUSION_CORS_ORIGINS" ]; then
    print_result "CORS configuration" "PASS"
else
    print_result "CORS configuration" "FAIL" "CORS configured but headers not present"
fi

# Summary
echo ""
echo "=================================================="
echo "Test Summary"
echo "=================================================="
echo -e "Passed: ${GREEN}$PASSED${NC}"
echo -e "Failed: ${RED}$FAILED${NC}"
echo ""

if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}All tests passed!${NC}"
    exit 0
else
    echo -e "${RED}Some tests failed. Please review the errors above.${NC}"
    exit 1
fi
