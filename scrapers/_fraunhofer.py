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
    PORTAL_BASE_URL = "https://vergabe.fraunhofer.de/NetServer/PublicationSearchControllerServlet"
    PORTAL_URL = f"{PORTAL_BASE_URL}?Searchkey=&function=Search&Category=InvitationToTender&TenderLaw=All&TenderKind=All&Authority="
    REQUIRES_SELENIUM = True

    def _build_search_url(self, keyword: str = "") -> str:
        """
        Build the search URL with optional keyword.

        This portal supports "Directly put item" strategy via URL parameter:
        - Searchkey={keyword} for keyword search
        - Searchkey= (empty) for all tenders

        Args:
            keyword: Optional search keyword for URL-based filtering

        Returns:
            Full search URL
        """
        params = {
            "Searchkey": keyword,
            "function": "Search",
            "Category": "InvitationToTender",
            "TenderLaw": "All",
            "TenderKind": "All",
            "Authority": "",
        }
        # Build URL manually to preserve empty string parameters
        param_str = "&".join(f"{k}={v}" for k, v in params.items())
        return f"{self.PORTAL_BASE_URL}?{param_str}"

    def scrape(self, keywords: List[str] = None) -> List[TenderResult]:
        """
        Execute scraping logic for Fraunhofer portal.

        Supports two scraping strategies:
        1. "First Scrape, then check" (default): Fetch all tenders, filter later
           - Called with no keywords: scrape()
        2. "Directly put item": Search portal with each keyword via URL
           - Called with keywords: scrape(keywords=["Rückbau", "Dekontamination"])
           - Each keyword is searched via Searchkey={keyword} URL parameter

        Args:
            keywords: Optional list of keywords for URL-based search.
                      If None, fetches all tenders (strategy 1).
                      If provided, searches for each keyword (strategy 2).

        Returns:
            List of TenderResult objects
        """
        all_results = []
        seen_ids = set()  # Deduplicate results across keyword searches

        try:
            # Determine search terms: all tenders (empty keyword) or specific keywords
            search_terms = keywords if keywords else [""]

            for idx, keyword in enumerate(search_terms):
                if keyword:
                    self.logger.info(f"Searching for keyword '{keyword}' ({idx + 1}/{len(search_terms)})")

                # Build and navigate to search URL
                search_url = self._build_search_url(keyword)
                self.logger.info(f"Navigating to: {search_url}")
                self.driver.get(search_url)
                time.sleep(3)

                # Accept cookies only on first page
                if idx == 0:
                    self.accept_cookies()
                time.sleep(2)

                # Get page HTML
                html = self.driver.page_source
                soup = BeautifulSoup(html, "lxml")

                # Parse results
                results = self._parse_results(soup)

                # Deduplicate and optionally tag with keyword
                for result in results:
                    if result.vergabe_id and result.vergabe_id in seen_ids:
                        continue
                    if result.vergabe_id:
                        seen_ids.add(result.vergabe_id)
                    # Tag result with keyword if using strategy 2
                    if keyword:
                        result.suchbegriff = keyword
                    all_results.append(result)

                if keyword:
                    self.logger.info(f"Found {len(results)} tenders for '{keyword}'")

            self.logger.info(f"Found {len(all_results)} total tenders (deduplicated)")

        except Exception as e:
            self.logger.error(f"Fraunhofer scraping failed: {e}")
            raise ScraperError(self.PORTAL_NAME, str(e)) from e

        return all_results

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
