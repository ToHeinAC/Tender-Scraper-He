"""
Scraper for e-Vergabe Online (Federal German Procurement Portal).

URL: https://www.evergabe-online.de
Federal government tenders from Germany.
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
from scrapers.utils import clean_text


@register_scraper
class EvergabeOnlineScraper(BaseScraper):
    """Scraper for evergabe-online.de federal procurement portal."""

    PORTAL_NAME = "evergabe_online"
    PORTAL_URL = "https://www.evergabe-online.de/search.html"
    REQUIRES_SELENIUM = True

    # Number of pages to scrape
    MAX_PAGES = 3

    # Cookie consent selectors specific to this portal
    COOKIE_SELECTORS = [
        "#cookieConsentAcceptAll",
        "button.btn-accept-all",
        "//button[contains(text(), 'Alle akzeptieren')]",
        "//button[contains(text(), 'Akzeptieren')]",
        ".cookie-consent-accept",
    ]

    def scrape(self) -> List[TenderResult]:
        """
        Execute scraping logic for e-Vergabe Online portal.

        Returns:
            List of TenderResult objects
        """
        all_results = []

        try:
            # Navigate to search page
            self.logger.info(f"Navigating to: {self.PORTAL_URL}")
            self.driver.get(self.PORTAL_URL)

            # Accept cookies if present
            time.sleep(2)
            self.accept_cookies()
            time.sleep(2)

            # Wait for results to load
            try:
                WebDriverWait(self.driver, 15).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, ".searchResultRow, table.searchResults, .result-item"))
                )
            except TimeoutException:
                self.logger.warning("Results not found with primary selectors, trying alternatives")
                time.sleep(3)

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

            self.logger.info(f"Found {len(all_results)} tenders")

        except Exception as e:
            self.logger.error(f"e-Vergabe Online scraping failed: {e}")
            raise ScraperError(self.PORTAL_NAME, str(e)) from e

        return all_results

    def _click_next_page(self) -> bool:
        """
        Click the next page button.

        Returns:
            True if successful, False if no more pages
        """
        try:
            # Look for pagination links
            next_selectors = [
                "a.navigator-next",
                "//a[contains(@class, 'navigator')][contains(text(), '>')]",
                "//a[contains(@class, 'pageLink')][last()]",
            ]

            for selector in next_selectors:
                try:
                    if selector.startswith("//"):
                        next_button = self.driver.find_element(By.XPATH, selector)
                    else:
                        next_button = self.driver.find_element(By.CSS_SELECTOR, selector)

                    if next_button.is_displayed() and next_button.is_enabled():
                        next_button.click()
                        time.sleep(2)
                        return True
                except NoSuchElementException:
                    continue

        except Exception as e:
            self.logger.debug(f"Next page click failed: {e}")

        return False

    def _parse_results(self, soup: BeautifulSoup) -> List[TenderResult]:
        """
        Parse e-Vergabe Online tender page HTML.

        Args:
            soup: BeautifulSoup object of page HTML

        Returns:
            List of TenderResult objects
        """
        results = []
        now = datetime.now()

        # Find tender links - format: tenderdetails.html?id=XXXXXX
        tender_links = soup.find_all("a", href=re.compile(r"tenderdetails\.html\?id=\d+"))

        self.logger.debug(f"Found {len(tender_links)} tender links")

        for link in tender_links:
            try:
                result = self._parse_tender_link(link, soup, now)
                if result and result.titel:
                    results.append(result)
            except Exception as e:
                self.logger.warning(f"Failed to parse tender: {e}")
                continue

        return results

    def _parse_tender_link(self, link, soup: BeautifulSoup, now: datetime) -> TenderResult:
        """
        Parse a single tender link and its surrounding context.

        Args:
            link: BeautifulSoup anchor element
            soup: Full page soup for context
            now: Current timestamp

        Returns:
            TenderResult object or None
        """
        href = link.get("href", "")
        titel = clean_text(link.get_text())

        # Extract ID from URL
        vergabe_id = ""
        id_match = re.search(r"id=(\d+)", href)
        if id_match:
            vergabe_id = id_match.group(1)

        # Build full URL
        full_link = f"https://www.evergabe-online.de/{href}" if not href.startswith("http") else href

        # Try to find the parent row to extract additional fields
        parent_row = link.find_parent("tr") or link.find_parent("div", class_=re.compile(r"row|result"))

        ausschreibungsstelle = ""
        ausfuehrungsort = ""
        ausschreibungsart = ""
        naechste_frist = ""
        veroeffentlicht = ""

        if parent_row:
            cells = parent_row.find_all(["td", "span", "div"])
            texts = [clean_text(c.get_text()) for c in cells if c.get_text(strip=True)]

            # Try to identify fields by content patterns
            for text in texts:
                # Skip the title
                if text == titel:
                    continue

                # Date pattern (DD.MM.YYYY or YYYY-MM-DD)
                date_match = re.search(r"\d{2}\.\d{2}\.\d{4}|\d{4}-\d{2}-\d{2}", text)
                if date_match:
                    if not naechste_frist:
                        naechste_frist = date_match.group(0)
                    elif not veroeffentlicht:
                        veroeffentlicht = date_match.group(0)
                    continue

                # Procedure type keywords
                if any(kw in text.lower() for kw in ["verfahren", "vergabe", "ausschreibung", "öffentlich", "beschränkt"]):
                    if not ausschreibungsart:
                        ausschreibungsart = text
                    continue

                # Location (typically short, contains city/region names)
                if len(text) < 50 and not ausschreibungsstelle:
                    ausschreibungsstelle = text

        return TenderResult(
            portal=self.PORTAL_NAME,
            suchbegriff=None,
            suchzeitpunkt=now,
            vergabe_id=vergabe_id,
            link=full_link,
            titel=titel,
            ausschreibungsstelle=ausschreibungsstelle,
            ausfuehrungsort=ausfuehrungsort,
            ausschreibungsart=ausschreibungsart,
            naechste_frist=naechste_frist,
            veroeffentlicht=veroeffentlicht,
        )
