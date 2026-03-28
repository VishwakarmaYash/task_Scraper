# Multi-Source Sitemap Scraper and Content Extractor

A robust Python-based sitemap crawler and content extraction tool. This project is designed as a high-fidelity evaluation task for **Project Anvil**, specifically testing an AI agent's ability to handle complex web scraping, error states, and strict output requirements.

## 🚀 Overview

The **Sitemap Scraper** recursively traverses XML sitemaps (including sitemap indexes), fetches discovered page URLs, and extracts structured metadata into a deterministic JSON format. It is built using only the Python standard library for maximum portability and compatibility.

## ✨ Key Features

- **Recursive Sitemap Traversal**: Support for standard `<urlset>` and `<sitemapindex>` formats.
- **Cycle Detection**: Prevents infinite loops caused by self-referencing sitemaps.
- **Content Extraction**: 
  - Page Title
  - Meta Description
  - `<h1>` element count
  - Link count (from `<a>` tags with `href`)
- **Robust Error Handling**: Handles network timeouts, HTTP 4xx/5xx status codes, and invalid URLs without crashing.
- **Deterministic Output**: Results are sorted alphabetically by URL to ensure reproducible evaluations.
- **ISO 8601 Compliance**: Reliable UTC timestamps for crawl logging.

## 🛠️ Usage

### Commands
Initialize the crawler with a sitemap URL:
```bash
python sitemap_scraper.py <sitemap_url> --output <output_file.json> [--timeout <seconds>] [--max-urls <count>]
```

| Argument | Required | Default | Description |
|----------|----------|---------|-------------|
| `sitemap_url` | Yes | — | The root sitemap URL to crawl (positional) |
| `--output` | Yes | — | Path to write the final JSON results |
| `--timeout` | No | `30` | Per-request timeout in seconds |
| `--max-urls` | No | `100` | Maximum limit for total pages to fetch |

## 📐 Project Anvil Evaluation

This repository is configured as a standalone **Anvil Task Instance**. It includes a full test harness to verify correct implementation.

### Evaluation Workflow
1. **Tests**: Use `pytest` to run the comprehensive evaluation suite.
   ```bash
   pytest task_tests.py
   ```
2. **Parser**: Use the provided `parser.py` to validate your output against the script requirements.
   ```bash
   python parser.py
   ```

### Performance Metrics
The system tracks **Oracle passes** via the `FAIL_TO_PASS` list in `instance_info.txt`. The current reference solution (`sitemap_scraper.py`) passes all 9 tests (8 Oracle, 1 Regression).

## 📂 File Structure

- `sitemap_scraper.py`: The core crawler implementation (Reference Solution).
- `problem.md`: Detailed specification and requirements.
- `task_tests.py`: Evaluation suite containing 9 test cases.
- `instance_info.txt`: Metadata for the Anvil benchmark harness.
- `parser.py`: Utility for result verification and validation.
- `tasks.csv`: Registry entry for the task database.
- `Dockerfile` & `run_script.sh`: Environment setup and execution scripts.