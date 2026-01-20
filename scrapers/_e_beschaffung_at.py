"""
Scraper for Austrian e-Beschaffung procurement portal.

URL: https://e-beschaffung.at
Austrian public procurement portal operated by vemap.
"""

import re
import time
from datetime import datetime
from typing import List

from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

from scrapers.base import BaseScraper, TenderResult, ScraperError
from scrapers.registry import register_scraper
from scrapers.utils import clean_text, normalize_url


@register_scraper
class EBeschaffungATScraper(BaseScraper):
    """Scraper for e-beschaffung.at procurement portal."""

    PORTAL_NAME = "e_beschaffung_at"
    PORTAL_URL = "https://e-beschaffung.at/publications"
    BASE_URL = "https://e-beschaffung.at"
    REQUIRES_SELENIUM = True

    # Maximum pages to scrape (50 items per page)
    MAX_PAGES = 5

    # Cookie consent selectors
    COOKIE_SELECTORS = [
        "#cookie-accept",
        ".cookie-accept",
        "button.accept-cookies",
        "//button[contains(text(), 'Akzeptieren')]",
        "//button[contains(text(), 'Accept')]",
        "//a[contains(text(), 'Akzeptieren')]",
        ".cc-btn.cc-accept",
    ]

    def _build_search_url(self, page: int = 1) -> str:
        """
        Build the search URL with Austrian filter and pagination.

        Args:
            page: Page number (1-indexed)

        Returns:
            Full search URL
        """
        # Filter for Austrian tenders only (nuts=AT)
        return f"{self.PORTAL_URL}?nuts=AT&page={page}"

    def scrape(self) -> List[TenderResult]:
        """
        Execute scraping logic for e-beschaffung.at portal.

        Returns:
            List of TenderResult objects
        """
        all_results = []
        seen_ids = set()

        try:
            # Navigate to first page
            search_url = self._build_search_url(page=1)
            self.logger.info(f"Navigating to: {search_url}")
            self.driver.get(search_url)

            # Wait for page to load
            time.sleep(3)
            self.accept_cookies()
            time.sleep(2)

            # Wait for table to load
            try:
                WebDriverWait(self.driver, 15).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "table"))
                )
            except TimeoutException:
                self.logger.warning("Table not found, trying to proceed anyway")
                time.sleep(3)

            # Scrape multiple pages
            for page in range(1, self.MAX_PAGES + 1):
                if page > 1:
                    # Navigate to next page
                    page_url = self._build_search_url(page=page)
                    self.logger.debug(f"Navigating to page {page}: {page_url}")
                    self.driver.get(page_url)
                    time.sleep(2)

                # Get page HTML
                html = self.driver.page_source
                soup = BeautifulSoup(html, "lxml")

                # Parse results
                results = self._parse_results(soup)

                if not results:
                    self.logger.info(f"No more results on page {page}")
                    break

                # Deduplicate results
                new_count = 0
                for result in results:
                    if result.vergabe_id and result.vergabe_id in seen_ids:
                        continue
                    if result.vergabe_id:
                        seen_ids.add(result.vergabe_id)
                    all_results.append(result)
                    new_count += 1

                self.logger.info(f"Page {page}: found {new_count} new tenders")

                # Check if we've reached the last page
                if not self._has_next_page(soup):
                    self.logger.info("Reached last page")
                    break

            self.logger.info(f"Found {len(all_results)} total tenders")

        except Exception as e:
            self.logger.error(f"e-beschaffung.at scraping failed: {e}")
            raise ScraperError(self.PORTAL_NAME, str(e)) from e

        return all_results

    def _has_next_page(self, soup: BeautifulSoup) -> bool:
        """
        Check if there's a next page available.

        Args:
            soup: BeautifulSoup object of current page

        Returns:
            True if next page exists
        """
        # Look for pagination controls
        pagination = soup.select_one(".pagination, nav[aria-label*='pagination'], .pager")
        if not pagination:
            return False

        # Check for "next" or "›" link that's not disabled
        next_selectors = [
            "a[rel='next']",
            ".pagination-next:not(.disabled)",
            "a:contains('›'):not(.disabled)",
            "li.next:not(.disabled) a",
        ]

        for selector in next_selectors:
            try:
                next_link = pagination.select_one(selector)
                if next_link:
                    return True
            except Exception:
                continue

        # Also check if "›" symbol is present and clickable
        all_links = pagination.find_all("a")
        for link in all_links:
            if "›" in link.get_text() and "disabled" not in link.get("class", []):
                return True

        return False

    def _parse_results(self, soup: BeautifulSoup) -> List[TenderResult]:
        """
        Parse e-beschaffung.at tender page HTML.

        Table structure:
        - Column 1: Status (aktiv)
        - Column 2: Publication date (DD.MM.YYYY)
        - Column 3: Deadline (DD.MM.YYYY)
        - Column 4: Title (with link to /publications/show/[ID])
        - Column 5: Organization

        Args:
            soup: BeautifulSoup object of page HTML

        Returns:
            List of TenderResult objects
        """
        results = []
        now = datetime.now()

        # Find table rows
        table_selectors = [
            "table tbody tr",
            "table tr:not(:first-child)",
            ".publication-list tr",
        ]

        rows = []
        for selector in table_selectors:
            rows = soup.select(selector)
            if rows:
                self.logger.debug(f"Found {len(rows)} rows with selector: {selector}")
                break

        if not rows:
            self.logger.warning("No tender rows found")
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
        if len(cells) < 4:
            return None

        # Extract fields based on column structure:
        # Column 0: Status (aktiv)
        # Column 1: Publication date
        # Column 2: Deadline
        # Column 3: Title with link
        # Column 4: Organization

        status = clean_text(cells[0].get_text()) if len(cells) > 0 else ""
        veroeffentlicht = clean_text(cells[1].get_text()) if len(cells) > 1 else ""
        naechste_frist = clean_text(cells[2].get_text()) if len(cells) > 2 else ""

        # Extract title and link from column 3
        titel = ""
        link = ""
        vergabe_id = ""

        if len(cells) > 3:
            link_elem = cells[3].find("a")
            if link_elem:
                titel = clean_text(link_elem.get_text())
                href = link_elem.get("href", "")
                if href:
                    link = normalize_url(href, self.BASE_URL)
                    # Extract ID from URL like /publications/show/2498213
                    id_match = re.search(r"/publications/show/(\d+)", href)
                    if id_match:
                        vergabe_id = id_match.group(1)
            else:
                titel = clean_text(cells[3].get_text())

        # Extract organization from column 4
        ausschreibungsstelle = ""
        if len(cells) > 4:
            ausschreibungsstelle = clean_text(cells[4].get_text())

        # Skip inactive tenders
        if status and status.lower() != "aktiv":
            return None

        return TenderResult(
            portal=self.PORTAL_NAME,
            suchbegriff=None,
            suchzeitpunkt=now,
            vergabe_id=vergabe_id,
            link=link,
            titel=titel,
            ausschreibungsstelle=ausschreibungsstelle,
            ausfuehrungsort="",  # Not provided in this portal
            ausschreibungsart="",  # Not provided in this portal
            naechste_frist=naechste_frist,
            veroeffentlicht=veroeffentlicht,
        )
