"""
Scraper for BGE (Bundesgesellschaft für Endlagerung).

URL: https://www.bge.de/de/aktuelles/ausschreibungen/
Federal Nuclear Waste Repository tenders.
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
class BGEScraper(BaseScraper):
    """Scraper for bge.de procurement portal."""

    PORTAL_NAME = "bge"
    PORTAL_URL = "https://www.bge.de/de/aktuelles/ausschreibungen/"
    REQUIRES_SELENIUM = True

    def scrape(self) -> List[TenderResult]:
        """
        Execute scraping logic for BGE portal.

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
            self.logger.error(f"BGE scraping failed: {e}")
            raise ScraperError(self.PORTAL_NAME, str(e)) from e

        return results

    def _parse_results(self, soup: BeautifulSoup) -> List[TenderResult]:
        """
        Parse BGE tender page HTML.

        Args:
            soup: BeautifulSoup object of page HTML

        Returns:
            List of TenderResult objects
        """
        results = []
        now = datetime.now()

        # BGE uses rss_item divs for tender listings
        items = soup.select("div[class='rss_item col-sm-10']")
        self.logger.debug(f"Found {len(items)} tender items")

        for item in items:
            try:
                result = self._parse_item(item, now)
                if result:
                    results.append(result)
            except Exception as e:
                self.logger.warning(f"Failed to parse BGE item: {e}")
                continue

        return results

    def _parse_item(self, item, now: datetime) -> TenderResult:
        """
        Parse a single tender item.

        Args:
            item: BeautifulSoup element for tender item
            now: Current timestamp

        Returns:
            TenderResult object
        """
        # Extract link
        link_elem = item.select_one("h3 a")
        link = link_elem["href"] if link_elem and link_elem.has_attr("href") else ""

        # Extract title and ID from h3
        # Format: "E12345678: Title text"
        h3_text = item.select_one("h3").get_text(strip=True) if item.select_one("h3") else ""
        if ":" in h3_text:
            parts = h3_text.split(":", 1)
            vergabe_id = parts[0].strip()
            titel = parts[1].strip() if len(parts) > 1 else h3_text
        else:
            vergabe_id = ""
            titel = h3_text

        # Extract table cells
        tds = item.select("td")
        ausschreibungsstelle = clean_text(tds[0].get_text()) if len(tds) > 0 else ""
        ausschreibungsart = clean_text(tds[2].get_text()) if len(tds) > 2 else ""

        # Extract deadline using regex
        naechste_frist = ""
        item_html = str(item)
        frist_match = re.search(r'frist</th><td>(.*?)</td></tr>', item_html)
        if frist_match:
            frist_text = frist_match.group(1)
            # Limit to datetime format (max 19 chars for DD.MM.YYYY HH:MM:SS)
            naechste_frist = frist_text[:19] if len(frist_text) > 19 else frist_text

        return TenderResult(
            portal=self.PORTAL_NAME,
            suchbegriff=None,
            suchzeitpunkt=now,
            vergabe_id=vergabe_id,
            link=link,
            titel=titel,
            ausschreibungsstelle=ausschreibungsstelle,
            ausfuehrungsort="",  # Not provided by BGE
            ausschreibungsart=ausschreibungsart,
            naechste_frist=naechste_frist,
            veroeffentlicht="",  # Not provided by BGE
        )
