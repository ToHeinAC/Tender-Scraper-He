# Product Requirements Document (PRD)
# Tender Scraper System

**Version**: 2.0
**Date**: 2026-01-14
**Status**: Draft

---

## 1. Executive Summary

The **Tender Scraper System** is an automated web scraping solution designed to monitor 25 German-language procurement portals (including Austrian, Swiss, and aggregator platforms) and identify relevant business opportunities based on configurable keyword searches. The system aggregates tender data, stores it persistently in a SQLite database, identifies new entries, and automatically sends daily email notifications via Microsoft Outlook.

The existing solution uses Jupyter notebooks (`.ipynb`) with Excel-based storage, presenting significant maintainability, reliability, and observability challenges. This refactored solution migrates to modular Python (`.py`) files with proper database storage, comprehensive logging, robust error handling, and extensive test coverage.

**MVP Goal**: Deliver a production-ready, modular Python application that reliably scrapes 25 procurement portals daily, persists data in SQLite, identifies new tenders, and sends formatted email notifications—all triggered via a single Windows Task Scheduler command.

---

## 2. Mission

### Mission Statement

> Empower business development teams to discover relevant procurement opportunities automatically by monitoring German-language tender portals, filtering by customizable keywords, and delivering timely email notifications—without manual intervention.

### Core Principles

1. **Reliability First**: The system must run daily without failures; individual scraper errors must not affect overall operation
2. **Observability**: Every operation must be logged with sufficient detail for debugging and monitoring
3. **Modularity**: Each scraper operates independently; adding new portals requires no core system changes
4. **Simplicity**: Single command-line execution; configuration via external files
5. **Data Integrity**: Persistent database storage with proper deduplication and historical tracking

---

## 3. Target Users

### Primary Persona: Business Development Manager

- **Role**: Identifies and pursues public tender opportunities
- **Technical Comfort**: Basic computer literacy; uses email daily; no programming knowledge
- **Needs**:
  - Receive daily digest of relevant new tenders
  - Trust that all major portals are being monitored
  - Understand which portals succeeded/failed
- **Pain Points**:
  - Missing tender deadlines due to manual monitoring gaps
  - Information overload from irrelevant tenders
  - No visibility into system health

### Secondary Persona: System Administrator

- **Role**: Maintains and monitors automated systems
- **Technical Comfort**: Proficient with Windows Server, Task Scheduler, log analysis
- **Needs**:
  - Schedule and monitor daily execution
  - Diagnose failures quickly via logs
  - Configure system without code changes
- **Pain Points**:
  - Current notebook-based system is difficult to troubleshoot
  - No centralized logging
  - Cannot easily restart failed jobs

### Tertiary Persona: Developer

- **Role**: Maintains and extends the scraping system
- **Technical Comfort**: Python development, web scraping, database management
- **Needs**:
  - Add new portal scrapers easily
  - Run comprehensive tests before deployment
  - Understand existing codebase quickly
- **Pain Points**:
  - Jupyter notebooks are hard to test and version control
  - No consistent patterns across scrapers
  - Missing documentation

---

## 4. MVP Scope

### Core Functionality

✅ Scrape 25 procurement portals daily (German, Austrian, Swiss, aggregators)
✅ Filter results by configurable keywords from `Suchbegriffe.txt`
✅ Store all tender data in persistent SQLite database (`tenders.db`)
✅ Detect and deduplicate entries using composite unique keys
✅ Identify new tenders since last successful email
✅ Generate formatted email with new tender results
✅ Send email via Windows Outlook COM interface
✅ Single command-line entry point (`python main.py`)
✅ Comprehensive debug logging to `debug.log`
✅ Continue execution despite individual scraper failures

### Technical

✅ Modular Python architecture (separate `.py` files per scraper)
✅ Base scraper class with common interface
✅ Scraper registry for automatic discovery
✅ SQLite database with proper schema and indexes
✅ YAML-based configuration management
✅ Log rotation (10MB max, 5 files retained)
✅ Configurable timeouts per scraper (default: 5 minutes)
✅ Random delays between scrapers (6-10 seconds)

### Testing

✅ Unit tests for each scraper's HTML parsing logic
✅ Unit tests for database operations
✅ Unit tests for email formatting
✅ Integration tests for scraper-to-database flow
✅ Integration tests for database-to-email flow
✅ End-to-end workflow tests
✅ Error recovery tests
✅ Test coverage target: >80%

### Documentation

✅ `CLAUDE.md` - Development guidelines and conventions
✅ `README.md` - User documentation and quick start
✅ `IMPLEMENTATION.md` - Technical implementation details
✅ `PRD.md` - This product requirements document

### Deployment

✅ Windows Task Scheduler integration
✅ Virtual environment setup
✅ Installation script/instructions
✅ Batch file for scheduled execution

---

### Out of Scope (Future Phases)

❌ Web-based user interface / dashboard
❌ Real-time notifications (push/SMS/Slack)
❌ Multi-user access control / authentication
❌ Cloud deployment (AWS/Azure/GCP)
❌ Mobile application
❌ REST API endpoints
❌ Historical data migration from Excel files
❌ New portal integrations beyond current 25
❌ Multi-language support beyond German/English
❌ Proxy rotation / advanced anti-detection

---

## 5. User Stories

### System Administrator Stories

**US-001**: As a sysadmin, I want to schedule the scraper via Windows Task Scheduler, so that it runs automatically every day without manual intervention.

> *Example*: Configure Task Scheduler to run `python main.py` at 06:00 daily. The system executes all scrapers, saves results, and sends email by 08:00.

**US-002**: As a sysadmin, I want to view detailed logs with timestamps, so that I can quickly diagnose failures and monitor system health.

> *Example*: Check `debug.log` and see entries like `[2026-01-14 06:15:23] [ERROR] [bge] Scraper failed: Connection timeout after 300s`

**US-003**: As a sysadmin, I want the system to continue running despite individual scraper failures, so that partial results are still delivered.

> *Example*: If `bge.de` fails, the remaining 24 scrapers still execute and email is sent with note "1 portal failed: bge"

**US-004**: As a sysadmin, I want to configure keywords and recipients without changing code, so that I can adapt to business needs quickly.

> *Example*: Edit `config/Suchbegriffe.txt` to add "Strahlenschutz" keyword; next execution uses updated list

### Business User Stories

**US-005**: As a business user, I want to receive a daily email with new tenders matching my keywords, so that I can identify opportunities without manual portal checking.

> *Example*: Receive email at 08:00 titled "Ausschreibungen 14.01.2026" containing 5 new matching tenders with titles, organizations, links, and deadlines

**US-006**: As a business user, I want tenders filtered by relevant keywords, so that I only see opportunities matching our business focus.

> *Example*: Only see tenders containing "business analytics", "KI", "Datenanalyse" in title or organization name

**US-007**: As a business user, I want to know which portals were checked and their status, so that I have confidence in complete coverage.

> *Example*: Email footer shows "22 Portale durchsucht: 21 erfolgreich, 1 Fehler (bge.de)"

### Developer Stories

**US-008**: As a developer, I want to add new scrapers by creating a single Python file, so that I can expand portal coverage without modifying core system.

> *Example*: Create `scrapers/new_portal.py` extending `BaseScraper`, add to config, done—no changes to `main.py` needed

**US-009**: As a developer, I want comprehensive tests with mocked dependencies, so that I can refactor with confidence and validate changes quickly.

> *Example*: Run `pytest tests/` and see 150+ tests pass with 85% coverage in under 60 seconds

**US-010**: As a developer, I want clear documentation explaining architecture and conventions, so that I can understand and contribute to the codebase quickly.

> *Example*: Read `CLAUDE.md` to understand coding standards, then `IMPLEMENTATION.md` for technical details

---

## 6. Core Architecture & Patterns

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    TENDER SCRAPER SYSTEM                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                 main.py (Orchestrator)                   │   │
│  │  • Load configuration          • Execute scrapers        │   │
│  │  • Initialize logging          • Handle errors           │   │
│  │  • Send email notification     • Log summary             │   │
│  └────────────────────────┬────────────────────────────────┘   │
│                           │                                     │
│           ┌───────────────┼───────────────┐                    │
│           ▼               ▼               ▼                     │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐             │
│  │  scrapers/  │  │  database/  │  │email_sender/│             │
│  │             │  │             │  │             │             │
│  │ • base.py   │  │ • db.py     │  │ • sender.py │             │
│  │ • bge.py    │  │ • queries.py│  │ • template. │             │
│  │ • ewn.py    │  │             │  │   py        │             │
│  │ • (23 more) │  │             │  │             │             │
│  └─────────────┘  └─────────────┘  └─────────────┘             │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                      config/                              │  │
│  │  • config.yaml  • Suchbegriffe_{PURPOSE}.txt             │  │
│  │  • email_config.yaml  • EMail_{PURPOSE}.txt              │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                       data/                               │  │
│  │  • tenders_{PURPOSE}.db (SQLite)  • debug_{PURPOSE}.log  │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ Windows Task Scheduler
                              ▼
                    python main.py (daily @ 06:00)
```

### Directory Structure

```
tender-scraper/
├── main.py                      # Entry point / orchestrator
├── requirements.txt             # Python dependencies
├── CLAUDE.md                    # Development guidelines
├── README.md                    # User documentation
├── IMPLEMENTATION.md            # Technical documentation
├── PRD.md                       # This document
│
├── config/
│   ├── config.yaml              # Main configuration
│   ├── Suchbegriffe_{PURPOSE}.txt  # Search keywords per purpose
│   ├── EMail_{PURPOSE}.txt      # Email recipients per purpose
│   └── email_config.yaml        # Base email settings
│
├── scrapers/
│   ├── __init__.py
│   ├── base.py                  # BaseScraper abstract class
│   ├── registry.py              # Automatic scraper discovery
│   ├── utils.py                 # Shared utilities (browser, parsing)
│   ├── vergabe_nrw.py           # evergabe.nrw.de
│   ├── deutsche_evergabe.py     # deutsche-evergabe.de
│   ├── bge.py                   # bge.de
│   ├── ewn.py                   # ewn-gmbh.de
│   └── ... (18 more scrapers)
│
├── database/
│   ├── __init__.py
│   ├── db.py                    # Database connection manager
│   ├── queries.py               # Common SQL queries
│   └── schema.sql               # Database schema
│
├── email_sender/
│   ├── __init__.py
│   ├── sender.py                # Outlook COM integration
│   └── templates.py             # Email templates
│
├── utils/
│   ├── __init__.py
│   ├── logging_config.py        # Logging setup
│   ├── keywords.py              # Keyword loading/matching
│   └── browser.py               # WebDriver utilities
│
├── data/                        # Created at runtime
│   ├── tenders_{PURPOSE}.db     # SQLite database per purpose
│   └── debug_{PURPOSE}.log      # Log file per purpose
│
└── tests/
    ├── conftest.py              # Pytest fixtures
    ├── fixtures/                # Sample HTML files
    ├── test_scrapers/           # Scraper unit tests
    ├── test_database/           # Database unit tests
    ├── test_email/              # Email unit tests
    └── test_integration/        # Integration tests
```

### Key Design Patterns

1. **Template Method Pattern** (Scrapers)
   - `BaseScraper` defines the skeleton: setup → scrape → teardown
   - Subclasses implement portal-specific `_parse_results()` method

2. **Registry Pattern** (Scraper Discovery)
   - Scrapers auto-register via decorators
   - Main orchestrator discovers all enabled scrapers from config

3. **Repository Pattern** (Database)
   - `TenderRepository` encapsulates all database operations
   - Clean separation between business logic and persistence

4. **Strategy Pattern** (Email Templates)
   - Different templates for: results found, no results, errors

5. **Dependency Injection** (Testing)
   - All external dependencies (browser, database, email) injectable
   - Enables mocking for unit tests

### Technology-Specific Patterns

**Selenium WebDriver**:
- Context manager for automatic cleanup
- Headless mode by default
- webdriver-manager for automatic driver updates
- Configurable implicit/explicit waits

**SQLite**:
- Connection pooling via context manager
- WAL mode for concurrent reads
- Parameterized queries (no SQL injection)
- UPSERT via INSERT OR IGNORE

**Outlook COM**:
- Late binding via win32com.client.Dispatch
- Graceful handling if Outlook not running
- Configurable recipients via YAML

---

## 7. Tools/Features

### Feature 1: Portal Scraper Engine

**Purpose**: Extract tender data from 25 procurement websites

**Operations**:
- Initialize browser session (Selenium WebDriver)
- Navigate to portal search page
- Handle cookie consent dialogs
- Execute search (pagination, scrolling, form submission)
- Parse HTML response (BeautifulSoup)
- Extract structured tender data
- Return list of `TenderResult` objects

**Key Features**:
- Each scraper is a standalone Python module
- Common interface via `BaseScraper` class
- Portal-specific implementations handle unique HTML structures
- Automatic retry on transient failures
- Configurable timeout (default: 5 minutes)

**Supported Portals** (25 active):

| Category | Portals |
|----------|---------|
| German Government | evergabe.nrw.de, deutsche-evergabe.de, dtvp.de, e-vergabe-online.de, service.bund.de, evergabe.de, vergabe-rlp.de |
| Baden-Württemberg | vergabe.vmpcenter.de, vergabe-bw.de |
| Austrian | e-beschaffung.at, auftrag.at, ausschreibungen.usp.gv.at |
| Swiss | simap.ch |
| EU | ted.europa.eu |
| Construction | bauportal-deutschland.de, ibau.de |
| Corporate/Energy | bge.de, ewn-gmbh.de, rwe.com |
| Research/Nuclear | fraunhofer.de, jen.fz-juelich.de, kte.kit.edu |
| Trade | gtai.de |
| Aggregator | germanytenders.com |

---

### Feature 2: Database Storage

**Purpose**: Persist tender data with deduplication and history tracking

**Operations**:
- Create/initialize database schema
- Insert new tender records (upsert logic)
- Query tenders by date range, portal, keywords
- Track scrape history (success/failure per portal)
- Track email history (sent timestamps)
- Identify "new" tenders since last email

**Key Features**:
- SQLite database (no external dependencies)
- Composite unique constraint prevents duplicates
- Indexed columns for fast queries
- Automatic timestamps (created_at, updated_at)
- Schema versioning for migrations

**Database Schema**:

```sql
-- Core tender data
CREATE TABLE tenders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    portal TEXT NOT NULL,
    suchbegriff TEXT,
    suchzeitpunkt DATETIME NOT NULL,
    vergabe_id TEXT,
    link TEXT,
    titel TEXT NOT NULL,
    ausschreibungsstelle TEXT,
    ausfuehrungsort TEXT,
    ausschreibungsart TEXT,
    naechste_frist TEXT,
    veroeffentlicht TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(portal, vergabe_id, link, titel)
);

-- Scrape execution history
CREATE TABLE scrape_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    portal TEXT NOT NULL,
    scrape_start DATETIME NOT NULL,
    scrape_end DATETIME,
    status TEXT NOT NULL,  -- 'success', 'failure', 'partial'
    records_found INTEGER DEFAULT 0,
    records_new INTEGER DEFAULT 0,
    error_message TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Email send history
CREATE TABLE email_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sent_at DATETIME NOT NULL,
    recipients TEXT NOT NULL,
    subject TEXT NOT NULL,
    new_tenders_count INTEGER DEFAULT 0,
    status TEXT NOT NULL,  -- 'success', 'failure'
    error_message TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

---

### Feature 3: Keyword Filtering

**Purpose**: Filter tenders to show only relevant opportunities

**Operations**:
- Load keywords from `Suchbegriffe.txt`
- Generate case variants (lowercase, Capitalized)
- Match keywords against tender title and organization
- Support exclusion keywords (e.g., "Massenspektrometer")
- Log which keyword matched each tender

**Key Features**:
- External configuration file (no code changes needed)
- UTF-8 support for German umlauts (ä, ö, ü, ß)
- Case-insensitive matching
- Comment lines supported (lines starting with #)
- Blank lines ignored

**Default Keywords**:
```
business analytics
machine learning
deep learning
Datenanalyse
data analysis
KI
künstliche Intelligenz
Maschinelles Lernen
```

---

### Feature 4: Email Notification

**Purpose**: Deliver daily digest of new tenders to recipients

**Operations**:
- Query new tenders since last successful email
- Format results using template
- Create Outlook mail item via COM
- Set recipients (To, CC, BCC from config)
- Send email
- Record in email_history table

**Key Features**:
- Windows Outlook integration (COM interface)
- Configurable recipients via YAML
- German-language email template
- Portal status summary in email
- Handles "no new results" gracefully
- Error notification if sending fails

**Email Template**:
```
Subject: Ausschreibungen {DD.MM.YYYY}

Dies ist eine automatisch generierte E-Mail.
Bitte nicht direkt antworten.

Ausführungszeitpunkt: {DD.MM.YYYY HH:MM:SS}

Durchsuchte Portale ({N} aktiv, {M} Fehler):
✓ evergabe.nrw.de - 12 Treffer
✓ bge.de - 3 Treffer
✗ ewn.de - Fehler: Connection timeout

NEUE AUSSCHREIBUNGEN ({TOTAL} gefunden)

1. {Titel}
   Stelle: {Ausschreibungsstelle}
   Link: {URL}
   Frist: {nächste Frist}
   Portal: {Portal}
   ----------------------------------------

2. ...

---
Tender Scraper System v1.0
```

---

### Feature 5: Logging & Debugging

**Purpose**: Provide comprehensive operational visibility

**Operations**:
- Initialize rotating file handler
- Log all operations with timestamps
- Capture error details with stack traces
- Record execution statistics

**Key Features**:
- Log file: `data/debug.log`
- Log rotation: 10MB max, 5 files retained
- Log levels: DEBUG, INFO, WARNING, ERROR, CRITICAL
- Structured format: `[TIMESTAMP] [LEVEL] [MODULE] Message`
- Console output for interactive debugging

**Log Events**:
| Event | Level | Example |
|-------|-------|---------|
| Script start | INFO | `Starting Tender Scraper v1.0` |
| Scraper start | INFO | `[bge] Starting scrape` |
| Scraper success | INFO | `[bge] Found 15 tenders, 3 new` |
| Scraper failure | ERROR | `[bge] Failed: Connection timeout` |
| Database write | DEBUG | `Inserted 3 new tenders` |
| Email sent | INFO | `Email sent to 2 recipients` |
| Script end | INFO | `Completed in 45m 23s` |

---

## 8. Technology Stack

### Core Technologies

| Component | Technology | Version | Purpose |
|-----------|------------|---------|---------|
| Language | Python | 3.9+ | Primary programming language |
| Database | SQLite | 3.x | Persistent data storage |
| Scraping | Selenium | 4.10+ | Browser automation |
| Parsing | BeautifulSoup4 | 4.12+ | HTML parsing |
| Email | pywin32 | 306+ | Outlook COM integration |
| Testing | pytest | 7.4+ | Test framework |

### Dependencies

```
# requirements.txt

# Web Scraping
selenium>=4.10.0
beautifulsoup4>=4.12.0
requests>=2.31.0
lxml>=4.9.0
webdriver-manager>=4.0.0
undetected-chromedriver>=3.5.0

# Data Processing
pandas>=2.0.0
openpyxl>=3.1.0

# Windows Integration
pywin32>=306

# Configuration
pyyaml>=6.0.0
python-dotenv>=1.0.0

# Testing
pytest>=7.4.0
pytest-cov>=4.1.0
pytest-mock>=3.11.0
pytest-timeout>=2.2.0
responses>=0.23.0
freezegun>=1.2.0

# Development
black>=23.0.0
flake8>=6.1.0
mypy>=1.5.0
```

### Third-Party Integrations

| Integration | Purpose | Authentication |
|-------------|---------|----------------|
| Microsoft Outlook | Email sending | Windows user identity |
| Chrome/Firefox | Web scraping | None (local browser) |
| 25 Procurement Portals | Data source | None (public data) |

---

## 9. Security & Configuration

### Security Scope

**In Scope**:
✅ No credentials stored in source code
✅ Database file restricted to application user
✅ Log files exclude sensitive email content
✅ HTTPS used for all portal connections
✅ Browser profiles cleaned up after use
✅ Rate limiting to avoid detection/blocking

**Out of Scope**:
❌ Encryption of database at rest
❌ Audit logging for compliance
❌ Network traffic encryption beyond HTTPS
❌ Multi-user access control

### Configuration Management

**Environment Variables** (optional):
```bash
TENDER_SCRAPER_CONFIG=C:\TenderScraper\config\config.yaml
TENDER_SCRAPER_LOG_LEVEL=DEBUG
```

**Configuration Files**:

```yaml
# config/config.yaml
general:
  log_level: INFO
  log_file: data/debug.log
  database_path: data/tenders.db

scraping:
  timeout_per_scraper: 300
  delay_min: 6
  delay_max: 10
  headless: true

keywords:
  file: config/Suchbegriffe.txt
  case_sensitive: false
  match_fields: [titel, ausschreibungsstelle]

scrapers:
  enabled: [vergabe_nrw, bge, ewn, ...]
  disabled: [ted_etendering, gtai]
```

```yaml
# config/email_config.yaml
sender: t.hein@brenk.com
recipients:
  to: [t.hein@brenk.com]
  cc: [tobias.hein@hotmail.de]
  bcc: []
subject_template: "Ausschreibungen {date}"
```

### Deployment Considerations

- **Runtime**: Windows Server 2016+ with Outlook installed
- **Python**: 3.9+ with virtual environment
- **Browser**: Chrome with ChromeDriver (auto-managed)
- **Scheduling**: Windows Task Scheduler (daily at 06:00)
- **Permissions**: User must have Outlook profile configured

---

## 10. Success Criteria

### MVP Success Definition

The MVP is successful when:

1. **Reliable Daily Execution**: System runs automatically via Task Scheduler 95%+ of days without intervention
2. **Complete Portal Coverage**: All 25 enabled scrapers execute (with individual failures logged but not blocking)
3. **Accurate New Tender Detection**: Zero false negatives (no missed new tenders) verified by manual spot checks
4. **Email Delivery**: Daily email received by all configured recipients
5. **Debuggability**: Any failure can be diagnosed within 5 minutes using debug.log

### Functional Requirements Checklist

✅ Single command `python main.py` executes entire workflow
✅ All 25 scrapers execute with proper error isolation
✅ New tenders correctly identified via database comparison
✅ Email sent via Outlook with formatted results
✅ Failures logged with timestamps and stack traces
✅ Configuration loaded from external YAML files
✅ Keywords loaded from external text file
✅ Database persists across executions
✅ Exit code reflects success (0) or failure (1)

### Quality Indicators

| Indicator | Target |
|-----------|--------|
| Test Coverage | >80% |
| Code Style (flake8) | 0 errors |
| Type Hints (mypy) | 0 errors |
| Documentation | 100% public APIs |
| Scraper Success Rate | >90% per scraper |

### User Experience Goals

- **Business Users**: Receive clear, scannable daily email by 08:00
- **Sysadmins**: Diagnose any failure in <5 minutes via logs
- **Developers**: Add new scraper in <1 hour following patterns

---

## 11. Implementation Phases

### Phase 1: Foundation

**Goal**: Establish project structure and core infrastructure

**Deliverables**:
✅ Project directory structure created
✅ `BaseScraper` abstract class implemented
✅ Database schema and connection manager
✅ Logging infrastructure with rotation
✅ Configuration loading (YAML)
✅ `CLAUDE.md` development guidelines

**Validation**:
- Run `python -c "from scrapers.base import BaseScraper"` successfully
- Create test database and verify schema
- Log entries appear in `debug.log`

---

### Phase 2: Scraper Migration

**Goal**: Convert all portal scrapers to Python modules

**Deliverables**:
✅ 25 scraper modules in `scrapers/` directory
✅ Scraper registry with auto-discovery
✅ Unit tests for each scraper's parsing logic
✅ Keyword filtering implementation
✅ Browser utilities (setup, teardown, scrolling)

**Validation**:
- Each scraper passes unit tests with sample HTML
- Run individual scraper: `python -c "from scrapers.bge import BGEScraper; BGEScraper().scrape()"`
- All 22 scrapers listed in registry

---

### Phase 3: Integration

**Goal**: Connect all components and implement orchestration

**Deliverables**:
✅ `main.py` orchestrator
✅ Email sender with Outlook integration
✅ Email templates
✅ Integration tests (scraper → database → email)
✅ Error handling and recovery
✅ Command-line argument parsing

**Validation**:
- Run `python main.py --dry-run` without errors
- Run `python main.py --skip-email` and verify database population
- Full run with email delivery verified

---

### Phase 4: Testing & Documentation

**Goal**: Complete test suite and documentation

**Deliverables**:
✅ End-to-end workflow tests
✅ Error recovery tests
✅ `README.md` with quick start guide
✅ `IMPLEMENTATION.md` with technical details
✅ Test coverage report >80%
✅ Code style compliance (flake8, black)

**Validation**:
- `pytest tests/ --cov` shows >80% coverage
- `flake8 .` returns 0 errors
- New developer can set up and run system following README

---

### Phase 5: Deployment

**Goal**: Production deployment with monitoring

**Deliverables**:
✅ Windows Task Scheduler task configured
✅ Batch file for scheduled execution
✅ Installation documentation
✅ Troubleshooting guide
✅ First week of successful daily runs

**Validation**:
- Task Scheduler triggers execution at 06:00
- Email received by 08:00 for 7 consecutive days
- Any failures diagnosed and resolved using logs

---

## 12. Future Considerations

### Post-MVP Enhancements

1. **Web Dashboard**: Real-time status display and historical analytics
2. **Slack/Teams Integration**: Push notifications for urgent tenders
3. **Machine Learning**: Relevance scoring based on historical interest
4. **API Layer**: RESTful endpoints for integration with other systems
5. **Multi-tenant**: Support multiple keyword sets for different teams

### Integration Opportunities

- **CRM Systems**: Push tender leads to Salesforce/HubSpot
- **Calendar**: Add tender deadlines to team calendar
- **Document Management**: Archive tender documents automatically
- **Analytics**: Export data to PowerBI/Tableau

### Advanced Features

- **Proxy Rotation**: Avoid IP-based blocking
- **CAPTCHA Solving**: Handle protected portals
- **PDF Parsing**: Extract tender details from PDF attachments
- **Change Detection**: Track tender modifications

---

## 13. Risks & Mitigations

### Risk 1: Website Structure Changes

**Probability**: High (websites update regularly)
**Impact**: Medium (individual scraper fails)
**Mitigation**:
- Modular scrapers enable quick fixes without affecting others
- Comprehensive unit tests catch parsing failures early
- Monitoring alerts when scraper success rate drops

### Risk 2: Anti-Scraping Detection

**Probability**: Medium
**Impact**: High (portal blocks access)
**Mitigation**:
- Random delays between requests (6-10 seconds)
- Rotate user agents
- Use undetected-chromedriver for protected sites
- Respect rate limits and robots.txt

### Risk 3: Outlook Integration Failures

**Probability**: Low
**Impact**: High (no email delivery)
**Mitigation**:
- Verify Outlook running before attempting send
- Fallback to error notification
- Log detailed error for manual intervention
- Consider future SMTP alternative

### Risk 4: Database Corruption

**Probability**: Low
**Impact**: High (data loss)
**Mitigation**:
- SQLite WAL mode for consistency
- Regular backups via script
- Integrity checks in startup
- Schema versioning for migrations

### Risk 5: ChromeDriver Incompatibility

**Probability**: Medium (Chrome auto-updates)
**Impact**: Medium (scrapers fail)
**Mitigation**:
- webdriver-manager auto-downloads correct version
- Pin Chrome version on server if needed
- Monitor for WebDriver exceptions

---

## 14. Appendix

### A. Portal URL Reference

| Portal | URL | Category |
|--------|-----|----------|
| vergabe_nrw | evergabe.nrw.de | Government (DE) |
| deutsche_evergabe | deutsche-evergabe.de | Government (DE) |
| deutsches_vergabeportal | dtvp.de | Government (DE) |
| e_vergabe_online | e-vergabe-online.de | Government (DE) |
| bund_de | bund.de | Federal (DE) |
| bge | bge.de | Corporate (Nuclear) |
| ewn | ewn-gmbh.de | Corporate (Nuclear) |
| rwe | rwe.com | Corporate (Energy) |
| fraunhofer | vergabe.fraunhofer.de | Research |
| e_beschaffung_at | e-beschaffung.at | Government (AT) |
| simap_ch | old.simap.ch | Government (CH) |
| bauportal_deutschland | bauportal-deutschland.de | Construction |
| germanytenders | germanytenders.com | Aggregator |

### B. Glossary

| Term | Definition |
|------|------------|
| Ausschreibung | Public tender / procurement notice |
| Vergabe | Procurement / award process |
| VgV | Vergabeverordnung - German procurement regulation |
| VOB | Construction procurement regulation |
| Portal | Government or corporate procurement website |
| Scraper | Module that extracts data from a specific portal |

### C. Related Documents

- `CLAUDE.md` - Development guidelines
- `README.md` - User documentation
- `IMPLEMENTATION.md` - Technical details
- `_old-solution-reference/` - Original Jupyter notebooks

---

## Document History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-01-14 | Development Team | Initial draft |
| 2.0 | 2026-01-14 | Development Team | Restructured to match PRD template |

---

**End of Document**
