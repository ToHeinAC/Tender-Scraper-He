"""
Scraper for SIMAP.CH (Swiss Public Procurement Portal).

URL: https://www.simap.ch
Swiss government tenders from Informationssystem über das öffentliche Beschaffungswesen.

Note: The old portal (old.simap.ch) was deprecated in 2024.
This implementation targets the new portal at www.simap.ch.
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
class SimapChScraper(BaseScraper):
    """Scraper for simap.ch Swiss procurement portal."""

    PORTAL_NAME = "simap_ch"
    PORTAL_URL = "https://www.simap.ch/shabforms/COMMON/search/searchForm.jsf"
    BASE_URL = "https://www.simap.ch"
    REQUIRES_SELENIUM = True

    # Cookie consent selectors for Swiss portal
    COOKIE_SELECTORS = [
        ".popin_tc_privacy_btn_accepter",
        "#accept-cookies",
        "#onetrust-accept-btn-handler",
        "button.ch-btn-accept",
        "//button[contains(text(), 'Akzeptieren')]",
        "//button[contains(text(), 'Accept')]",
        "//button[contains(text(), 'Alle akzeptieren')]",
    ]

    def scrape(self) -> List[TenderResult]:
        """
        Execute scraping logic for SIMAP.CH portal.

        Returns:
            List of TenderResult objects
        """
        results = []

        try:
            self.logger.info(f"Navigating to {self.PORTAL_URL}")
            self.driver.get(self.PORTAL_URL)
            time.sleep(3)

            self.accept_cookies()
            time.sleep(1)

            # Try to perform search (get all recent tenders)
            results = self._perform_search_and_parse()

        except Exception as e:
            self.logger.error(f"SIMAP.CH scraping failed: {e}")
            raise ScraperError(self.PORTAL_NAME, str(e)) from e

        return results

    def _perform_search_and_parse(self) -> List[TenderResult]:
        """Perform search and parse results."""
        # Try to find and click search button
        search_selectors = [
            '//*[@id="recherche"]/div/div[3]/input',
            "input[type='submit']",
            "button[type='submit']",
            ".search-button",
            "//input[@value='Suchen']",
            "//button[contains(text(), 'Suchen')]",
            "//input[@value='Search']",
        ]

        search_clicked = False
        for selector in search_selectors:
            try:
                if selector.startswith("//"):
                    btn = self.driver.find_element(By.XPATH, selector)
                else:
                    btn = self.driver.find_element(By.CSS_SELECTOR, selector)

                if btn.is_displayed():
                    btn.click()
                    search_clicked = True
                    self.logger.debug(f"Clicked search with selector: {selector}")
                    break
            except NoSuchElementException:
                continue
            except Exception as e:
                self.logger.debug(f"Search click failed with {selector}: {e}")
                continue

        if not search_clicked:
            self.logger.warning("Could not find search button, trying to parse current page")

        time.sleep(3)

        # Scroll to load all results
        self._scroll_to_load_all()

        html = self.driver.page_source
        soup = BeautifulSoup(html, "lxml")
        return self._parse_results(soup)

    def _scroll_to_load_all(self, timeout: int = 30) -> None:
        """Scroll page to load dynamic content."""
        last_height = self.driver.execute_script("return document.body.scrollHeight")
        start_time = time.time()

        while time.time() - start_time < timeout:
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)
            new_height = self.driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                break
            last_height = new_height

    def _parse_results(self, soup: BeautifulSoup) -> List[TenderResult]:
        """
        Parse SIMAP.CH results table.

        Args:
            soup: BeautifulSoup object of page HTML

        Returns:
            List of TenderResult objects
        """
        results = []
        now = datetime.now()

        # Try multiple table selectors (old and new portal)
        table_selectors = [
            "table#resultList",
            "table.results",
            "table.tender-list",
            "#searchResults table",
            ".search-results table",
            "table[class*='result']",
        ]

        table = None
        for selector in table_selectors:
            table = soup.select_one(selector)
            if table:
                self.logger.debug(f"Found results table with: {selector}")
                break

        # Fallback: find any table with data
        if not table:
            tables = soup.select("table")
            for t in tables:
                rows = t.select("tr")
                if len(rows) > 1:  # At least header + 1 data row
                    cells = rows[1].select("td") if len(rows) > 1 else []
                    if len(cells) >= 3:
                        table = t
                        self.logger.debug("Found table by searching all tables")
                        break

        if not table:
            self.logger.warning("No results table found on SIMAP.CH")
            self._save_debug_html(soup)
            return results

        rows = table.select("tr")
        # Skip header row if present
        data_rows = rows[1:] if rows else []
        self.logger.debug(f"Found {len(data_rows)} potential tender rows")

        for row in data_rows:
            try:
                result = self._parse_row(row, now)
                if result and result.titel:
                    results.append(result)
            except Exception as e:
                self.logger.warning(f"Failed to parse SIMAP row: {e}")
                continue

        return results

    def _parse_row(self, row, now: datetime) -> TenderResult:
        """
        Parse a single table row.

        Args:
            row: BeautifulSoup element for table row
            now: Current timestamp

        Returns:
            TenderResult object or None if parsing fails
        """
        cells = row.select("td")
        if len(cells) < 3:
            return None

        # Column mapping based on old implementation:
        # 0: Date (Veröffentlicht), 1: ID, 2: Type+Deadline, 3: Title, 4: Link
        # But structure may vary - try flexible parsing

        veroeffentlicht = ""
        vergabe_id = ""
        ausschreibungsart = ""
        naechste_frist = ""
        titel = ""
        link = ""

        # Try to extract data from cells
        if len(cells) >= 5:
            # Old 5-column layout
            veroeffentlicht = clean_text(cells[0].get_text())
            vergabe_id = clean_text(cells[1].get_text())

            # Column 2 may contain type and deadline
            col2_text = str(cells[2])
            ausschreibungsart = self._extract_type(col2_text)
            naechste_frist = self._extract_deadline(col2_text)

            titel = clean_text(cells[3].get_text())

            # Extract link from column 4 or 3
            link = self._extract_link(cells[4]) or self._extract_link(cells[3])

        elif len(cells) >= 4:
            # 4-column layout
            veroeffentlicht = clean_text(cells[0].get_text())
            vergabe_id = clean_text(cells[1].get_text())
            titel = clean_text(cells[2].get_text())
            link = self._extract_link(cells[3]) or self._extract_link(cells[2])

            # Try to extract deadline from any cell
            for cell in cells:
                deadline = self._extract_deadline(str(cell))
                if deadline:
                    naechste_frist = deadline
                    break

        elif len(cells) >= 3:
            # Minimal 3-column layout
            vergabe_id = clean_text(cells[0].get_text())
            titel = clean_text(cells[1].get_text())
            link = self._extract_link(cells[2]) or self._extract_link(cells[1])

        # Also try to find link in any cell if not found
        if not link:
            link_elem = row.select_one("a[href]")
            if link_elem:
                link = link_elem.get("href", "")

        # Normalize link
        if link and not link.startswith("http"):
            link = normalize_url(link, self.BASE_URL)

        if not titel:
            return None

        return TenderResult(
            portal=self.PORTAL_NAME,
            suchbegriff=None,
            suchzeitpunkt=now,
            vergabe_id=vergabe_id,
            link=link,
            titel=titel,
            ausschreibungsstelle="",  # Not typically provided in table
            ausfuehrungsort="",
            ausschreibungsart=ausschreibungsart,
            naechste_frist=naechste_frist,
            veroeffentlicht=veroeffentlicht,
        )

    def _extract_link(self, cell) -> str:
        """Extract link URL from a cell."""
        if not cell:
            return ""
        link_elem = cell.select_one("a[href]")
        if link_elem:
            return link_elem.get("href", "")
        return ""

    def _extract_type(self, html_text: str) -> str:
        """Extract tender type from HTML text."""
        try:
            # Look for text between <br/> tags
            matches = re.findall(r'<br\s*/?>(.*?)<br\s*/?>', html_text, re.IGNORECASE)
            if matches:
                return clean_text(matches[-1].split('<br')[0])
        except Exception:
            pass
        return ""

    def _extract_deadline(self, text: str) -> str:
        """Extract deadline datetime from text."""
        try:
            # Pattern for datetime: DD.MM.YYYY HH:MM
            patterns = [
                r'(\d{1,2}\.\d{1,2}\.\d{2,4}\s+\d{1,2}:\d{2})',
                r'(\d{1,2}\.\d{1,2}\.\d{2,4})',
            ]
            for pattern in patterns:
                match = re.search(pattern, text)
                if match:
                    return match.group(1)
        except Exception:
            pass
        return ""

    def _save_debug_html(self, soup: BeautifulSoup) -> None:
        """Save HTML for debugging when parsing fails."""
        try:
            debug_path = f"data/simap_debug_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
            with open(debug_path, "w", encoding="utf-8") as f:
                f.write(str(soup))
            self.logger.debug(f"Saved debug HTML to: {debug_path}")
        except Exception as e:
            self.logger.debug(f"Could not save debug HTML: {e}")
