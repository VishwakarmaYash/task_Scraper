"""
Test suite for Multi-Source Web Scraping and Parsing task.
Tests validate OUTPUT BEHAVIOR only — not internal implementation.

Each test spins up a local mock HTTP server, runs `sitemap_scraper.py`
as a subprocess, and validates the JSON output file.
"""

import json
import os
import socket
import subprocess
import tempfile
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path


# ---------------------------------------------------------------------------
# Mock HTTP server infrastructure
# ---------------------------------------------------------------------------

class MockServerHandler(BaseHTTPRequestHandler):
    """Configurable mock HTTP server for testing."""

    # Class-level route table, overridden per test
    routes = {}  # path -> {"body": str, "status": int, "delay": float, "content_type": str}

    def log_message(self, format, *args):
        pass  # suppress console noise

    def do_GET(self):
        route = self.routes.get(self.path)

        if route is None:
            self.send_error(404, "Not Found")
            return

        delay = route.get("delay", 0)
        if delay:
            time.sleep(delay)

        status = route.get("status", 200)
        body = route.get("body", "")
        content_type = route.get("content_type", "text/html")

        if status >= 400:
            self.send_error(status)
            return

        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))


def _free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        s.listen(1)
        return s.getsockname()[1]


def _start_server(port, routes):
    """Start a mock server in a daemon thread; returns the HTTPServer."""
    MockServerHandler.routes = routes
    server = HTTPServer(("127.0.0.1", port), MockServerHandler)
    t = threading.Thread(target=server.serve_forever)
    t.daemon = True
    t.start()
    time.sleep(0.15)  # let the socket bind
    return server


def _run_scraper(extra_args, timeout=60):
    """
    Invoke sitemap_scraper.py as a subprocess.
    Returns (exit_code, parsed_json_or_None, stderr_text).
    """
    result = subprocess.run(
        ["python", "sitemap_scraper.py"] + extra_args,
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=str(Path(__file__).parent),
    )
    output_json = None
    if "--output" in extra_args:
        idx = extra_args.index("--output")
        p = Path(extra_args[idx + 1])
        if p.exists():
            output_json = json.loads(p.read_text())
    return result.returncode, output_json, result.stderr


# ---------------------------------------------------------------------------
# Sitemap XML helpers
# ---------------------------------------------------------------------------

def _urlset(port, paths):
    """Build a <urlset> sitemap with URLs for the given paths."""
    locs = "\n".join(
        f'  <url><loc>http://127.0.0.1:{port}{p}</loc></url>' for p in paths
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f'{locs}\n</urlset>'
    )


def _sitemap_index(port, sitemap_paths):
    """Build a <sitemapindex> pointing to child sitemaps."""
    entries = "\n".join(
        f'  <sitemap><loc>http://127.0.0.1:{port}{p}</loc></sitemap>'
        for p in sitemap_paths
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f'{entries}\n</sitemapindex>'
    )


def _html(title="", description="", h1s=0, links=0):
    """Generate a simple HTML page with controllable elements."""
    head_parts = []
    if title:
        head_parts.append(f"<title>{title}</title>")
    if description:
        head_parts.append(f'<meta name="description" content="{description}">')
    body = ""
    for i in range(h1s):
        body += f"<h1>Heading {i}</h1>"
    for i in range(links):
        body += f'<a href="/link{i}">Link {i}</a>'
    return f"<html><head>{''.join(head_parts)}</head><body>{body}</body></html>"


# ===========================================================================
# TEST CASES
# ===========================================================================

class TestSitemapScraper:
    """All tests invoke the scraper as a subprocess and check JSON output."""

    # -----------------------------------------------------------------------
    # 1. SUCCESS CASE — FAIL_TO_PASS
    # -----------------------------------------------------------------------
    def test_success_case_multiple_pages(self):
        """
        Valid sitemap → 3 healthy pages.
        Validates full output structure, content extraction, sort order,
        and count invariants.
        """
        port = _free_port()
        routes = {
            "/sitemap.xml": {
                "body": _urlset(port, ["/page1", "/page2", "/page3"]),
                "content_type": "application/xml",
            },
            "/page1": {"body": _html("First Page", "Desc one", h1s=1, links=1)},
            "/page2": {"body": _html("Second Page", "Desc two", h1s=2, links=3)},
            "/page3": {"body": _html("Third Page", "", h1s=0, links=0)},
        }
        server = _start_server(port, routes)
        try:
            with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
                out = f.name
            code, data, err = _run_scraper([
                f"http://127.0.0.1:{port}/sitemap.xml", "--output", out
            ])

            assert code == 0, f"exit {code}: {err}"
            assert data is not None

            # Top-level fields present
            for key in ("sitemap_url", "crawl_timestamp", "total_urls_discovered",
                        "successful_extractions", "failed_extractions", "results", "errors"):
                assert key in data, f"missing key: {key}"

            # Counts
            assert data["total_urls_discovered"] == 3
            assert data["successful_extractions"] == 3
            assert data["failed_extractions"] == 0
            assert len(data["errors"]) == 0

            # Sorted by URL
            urls = [r["url"] for r in data["results"]]
            assert urls == sorted(urls), "results must be sorted by URL"

            # Page-1 content
            p1 = next(r for r in data["results"] if "/page1" in r["url"])
            assert p1["status_code"] == 200
            assert p1["title"] == "First Page"
            assert p1["description"] == "Desc one"
            assert p1["h1_count"] == 1
            assert p1["link_count"] == 1
            assert p1["error"] is None

            # Page-2 multi-count
            p2 = next(r for r in data["results"] if "/page2" in r["url"])
            assert p2["h1_count"] == 2
            assert p2["link_count"] == 3

            # Page-3 missing description → empty string
            p3 = next(r for r in data["results"] if "/page3" in r["url"])
            assert p3["h1_count"] == 0
            assert p3["description"] == ""
        finally:
            server.shutdown()
            if os.path.exists(out):
                os.unlink(out)

    # -----------------------------------------------------------------------
    # 2. TIMEOUT CASE — FAIL_TO_PASS
    # -----------------------------------------------------------------------
    def test_timeout_handling(self):
        """
        One fast page, one slow page (exceeds --timeout).
        Verifies partial success and correct error_type.
        """
        port = _free_port()
        routes = {
            "/sitemap.xml": {
                "body": _urlset(port, ["/fast", "/slow"]),
                "content_type": "application/xml",
            },
            "/fast": {"body": _html("Fast Page")},
            "/slow": {"body": _html("Slow Page"), "delay": 12},
        }
        server = _start_server(port, routes)
        try:
            with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
                out = f.name
            code, data, err = _run_scraper([
                f"http://127.0.0.1:{port}/sitemap.xml",
                "--output", out, "--timeout", "2",
            ], timeout=30)

            assert code == 0, f"partial success expected, got exit {code}: {err}"
            assert data["total_urls_discovered"] == 2
            assert data["successful_extractions"] == 1
            assert data["failed_extractions"] == 1

            assert len(data["errors"]) == 1
            timeout_err = data["errors"][0]
            assert "slow" in timeout_err["url"].lower()
            assert timeout_err["error_type"] == "timeout"

            fast = next(r for r in data["results"] if "/fast" in r["url"])
            assert fast["title"] == "Fast Page"
            assert fast["error"] is None
        finally:
            server.shutdown()
            if os.path.exists(out):
                os.unlink(out)

    # -----------------------------------------------------------------------
    # 3. HTTP ERROR CASE — FAIL_TO_PASS
    # -----------------------------------------------------------------------
    def test_http_error_handling(self):
        """
        One good page, one 404, one 500.
        HTTP errors must appear in both results (with status) AND errors array.
        """
        port = _free_port()
        routes = {
            "/sitemap.xml": {
                "body": _urlset(port, ["/good", "/missing", "/broken"]),
                "content_type": "application/xml",
            },
            "/good":    {"body": _html("Good Page", "ok")},
            "/missing": {"status": 404},
            "/broken":  {"status": 500},
        }
        server = _start_server(port, routes)
        try:
            with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
                out = f.name
            code, data, err = _run_scraper([
                f"http://127.0.0.1:{port}/sitemap.xml", "--output", out
            ])

            assert code == 0
            assert data["total_urls_discovered"] == 3
            assert data["successful_extractions"] == 1
            assert data["failed_extractions"] == 2

            assert len(data["errors"]) == 2
            err_types = {e["error_type"] for e in data["errors"]}
            assert "http_error" in err_types

            m = next(r for r in data["results"] if "/missing" in r["url"])
            assert m["status_code"] == 404
            assert m["title"] == ""
            assert m["error"] is not None

            b = next(r for r in data["results"] if "/broken" in r["url"])
            assert b["status_code"] == 500
        finally:
            server.shutdown()
            if os.path.exists(out):
                os.unlink(out)

    # -----------------------------------------------------------------------
    # 4. PARTIAL EXTRACTION — FAIL_TO_PASS
    # -----------------------------------------------------------------------
    def test_partial_extraction_with_failures(self):
        """
        5 URLs: 3 succeed, 2 fail (404 + 500).
        Tests count invariant and that all URLs appear in results.
        """
        port = _free_port()
        routes = {
            "/sitemap.xml": {
                "body": _urlset(port, ["/a", "/b", "/c", "/err4", "/err5"]),
                "content_type": "application/xml",
            },
            "/a":    {"body": _html("A", "da", h1s=1, links=0)},
            "/b":    {"body": _html("B", "db", h1s=0, links=2)},
            "/c":    {"body": _html("C", "dc", h1s=1, links=1)},
            "/err4": {"status": 404},
            "/err5": {"status": 500},
        }
        server = _start_server(port, routes)
        try:
            with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
                out = f.name
            code, data, err = _run_scraper([
                f"http://127.0.0.1:{port}/sitemap.xml", "--output", out
            ])

            assert code == 0
            assert data["total_urls_discovered"] == 5
            assert data["successful_extractions"] == 3
            assert data["failed_extractions"] == 2
            assert (data["successful_extractions"] + data["failed_extractions"]
                    == data["total_urls_discovered"])
            assert len(data["errors"]) == data["failed_extractions"]

            # All 5 must be in results
            assert len(data["results"]) == 5
            urls = [r["url"] for r in data["results"]]
            assert urls == sorted(urls)

            ok = [r for r in data["results"] if r["error"] is None]
            assert len(ok) == 3
            for r in ok:
                assert r["status_code"] == 200
                assert r["title"] != ""

            fail = [r for r in data["results"] if r["error"] is not None]
            assert len(fail) == 2
            for r in fail:
                assert r["title"] == ""
        finally:
            server.shutdown()
            if os.path.exists(out):
                os.unlink(out)

    # -----------------------------------------------------------------------
    # 5. MALFORMED INPUT — FAIL_TO_PASS
    # -----------------------------------------------------------------------
    def test_malformed_input_handling(self):
        """
        Sitemap contains valid URLs, an invalid URL, and an empty <loc>.
        Invalid URLs must be recorded with error_type 'invalid_url'.
        """
        port = _free_port()

        raw_sitemap = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            f'  <url><loc>http://127.0.0.1:{port}/ok1</loc></url>\n'
            '  <url><loc>not-a-valid-url</loc></url>\n'
            f'  <url><loc>http://127.0.0.1:{port}/ok2</loc></url>\n'
            '  <url><loc></loc></url>\n'
            f'  <url><loc>http://127.0.0.1:{port}/ok3</loc></url>\n'
            '</urlset>'
        )

        routes = {
            "/sitemap.xml": {"body": raw_sitemap, "content_type": "application/xml"},
            "/ok1": {"body": _html("OK1")},
            "/ok2": {"body": _html("OK2")},
            "/ok3": {"body": _html("OK3")},
        }
        server = _start_server(port, routes)
        try:
            with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
                out = f.name
            code, data, err = _run_scraper([
                f"http://127.0.0.1:{port}/sitemap.xml", "--output", out
            ])

            assert code == 0
            assert data["total_urls_discovered"] == 5

            invalid_errs = [e for e in data["errors"] if e["error_type"] == "invalid_url"]
            assert len(invalid_errs) >= 1, "must record at least 1 invalid_url error"

            ok_results = [r for r in data["results"] if r["error"] is None]
            assert len(ok_results) >= 2, "valid pages should still succeed"
        finally:
            server.shutdown()
            if os.path.exists(out):
                os.unlink(out)

    # -----------------------------------------------------------------------
    # 6. LARGE INPUT / MAX-URLS — FAIL_TO_PASS
    # -----------------------------------------------------------------------
    def test_large_input_respects_max_urls(self):
        """
        Sitemap with 50 URLs, --max-urls 10.
        Only 10 should be processed; others silently dropped.
        """
        port = _free_port()
        paths = [f"/p{i}" for i in range(50)]
        page_routes = {
            p: {"body": _html(f"Page{p}")} for p in paths
        }
        page_routes["/sitemap.xml"] = {
            "body": _urlset(port, paths),
            "content_type": "application/xml",
        }
        server = _start_server(port, page_routes)
        try:
            with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
                out = f.name
            code, data, err = _run_scraper([
                f"http://127.0.0.1:{port}/sitemap.xml",
                "--output", out, "--max-urls", "10",
            ], timeout=120)

            assert code == 0, f"exit {code}: {err}"
            assert data["total_urls_discovered"] == 10
            assert len(data["results"]) == 10
            assert data["successful_extractions"] == 10
            assert data["failed_extractions"] == 0
        finally:
            server.shutdown()
            if os.path.exists(out):
                os.unlink(out)

    # -----------------------------------------------------------------------
    # 7. SITEMAP INDEX RECURSIVE — FAIL_TO_PASS
    # -----------------------------------------------------------------------
    def test_sitemap_index_recursive(self):
        """
        Root is a <sitemapindex> pointing to two child sitemaps.
        All page URLs from children must appear in the output.
        """
        port = _free_port()

        child1 = _urlset(port, ["/alpha", "/beta"])
        child2 = _urlset(port, ["/gamma"])
        index = _sitemap_index(port, ["/child1.xml", "/child2.xml"])

        routes = {
            "/sitemap.xml": {"body": index, "content_type": "application/xml"},
            "/child1.xml":  {"body": child1, "content_type": "application/xml"},
            "/child2.xml":  {"body": child2, "content_type": "application/xml"},
            "/alpha": {"body": _html("Alpha")},
            "/beta":  {"body": _html("Beta")},
            "/gamma": {"body": _html("Gamma")},
        }
        server = _start_server(port, routes)
        try:
            with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
                out = f.name
            code, data, err = _run_scraper([
                f"http://127.0.0.1:{port}/sitemap.xml", "--output", out
            ])

            assert code == 0, f"exit {code}: {err}"
            assert data["total_urls_discovered"] == 3
            assert data["successful_extractions"] == 3

            result_urls = [r["url"] for r in data["results"]]
            assert any("/alpha" in u for u in result_urls)
            assert any("/beta" in u for u in result_urls)
            assert any("/gamma" in u for u in result_urls)
        finally:
            server.shutdown()
            if os.path.exists(out):
                os.unlink(out)

    # -----------------------------------------------------------------------
    # 8. ALL FAILURES → EXIT 1 — FAIL_TO_PASS
    # -----------------------------------------------------------------------
    def test_all_failures_returns_exit_code_one(self):
        """
        Every page returns an HTTP error → exit code must be 1.
        """
        port = _free_port()
        routes = {
            "/sitemap.xml": {
                "body": _urlset(port, ["/fail1", "/fail2"]),
                "content_type": "application/xml",
            },
            "/fail1": {"status": 500},
            "/fail2": {"status": 404},
        }
        server = _start_server(port, routes)
        try:
            with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
                out = f.name
            code, data, err = _run_scraper([
                f"http://127.0.0.1:{port}/sitemap.xml", "--output", out
            ])

            assert code == 1, f"expected exit 1, got {code}"
            assert data["successful_extractions"] == 0
            assert data["failed_extractions"] == 2
            assert len(data["errors"]) == 2
        finally:
            server.shutdown()
            if os.path.exists(out):
                os.unlink(out)

    # -----------------------------------------------------------------------
    # 9. DETERMINISTIC ORDER — PASS_TO_PASS
    # -----------------------------------------------------------------------
    def test_deterministic_output_order(self):
        """
        Two runs with the same input must produce identical URL ordering.
        The ordering must be alphabetical by URL.
        """
        port = _free_port()
        routes = {
            "/sitemap.xml": {
                "body": _urlset(port, ["/zebra", "/alpha", "/mango"]),
                "content_type": "application/xml",
            },
            "/zebra": {"body": _html("Z")},
            "/alpha": {"body": _html("A")},
            "/mango": {"body": _html("M")},
        }
        server = _start_server(port, routes)
        runs = []
        try:
            for _ in range(2):
                with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
                    out = f.name
                code, data, _ = _run_scraper([
                    f"http://127.0.0.1:{port}/sitemap.xml", "--output", out
                ])
                assert code == 0
                runs.append([r["url"] for r in data["results"]])
                os.unlink(out)
            assert runs[0] == runs[1], "output must be deterministic across runs"
            assert runs[0] == sorted(runs[0]), "results must be sorted alphabetically"
        finally:
            server.shutdown()


# ---------------------------------------------------------------------------
# Anvil test classification
# ---------------------------------------------------------------------------
FAIL_TO_PASS = [
    "test_success_case_multiple_pages",
    "test_timeout_handling",
    "test_http_error_handling",
    "test_partial_extraction_with_failures",
    "test_malformed_input_handling",
    "test_large_input_respects_max_urls",
    "test_sitemap_index_recursive",
    "test_all_failures_returns_exit_code_one",
]

PASS_TO_PASS = [
    "test_deterministic_output_order",
]