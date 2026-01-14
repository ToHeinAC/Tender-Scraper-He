# Tender Scraper System

Automated scraper for German-language procurement portals. Collects tender announcements, filters by keywords, stores in SQLite, and sends daily email reports via Outlook.

## Features

- **Multi-Portal Scraping**: Supports 22+ procurement portals (BGE, EWN, Vergabe NRW, etc.)
- **Keyword Filtering**: Configurable search terms with exclusion support
- **SQLite Storage**: Persistent storage with duplicate detection
- **Email Reports**: Automated Outlook notifications with new tenders
- **Progress Logging**: Real-time status updates during execution

## Quick Start

```bash
# 1. Create virtual environment
python -m venv venv
.\venv\Scripts\activate  # Windows
source venv/bin/activate # Linux/Mac

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure keywords
# Edit config/Suchbegriffe.txt (one keyword per line)

# 4. Configure email recipients
# Edit config/email_config.yaml

# 5. Run scraper
python main.py              # Full run with email
python main.py --dry-run    # Test without saving/emailing
python main.py --verbose    # Debug output
```

## Command Line Options

| Option | Description |
|--------|-------------|
| `--dry-run` | Test mode: no database writes, no emails |
| `--verbose` | Enable debug logging |
| `--skip-email` | Run scrapers but don't send email |
| `--scrapers bge,ewn` | Run specific scrapers only |
| `--config path` | Use custom config file |

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
│   ├── email_config.yaml   # Email settings
│   └── Suchbegriffe.txt    # Search keywords
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
    ├── tenders.db          # SQLite database
    └── debug.log           # Log file
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

3. Test with: `python main.py --dry-run --scrapers portal_name`

## Database

SQLite database at `data/tenders.db` with tables:
- `tenders`: All scraped tender records
- `scrape_history`: Scraper run logs
- `email_history`: Email send logs

Inspect manually:
```bash
sqlite3 data/tenders.db
SELECT * FROM tenders ORDER BY id DESC LIMIT 10;
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
