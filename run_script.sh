#!/bin/bash
# ==========================================================================
# Run script for Multi-Source Web Scraping and Parsing task
#
# Execution order:
#   1. Validate that the solution file (sitemap_scraper.py) exists
#   2. Quick-check the solution interface (argparse / output / json)
#   3. Install Python test dependencies (pytest)
#   4. Run the pytest suite
#   5. Invoke parser.py to generate a machine-readable JSON report
# ==========================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="${PYTHON:-python3}"

# Colours
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "=========================================="
echo " Multi-Source Web Scraping Task Execution"
echo "=========================================="

# ------------------------------------------------------------------
# 1. Check solution exists
# ------------------------------------------------------------------
SOLUTION="${SCRIPT_DIR}/sitemap_scraper.py"
if [ ! -f "$SOLUTION" ]; then
    echo -e "${RED}ERROR: sitemap_scraper.py not found${NC}"
    echo "Expected: $SOLUTION"
    exit 1
fi
echo -e "${GREEN}✓${NC} Solution file found"

# ------------------------------------------------------------------
# 2. Quick interface check (non-blocking warnings only)
# ------------------------------------------------------------------
echo ""
echo "Checking solution interface..."

if ! grep -qE 'argparse|ArgumentParser|sys\.argv|click|typer' "$SOLUTION"; then
    echo -e "${YELLOW}⚠ Solution may not parse CLI arguments${NC}"
fi
if ! grep -qiE 'json\.dump|json_encode|output' "$SOLUTION"; then
    echo -e "${YELLOW}⚠ Solution may not produce JSON output${NC}"
fi
echo -e "${GREEN}✓${NC} Interface check done"

# ------------------------------------------------------------------
# 3. Ensure pytest is available
# ------------------------------------------------------------------
echo ""
if ! "$PYTHON" -m pytest --version >/dev/null 2>&1; then
    echo "Installing pytest..."
    pip install --quiet pytest
fi
echo -e "${GREEN}✓${NC} pytest available"

# ------------------------------------------------------------------
# 4. Run the test suite
# ------------------------------------------------------------------
echo ""
echo "=========================================="
echo " Running Test Suite"
echo "=========================================="

set +e  # do not exit on test failure
TEST_OUTPUT=$("$PYTHON" -m pytest "${SCRIPT_DIR}/task_tests.py" -v --tb=short 2>&1)
TEST_EXIT=$?
set -e

echo "$TEST_OUTPUT"

# ------------------------------------------------------------------
# 5. Summary
# ------------------------------------------------------------------
echo ""
echo "=========================================="
echo " Test Results Summary"
echo "=========================================="

PASSED=$(echo "$TEST_OUTPUT" | grep -c " PASSED" || true)
FAILED=$(echo "$TEST_OUTPUT" | grep -c " FAILED" || true)
ERRORS=$(echo "$TEST_OUTPUT" | grep -c " ERROR"  || true)

echo -e "Passed:  ${GREEN}${PASSED}${NC}"
echo -e "Failed:  ${RED}${FAILED}${NC}"
echo -e "Errors:  ${RED}${ERRORS}${NC}"

echo ""
echo "Test Classification:"
echo "  FAIL_TO_PASS (new functionality):"
echo "    - test_success_case_multiple_pages"
echo "    - test_timeout_handling"
echo "    - test_http_error_handling"
echo "    - test_partial_extraction_with_failures"
echo "    - test_malformed_input_handling"
echo "    - test_large_input_respects_max_urls"
echo "    - test_sitemap_index_recursive"
echo "    - test_all_failures_returns_exit_code_one"
echo ""
echo "  PASS_TO_PASS (existing behaviour):"
echo "    - test_deterministic_output_order"

# ------------------------------------------------------------------
# 6. Generate parsed JSON report
# ------------------------------------------------------------------
echo ""
echo "=========================================="
echo " Generating Parsed Results"
echo "=========================================="

PARSER_OUT=$("$PYTHON" "${SCRIPT_DIR}/parser.py" 2>&1)
echo "$PARSER_OUT"

RESULTS_FILE="${SCRIPT_DIR}/test_results.json"
echo "$PARSER_OUT" > "$RESULTS_FILE"
echo -e "${GREEN}Results written to: ${RESULTS_FILE}${NC}"

# ------------------------------------------------------------------
# 7. Exit code
# ------------------------------------------------------------------
if [ "$TEST_EXIT" -eq 0 ]; then
    echo ""
    echo -e "${GREEN}==========================================
 ALL TESTS PASSED
==========================================${NC}"
    exit 0
else
    echo ""
    echo -e "${RED}==========================================
 SOME TESTS FAILED
==========================================${NC}"
    exit 1
fi