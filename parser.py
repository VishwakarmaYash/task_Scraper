"""
Parser for sitemap scraper task evaluation.

Extracts structured results from pytest output and validates
the scraper's JSON output against the specification.
"""

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Pytest output parsing
# ---------------------------------------------------------------------------

def parse_pytest_output(stdout: str, stderr: str) -> dict[str, Any]:
    """
    Parse verbose pytest output into a normalised result dict.

    Returns:
        {
            "passed": [test_name, ...],
            "failed": [test_name, ...],
            "errors": [module_path, ...],
            "summary": {"total": int, "passed": int, "failed": int, "errors": int}
        }
    """
    result: dict[str, Any] = {
        "passed": [],
        "failed": [],
        "errors": [],
        "summary": {"total": 0, "passed": 0, "failed": 0, "errors": 0},
    }

    # Collect test names from verbose lines  (e.g.  "test_foo PASSED")
    for m in re.finditer(r"(\w[\w.]*)::(\w+)\s+PASSED", stdout):
        result["passed"].append(m.group(2))
    for m in re.finditer(r"(\w[\w.]*)::(\w+)\s+FAILED", stdout):
        result["failed"].append(m.group(2))

    # Collection-level errors
    for m in re.finditer(r"ERROR collecting (\S+)", stdout):
        result["errors"].append(m.group(1))

    # Summary line — e.g. "5 passed, 2 failed in 4.32s"
    summary_re = (
        r"(\d+)\s+passed"
        r"(?:,\s*(\d+)\s+failed)?"
        r"(?:,\s*(\d+)\s+error)?"
        r"(?:,\s*(\d+)\s+skipped)?"
        r"\s+in\s+[\d.]+s"
    )
    sm = re.search(summary_re, stdout)
    if sm:
        result["summary"]["passed"] = int(sm.group(1))
        result["summary"]["failed"] = int(sm.group(2) or 0)
        result["summary"]["errors"] = int(sm.group(3) or 0)
        result["summary"]["total"] = (
            result["summary"]["passed"]
            + result["summary"]["failed"]
            + result["summary"]["errors"]
        )

    # Also check the "all failed" summary format: "2 failed in 1.23s"
    if not sm:
        sm2 = re.search(r"(\d+)\s+failed\s+in\s+[\d.]+s", stdout)
        if sm2:
            result["summary"]["failed"] = int(sm2.group(1))
            result["summary"]["total"] = result["summary"]["failed"]

    return result


# ---------------------------------------------------------------------------
# Run pytest
# ---------------------------------------------------------------------------

def run_tests(test_file: Path) -> dict[str, Any]:
    """Run pytest on *test_file* and return parsed results."""
    cmd = [
        sys.executable, "-m", "pytest",
        str(test_file),
        "-v", "--tb=short", "--no-header", "-q",
    ]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=180, cwd=str(test_file.parent),
        )
        return parse_pytest_output(proc.stdout, proc.stderr)
    except subprocess.TimeoutExpired:
        return {
            "passed": [], "failed": [], "errors": [],
            "summary": {"total": 0, "passed": 0, "failed": 0, "errors": 0},
            "timeout": True,
        }
    except Exception as exc:
        return {
            "passed": [], "failed": [], "errors": [],
            "summary": {"total": 0, "passed": 0, "failed": 0, "errors": 0},
            "error": str(exc),
        }


# ---------------------------------------------------------------------------
# Test classification (for Anvil FAIL_TO_PASS / PASS_TO_PASS)
# ---------------------------------------------------------------------------

def classify_tests() -> dict[str, list[str]]:
    return {
        "FAIL_TO_PASS": [
            "test_success_case_multiple_pages",
            "test_timeout_handling",
            "test_http_error_handling",
            "test_partial_extraction_with_failures",
            "test_malformed_input_handling",
            "test_large_input_respects_max_urls",
            "test_sitemap_index_recursive",
            "test_all_failures_returns_exit_code_one",
        ],
        "PASS_TO_PASS": [
            "test_deterministic_output_order",
        ],
    }


# ---------------------------------------------------------------------------
# JSON output validator
# ---------------------------------------------------------------------------

REQUIRED_TOP_KEYS = [
    "sitemap_url", "crawl_timestamp", "total_urls_discovered",
    "successful_extractions", "failed_extractions", "results", "errors",
]

REQUIRED_RESULT_KEYS = [
    "url", "status_code", "title", "description", "h1_count", "link_count", "error",
]

VALID_ERROR_TYPES = {"timeout", "http_error", "invalid_url", "parse_error"}


def validate_output(path: Path) -> dict[str, Any]:
    """
    Validate the scraper's output JSON against the specification.

    Returns {"valid": True, "data": dict}  or  {"valid": False, "error": str}.
    """
    if not path.exists():
        return {"valid": False, "error": "output file not found"}

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {"valid": False, "error": f"invalid JSON: {exc}"}

    # Top-level keys
    missing = [k for k in REQUIRED_TOP_KEYS if k not in data]
    if missing:
        return {"valid": False, "error": f"missing top-level keys: {missing}"}

    # Count invariant
    total = data["total_urls_discovered"]
    ok = data["successful_extractions"]
    fail = data["failed_extractions"]
    if ok + fail != total:
        return {"valid": False, "error": f"successful({ok}) + failed({fail}) != total({total})"}
    if len(data["errors"]) != fail:
        return {"valid": False, "error": f"len(errors)={len(data['errors'])} != failed_extractions={fail}"}

    # Result-level keys
    for i, r in enumerate(data["results"]):
        rm = [k for k in REQUIRED_RESULT_KEYS if k not in r]
        if rm:
            return {"valid": False, "error": f"result[{i}] missing keys: {rm}"}

    # Error-type enum
    for i, e in enumerate(data["errors"]):
        et = e.get("error_type")
        if et not in VALID_ERROR_TYPES:
            return {"valid": False, "error": f"errors[{i}].error_type '{et}' not in {VALID_ERROR_TYPES}"}

    # Sorted
    urls = [r["url"] for r in data["results"]]
    if urls != sorted(urls):
        return {"valid": False, "error": "results not sorted by URL"}

    return {"valid": True, "data": data}


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    test_file = Path(__file__).parent / "task_tests.py"
    results = run_tests(test_file)
    print(json.dumps(results, indent=2))