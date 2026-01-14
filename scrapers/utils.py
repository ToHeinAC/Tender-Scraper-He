"""
Shared utilities for scraper modules.

Provides common functions used across multiple scrapers.
"""

import re
import time
from datetime import datetime
from typing import Optional
from urllib.parse import urljoin, urlparse


def clean_text(text: Optional[str]) -> str:
    """
    Clean and normalize text.

    Args:
        text: Text to clean

    Returns:
        Cleaned text
    """
    if not text:
        return ""

    # Remove extra whitespace
    text = re.sub(r"\s+", " ", text)

    # Strip leading/trailing whitespace
    text = text.strip()

    return text


def extract_date(text: Optional[str]) -> str:
    """
    Extract and normalize a date from text.

    Handles various German date formats.

    Args:
        text: Text containing a date

    Returns:
        Normalized date string (DD.MM.YYYY) or original text
    """
    if not text:
        return ""

    text = clean_text(text)

    # Common German date patterns
    patterns = [
        # DD.MM.YYYY
        r"(\d{1,2})\.(\d{1,2})\.(\d{4})",
        # DD.MM.YY
        r"(\d{1,2})\.(\d{1,2})\.(\d{2})(?!\d)",
        # YYYY-MM-DD
        r"(\d{4})-(\d{2})-(\d{2})",
    ]

    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            groups = match.groups()
            if len(groups) == 3:
                if len(groups[0]) == 4:  # YYYY-MM-DD
                    return f"{groups[2]}.{groups[1]}.{groups[0]}"
                elif len(groups[2]) == 2:  # DD.MM.YY
                    year = f"20{groups[2]}"
                    return f"{groups[0].zfill(2)}.{groups[1].zfill(2)}.{year}"
                else:  # DD.MM.YYYY
                    return f"{groups[0].zfill(2)}.{groups[1].zfill(2)}.{groups[2]}"

    return text


def extract_datetime(text: Optional[str]) -> str:
    """
    Extract and normalize a datetime from text.

    Args:
        text: Text containing a datetime

    Returns:
        Normalized datetime string or original text
    """
    if not text:
        return ""

    text = clean_text(text)

    # Pattern: DD.MM.YYYY HH:MM or DD.MM.YYYY HH:MM:SS
    pattern = r"(\d{1,2})\.(\d{1,2})\.(\d{4})\s+(\d{1,2}):(\d{2})(?::(\d{2}))?"
    match = re.search(pattern, text)

    if match:
        day, month, year, hour, minute = match.groups()[:5]
        second = match.group(6) or "00"
        return f"{day.zfill(2)}.{month.zfill(2)}.{year} {hour.zfill(2)}:{minute}:{second}"

    return extract_date(text)


def normalize_url(url: Optional[str], base_url: str = "") -> str:
    """
    Normalize and resolve a URL.

    Args:
        url: URL to normalize
        base_url: Base URL for relative URLs

    Returns:
        Normalized absolute URL
    """
    if not url:
        return ""

    url = url.strip()

    # Handle relative URLs
    if base_url and not url.startswith(("http://", "https://")):
        url = urljoin(base_url, url)

    return url


def extract_id_from_url(url: str, pattern: Optional[str] = None) -> str:
    """
    Extract an ID from a URL.

    Args:
        url: URL to parse
        pattern: Optional regex pattern for ID extraction

    Returns:
        Extracted ID or empty string
    """
    if not url:
        return ""

    if pattern:
        match = re.search(pattern, url)
        if match:
            return match.group(1) if match.groups() else match.group(0)

    # Default: try to extract common ID patterns
    patterns = [
        r"[?&]id=(\d+)",
        r"/(\d+)/?$",
        r"ID=(\d+)",
        r"vergabe[_-]?id[=:]?(\d+)",
    ]

    for p in patterns:
        match = re.search(p, url, re.IGNORECASE)
        if match:
            return match.group(1)

    return ""


def wait_random(min_seconds: float = 1.0, max_seconds: float = 3.0) -> None:
    """
    Wait for a random amount of time.

    Args:
        min_seconds: Minimum wait time
        max_seconds: Maximum wait time
    """
    import random

    wait_time = random.uniform(min_seconds, max_seconds)
    time.sleep(wait_time)


def parse_german_date(date_str: str) -> Optional[datetime]:
    """
    Parse a German-format date string.

    Args:
        date_str: Date string (DD.MM.YYYY)

    Returns:
        Datetime object or None if parsing fails
    """
    if not date_str:
        return None

    formats = [
        "%d.%m.%Y",
        "%d.%m.%Y %H:%M",
        "%d.%m.%Y %H:%M:%S",
        "%Y-%m-%d",
        "%Y-%m-%d %H:%M:%S",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(date_str.strip(), fmt)
        except ValueError:
            continue

    return None


def get_domain(url: str) -> str:
    """
    Extract domain from URL.

    Args:
        url: URL to parse

    Returns:
        Domain name
    """
    if not url:
        return ""

    parsed = urlparse(url)
    return parsed.netloc


def is_valid_url(url: Optional[str]) -> bool:
    """
    Check if URL is valid.

    Args:
        url: URL to check

    Returns:
        True if valid
    """
    if not url:
        return False

    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except Exception:
        return False


def truncate_text(text: str, max_length: int = 200) -> str:
    """
    Truncate text to a maximum length.

    Args:
        text: Text to truncate
        max_length: Maximum length

    Returns:
        Truncated text with ellipsis if needed
    """
    if not text or len(text) <= max_length:
        return text

    return text[: max_length - 3] + "..."


def remove_html_tags(text: str) -> str:
    """
    Remove HTML tags from text.

    Args:
        text: Text with HTML tags

    Returns:
        Plain text
    """
    if not text:
        return ""

    # Remove HTML tags
    clean = re.sub(r"<[^>]+>", " ", text)

    # Clean up whitespace
    clean = re.sub(r"\s+", " ", clean)

    return clean.strip()
