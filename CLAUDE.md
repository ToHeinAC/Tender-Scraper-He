# CLAUDE.md - Development Guidelines

## Project Overview

The Tender Scraper System is a modular Python application that scrapes 22+ German-language procurement portals, stores tender data in SQLite, and sends daily email notifications via Outlook.

## Quick Start

```bash
# Create virtual environment
python -m venv venv
.\venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run tests
pytest tests/ -v

# Run scraper (dry run)
python main.py --dry-run --verbose

# Run scraper (full)
python main.py
```

## Project Structure

```
tender-scraper/
├── main.py                 # Entry point / orchestrator
├── config/                 # Configuration files
│   ├── config.yaml         # Main configuration
│   ├── email_config.yaml   # Email recipients
│   └── Suchbegriffe.txt    # Search keywords
├── scrapers/               # Portal scraper modules
│   ├── base.py             # BaseScraper abstract class
│   ├── registry.py         # Scraper auto-discovery
│   └── *.py                # Individual scrapers
├── database/               # Database operations
│   ├── db.py               # Connection manager
│   └── queries.py          # SQL queries
├── email_sender/           # Email functionality
│   ├── sender.py           # Outlook integration
│   └── templates.py        # Email templates
├── utils/                  # Shared utilities
│   ├── logging_config.py   # Logging setup
│   ├── keywords.py         # Keyword matching
│   └── browser.py          # WebDriver utilities
├── data/                   # Runtime data (gitignored)
│   ├── tenders.db          # SQLite database
│   └── debug.log           # Log file
└── tests/                  # Test suite
```

## Code Style

### General Guidelines

- **Python Version**: 3.9+
- **Style Guide**: PEP 8
- **Formatter**: Black (line length 100)
- **Linter**: Flake8
- **Type Hints**: Required for all public functions

### Naming Conventions

```python
# Classes: PascalCase
class BGEScraper(BaseScraper):
    pass

# Functions/Methods: snake_case
def get_new_tenders(since: datetime) -> List[TenderResult]:
    pass

# Constants: UPPER_SNAKE_CASE
DEFAULT_TIMEOUT = 300
MAX_RETRIES = 3

# Private methods: _leading_underscore
def _parse_html(self, html: str) -> List[dict]:
    pass
```

### Import Order

```python
# 1. Standard library
import logging
from datetime import datetime
from typing import List, Optional

# 2. Third-party packages
from selenium import webdriver
from bs4 import BeautifulSoup
import pandas as pd

# 3. Local imports
from scrapers.base import BaseScraper, TenderResult
from database.db import Database
from utils.logging_config import setup_logging
```

## Scraper Development

### Creating a New Scraper

1. Create new file in `scrapers/` directory
2. Inherit from `BaseScraper`
3. Implement required methods
4. Register in config
5. Add unit tests

### Scraper Template

```python
"""
Scraper for [Portal Name]
URL: https://example.com
"""
from datetime import datetime
from typing import List
import logging

from bs4 import BeautifulSoup

from scrapers.base import BaseScraper, TenderResult
from scrapers.registry import register_scraper


@register_scraper
class ExampleScraper(BaseScraper):
    """Scraper for example.com procurement portal."""

    PORTAL_NAME = "example"
    PORTAL_URL = "https://example.com/tenders"
    REQUIRES_SELENIUM = True

    def __init__(self, config: dict, logger: logging.Logger):
        super().__init__(config, logger)

    def scrape(self) -> List[TenderResult]:
        """Execute scraping logic."""
        results = []

        try:
            self.setup_driver()
            self.driver.get(self.PORTAL_URL)
            self.accept_cookies()

            # Get page HTML
            html = self.driver.page_source
            soup = BeautifulSoup(html, "lxml")

            # Parse results
            results = self._parse_results(soup)

        except Exception as e:
            self.logger.error(f"Scraping failed: {e}")
            raise
        finally:
            self.teardown_driver()

        return results

    def _parse_results(self, soup: BeautifulSoup) -> List[TenderResult]:
        """Parse HTML and extract tender data."""
        results = []
        now = datetime.now()

        for item in soup.select("div.tender-item"):
            try:
                result = TenderResult(
                    portal=self.PORTAL_NAME,
                    suchbegriff=None,
                    suchzeitpunkt=now,
                    vergabe_id=item.select_one(".id").text.strip(),
                    link=item.select_one("a")["href"],
                    titel=item.select_one(".title").text.strip(),
                    ausschreibungsstelle=item.select_one(".org").text.strip(),
                    ausfuehrungsort=item.select_one(".location").text.strip(),
                    ausschreibungsart=item.select_one(".type").text.strip(),
                    naechste_frist=item.select_one(".deadline").text.strip(),
                    veroeffentlicht=item.select_one(".published").text.strip(),
                )
                results.append(result)
            except Exception as e:
                self.logger.warning(f"Failed to parse item: {e}")
                continue

        return results
```

### Common Scraping Patterns

#### Pagination (Click-based)

```python
def scrape(self) -> List[TenderResult]:
    results = []
    page = 1
    max_pages = 10

    while page <= max_pages:
        self.logger.debug(f"Scraping page {page}")
        results.extend(self._parse_current_page())

        # Try to click next page
        try:
            next_btn = self.driver.find_element(By.CSS_SELECTOR, ".next-page")
            if not next_btn.is_enabled():
                break
            next_btn.click()
            time.sleep(2)
            page += 1
        except NoSuchElementException:
            break

    return results
```

#### Infinite Scroll

```python
def _scroll_to_load_all(self, timeout: int = 30):
    """Scroll page to load all dynamic content."""
    last_height = self.driver.execute_script("return document.body.scrollHeight")
    start_time = time.time()

    while time.time() - start_time < timeout:
        self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(2)

        new_height = self.driver.execute_script("return document.body.scrollHeight")
        if new_height == last_height:
            break
        last_height = new_height
```

#### Cookie Consent

```python
def accept_cookies(self):
    """Handle cookie consent dialog."""
    selectors = [
        "#cookie-accept",
        ".cookie-consent-accept",
        "button[data-action='accept']",
        "//button[contains(text(), 'Akzeptieren')]",
    ]

    for selector in selectors:
        try:
            if selector.startswith("//"):
                btn = self.driver.find_element(By.XPATH, selector)
            else:
                btn = self.driver.find_element(By.CSS_SELECTOR, selector)
            btn.click()
            time.sleep(1)
            return
        except NoSuchElementException:
            continue
```

## Database Operations

### Using the Database

```python
from database.db import Database

# Context manager ensures proper cleanup
with Database("data/tenders.db") as db:
    # Insert tenders
    new_count = db.insert_tenders(results)

    # Query new tenders
    new_tenders = db.get_new_tenders_since(last_email_time)

    # Log scrape history
    db.log_scrape(portal="bge", status="success", records=15)
```

### Transaction Safety

```python
# Database operations are atomic
# Failures roll back automatically
try:
    db.insert_tenders(results)
except Exception as e:
    logger.error(f"Database error: {e}")
    # Transaction already rolled back
```

## Testing

### Test Structure

```
tests/
├── conftest.py           # Shared fixtures
├── fixtures/             # Sample HTML files
│   ├── bge_sample.html
│   └── ewn_sample.html
├── test_scrapers/        # Scraper unit tests
│   ├── test_base.py
│   ├── test_bge.py
│   └── test_ewn.py
├── test_database/        # Database tests
│   ├── test_db.py
│   └── test_queries.py
├── test_email/           # Email tests
│   └── test_sender.py
└── test_integration/     # Integration tests
    └── test_workflow.py
```

### Writing Tests

```python
# tests/test_scrapers/test_bge.py
import pytest
from pathlib import Path
from unittest.mock import Mock, patch

from scrapers.bge import BGEScraper


@pytest.fixture
def bge_html():
    """Load sample HTML fixture."""
    fixture_path = Path(__file__).parent.parent / "fixtures" / "bge_sample.html"
    return fixture_path.read_text(encoding="utf-8")


@pytest.fixture
def scraper():
    """Create scraper with mocked dependencies."""
    config = {"timeout": 300}
    logger = Mock()
    return BGEScraper(config, logger)


def test_parse_results(scraper, bge_html):
    """Test HTML parsing extracts correct data."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(bge_html, "lxml")

    results = scraper._parse_results(soup)

    assert len(results) > 0
    assert results[0].portal == "bge"
    assert results[0].titel is not None


def test_scraper_handles_empty_results(scraper):
    """Test scraper handles empty response gracefully."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup("<html></html>", "lxml")

    results = scraper._parse_results(soup)

    assert results == []
```

### Running Tests

```bash
# All tests
pytest tests/ -v

# Specific test file
pytest tests/test_scrapers/test_bge.py -v

# With coverage
pytest --cov=scrapers --cov=database --cov-report=html

# Only fast tests (skip integration)
pytest tests/ -v -m "not slow"
```

## Error Handling

### Scraper Errors

```python
# Scrapers should catch and log errors, then re-raise
try:
    results = self._parse_results(soup)
except Exception as e:
    self.logger.error(f"Parse error: {e}", exc_info=True)
    raise ScraperError(f"Failed to parse {self.PORTAL_NAME}") from e
```

### Database Errors

```python
# Database errors are logged and re-raised
# The orchestrator handles retry/skip logic
try:
    db.insert_tenders(results)
except sqlite3.Error as e:
    logger.error(f"Database error: {e}")
    raise
```

### Email Errors

```python
# Email errors don't stop the workflow
# Results are still saved to database
try:
    send_email(results)
except OutlookError as e:
    logger.error(f"Email failed: {e}")
    # Continue - data is still persisted
```

## Logging

### Log Levels

- **DEBUG**: Detailed diagnostic info (HTML snippets, SQL queries)
- **INFO**: Normal operations (scraper start/end, record counts)
- **WARNING**: Unexpected but handled (missing field, retry)
- **ERROR**: Failures (scraper crash, database error)
- **CRITICAL**: System failure (cannot start, config error)

### Logging Pattern

```python
# At module level
logger = logging.getLogger(__name__)

# In functions
def scrape(self):
    self.logger.info(f"Starting scrape of {self.PORTAL_NAME}")

    try:
        results = self._do_scrape()
        self.logger.info(f"Found {len(results)} tenders")
        return results
    except Exception as e:
        self.logger.error(f"Scrape failed: {e}", exc_info=True)
        raise
```

## Configuration

### config.yaml Structure

```yaml
general:
  log_level: INFO
  log_file: data/debug.log
  database_path: data/tenders.db

scraping:
  timeout_per_scraper: 300
  delay_min: 6
  delay_max: 10
  headless: true
  user_agent: "Mozilla/5.0..."

keywords:
  file: config/Suchbegriffe.txt
  case_sensitive: false
  match_fields:
    - titel
    - ausschreibungsstelle

scrapers:
  enabled:
    - bge
    - ewn
    - vergabe_nrw
  disabled:
    - ted_etendering
```

### Accessing Config

```python
from utils.config import load_config

config = load_config("config/config.yaml")

timeout = config["scraping"]["timeout_per_scraper"]
enabled_scrapers = config["scrapers"]["enabled"]
```

## Git Workflow

### Branch Naming

- `feature/add-new-scraper`
- `fix/bge-parsing-error`
- `docs/update-readme`

### Commit Messages

```
feat(scrapers): add support for new portal

- Implement ExampleScraper class
- Add unit tests with HTML fixtures
- Update config with new scraper entry

Closes #123
```

### Pre-commit Checks

```bash
# Run before committing
black .
flake8 .
pytest tests/ -v
```

## Common Issues

### ChromeDriver Version Mismatch

```python
# webdriver-manager handles this automatically
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service

service = Service(ChromeDriverManager().install())
driver = webdriver.Chrome(service=service)
```

### Outlook COM Errors

```python
# Ensure Outlook is running
import win32com.client

try:
    outlook = win32com.client.Dispatch("Outlook.Application")
except Exception as e:
    logger.error("Outlook not available. Start Outlook first.")
    raise
```

### Database Locked

```python
# Use WAL mode for better concurrency
conn.execute("PRAGMA journal_mode=WAL")
```

## Performance Tips

1. **Use headless browser** for faster scraping
2. **Batch database inserts** when possible
3. **Cache parsed results** during development
4. **Run scrapers in sequence** (not parallel) to avoid detection
5. **Use lxml parser** instead of html.parser for speed

## Debugging

### Enable Debug Logging

```bash
python main.py --verbose
# or
export TENDER_SCRAPER_LOG_LEVEL=DEBUG
```

### Interactive Testing

```python
# Test a single scraper interactively
from scrapers.bge import BGEScraper
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger()

scraper = BGEScraper(config={}, logger=logger)
results = scraper.scrape()
print(f"Found {len(results)} results")
```

### Inspect Database

```bash
sqlite3 data/tenders.db
.schema
SELECT * FROM tenders LIMIT 10;
SELECT * FROM scrape_history ORDER BY scrape_start DESC LIMIT 5;
```
