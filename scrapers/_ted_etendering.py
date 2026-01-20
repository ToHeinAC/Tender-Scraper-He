"""
Scraper for TED eTendering (EU Tenders Portal).

URL: https://etendering.ted.europa.eu
European Union public procurement tenders from Tenders Electronic Daily.

Note: Portal structure may have changed. This implementation includes
multiple fallback selectors to handle potential redesigns.
"""

import re
import time
from datetime import datetime
from typing import List

from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException, TimeoutException

from scrapers.base import BaseScraper, TenderResult, ScraperError
from scrapers.registry import register_scraper
from scrapers.utils import clean_text, normalize_url


@register_scraper
class TedETenderingScraper(BaseScraper):
    """Scraper for TED eTendering EU procurement portal."""

    PORTAL_NAME = "ted_etendering"
    PORTAL_URL = "https://etendering.ted.europa.eu/cft/cft-search.html"
    BASE_URL = "https://etendering.ted.europa.eu"
    REQUIRES_SELENIUM = True

    # URL parameters for filtering
    SEARCH_PARAMS = {
        "_caList": "1",
        "_procedureTypeForthcoming": "1",
        "_procedureTypeOngoing": "1",
        "maxResults": "100",
        "confirm": "Search",
    }

    # Cookie consent selectors for EU portal
    COOKIE_SELECTORS = [
        "#cookie-consent-accept",
        ".eu-cookie-compliance-accept",
        "//button[contains(text(), 'Accept')]",
        "//button[contains(text(), 'Akzeptieren')]",
        "//a[contains(@class, 'accept-cookie')]",
        ".cck-actions button",
    ]

    def _build_search_url(self) -> str:
        """Build search URL with parameters."""
        params = "&".join(f"{k}={v}" for k, v in self.SEARCH_PARAMS.items())
        return f"{self.PORTAL_URL}?{params}"

    def scrape(self) -> List[TenderResult]:
        """
        Execute scraping logic for TED eTendering portal.

        Returns:
            List of TenderResult objects
        """
        results = []

        try:
            search_url = self._build_search_url()
            self.logger.info(f"Navigating to: {search_url}")
            self.driver.get(search_url)
            time.sleep(3)

            self.accept_cookies()
            time.sleep(2)

            # Parse results from page
            html = self.driver.page_source
            soup = BeautifulSoup(html, "lxml")
            results = self._parse_results(soup)

            # Try pagination if results found
            if results:
                results.extend(self._scrape_additional_pages(soup))

        except Exception as e:
            self.logger.error(f"TED eTendering scraping failed: {e}")
            raise ScraperError(self.PORTAL_NAME, str(e)) from e

        return results

    def _scrape_additional_pages(self, soup: BeautifulSoup) -> List[TenderResult]:
        """Scrape additional result pages if pagination exists."""
        additional_results = []
        max_pages = 5  # Limit pages to avoid excessive scraping

        for page in range(2, max_pages + 1):
            try:
                # Look for next page link or pagination
                next_selectors = [
                    f"//a[contains(@href, 'page={page}')]",
                    ".pagination .next a",
                    "a.next-page",
                    f"//a[text()='{page}']",
                ]

                next_btn = None
                for selector in next_selectors:
                    try:
                        if selector.startswith("//"):
                            next_btn = self.driver.find_element(By.XPATH, selector)
                        else:
                            next_btn = self.driver.find_element(By.CSS_SELECTOR, selector)
                        if next_btn.is_displayed():
                            break
                    except NoSuchElementException:
                        continue

                if not next_btn:
                    break

                next_btn.click()
                time.sleep(2)

                html = self.driver.page_source
                soup = BeautifulSoup(html, "lxml")
                page_results = self._parse_results(soup)

                if not page_results:
                    break

                additional_results.extend(page_results)
                self.logger.debug(f"Page {page}: found {len(page_results)} tenders")

            except Exception as e:
                self.logger.debug(f"Pagination stopped at page {page}: {e}")
                break

        return additional_results

    def _parse_results(self, soup: BeautifulSoup) -> List[TenderResult]:
        """
        Parse TED eTendering results.

        Args:
            soup: BeautifulSoup object of page HTML

        Returns:
            List of TenderResult objects
        """
        results = []
        now = datetime.now()

        # Try multiple table selectors (old and potential new)
        table_selectors = [
            "table.strongTable",
            "table.results-table",
            ".cft-results table",
            "#searchResults table",
            "table[class*='result']",
            ".search-results table",
        ]

        table = None
        for selector in table_selectors:
            table = soup.select_one(selector)
            if table:
                self.logger.debug(f"Found table with selector: {selector}")
                break

        # Fallback: find any table with data rows
        if not table:
            tables = soup.select("table")
            for t in tables:
                rows = t.select("tr")
                for row in rows:
                    cells = row.select("td")
                    if len(cells) >= 5:
                        table = t
                        self.logger.debug("Found table by searching all tables")
                        break
                if table:
                    break

        if not table:
            self.logger.warning("No results table found on TED eTendering")
            self._save_debug_html(soup)
            return results

        rows = table.select("tr")
        self.logger.debug(f"Found {len(rows)} total rows")

        for row in rows:
            cells = row.select("td")
            if len(cells) < 5:
                continue

            try:
                result = self._parse_row(cells, now)
                if result and result.titel:
                    results.append(result)
            except Exception as e:
                self.logger.warning(f"Failed to parse TED row: {e}")
                continue

        return results

    def _parse_row(self, cells, now: datetime) -> TenderResult:
        """
        Parse a single result row.

        Args:
            cells: List of table cells (td elements)
            now: Current timestamp

        Returns:
            TenderResult object or None
        """
        # Column mapping from old implementation:
        # 0: Marker/checkbox, 1: Reference ID, 2: Title+Link, 3: Organization
        # 4: Status, 5: Published, 6: Deadline
        # Structure may vary - use flexible parsing

        vergabe_id = ""
        titel = ""
        link = ""
        ausschreibungsstelle = ""
        status = ""
        veroeffentlicht = ""
        naechste_frist = ""

        # Try standard 7-column layout first
        if len(cells) >= 7:
            vergabe_id = clean_text(cells[1].get_text())

            # Title and link from column 2
            link_elem = cells[2].select_one("a")
            if link_elem:
                titel = link_elem.get("title", "") or clean_text(link_elem.get_text())
                link = link_elem.get("href", "")
            else:
                titel = clean_text(cells[2].get_text())

            ausschreibungsstelle = clean_text(cells[3].get_text())
            status = clean_text(cells[4].get_text())
            veroeffentlicht = self._normalize_date(clean_text(cells[5].get_text()))
            naechste_frist = self._normalize_date(clean_text(cells[6].get_text()))

        elif len(cells) >= 5:
            # Simplified 5-column layout
            vergabe_id = clean_text(cells[0].get_text())

            # Find link in any cell
            for i, cell in enumerate(cells[1:4], 1):
                link_elem = cell.select_one("a")
                if link_elem:
                    titel = link_elem.get("title", "") or clean_text(link_elem.get_text())
                    link = link_elem.get("href", "")
                    break

            if not titel:
                titel = clean_text(cells[1].get_text())

            ausschreibungsstelle = clean_text(cells[2].get_text()) if len(cells) > 2 else ""

            # Extract dates from remaining cells
            for cell in cells[3:]:
                cell_text = clean_text(cell.get_text())
                if self._looks_like_date(cell_text):
                    if not veroeffentlicht:
                        veroeffentlicht = self._normalize_date(cell_text)
                    elif not naechste_frist:
                        naechste_frist = self._normalize_date(cell_text)

        # Normalize link
        if link and not link.startswith("http"):
            link = normalize_url(link, self.BASE_URL)

        # Filter out closed tenders
        if status and "open" not in status.lower() and "forthcoming" not in status.lower():
            # Check if explicitly closed
            if "closed" in status.lower() or "awarded" in status.lower():
                return None

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
            ausfuehrungsort="",  # Not typically provided
            ausschreibungsart="",  # Not directly in table
            naechste_frist=naechste_frist,
            veroeffentlicht=veroeffentlicht,
        )

    def _normalize_date(self, date_str: str) -> str:
        """Normalize date format (convert / to .)."""
        if not date_str:
            return ""
        # Replace / with . for consistent German format
        normalized = date_str.replace("/", ".")
        return normalized

    def _looks_like_date(self, text: str) -> bool:
        """Check if text looks like a date."""
        if not text:
            return False
        # Check for date patterns
        date_patterns = [
            r'\d{1,2}[./]\d{1,2}[./]\d{2,4}',
            r'\d{4}[.-]\d{2}[.-]\d{2}',
        ]
        for pattern in date_patterns:
            if re.search(pattern, text):
                return True
        return False

    def _save_debug_html(self, soup: BeautifulSoup) -> None:
        """Save HTML for debugging when parsing fails."""
        try:
            debug_path = f"data/ted_debug_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
            with open(debug_path, "w", encoding="utf-8") as f:
                f.write(str(soup))
            self.logger.debug(f"Saved debug HTML to: {debug_path}")
        except Exception as e:
            self.logger.debug(f"Could not save debug HTML: {e}")
