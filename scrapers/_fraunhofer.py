"""
Scraper for Fraunhofer Gesellschaft Procurement Portal.

URL: https://vergabe.fraunhofer.de
Research institution tenders from Fraunhofer, Germany.
"""

import re
import time
from datetime import datetime
from typing import List

from bs4 import BeautifulSoup

from scrapers.base import BaseScraper, TenderResult, ScraperError
from scrapers.registry import register_scraper
from scrapers.utils import clean_text


@register_scraper
class FraunhoferScraper(BaseScraper):
    """Scraper for vergabe.fraunhofer.de procurement portal."""

    PORTAL_NAME = "fraunhofer"
    PORTAL_URL = "https://vergabe.fraunhofer.de/NetServer/PublicationSearchControllerServlet?Searchkey=&function=Search&Category=InvitationToTender&TenderLaw=All&TenderKind=All&Authority="
    REQUIRES_SELENIUM = True

    def scrape(self) -> List[TenderResult]:
        """
        Execute scraping logic for Fraunhofer portal.

        Returns:
            List of TenderResult objects
        """
        results = []

        try:
            # Navigate to search page
            self.logger.info(f"Navigating to: {self.PORTAL_URL}")
            self.driver.get(self.PORTAL_URL)
            time.sleep(3)

            # Accept cookies
            self.accept_cookies()
            time.sleep(2)

            # Get page HTML
            html = self.driver.page_source
            soup = BeautifulSoup(html, "lxml")

            # Parse results
            results = self._parse_results(soup)

        except Exception as e:
            self.logger.error(f"Fraunhofer scraping failed: {e}")
            raise ScraperError(self.PORTAL_NAME, str(e)) from e

        return results

    def _parse_results(self, soup: BeautifulSoup) -> List[TenderResult]:
        """
        Parse Fraunhofer tender page HTML.

        Uses NetServer format similar to vergabe_bw.

        Args:
            soup: BeautifulSoup object of page HTML

        Returns:
            List of TenderResult objects
        """
        results = []
        now = datetime.now()

        # Find all tender rows (NetServer format)
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
            TenderResult object or None
        """
        # Extract title from link
        titel = ""
        link = ""
        link_elem = row.find("a")
        if link_elem:
            titel = clean_text(link_elem.get_text())
            href = link_elem.get("href", "")
            if href:
                link = f"https://vergabe.fraunhofer.de/NetServer/{href.lstrip('/')}"

        # Extract ID from data-oid attribute
        vergabe_id = ""
        oid_match = re.search(r'data-oid="([^"]+)"', str(row))
        if oid_match:
            vergabe_id = oid_match.group(1)

        # Extract type from tenderType cell
        ausschreibungsart = ""
        type_cell = row.select_one("td.tenderType")
        if type_cell:
            ausschreibungsart = clean_text(type_cell.get_text())

        # Extract deadline from tenderDeadline cell
        naechste_frist = ""
        deadline_cell = row.select_one("td.tenderDeadline")
        if deadline_cell:
            naechste_frist = clean_text(deadline_cell.get_text())

        # Extract publication date from first td
        veroeffentlicht = ""
        first_td = row.find("td")
        if first_td:
            veroeffentlicht = clean_text(first_td.get_text())

        # Extract authority from tenderAuthority cell
        ausschreibungsstelle = "Fraunhofer-Gesellschaft"
        authority_cell = row.select_one("td.tenderAuthority")
        if authority_cell:
            authority_text = clean_text(authority_cell.get_text())
            if authority_text:
                ausschreibungsstelle = f"Fraunhofer-Gesellschaft / {authority_text}"

        if not titel:
            return None

        return TenderResult(
            portal=self.PORTAL_NAME,
            suchbegriff=None,
            suchzeitpunkt=now,
            vergabe_id=vergabe_id,
            link=link,
            titel=titel,
            ausschreibungsstelle=ausschreibungsstelle,
            ausfuehrungsort="",
            ausschreibungsart=ausschreibungsart,
            naechste_frist=naechste_frist,
            veroeffentlicht=veroeffentlicht,
        )
