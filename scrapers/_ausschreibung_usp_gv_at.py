"""
Scraper for Austrian Public Procurement Portal (USP).

URL: https://ausschreibungen.usp.gv.at
Austrian government tenders from the Unternehmensserviceportal.
"""

import re
import time
from datetime import datetime, timedelta
from typing import List
from urllib.parse import urlencode

from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

from scrapers.base import BaseScraper, TenderResult, ScraperError
from scrapers.registry import register_scraper
from scrapers.utils import clean_text


@register_scraper
class AusschreibungUSPScraper(BaseScraper):
    """Scraper for ausschreibungen.usp.gv.at procurement portal."""

    PORTAL_NAME = "ausschreibung_usp_gv_at"
    PORTAL_URL = "https://ausschreibungen.usp.gv.at/at.gv.bmdw.eproc-p/public/tenderlist"
    REQUIRES_SELENIUM = True

    # Default date range: last 7 days
    DEFAULT_DATE_RANGE_DAYS = 7

    # Cookie consent selectors specific to this portal
    COOKIE_SELECTORS = [
        "button.btn-accept-all",
        "#cookie-accept-all",
        "//button[contains(text(), 'Alle akzeptieren')]",
        "//button[contains(text(), 'Akzeptieren')]",
        ".cookie-consent-accept",
    ]

    def _build_search_url(self, from_date: str, to_date: str) -> str:
        """
        Build the search URL with date filters.

        Args:
            from_date: Start date (YYYY-MM-DD)
            to_date: End date (YYYY-MM-DD)

        Returns:
            Full search URL
        """
        params = {
            "q": "",
            "loaded": "true",
            "orderColumn": "2",
            "orderDir": "desc",
            "pageLength": "100",
            "fromdate": from_date,
            "todate": to_date,
        }
        return f"{self.PORTAL_URL}?{urlencode(params)}"

    def scrape(self) -> List[TenderResult]:
        """
        Execute scraping logic for Austrian USP portal.

        Returns:
            List of TenderResult objects
        """
        all_results = []

        try:
            # Calculate date range
            today = datetime.now()
            from_date = (today - timedelta(days=self.DEFAULT_DATE_RANGE_DAYS)).strftime("%Y-%m-%d")
            to_date = today.strftime("%Y-%m-%d")

            # Build and navigate to search URL
            search_url = self._build_search_url(from_date, to_date)
            self.logger.info(f"Navigating to: {search_url}")
            self.driver.get(search_url)

            # Accept cookies if present
            time.sleep(2)
            self.accept_cookies()
            time.sleep(2)

            # Wait for table to load
            try:
                WebDriverWait(self.driver, 15).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "table.table, .tender-list, #tenderTable"))
                )
            except TimeoutException:
                self.logger.warning("Table not found with primary selectors, trying alternatives")
                time.sleep(3)

            # Get page HTML
            html = self.driver.page_source
            soup = BeautifulSoup(html, "lxml")

            # Parse results
            results = self._parse_results(soup)
            all_results.extend(results)

            self.logger.info(f"Found {len(all_results)} tenders")

        except Exception as e:
            self.logger.error(f"USP Austria scraping failed: {e}")
            raise ScraperError(self.PORTAL_NAME, str(e)) from e

        return all_results

    def _parse_results(self, soup: BeautifulSoup) -> List[TenderResult]:
        """
        Parse USP Austria tender page HTML.

        Args:
            soup: BeautifulSoup object of page HTML

        Returns:
            List of TenderResult objects
        """
        results = []
        now = datetime.now()

        # Try multiple table selectors
        table_selectors = [
            "table.table tbody tr",
            "table tbody tr",
            ".tender-list tr",
            "#tenderTable tbody tr",
            "table.dataTable tbody tr",
        ]

        rows = []
        for selector in table_selectors:
            rows = soup.select(selector)
            if rows:
                self.logger.debug(f"Found {len(rows)} rows with selector: {selector}")
                break

        if not rows:
            self.logger.warning("No tender rows found")
            # Save HTML for debugging
            self._save_debug_html(soup)
            return results

        for row in rows:
            try:
                result = self._parse_row(row, now)
                if result and result.titel:
                    results.append(result)
            except Exception as e:
                self.logger.warning(f"Failed to parse row: {e}")
                continue

        return results

    def _parse_row(self, row, now: datetime) -> TenderResult:
        """
        Parse a single table row.

        Args:
            row: BeautifulSoup element for table row
            now: Current timestamp

        Returns:
            TenderResult object or None
        """
        cells = row.find_all("td")
        if len(cells) < 3:
            return None

        # Extract link and title from first cell (usually)
        link = ""
        titel = ""
        vergabe_id = ""

        # Try to find link in any cell
        link_elem = row.select_one("a[href]")
        if link_elem:
            href = link_elem.get("href", "")
            if href and not href.startswith("#"):
                # Make absolute URL if relative
                base_url = "https://ausschreibungen.usp.gv.at/at.gv.bmdw.eproc-p/public/"
                if href.startswith("/"):
                    link = f"https://ausschreibungen.usp.gv.at{href}"
                elif href.startswith("http"):
                    link = href
                else:
                    # Relative URL like 'tender-detail?object=...'
                    link = f"{base_url}{href}"

                # Extract ID from object parameter (format: object=UUID-...-ID)
                id_match = re.search(r"object=([^&]+)", link)
                if id_match:
                    vergabe_id = id_match.group(1)
                else:
                    # Try other ID patterns
                    id_match = re.search(r"[?&]id=([^&]+)", link)
                    if id_match:
                        vergabe_id = id_match.group(1)

            titel = clean_text(link_elem.get_text())

        # If no title from link, try first cell
        if not titel and cells:
            titel = clean_text(cells[0].get_text())

        # Extract other fields based on actual column layout:
        # Column 0: Bezeichnung (Title) - already extracted from link
        # Column 1: Organisation (Ausschreibungsstelle)
        # Column 2: Veröffentlicht am (Published date)
        # Column 3: Angebotsfrist (Deadline)
        ausschreibungsstelle = ""
        ausschreibungsart = ""  # Not provided in this portal
        naechste_frist = ""
        veroeffentlicht = ""

        if len(cells) >= 2:
            ausschreibungsstelle = clean_text(cells[1].get_text())
        if len(cells) >= 3:
            veroeffentlicht = clean_text(cells[2].get_text())
        if len(cells) >= 4:
            naechste_frist = clean_text(cells[3].get_text())

        return TenderResult(
            portal=self.PORTAL_NAME,
            suchbegriff=None,
            suchzeitpunkt=now,
            vergabe_id=vergabe_id,
            link=link,
            titel=titel,
            ausschreibungsstelle=ausschreibungsstelle,
            ausfuehrungsort="",  # Not typically provided
            ausschreibungsart=ausschreibungsart,
            naechste_frist=naechste_frist,
            veroeffentlicht=veroeffentlicht,
        )

    def _save_debug_html(self, soup: BeautifulSoup) -> None:
        """Save HTML for debugging purposes."""
        try:
            debug_path = f"/tmp/usp_debug_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
            with open(debug_path, "w", encoding="utf-8") as f:
                f.write(str(soup))
            self.logger.debug(f"Saved debug HTML to: {debug_path}")
        except Exception as e:
            self.logger.debug(f"Could not save debug HTML: {e}")
