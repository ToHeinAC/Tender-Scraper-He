#!/usr/bin/env python3
"""
Tender Scraper System - Main Orchestrator.

Command-line interface for running tender scrapers, storing results,
and sending email notifications.

Usage:
    python main.py --purpose PURPOSE [options]

Options:
    --purpose NAME      Purpose to run (e.g., BA, NORM) - REQUIRED
    --list-purposes     List available purposes and exit
    --config PATH       Path to config file (default: config/config.yaml)
    --scrapers LIST     Comma-separated scraper names (default: all enabled)
    --skip-email        Skip sending email notification
    --dry-run           Don't save to database or send email
    --verbose           Enable debug logging
    --help              Show this help message

Purposes are auto-discovered from config/Suchbegriffe_*.txt files.
Each purpose has its own keywords, email recipients, database, and log file.
"""

import argparse
import random
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from database.db import Database
from email_sender.sender import OutlookSender, OutlookError
from email_sender.templates import EmailTemplates
from scrapers.base import TenderResult, ScraperError
from scrapers.registry import (
    discover_scrapers,
    get_scraper,
    get_enabled_scrapers,
    create_scraper,
)
from utils.keywords import KeywordMatcher
from utils.logging_config import setup_logging, get_logger


# =============================================================================
# Purpose Discovery and Configuration
# =============================================================================


def discover_purposes() -> List[str]:
    """
    Discover available purposes from config/Suchbegriffe_*.txt files.

    Returns:
        Sorted list of purpose names (e.g., ['BA', 'NORM'])
    """
    config_dir = Path("config")
    purposes = []

    for f in config_dir.glob("Suchbegriffe_*.txt"):
        # Extract purpose name: Suchbegriffe_BA.txt -> BA
        purpose = f.stem.replace("Suchbegriffe_", "")
        purposes.append(purpose)

    return sorted(purposes)


def get_purpose_paths(purpose: str) -> Dict[str, str]:
    """
    Get all file paths for a specific purpose.

    Args:
        purpose: Purpose name (e.g., 'BA', 'NORM')

    Returns:
        Dictionary with paths for keywords_file, email_file, database_path, log_file
    """
    return {
        "keywords_file": f"config/Suchbegriffe_{purpose}.txt",
        "email_file": f"config/EMail_{purpose}.txt",
        "database_path": f"data/tenders_{purpose}.db",
        "log_file": f"data/debug_{purpose}.log",
    }


def validate_purpose(purpose: str) -> Optional[str]:
    """
    Validate that a purpose has all required files.

    Args:
        purpose: Purpose name to validate

    Returns:
        Error message if invalid, None if valid
    """
    paths = get_purpose_paths(purpose)

    # Check keywords file
    if not Path(paths["keywords_file"]).exists():
        return f"Keywords file not found: {paths['keywords_file']}"

    # Check email file
    if not Path(paths["email_file"]).exists():
        return f"Email config not found: {paths['email_file']}"

    return None


def load_purpose_email_config(purpose: str, base_config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Load email configuration for a specific purpose.

    Merges purpose-specific recipients with base email settings.

    Args:
        purpose: Purpose name
        base_config: Base email configuration from email_config.yaml

    Returns:
        Merged email configuration dictionary
    """
    paths = get_purpose_paths(purpose)
    email_file = Path(paths["email_file"])

    if not email_file.exists():
        raise FileNotFoundError(f"Email config not found for purpose '{purpose}': {email_file}")

    with open(email_file, "r", encoding="utf-8") as f:
        purpose_config = yaml.safe_load(f)

    # Start with base config and override with purpose-specific settings
    merged = base_config.copy()

    # Override recipients from purpose-specific file
    if "recipients" in purpose_config:
        merged["recipients"] = purpose_config["recipients"]

    # Update subject template to include purpose
    base_subject = merged.get("subject_template", "Ausschreibungen {date}")
    if "{purpose}" not in base_subject:
        # Add purpose to subject if not already in template
        merged["subject_template"] = f"Ausschreibungen {purpose} - {{date}}"

    return merged


def load_config(config_path: str) -> Dict[str, Any]:
    """
    Load configuration from YAML file.

    Args:
        config_path: Path to config file

    Returns:
        Configuration dictionary
    """
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_email_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Load email configuration from separate YAML file.

    Args:
        config: Main configuration dictionary

    Returns:
        Email configuration dictionary
    """
    email_config_path = config.get("email", {}).get("config_file", "config/email_config.yaml")
    path = Path(email_config_path)

    if not path.exists():
        raise FileNotFoundError(f"Email config file not found: {email_config_path}")

    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def filter_by_keywords(
    results: List[TenderResult],
    matcher: KeywordMatcher,
    match_fields: List[str],
) -> List[TenderResult]:
    """
    Filter tender results by keywords.

    Args:
        results: List of TenderResult objects
        matcher: KeywordMatcher instance
        match_fields: List of field names to match against

    Returns:
        Filtered list of TenderResult objects
    """
    filtered = []

    for result in results:
        # Build list of field values to check
        fields_to_check = []
        for field in match_fields:
            value = getattr(result, field, None)
            if value:
                fields_to_check.append(value)

        # Check if any field matches
        if matcher.matches_any_field(fields_to_check):
            # Get the matching keyword for the suchbegriff field
            matching_kw = matcher.get_first_match(fields_to_check)
            if matching_kw:
                # Create new result with suchbegriff set
                result_dict = result.to_dict()
                result_dict["suchbegriff"] = matching_kw
                result = TenderResult(**result_dict)
            filtered.append(result)

    return filtered


def run_scraper(
    portal_name: str,
    config: Dict[str, Any],
    db: Database,
    matcher: KeywordMatcher,
    match_fields: List[str],
    dry_run: bool,
    logger,
) -> Dict[str, Any]:
    """
    Run a single scraper with error isolation.

    Args:
        portal_name: Name of the portal to scrape
        config: Configuration dictionary
        db: Database instance
        matcher: KeywordMatcher instance
        match_fields: Fields to match keywords against
        dry_run: If True, don't save to database
        logger: Logger instance

    Returns:
        Status dictionary with success, records_found, records_new, error
    """
    status = {
        "success": False,
        "records_found": 0,
        "records_new": 0,
        "error": None,
    }

    scrape_id = None
    if not dry_run:
        scrape_id = db.log_scrape_start(portal_name)

    try:
        # Create scraper instance
        scraper = create_scraper(portal_name, config)
        if not scraper:
            raise ScraperError(portal_name, f"Scraper not found: {portal_name}")

        # Run scraper
        results = scraper.run()
        status["records_found"] = len(results)

        # Filter by keywords
        filtered = filter_by_keywords(results, matcher, match_fields)
        logger.info(f"{portal_name}: {len(results)} total, {len(filtered)} matched keywords")

        # Save to database
        if not dry_run and filtered:
            tenders_dicts = [r.to_dict() for r in filtered]
            new_count = db.insert_tenders(tenders_dicts)
            status["records_new"] = new_count
            logger.info(f"{portal_name}: {new_count} new tenders saved")
        elif dry_run and filtered:
            status["records_new"] = len(filtered)

        status["success"] = True

    except ScraperError as e:
        status["error"] = str(e)
        logger.error(f"{portal_name} scraper failed: {e}")

    except Exception as e:
        status["error"] = str(e)
        logger.error(f"{portal_name} unexpected error: {e}", exc_info=True)

    finally:
        if scrape_id and not dry_run:
            db.log_scrape_end(
                scrape_id=scrape_id,
                status="success" if status["success"] else "failure",
                records_found=status["records_found"],
                records_new=status["records_new"],
                error_message=status["error"],
            )

    return status


def send_report_email(
    tenders: List[Dict[str, Any]],
    portal_status: Dict[str, Dict[str, Any]],
    email_config: Dict[str, Any],
    db: Database,
    dry_run: bool,
    logger,
) -> bool:
    """
    Send tender report email.

    Args:
        tenders: List of new tender dictionaries
        portal_status: Status dictionary for each portal
        email_config: Email configuration
        db: Database instance
        dry_run: If True, don't actually send
        logger: Logger instance

    Returns:
        True if sent successfully
    """
    # Generate subject
    today = datetime.now()
    subject_template = email_config.get("subject_template", "Ausschreibungen {date}")
    subject = subject_template.format(
        date=today.strftime("%d.%m.%Y"),
        count=len(tenders),
    )

    # Generate body
    body = EmailTemplates.format_tender_report(
        tenders=tenders,
        portal_status=portal_status,
        timestamp=today,
    )

    if dry_run:
        logger.info("DRY RUN: Would send email")
        logger.info(f"Subject: {subject}")
        logger.info(f"Body preview:\n{body[:500]}...")
        return True

    try:
        sender = OutlookSender(email_config)
        sender.send_email(subject=subject, body=body)

        # Log email sent
        recipients = "; ".join(email_config.get("recipients", {}).get("to", []))
        db.log_email_sent(
            recipients=recipients,
            subject=subject,
            new_tenders_count=len(tenders),
            status="success",
        )

        logger.info(f"Email sent: {subject}")
        return True

    except OutlookError as e:
        logger.error(f"Failed to send email: {e}")

        # Log failed email
        recipients = "; ".join(email_config.get("recipients", {}).get("to", []))
        db.log_email_sent(
            recipients=recipients,
            subject=subject,
            new_tenders_count=len(tenders),
            status="failure",
            error_message=str(e),
        )

        return False


def main():
    """Main entry point."""
    # Parse arguments
    parser = argparse.ArgumentParser(
        description="Tender Scraper System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--purpose",
        help="Purpose to run (e.g., BA, NORM). Required unless using --list-purposes.",
    )
    parser.add_argument(
        "--list-purposes",
        action="store_true",
        help="List available purposes and exit",
    )
    parser.add_argument(
        "--config",
        default="config/config.yaml",
        help="Path to config file (default: config/config.yaml)",
    )
    parser.add_argument(
        "--scrapers",
        help="Comma-separated scraper names (default: all enabled)",
    )
    parser.add_argument(
        "--skip-email",
        action="store_true",
        help="Skip sending email notification",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't save to database or send email",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging",
    )

    args = parser.parse_args()

    # Handle --list-purposes
    if args.list_purposes:
        purposes = discover_purposes()
        if purposes:
            print("Available purposes:")
            for p in purposes:
                paths = get_purpose_paths(p)
                print(f"  {p}")
                print(f"      Keywords: {paths['keywords_file']}")
                print(f"      Email:    {paths['email_file']}")
                print(f"      Database: {paths['database_path']}")
        else:
            print("No purposes found. Create config/Suchbegriffe_<PURPOSE>.txt files.")
        sys.exit(0)

    # Require --purpose argument
    if not args.purpose:
        purposes = discover_purposes()
        print("ERROR: --purpose is required.", file=sys.stderr)
        print("", file=sys.stderr)
        if purposes:
            print(f"Available purposes: {', '.join(purposes)}", file=sys.stderr)
            print("", file=sys.stderr)
            print("Usage examples:", file=sys.stderr)
            print(f"  python main.py --purpose {purposes[0]}", file=sys.stderr)
            print(f"  python main.py --purpose {purposes[0]} --dry-run", file=sys.stderr)
        else:
            print("No purposes found. Create config/Suchbegriffe_<PURPOSE>.txt files.", file=sys.stderr)
        print("", file=sys.stderr)
        print("Use --list-purposes to see all available purposes.", file=sys.stderr)
        sys.exit(1)

    # Validate purpose
    purpose = args.purpose.upper()  # Normalize to uppercase
    error = validate_purpose(purpose)
    if error:
        print(f"ERROR: {error}", file=sys.stderr)
        purposes = discover_purposes()
        if purposes:
            print(f"Available purposes: {', '.join(purposes)}", file=sys.stderr)
        sys.exit(1)

    # Get purpose-specific paths
    purpose_paths = get_purpose_paths(purpose)

    # Load configuration
    try:
        config = load_config(args.config)
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    # Setup logging (purpose-specific log file)
    general_config = config.get("general", {})
    log_level = "DEBUG" if args.verbose else general_config.get("log_level", "INFO")
    setup_logging(
        log_file=purpose_paths["log_file"],
        log_level=log_level,
        max_bytes=general_config.get("log_max_bytes", 10 * 1024 * 1024),
        backup_count=general_config.get("log_backup_count", 5),
    )

    logger = get_logger(__name__)
    logger.info("=" * 60)
    logger.info(f"Tender Scraper System started - Purpose: {purpose}")
    logger.info("=" * 60)
    logger.info(f"Keywords: {purpose_paths['keywords_file']}")
    logger.info(f"Database: {purpose_paths['database_path']}")
    logger.info(f"Log file: {purpose_paths['log_file']}")

    if args.dry_run:
        logger.info("DRY RUN MODE - No database writes or emails")

    # Initialize database (purpose-specific database)
    db = Database(purpose_paths["database_path"])
    db.initialize()

    # Load keywords (purpose-specific keywords file)
    keywords_config = config.get("keywords", {})
    exclusions = keywords_config.get("exclusions", [])
    case_sensitive = keywords_config.get("case_sensitive", False)
    match_fields = keywords_config.get("match_fields", ["titel"])

    matcher = KeywordMatcher(
        keywords_file=purpose_paths["keywords_file"],
        case_sensitive=case_sensitive,
        exclusions=exclusions,
    )

    # Discover scrapers
    discover_scrapers()

    # Determine which scrapers to run
    if args.scrapers:
        scrapers_to_run = [s.strip() for s in args.scrapers.split(",")]
    else:
        scrapers_to_run = get_enabled_scrapers(config)

    logger.info(f"Scrapers to run: {scrapers_to_run}")

    # Get scraping settings
    scraping_config = config.get("scraping", {})
    delay_min = scraping_config.get("delay_min", 6)
    delay_max = scraping_config.get("delay_max", 10)

    # Run scrapers
    portal_status = {}
    total_found = 0
    total_new = 0

    for i, portal_name in enumerate(scrapers_to_run):
        logger.info(f"[{i + 1}/{len(scrapers_to_run)}] Starting {portal_name}...")

        status = run_scraper(
            portal_name=portal_name,
            config=config,
            db=db,
            matcher=matcher,
            match_fields=match_fields,
            dry_run=args.dry_run,
            logger=logger,
        )

        portal_status[portal_name] = status
        total_found += status["records_found"]
        total_new += status["records_new"]

        # Show progress after each scraper
        logger.info(
            f"[{i + 1}/{len(scrapers_to_run)}] {portal_name}: "
            f"{status['records_found']} found, {status['records_new']} matched"
        )

        # Add delay between scrapers (except for last one)
        if i < len(scrapers_to_run) - 1:
            delay = random.uniform(delay_min, delay_max)
            logger.info(f"Waiting {delay:.0f}s before next scraper...")
            time.sleep(delay)

    # Summary
    successful = sum(1 for s in portal_status.values() if s["success"])
    failed = len(portal_status) - successful

    logger.info("-" * 60)
    logger.info("SCRAPING SUMMARY")
    logger.info("-" * 60)
    logger.info(f"Scrapers: {successful} succeeded, {failed} failed")
    logger.info(f"Records: {total_found} found, {total_new} new")

    # Get tenders that haven't been sent by email yet
    unsent_tenders = db.get_unsent_tenders()
    logger.info(f"Unsent tenders: {len(unsent_tenders)}")

    # Send email if enabled and not skipped
    email_enabled = config.get("email", {}).get("enabled", True)
    send_empty = True  # Default to send even if no tenders

    try:
        # Load base email config, then merge with purpose-specific recipients
        base_email_config = load_email_config(config)
        email_config = load_purpose_email_config(purpose, base_email_config)
        send_empty = email_config.get("send_empty_report", True)
        logger.info(f"Email recipients: {email_config.get('recipients', {}).get('to', [])}")
    except FileNotFoundError as e:
        logger.warning(f"Email config not found: {e}")
        email_enabled = False

    should_send = (
        email_enabled
        and not args.skip_email
        and (unsent_tenders or send_empty)
    )

    if should_send:
        logger.info("Sending email report...")
        email_success = send_report_email(
            tenders=unsent_tenders,
            portal_status=portal_status,
            email_config=email_config,
            db=db,
            dry_run=args.dry_run,
            logger=logger,
        )

        # Mark tenders as sent if email was successful
        if email_success and unsent_tenders and not args.dry_run:
            tender_ids = [t["id"] for t in unsent_tenders]
            marked = db.mark_tenders_as_sent(tender_ids)
            logger.info(f"Marked {marked} tenders as sent")

    elif args.skip_email:
        logger.info("Email skipped (--skip-email)")
    elif not unsent_tenders and not send_empty:
        logger.info("No unsent tenders, skipping email")
    else:
        logger.info("Email disabled in config")

    # Close database
    db.close()

    logger.info("=" * 60)
    logger.info(f"Tender Scraper System finished - Purpose: {purpose}")
    logger.info("=" * 60)

    # Exit with error code if any scrapers failed
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
