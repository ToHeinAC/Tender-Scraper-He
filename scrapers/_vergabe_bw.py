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
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException

from scrapers.base import BaseScraper, TenderResult, ScraperError
from scrapers.registry import register_scraper
from scrapers.utils import clean_text


@register_scraper
class VergabeBWScraper(BaseScraper):
    """Scraper for vergabe.landbw.de procurement portal (NetServer)."""

    PORTAL_NAME = "vergabe_bw"
    PORTAL_URL = "https://vergabe.landbw.de/NetServer/index.jsp?function=Search&OrderBy=Publishing&Order=desc"
    REQUIRES_SELENIUM = True

    # Maximum pages to scrape (236 tenders / ~25 per page = ~10 pages)
    MAX_PAGES = 10

    def scrape(self) -> List[TenderResult]:
        """
        Execute scraping logic for Vergabe BW portal.

        Returns:
            List of TenderResult objects
        """
        all_results = []
        seen_ids = set()

        try:
            # Navigate to search page
            self.driver.get(self.PORTAL_URL)
            self.accept_cookies()
            time.sleep(3)

            # Scrape all pages
            for page in range(1, self.MAX_PAGES + 1):
                self.logger.debug(f"Scraping page {page}")

                # Get page HTML
                html = self.driver.page_source
                soup = BeautifulSoup(html, "lxml")

                # Parse results
                results = self._parse_results(soup)

                if not results:
                    if page == 1:
                        self.logger.warning("No results found on first page")
                    break

                # Deduplicate
                new_count = 0
                for result in results:
                    if result.vergabe_id and result.vergabe_id in seen_ids:
                        continue
                    if result.vergabe_id:
                        seen_ids.add(result.vergabe_id)
                    all_results.append(result)
                    new_count += 1

                self.logger.info(f"Page {page}: found {new_count} new tenders")

                # Try next page
                if page < self.MAX_PAGES:
                    if not self._click_next_page():
                        self.logger.debug("No more pages available")
                        break
                    time.sleep(3)

            self.logger.info(f"Found {len(all_results)} total tenders")

        except Exception as e:
            self.logger.error(f"Vergabe BW scraping failed: {e}")
            raise ScraperError(self.PORTAL_NAME, str(e)) from e

        return all_results

    def _click_next_page(self) -> bool:
        """
        Click the next page button (NetServer pagination).

        Returns:
            True if successful, False if no more pages
        """
        next_selectors = [
            # NetServer specific selectors
            "a.pageNavigatorButton[title*='nächste']",
            "a.pageNavigatorButton[title*='Nächste']",
            "a[href*='thContext=next']",
            # "Weitere Ausschreibungen" link
            "a[href*='Weitere']",
            "//a[contains(text(), 'Weitere Ausschreibungen')]",
            "//a[contains(text(), 'Weitere')]",
            # Generic next page selectors
            "a[title*='nächste Seite']",
            "a[title*='Nächste Seite']",
            ".pagination a.next",
            "//a[contains(@class, 'next')]",
        ]

        for selector in next_selectors:
            try:
                if selector.startswith("//"):
                    next_btn = self.driver.find_element(By.XPATH, selector)
                else:
                    next_btn = self.driver.find_element(By.CSS_SELECTOR, selector)

                if next_btn.is_displayed() and next_btn.is_enabled():
                    self.logger.debug(f"Clicking next page with selector: {selector}")
                    next_btn.click()
                    time.sleep(2)
                    return True
            except NoSuchElementException:
                continue
            except Exception as e:
                self.logger.debug(f"Next page click failed with selector {selector}: {e}")
                continue

        return False

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
