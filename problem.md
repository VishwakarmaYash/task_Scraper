# Multi-Source Web Scraping and Parsing

## Task Description

Implement a robust sitemap crawler and content extractor that recursively traverses sitemap URLs, fetches web pages, handles various failure modes, and produces a structured JSON output.

You must create a single Python script called `sitemap_scraper.py` in the current working directory.

## Requirements

### Input

Your tool must accept a sitemap URL as a command-line argument:

```bash
python sitemap_scraper.py <sitemap_url> --output <output_file.json> [--timeout <seconds>] [--max-urls <count>]
```

| Argument | Required | Default | Description |
|----------|----------|---------|-------------|
| `sitemap_url` | Yes | — | Positional: the root sitemap URL to crawl |
| `--output` | Yes | — | Path to write the output JSON file |
| `--timeout` | No | `30` | Per-request timeout in seconds |
| `--max-urls` | No | `100` | Maximum number of page URLs to fetch |

### Core Functionality

1. **Sitemap Parsing**: Parse XML sitemaps (both regular `<urlset>` and sitemap index `<sitemapindex>` files)
   - Extract page URLs from `<loc>` tags inside `<url>` elements
   - Recursively follow sitemap references inside `<sitemap>` → `<loc>` elements in index files
   - Detect and handle cyclic sitemap references (track visited sitemap URLs; never re-fetch one)

2. **Page Fetching**: Fetch each discovered page URL
   - Use HTTP GET requests
   - Respect `--timeout` parameter (default 30 seconds per request)
   - Limit total page URLs fetched with `--max-urls` (default 100). Once the limit is reached, stop discovering new URLs — do NOT fetch more.
   - Handle redirects (follow up to 5 redirects)

3. **Content Extraction**: From each successfully fetched HTML page, extract:
   - `url`: The final URL (after redirects)
   - `title`: Text content of the first `<title>` tag (trimmed of whitespace). Empty string if missing.
   - `description`: Value of the `content` attribute of `<meta name="description">`. Empty string if missing.
   - `h1_count`: Number of `<h1>` tags on the page (integer)
   - `link_count`: Number of `<a>` tags that have an `href` attribute (integer)
   - `status_code`: HTTP response status code (integer)

4. **Error Handling**: Gracefully handle all of the following without crashing:
   - **Invalid/malformed URLs** — skip, record in errors with `error_type: "invalid_url"`
   - **Network timeouts** — skip, record in errors with `error_type: "timeout"`
   - **HTTP 4xx/5xx errors** — include in `results` with the status code but empty content fields; also record in `errors` with `error_type: "http_error"`
   - **Malformed HTML** — extract whatever is possible; use empty string for missing fields, 0 for missing counts
   - **Cyclic sitemap references** — track visited sitemaps; avoid re-processing

### Output Format

Output MUST be a JSON file with the following structure:

```json
{
  "sitemap_url": "<original sitemap url>",
  "crawl_timestamp": "<ISO 8601 timestamp>",
  "total_urls_discovered": <int>,
  "successful_extractions": <int>,
  "failed_extractions": <int>,
  "results": [
    {
      "url": "<page url>",
      "status_code": <int or null>,
      "title": "<title or empty string>",
      "description": "<description or empty string>",
      "h1_count": <int or 0>,
      "link_count": <int or 0>,
      "error": "<error message or null>"
    }
  ],
  "errors": [
    {
      "url": "<failed url>",
      "error": "<error message>",
      "error_type": "<timeout|http_error|invalid_url|parse_error>"
    }
  ]
}
```

### Strict Requirements

1. **Deterministic Output**: Running with same input must produce same `results` order (sorted by URL alphabetically).

2. **Null Handling**:
   - `error` in each result must be `null` (not absent, not empty string) for successful extractions
   - `error_type` must be one of: `timeout`, `http_error`, `invalid_url`, `parse_error`

3. **Count Consistency** (invariants that MUST hold):
   - `successful_extractions + failed_extractions == total_urls_discovered`
   - `failed_extractions == len(errors)`

4. **Timestamp Format**: ISO 8601 UTC: `YYYY-MM-DDTHH:MM:SSZ`

5. **Results array**: MUST contain entries for ALL discovered URLs — both successful and failed. Failed entries have empty content fields and a non-null `error` string.

### Edge Cases

| Scenario | Expected Behavior |
|----------|-------------------|
| Invalid URL in sitemap (e.g. `not-a-url`, empty `<loc>`) | Add to errors with `error_type: "invalid_url"`, include in results with `status_code: null` |
| Cyclic sitemaps (A→B→A) | Track visited sitemap URLs; skip already-visited ones |
| Timeout on page fetch | Record with `error_type: "timeout"` |
| HTTP 4xx/5xx on page | Include in results with status code, empty content fields, and non-null error |
| Partial failures (mix of success/fail) | Return exit code 0; include all in results; only failures in errors |
| All fetches fail | Return exit code 1 |
| `--max-urls 10` with 50 URLs in sitemap | Process only 10 URLs total |
| Malformed HTML (no `<title>`, no `<meta>`) | Use empty strings and 0 for counts |

### Exit Codes

- `0`: At least one successful extraction
- `1`: All extractions failed (zero successful)
- `2`: Invalid arguments or configuration error (e.g. missing required args)