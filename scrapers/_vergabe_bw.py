"""
Scraper for Vergabe Baden-Wuerttemberg (NetServer).

URL: https://vergabe.landbw.de/NetServer/
Government tenders from Baden-Wuerttemberg, Germany.
"""

import time
from datetime import datetime
from typing import List
import logging

from bs4 import BeautifulSoup

from scrapers.base import BaseScraper, TenderResult, ScraperError
from scrapers.registry import register_scraper
from scrapers.utils import clean_text


@register_scraper
class VergabeBWScraper(BaseScraper):
    """Scraper for vergabe.landbw.de procurement portal (NetServer)."""

    PORTAL_NAME = "vergabe_bw"
    PORTAL_URL = "https://vergabe.landbw.de/NetServer/index.jsp?function=Search&OrderBy=Publishing&Order=desc"
    REQUIRES_SELENIUM = True

    def scrape(self) -> List[TenderResult]:
        """
        Execute scraping logic for Vergabe BW portal.

        Returns:
            List of TenderResult objects
        """
        results = []

        try:
            # Navigate to search page
            self.driver.get(self.PORTAL_URL)
            self.accept_cookies()
            time.sleep(3)

            # Get page HTML
            html = self.driver.page_source
            soup = BeautifulSoup(html, "lxml")

            # Parse results
            results = self._parse_results(soup)

        except Exception as e:
            self.logger.error(f"Vergabe BW scraping failed: {e}")
            raise ScraperError(self.PORTAL_NAME, str(e)) from e

        return results

    def _parse_results(self, soup: BeautifulSoup) -> List[TenderResult]:
        """
        Parse Vergabe BW tender page HTML.

        Args:
            soup: BeautifulSoup object of page HTML

        Returns:
            List of TenderResult objects
        """
        results = []
        now = datetime.now()

        # Find all tender rows
        rows = soup.select("tr.tableRow.clickable-row.publicationDetail")
        self.logger.debug(f"Found {len(rows)} tender rows")

        for row in rows:
            try:
                result = self._parse_row(row, now)
                if result:
                    results.append(result)
            except Exception as e:
                self.logger.warning(f"Failed to parse row: {e}")
                continue

        return results

    def _parse_row(self, row, now: datetime) -> TenderResult:
        """
        Parse a single table row.

        Args:
            row: BeautifulSoup row element
            now: Current timestamp

        Returns:
            TenderResult object
        """
        cells = row.find_all("td")

        if len(cells) < 5:
            self.logger.warning(f"Row has insufficient cells: {len(cells)}")
            return None

        # Extract data from table columns
        # Column 0: Publication date (veröffentlicht)
        veroeffentlicht = clean_text(cells[0].get_text())

        # Column 1: Title (Titel)
        titel = clean_text(cells[1].get_text())

        # Column 2: Organization (Ausschreibungsstelle)
        ausschreibungsstelle = clean_text(cells[2].get_text())

        # Column 3: Procurement type (Ausschreibungsart)
        ausschreibungsart = clean_text(cells[3].get_text())

        # Column 4: Deadline (nächste Frist)
        naechste_frist = clean_text(cells[4].get_text())

        # Extract data attributes for link construction
        vergabe_id = row.get("data-oid", "")
        category = row.get("data-category", "")

        # Construct detail link
        link = ""
        if vergabe_id and category:
            link = (
                f"https://vergabe.landbw.de/NetServer/PublicationControllerServlet"
                f"?function=Detail&TOID={vergabe_id}&Category={category}"
            )

        return TenderResult(
            portal=self.PORTAL_NAME,
            suchbegriff=None,
            suchzeitpunkt=now,
            vergabe_id=vergabe_id,
            link=link,
            titel=titel,
            ausschreibungsstelle=ausschreibungsstelle,
            ausfuehrungsort="",  # Not provided by this portal
            ausschreibungsart=ausschreibungsart,
            naechste_frist=naechste_frist,
            veroeffentlicht=veroeffentlicht,
        )
