"""
Tender Scraper - Database Package

This package handles all database operations including:
- Connection management
- Schema initialization
- CRUD operations for tenders
- Scrape and email history tracking
"""

from database.db import Database
from database.queries import TenderQueries

__all__ = ["Database", "TenderQueries"]
