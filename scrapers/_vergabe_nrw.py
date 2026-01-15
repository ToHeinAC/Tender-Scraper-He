"""
Scraper for Vergabe NRW (North Rhine-Westphalia Procurement).

URL: https://www.evergabe.nrw.de
Government tenders from North Rhine-Westphalia, Germany.
"""

import re
import time
from datetime import datetime
from typing import List
import logging

from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException

from scrapers.base import BaseScraper, TenderResult, ScraperError
from scrapers.registry import register_scraper
from scrapers.utils import clean_text


@register_scraper
class VergabeNRWScraper(BaseScraper):
    """Scraper for evergabe.nrw.de procurement portal."""

    PORTAL_NAME = "vergabe_nrw"
    PORTAL_URL = "https://www.evergabe.nrw.de/VMPCenter/common/project/search.do?method=showExtendedSearch&fromExternal=true"
    REQUIRES_SELENIUM = True

    # Number of pages to scrape
    MAX_PAGES = 5

    def scrape(self) -> List[TenderResult]:
        """
        Execute scraping logic for Vergabe NRW portal.

        Returns:
            List of TenderResult objects
        """
        all_results = []

        try:
            # Navigate to search page
            self.driver.get(self.PORTAL_URL)
            self.accept_cookies()
            time.sleep(2)

            # Scrape multiple pages
            for page in range(self.MAX_PAGES):
                self.logger.debug(f"Scraping page {page + 1}")

                # Get page HTML
                html = self.driver.page_source
                soup = BeautifulSoup(html, "lxml")

                # Parse current page results
                results = self._parse_results(soup)
                all_results.extend(results)

                # Try to go to next page
                if page < self.MAX_PAGES - 1:
                    if not self._click_next_page():
                        self.logger.debug("No more pages available")
                        break
                    time.sleep(2)

        except Exception as e:
            self.logger.error(f"Vergabe NRW scraping failed: {e}")
            raise ScraperError(self.PORTAL_NAME, str(e)) from e

        return all_results

    def _click_next_page(self) -> bool:
        """
        Click the next page button.

        Returns:
            True if successful, False if no more pages
        """
        try:
            next_button = self.driver.find_element(By.XPATH, '//*[@id="nextPage"]')
            if next_button.is_displayed() and next_button.is_enabled():
                next_button.click()
                return True
        except NoSuchElementException:
            pass
        except Exception as e:
            self.logger.debug(f"Next page click failed: {e}")

        return False

    def _parse_results(self, soup: BeautifulSoup) -> List[TenderResult]:
        """
        Parse Vergabe NRW tender page HTML.

        Args:
            soup: BeautifulSoup object of page HTML

        Returns:
            List of TenderResult objects
        """
        results = []
        now = datetime.now()

        try:
            # Find the list template div
            list_template = soup.select_one("div[id=listTemplate]")
            if not list_template:
                self.logger.warning("No listTemplate found")
                return results

            # Get all table cells (skip header row)
            cells = list_template.find_all("td")[1:]
            self.logger.debug(f"Found {len(cells)} table cells")

            # Each row has 6 columns
            cols = 6
            num_rows = len(cells) // cols

            for row in range(num_rows):
                try:
                    result = self._parse_row(cells, row, cols, now)
                    if result:
                        results.append(result)
                except Exception as e:
                    self.logger.warning(f"Failed to parse row {row}: {e}")
                    continue

        except Exception as e:
            self.logger.error(f"Failed to parse Vergabe NRW page: {e}")

        return results

    def _parse_row(self, cells, row: int, cols: int, now: datetime) -> TenderResult:
        """
        Parse a single table row.

        Args:
            cells: List of all table cells
            row: Row index
            cols: Number of columns per row
            now: Current timestamp

        Returns:
            TenderResult object
        """
        base_idx = row * cols

        # Column 0: Publication date (veröffentlicht)
        veroeffentlicht = clean_text(cells[base_idx + 0].get_text())

        # Column 1: Deadline (nächste Frist)
        naechste_frist = clean_text(cells[base_idx + 1].get_text())

        # Column 2: Title (Titel)
        titel = clean_text(cells[base_idx + 2].get_text())

        # Column 3: Procurement type (Ausschreibungsart)
        ausschreibungsart = clean_text(cells[base_idx + 3].get_text())

        # Column 4: Organization (Ausschreibungsstelle)
        ausschreibungsstelle = clean_text(cells[base_idx + 4].get_text())

        # Column 5: Link and ID
        link_cell = cells[base_idx + 5]
        link = ""
        vergabe_id = ""

        link_elem = link_cell.select_one("a")
        if link_elem and link_elem.has_attr("href"):
            href = link_elem["href"]
            # Extract actual URL from JavaScript popup call
            link_match = re.search(r"Popup\(['\"]([^'\"]+)['\"]", str(href))
            if link_match:
                link = link_match.group(1)

            # Extract ID from URL
            id_match = re.search(r"pid=(\d+)", link)
            if id_match:
                vergabe_id = id_match.group(1)

        return TenderResult(
            portal=self.PORTAL_NAME,
            suchbegriff=None,
            suchzeitpunkt=now,
            vergabe_id=vergabe_id,
            link=link,
            titel=titel,
            ausschreibungsstelle=ausschreibungsstelle,
            ausfuehrungsort="",  # Not provided
            ausschreibungsart=ausschreibungsart,
            naechste_frist=naechste_frist,
            veroeffentlicht=veroeffentlicht,
        )
