"""
Reference solution: Multi-Source Sitemap Crawler & Content Extractor.

Usage:
    python sitemap_scraper.py <sitemap_url> --output <file.json> [--timeout N] [--max-urls N]
"""

import argparse
import json
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


# ---------------------------------------------------------------------------
# HTML content extractor (stdlib only — no bs4 dependency)
# ---------------------------------------------------------------------------

class _HTMLExtractor(HTMLParser):
    """Lightweight extractor for title, meta-description, h1 count, link count."""

    def __init__(self):
        super().__init__()
        self.title = ""
        self.description = ""
        self.h1_count = 0
        self.link_count = 0
        self._in_title = False
        self._title_parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag == "title":
            self._in_title = True
        elif tag == "meta":
            attr_dict = {k.lower(): v for k, v in attrs}
            if attr_dict.get("name", "").lower() == "description":
                self.description = (attr_dict.get("content") or "").strip()
        elif tag == "h1":
            self.h1_count += 1
        elif tag == "a":
            if any(k.lower() == "href" for k, _ in attrs):
                self.link_count += 1

    def handle_endtag(self, tag):
        if tag.lower() == "title":
            self._in_title = False
            self.title = "".join(self._title_parts).strip()

    def handle_data(self, data):
        if self._in_title:
            self._title_parts.append(data)


def _extract_content(html: str) -> dict:
    parser = _HTMLExtractor()
    try:
        parser.feed(html)
    except Exception:
        pass
    return {
        "title": parser.title,
        "description": parser.description,
        "h1_count": parser.h1_count,
        "link_count": parser.link_count,
    }


# ---------------------------------------------------------------------------
# Sitemap parsing (recursive, with cycle detection)
# ---------------------------------------------------------------------------

NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}


def _fetch_url(url: str, timeout: int) -> tuple[int, str]:
    """Fetch a URL; returns (status_code, body_text). Raises on failure."""
    req = Request(url, headers={"User-Agent": "AnvilSitemapCrawler/1.0"})
    resp = urlopen(req, timeout=timeout)  # follows redirects automatically
    return resp.status, resp.read().decode("utf-8", errors="replace")


def _is_valid_url(url: str) -> bool:
    return url.startswith("http://") or url.startswith("https://")


def _collect_page_urls(
    sitemap_url: str,
    timeout: int,
    max_urls: int,
    visited_sitemaps: set[str] | None = None,
) -> list[str]:
    """Recursively traverse sitemaps and return page URLs (up to max_urls)."""
    if visited_sitemaps is None:
        visited_sitemaps = set()

    if sitemap_url in visited_sitemaps:
        return []
    visited_sitemaps.add(sitemap_url)

    try:
        _, body = _fetch_url(sitemap_url, timeout)
    except Exception:
        return []

    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        return []

    page_urls: list[str] = []

    # Sitemap index → recurse into children
    for sitemap_el in root.findall("sm:sitemap", NS):
        loc_el = sitemap_el.find("sm:loc", NS)
        if loc_el is not None and loc_el.text:
            child_url = loc_el.text.strip()
            if len(page_urls) >= max_urls:
                break
            child_urls = _collect_page_urls(
                child_url, timeout, max_urls - len(page_urls), visited_sitemaps
            )
            page_urls.extend(child_urls)

    # Regular urlset → collect <loc> values
    for url_el in root.findall("sm:url", NS):
        if len(page_urls) >= max_urls:
            break
        loc_el = url_el.find("sm:loc", NS)
        if loc_el is not None:
            page_urls.append((loc_el.text or "").strip())

    return page_urls[:max_urls]


# ---------------------------------------------------------------------------
# Main crawl logic
# ---------------------------------------------------------------------------

def crawl(sitemap_url: str, output_path: str, timeout: int, max_urls: int) -> int:
    """
    Crawl *sitemap_url*, fetch pages, write JSON to *output_path*.
    Returns exit code (0 = at least one success, 1 = all failed, 2 = config error).
    """
    raw_urls = _collect_page_urls(sitemap_url, timeout, max_urls)

    results: list[dict] = []
    errors: list[dict] = []

    for url in raw_urls:
        # Invalid URL check
        if not _is_valid_url(url):
            results.append({
                "url": url,
                "status_code": None,
                "title": "",
                "description": "",
                "h1_count": 0,
                "link_count": 0,
                "error": f"Invalid URL: {url}",
            })
            errors.append({
                "url": url,
                "error": f"Invalid URL: {url}",
                "error_type": "invalid_url",
            })
            continue

        # Fetch the page
        try:
            status, body = _fetch_url(url, timeout)
        except HTTPError as exc:
            status = exc.code
            results.append({
                "url": url,
                "status_code": status,
                "title": "",
                "description": "",
                "h1_count": 0,
                "link_count": 0,
                "error": f"HTTP {status}",
            })
            errors.append({
                "url": url,
                "error": f"HTTP {status}",
                "error_type": "http_error",
            })
            continue
        except (TimeoutError, OSError, URLError) as exc:
            err_str = str(exc)
            if "timed out" in err_str.lower() or isinstance(exc, TimeoutError):
                error_type = "timeout"
            else:
                error_type = "parse_error"
            results.append({
                "url": url,
                "status_code": None,
                "title": "",
                "description": "",
                "h1_count": 0,
                "link_count": 0,
                "error": err_str,
            })
            errors.append({
                "url": url,
                "error": err_str,
                "error_type": error_type,
            })
            continue
        except Exception as exc:
            results.append({
                "url": url,
                "status_code": None,
                "title": "",
                "description": "",
                "h1_count": 0,
                "link_count": 0,
                "error": str(exc),
            })
            errors.append({
                "url": url,
                "error": str(exc),
                "error_type": "parse_error",
            })
            continue

        # HTTP-level errors (shouldn't normally reach here, but safety net)
        if status >= 400:
            results.append({
                "url": url,
                "status_code": status,
                "title": "",
                "description": "",
                "h1_count": 0,
                "link_count": 0,
                "error": f"HTTP {status}",
            })
            errors.append({
                "url": url,
                "error": f"HTTP {status}",
                "error_type": "http_error",
            })
            continue

        # Success — extract content
        content = _extract_content(body)
        results.append({
            "url": url,
            "status_code": status,
            "title": content["title"],
            "description": content["description"],
            "h1_count": content["h1_count"],
            "link_count": content["link_count"],
            "error": None,
        })

    # Sort deterministically
    results.sort(key=lambda r: r["url"])

    successful = sum(1 for r in results if r["error"] is None)
    failed = len(results) - successful

    output = {
        "sitemap_url": sitemap_url,
        "crawl_timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "total_urls_discovered": len(results),
        "successful_extractions": successful,
        "failed_extractions": failed,
        "results": results,
        "errors": errors,
    }

    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump(output, fh, indent=2, ensure_ascii=False)

    return 0 if successful > 0 else 1


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Sitemap crawler & content extractor")
    parser.add_argument("sitemap_url", help="Root sitemap URL to crawl")
    parser.add_argument("--output", required=True, help="Output JSON file path")
    parser.add_argument("--timeout", type=int, default=30, help="Per-request timeout (seconds)")
    parser.add_argument("--max-urls", type=int, default=100, help="Max page URLs to fetch")

    args = parser.parse_args()
    exit_code = crawl(args.sitemap_url, args.output, args.timeout, args.max_urls)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
