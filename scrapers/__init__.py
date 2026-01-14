"""
Tender Scraper - Portal Scrapers Package

This package contains individual scraper modules for each procurement portal.
Each scraper inherits from BaseScraper and implements portal-specific logic.
"""

from scrapers.base import BaseScraper, TenderResult, ScraperError
from scrapers.registry import get_scraper, get_all_scrapers, register_scraper

__all__ = [
    "BaseScraper",
    "TenderResult",
    "ScraperError",
    "get_scraper",
    "get_all_scrapers",
    "register_scraper",
]
