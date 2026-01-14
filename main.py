#!/usr/bin/env python3
"""
Tender Scraper System - Main Orchestrator.

Command-line interface for running tender scrapers, storing results,
and sending email notifications.

Usage:
    python main.py [options]

Options:
    --config PATH       Path to config file (default: config/config.yaml)
    --scrapers LIST     Comma-separated scraper names (default: all enabled)
    --skip-email        Skip sending email notification
    --dry-run           Don't save to database or send email
    --verbose           Enable debug logging
    --help              Show this help message
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

    # Load configuration
    try:
        config = load_config(args.config)
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    # Setup logging
    general_config = config.get("general", {})
    log_level = "DEBUG" if args.verbose else general_config.get("log_level", "INFO")
    setup_logging(
        log_file=general_config.get("log_file", "data/debug.log"),
        log_level=log_level,
        max_bytes=general_config.get("log_max_bytes", 10 * 1024 * 1024),
        backup_count=general_config.get("log_backup_count", 5),
    )

    logger = get_logger(__name__)
    logger.info("=" * 60)
    logger.info("Tender Scraper System started")
    logger.info("=" * 60)

    if args.dry_run:
        logger.info("DRY RUN MODE - No database writes or emails")

    # Initialize database
    db_path = general_config.get("database_path", "data/tenders.db")
    db = Database(db_path)
    db.initialize()

    # Load keywords
    keywords_config = config.get("keywords", {})
    keywords_file = keywords_config.get("file", "config/Suchbegriffe.txt")
    exclusions = keywords_config.get("exclusions", [])
    case_sensitive = keywords_config.get("case_sensitive", False)
    match_fields = keywords_config.get("match_fields", ["titel"])

    matcher = KeywordMatcher(
        keywords_file=keywords_file,
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

    # Get new tenders since last email
    new_tenders = db.get_new_tenders_since_last_email()
    logger.info(f"New tenders since last email: {len(new_tenders)}")

    # Send email if enabled and not skipped
    email_enabled = config.get("email", {}).get("enabled", True)
    send_empty = True  # Default to send even if no tenders

    try:
        email_config = load_email_config(config)
        send_empty = email_config.get("send_empty_report", True)
    except FileNotFoundError as e:
        logger.warning(f"Email config not found: {e}")
        email_enabled = False

    should_send = (
        email_enabled
        and not args.skip_email
        and (new_tenders or send_empty)
    )

    if should_send:
        logger.info("Sending email report...")
        send_report_email(
            tenders=new_tenders,
            portal_status=portal_status,
            email_config=email_config,
            db=db,
            dry_run=args.dry_run,
            logger=logger,
        )
    elif args.skip_email:
        logger.info("Email skipped (--skip-email)")
    elif not new_tenders and not send_empty:
        logger.info("No new tenders, skipping email")
    else:
        logger.info("Email disabled in config")

    # Close database
    db.close()

    logger.info("=" * 60)
    logger.info("Tender Scraper System finished")
    logger.info("=" * 60)

    # Exit with error code if any scrapers failed
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
