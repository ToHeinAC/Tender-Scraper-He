"""
Scraper for GTAI (Germany Trade and Invest) Tender Portal.

URL: https://www.gtai.de/de/trade/ausschreibungen-projekte
EU-wide tender announcements from GTAI, Germany.

Note: Full tender database access requires authentication.
This scraper extracts publicly available tender information.

Selenium Required: Yes
- JavaScript-rendered content: Search results load dynamically via JS
- Cookie consent dialog: Requires interaction to dismiss
- Filter interactions: Ausschreibungen checkbox needs to be clicked
- Pagination: Dynamic page loading without full URL navigation
"""

import re
import time
from datetime import datetime
from typing import List
from urllib.parse import urljoin, urlencode

from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

from scrapers.base import BaseScraper, TenderResult, ScraperError
from scrapers.registry import register_scraper
from scrapers.utils import clean_text


@register_scraper
class GTAIScraper(BaseScraper):
    """Scraper for gtai.de tender portal."""

    PORTAL_NAME = "gtai"
    PORTAL_URL = "https://www.gtai.de/de/trade/ausschreibungen-projekte"
    REQUIRES_SELENIUM = True

    # Search URL with Ausschreibungen filter applied
    # The rubrik=ausschreibungen parameter filters for tender content
    TENDER_SEARCH_URL = "https://www.gtai.de/de/meta/suche?rubrik=ausschreibungen"

    # Maximum pages to scrape
    MAX_PAGES = 5

    def scrape(self) -> List[TenderResult]:
        """
        Execute scraping logic for GTAI portal.

        Returns:
            List of TenderResult objects
        """
        all_results = []

        try:
            # Navigate to tender search page with Ausschreibungen filter
            self.logger.info(f"Navigating to: {self.TENDER_SEARCH_URL}")
            self.driver.get(self.TENDER_SEARCH_URL)
            time.sleep(4)  # Wait for bot protection and page load

            # Accept cookies
            self.accept_cookies()
            time.sleep(2)

            # Wait for search results to load
            try:
                WebDriverWait(self.driver, 15).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "li.result-item, .searchResults"))
                )
            except TimeoutException:
                self.logger.warning("Timeout waiting for search results, trying to continue...")

            # If filter not applied via URL, try clicking the checkbox
            self._ensure_ausschreibungen_filter()
            time.sleep(2)

            # Scrape multiple pages
            for page in range(self.MAX_PAGES):
                self.logger.debug(f"Scraping page {page + 1}")

                # Get page HTML
                html = self.driver.page_source
                soup = BeautifulSoup(html, "lxml")

                # Parse current page results
                page_results = self._parse_results(soup)
                self.logger.debug(f"Page {page + 1}: found {len(page_results)} results")

                if not page_results:
                    self.logger.debug("No results on page, stopping pagination")
                    break

                all_results.extend(page_results)

                # Try to go to next page
                if page < self.MAX_PAGES - 1:
                    if not self._click_next_page():
                        self.logger.debug("No more pages available")
                        break
                    time.sleep(3)

            self.logger.info(f"Found {len(all_results)} total tenders")

        except Exception as e:
            self.logger.error(f"GTAI scraping failed: {e}")
            raise ScraperError(self.PORTAL_NAME, str(e)) from e

        # Remove duplicates based on link
        seen = set()
        unique_results = []
        for r in all_results:
            if r.link and r.link not in seen:
                seen.add(r.link)
                unique_results.append(r)

        return unique_results

    def _ensure_ausschreibungen_filter(self):
        """Ensure the Ausschreibungen filter is selected."""
        try:
            # First, try to expand the Rubriken filter accordion if collapsed
            rubriken_link = None
            try:
                rubriken_link = self.driver.find_element(
                    By.XPATH, "//a[contains(@class, 'accFilterLink') and contains(text(), 'Rubriken')]"
                )
                if rubriken_link.is_displayed():
                    rubriken_link.click()
                    time.sleep(1)
            except NoSuchElementException:
                pass

            # Look for Ausschreibungen checkbox (value 99662 based on HTML)
            checkbox_selectors = [
                "input#f-99662",  # Direct ID
                "input[value='99662']",  # By value
                "//input[following-sibling::label[contains(., 'Ausschreibungen')]]",
                "//label[contains(text(), 'Ausschreibungen')]/preceding-sibling::input",
            ]

            for selector in checkbox_selectors:
                try:
                    if selector.startswith("//"):
                        checkbox = self.driver.find_element(By.XPATH, selector)
                    else:
                        checkbox = self.driver.find_element(By.CSS_SELECTOR, selector)

                    if checkbox and not checkbox.is_selected():
                        # Click the label instead if checkbox is hidden
                        try:
                            label = self.driver.find_element(
                                By.CSS_SELECTOR, f"label[for='{checkbox.get_attribute('id')}']"
                            )
                            label.click()
                        except NoSuchElementException:
                            checkbox.click()
                        self.logger.debug("Clicked Ausschreibungen filter checkbox")
                        time.sleep(2)
                        return
                    elif checkbox and checkbox.is_selected():
                        self.logger.debug("Ausschreibungen filter already selected")
                        return
                except NoSuchElementException:
                    continue

        except Exception as e:
            self.logger.debug(f"Could not select Ausschreibungen filter: {e}")

    def _click_next_page(self) -> bool:
        """
        Click the next page link in pagination.

        Returns:
            True if successfully clicked next page, False otherwise
        """
        try:
            # Look for pagination links - GTAI uses ?page=N parameter
            next_selectors = [
                "//a[contains(@title, 'zur Seite') and not(contains(@title, 'letzten'))]",
                "//a[contains(@href, 'page=') and contains(@class, 'icon-angle-right')]",
                ".pagination a.next",
                "a[title*='nächste']",
            ]

            for selector in next_selectors:
                try:
                    if selector.startswith("//"):
                        elements = self.driver.find_elements(By.XPATH, selector)
                    else:
                        elements = self.driver.find_elements(By.CSS_SELECTOR, selector)

                    for elem in elements:
                        if elem.is_displayed() and elem.is_enabled():
                            # Get current URL to compare
                            current_url = self.driver.current_url

                            elem.click()
                            time.sleep(2)

                            # Verify page changed
                            new_url = self.driver.current_url
                            if new_url != current_url:
                                return True

                except NoSuchElementException:
                    continue

        except Exception as e:
            self.logger.debug(f"Next page click failed: {e}")

        return False

    def _parse_results(self, soup: BeautifulSoup) -> List[TenderResult]:
        """
        Parse GTAI search results page HTML.

        Args:
            soup: BeautifulSoup object of page HTML

        Returns:
            List of TenderResult objects
        """
        results = []
        now = datetime.now()

        # GTAI uses li.result-item for search results
        items = soup.select("li.result-item")
        self.logger.debug(f"Found {len(items)} result items")

        for item in items:
            result = self._parse_result_item(item, now)
            if result:
                results.append(result)

        return results

    def _parse_result_item(self, item, now: datetime) -> TenderResult:
        """
        Parse a GTAI search result item.

        HTML structure:
        <li class="result-item">
          <div class="overline">
            <span class="overline__text date">04.12.2025</span>
          </div>
          <div class="content">
            <a href="/de/trade/...">
              <h3>Title</h3>
            </a>
            <p class="excerpt">Description...</p>
          </div>
        </li>

        Args:
            item: BeautifulSoup element
            now: Current timestamp

        Returns:
            TenderResult object or None
        """
        try:
            titel = ""
            link = ""
            veroeffentlicht = ""
            description = ""

            # Find published date from .overline__text.date
            date_elem = item.select_one(".overline__text.date, .overline .date, span.date")
            if date_elem:
                veroeffentlicht = clean_text(date_elem.get_text())

            # Find title from .content h3
            title_elem = item.select_one(".content h3, .content h2, h3")
            if title_elem:
                titel = clean_text(title_elem.get_text())

            # Find link from .content a
            link_elem = item.select_one(".content a[href], a[href]")
            if link_elem:
                href = link_elem.get("href", "")
                link = href if href.startswith("http") else urljoin("https://www.gtai.de", href)
                # If no title found yet, use link text
                if not titel:
                    titel = clean_text(link_elem.get_text())

            # Find description from p.excerpt
            excerpt_elem = item.select_one("p.excerpt, .excerpt, .description")
            if excerpt_elem:
                description = clean_text(excerpt_elem.get_text())[:300]

            # Skip if no valid title
            if not titel or len(titel) < 5:
                return None

            # Skip navigation/menu items and non-tender content
            skip_words = [
                "suche", "filter", "mehr anzeigen", "login", "registrier",
                "kontakt", "impressum", "datenschutz", "cookie", "newsletter"
            ]
            titel_lower = titel.lower()
            if any(word in titel_lower for word in skip_words):
                return None

            # Skip "Seite merken" bookmarking links
            if "seite merken" in titel_lower or "seite gemerkt" in titel_lower:
                return None

            # Extract vergabe_id from link if present (e.g., -123456 pattern)
            vergabe_id = ""
            id_match = re.search(r'-(\d{5,})(?:\?|$|!)', link)
            if id_match:
                vergabe_id = id_match.group(1)

            return TenderResult(
                portal=self.PORTAL_NAME,
                suchbegriff=None,
                suchzeitpunkt=now,
                vergabe_id=vergabe_id,
                link=link,
                titel=titel,
                ausschreibungsstelle=description,  # Use description as source info
                ausfuehrungsort="",
                ausschreibungsart="EU-Ausschreibung",
                naechste_frist="",  # GTAI doesn't show deadline in list view
                veroeffentlicht=veroeffentlicht,
            )
        except Exception as e:
            self.logger.warning(f"Failed to parse result item: {e}")
            return None

