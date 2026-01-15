# Tender Scraper System

Automated scraper for German-language procurement portals. Collects tender announcements, filters by keywords, stores in SQLite, and sends daily email reports via Outlook.

## Features

- **Multi-Portal Scraping**: Supports 22+ procurement portals (BGE, EWN, Vergabe NRW, etc.)
- **Multi-Purpose Support**: Run separate scraping campaigns with different keywords and recipients
- **Keyword Filtering**: Configurable search terms with exclusion support
- **SQLite Storage**: Persistent storage with duplicate detection and per-tender email tracking
- **Email Reports**: Automated Outlook notifications with purpose-specific recipients
- **Progress Logging**: Real-time status updates during execution

## Quick Start

```bash
# 1. Create virtual environment
python -m venv venv
.\venv\Scripts\activate  # Windows
source venv/bin/activate # Linux/Mac

# 2. Install dependencies
pip install -r requirements.txt

# 3. Create a purpose (e.g., "BA" for Business Analytics)
# Create config/Suchbegriffe_BA.txt (keywords, one per line)
# Create config/EMail_BA.txt (email recipients in YAML format)

# 4. List available purposes
python main.py --list-purposes

# 5. Run scraper for a purpose
python main.py --purpose BA              # Full run with email
python main.py --purpose BA --dry-run    # Test without saving/emailing
python main.py --purpose BA --verbose    # Debug output
```

## Command Line Options

| Option | Description |
|--------|-------------|
| `--purpose NAME` | **Required.** Purpose to run (e.g., BA, NORM) |
| `--list-purposes` | List available purposes and exit |
| `--dry-run` | Test mode: no database writes, no emails |
| `--verbose` | Enable debug logging |
| `--skip-email` | Run scrapers but don't send email |
| `--scrapers bge,ewn` | Run specific scrapers only |
| `--config path` | Use custom config file |

## Multi-Purpose Support

The scraper supports multiple "purposes" - each with its own keywords, email recipients, database, and log file. Purposes are auto-discovered from `config/Suchbegriffe_*.txt` files.

### File Naming Convention

For each purpose (e.g., `BA`, `NORM`), create:

| File | Description |
|------|-------------|
| `config/Suchbegriffe_BA.txt` | Keywords (one per line) |
| `config/EMail_BA.txt` | Email recipients (YAML format) |

The system automatically creates:

| File | Description |
|------|-------------|
| `data/tenders_BA.db` | SQLite database |
| `data/debug_BA.log` | Log file |

### Example: EMail_BA.txt

```yaml
recipients:
  to:
    - user1@example.com
    - user2@example.com
  cc:
    - manager@example.com
  bcc: []
```

### Running Multiple Purposes

```bash
# Run for Business Analytics
python main.py --purpose BA

# Run for NORM (Nuclear materials)
python main.py --purpose NORM

# Each purpose has isolated data - run them independently
```

## Configuration

### Main Config (`config/config.yaml`)

```yaml
general:
  log_level: INFO
  database_path: data/tenders.db

scraping:
  timeout_per_scraper: 300
  headless: true
  delay_min: 6
  delay_max: 10

keywords:
  file: config/Suchbegriffe.txt
  case_sensitive: false
  match_fields: [titel, ausschreibungsstelle]
  exclusions: [Massenspektrometer]

scrapers:
  enabled: [bge, ewn, vergabe_nrw]
  disabled: [ted_etendering, ...]
```

### Keywords (`config/Suchbegriffe.txt`)

```
Rückbau
Dekontamination
Nuklear
...
```

### Email (`config/email_config.yaml`)

```yaml
recipients:
  to: [user@example.com]
  cc: []
subject_template: "Ausschreibungen {date}"
send_empty_report: true
```

## Project Structure

```
tender-scraper/
├── main.py                 # Entry point
├── config/
│   ├── config.yaml         # Main configuration
│   ├── email_config.yaml   # Base email settings
│   ├── Suchbegriffe_BA.txt # Keywords for purpose "BA"
│   ├── EMail_BA.txt        # Email recipients for "BA"
│   ├── Suchbegriffe_NORM.txt # Keywords for purpose "NORM"
│   └── EMail_NORM.txt      # Email recipients for "NORM"
├── scrapers/
│   ├── base.py             # BaseScraper class
│   ├── registry.py         # Auto-discovery
│   ├── bge.py              # BGE portal scraper
│   ├── ewn.py              # EWN portal scraper
│   └── vergabe_nrw.py      # Vergabe NRW scraper
├── database/
│   └── db.py               # SQLite operations
├── email_sender/
│   ├── sender.py           # Outlook integration
│   └── templates.py        # Email formatting
├── utils/
│   ├── logging_config.py   # Logging setup
│   ├── keywords.py         # Keyword matching
│   └── browser.py          # Selenium utilities
└── data/                   # Runtime data (gitignored)
    ├── tenders_BA.db       # Database for purpose "BA"
    ├── debug_BA.log        # Log file for "BA"
    ├── tenders_NORM.db     # Database for purpose "NORM"
    └── debug_NORM.log      # Log file for "NORM"
```

## Adding a New Scraper

1. Create `scrapers/portal_name.py`:

```python
from scrapers.base import BaseScraper, TenderResult
from scrapers.registry import register_scraper

@register_scraper
class PortalScraper(BaseScraper):
    PORTAL_NAME = "portal_name"
    PORTAL_URL = "https://example.com/tenders"
    REQUIRES_SELENIUM = True

    def scrape(self):
        self.driver.get(self.PORTAL_URL)
        self.accept_cookies()
        # Parse HTML and return List[TenderResult]
        return results
```

2. Add to `config/config.yaml` under `scrapers.enabled`

3. Test with: `python main.py --purpose BA --dry-run --scrapers portal_name`

## Database

Each purpose has its own SQLite database at `data/tenders_{PURPOSE}.db` with tables:
- `tenders`: All scraped tender records (includes `email_sent` tracking)
- `scrape_history`: Scraper run logs
- `email_history`: Email send logs

### Email Tracking

Each tender has `email_sent` and `email_sent_at` columns to track whether it has been included in an email report. This prevents the same tender from being sent multiple times.

Inspect manually:
```bash
sqlite3 data/tenders_BA.db
SELECT id, titel, email_sent, email_sent_at FROM tenders ORDER BY id DESC LIMIT 10;
```

## Requirements

- Python 3.9+
- Google Chrome (for Selenium)
- Microsoft Outlook (for email sending, Windows only)

## Troubleshooting

| Issue | Solution |
|-------|----------|
| ChromeDriver error | Update Chrome or delete `~/.wdm/drivers/` cache |
| Outlook COM error | Ensure Outlook is running |
| Scraper timeout | Increase `timeout_per_scraper` in config |
| No results | Check keywords in `Suchbegriffe.txt` |

## License

Internal use only.
