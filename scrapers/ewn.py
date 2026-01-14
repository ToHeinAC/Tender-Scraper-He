"""
Scraper for EWN (Entsorgungswerk für Nuklearanlagen).

URL: https://www.ewn-gmbh.de/ausschreibungen
Nuclear decommissioning tenders.
"""

import re
from datetime import datetime
from typing import List
import logging

from bs4 import BeautifulSoup

from scrapers.base import BaseScraper, TenderResult, ScraperError
from scrapers.registry import register_scraper
from scrapers.utils import clean_text


@register_scraper
class EWNScraper(BaseScraper):
    """Scraper for ewn-gmbh.de procurement portal."""

    PORTAL_NAME = "ewn"
    PORTAL_URL = "https://www.ewn-gmbh.de/ausschreibungen"
    REQUIRES_SELENIUM = True

    def scrape(self) -> List[TenderResult]:
        """
        Execute scraping logic for EWN portal.

        Returns:
            List of TenderResult objects
        """
        results = []

        try:
            # Navigate to tenders page
            self.driver.get(self.PORTAL_URL)
            self.accept_cookies()

            # Wait for page to load
            import time
            time.sleep(2)

            # Get page HTML
            html = self.driver.page_source
            soup = BeautifulSoup(html, "lxml")

            # Parse results
            results = self._parse_results(soup)

        except Exception as e:
            self.logger.error(f"EWN scraping failed: {e}")
            raise ScraperError(self.PORTAL_NAME, str(e)) from e

        return results

    def _parse_results(self, soup: BeautifulSoup) -> List[TenderResult]:
        """
        Parse EWN tender page HTML.

        Args:
            soup: BeautifulSoup object of page HTML

        Returns:
            List of TenderResult objects
        """
        results = []
        now = datetime.now()

        # EWN uses announcements table with div pairs
        try:
            table = soup.select_one("table[class='announcements']")
            if not table:
                self.logger.warning("No announcements table found")
                return results

            items = table.find_all("div")
            self.logger.debug(f"Found {len(items)} div elements in table")

            # Process items in pairs (info div + button div)
            for i in range(0, len(items), 2):
                try:
                    info_div = items[i]
                    button_div = items[i + 1] if i + 1 < len(items) else None

                    result = self._parse_item(info_div, button_div, now)
                    if result:
                        results.append(result)
                except Exception as e:
                    self.logger.warning(f"Failed to parse EWN item at index {i}: {e}")
                    continue

        except Exception as e:
            self.logger.error(f"Failed to parse EWN table: {e}")

        return results

    def _parse_item(self, info_div, button_div, now: datetime) -> TenderResult:
        """
        Parse a single tender item.

        Args:
            info_div: BeautifulSoup element with tender info
            button_div: BeautifulSoup element with link button
            now: Current timestamp

        Returns:
            TenderResult object
        """
        # Extract ID
        id_elem = info_div.select_one("span[class='tender--identifier']")
        vergabe_id = clean_text(id_elem.get_text()) if id_elem else ""

        # Extract title
        title_elem = info_div.select_one("span[class='title']")
        titel = clean_text(title_elem.get_text()) if title_elem else ""

        # Extract category info (procurement type and deadline)
        ausschreibungsart = ""
        naechste_frist = ""

        category_elem = info_div.select_one("p[class='category']")
        if category_elem:
            category_text = category_elem.get_text()

            # Extract procurement type
            art_match = re.search(r'Vergabeart:\s*([^\n]+)', category_text)
            if art_match:
                ausschreibungsart = clean_text(art_match.group(1))

            # Extract deadline
            frist_match = re.search(r'Angebotsschlusstermin:\s*([^\s]+)', category_text)
            if frist_match:
                naechste_frist = clean_text(frist_match.group(1))

        # Extract link from button div
        link = ""
        if button_div:
            link_elem = button_div.select_one("a[class='button']")
            if link_elem and link_elem.has_attr("href"):
                link = link_elem["href"]

        now_str = now.strftime("%d.%m.%Y %H:%M:%S")

        return TenderResult(
            portal=self.PORTAL_NAME,
            suchbegriff=None,
            suchzeitpunkt=now,
            vergabe_id=vergabe_id,
            link=link,
            titel=titel,
            ausschreibungsstelle="EWN",  # Always EWN for this portal
            ausfuehrungsort="",
            ausschreibungsart=ausschreibungsart,
            naechste_frist=naechste_frist,
            veroeffentlicht=now_str,
        )
