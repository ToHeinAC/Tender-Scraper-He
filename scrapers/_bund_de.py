"""
Scraper for service.bund.de (German Federal Procurement Portal).

URL: https://www.service.bund.de/Content/DE/Ausschreibungen/Suche/Formular.html
Central public procurement database for German federal, state, and municipal authorities.

Selenium Required: Yes
- JavaScript-rendered search results: Content loads dynamically via JS
- Cookie consent dialog: Requires interaction to dismiss
- Pagination: Dynamic pagination without full page reloads
- Sort/filter interactions: Requires JS for filter selections
"""

import re
import time
from datetime import datetime
from typing import List
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

from scrapers.base import BaseScraper, TenderResult, ScraperError
from scrapers.registry import register_scraper
from scrapers.utils import clean_text


@register_scraper
class BundDeScraper(BaseScraper):
    """Scraper for service.bund.de federal procurement portal."""

    PORTAL_NAME = "bund_de"
    PORTAL_URL = "https://www.service.bund.de/Content/DE/Ausschreibungen/Suche/Formular.html"
    REQUIRES_SELENIUM = True

    # Base URL for resolving relative links
    BASE_URL = "https://www.service.bund.de"

    # Maximum pages to scrape
    MAX_PAGES = 5

    # Cookie consent selectors for bund.de
    COOKIE_SELECTORS = [
        "//button[contains(@class, 'cookie') and contains(text(), 'Akzeptieren')]",
        "//button[contains(text(), 'Alle akzeptieren')]",
        "//button[contains(@class, 'accept')]",
        ".cookie-banner__accept",
        "#cookie-consent-accept",
        "button[data-testid='cookie-accept']",
    ]

    # Regex patterns for dates - supports both DD.MM.YY and DD.MM.YYYY formats
    DATE_PATTERN_2DIGIT = r"(\d{1,2}\.\d{1,2}\.\d{2})"
    DATE_PATTERN_4DIGIT = r"(\d{1,2}\.\d{1,2}\.\d{4})"
    DATE_PATTERN_ANY = r"(\d{1,2}\.\d{1,2}\.\d{2,4})"

    def _extract_metadata_from_text(self, text: str) -> dict:
        """
        Extract structured metadata from concatenated text.

        Bund.de often returns text like:
        "AusschreibungTitle... Vergabestelle OrgName Veröffentlicht 20.01.26 Angebotsfrist 19.02.26"

        This method extracts the individual fields.

        Args:
            text: The concatenated text to parse

        Returns:
            Dict with keys: titel, vergabestelle, veroeffentlicht, angebotsfrist
        """
        result = {
            "titel": "",
            "vergabestelle": "",
            "veroeffentlicht": "",
            "angebotsfrist": "",
        }

        if not text:
            return result

        # Work with the text
        working_text = text

        # Extract Angebotsfrist (deadline) - look for "Angebotsfrist" followed by date
        angebotsfrist_match = re.search(
            r"Angebotsfrist\s*" + self.DATE_PATTERN_ANY,
            working_text,
            re.IGNORECASE
        )
        if angebotsfrist_match:
            result["angebotsfrist"] = angebotsfrist_match.group(1)
            # Remove this part from the text
            working_text = working_text[:angebotsfrist_match.start()] + working_text[angebotsfrist_match.end():]

        # Extract Veröffentlicht (published date)
        veroeffentlicht_match = re.search(
            r"Veröffentlicht\s*" + self.DATE_PATTERN_ANY,
            working_text,
            re.IGNORECASE
        )
        if veroeffentlicht_match:
            result["veroeffentlicht"] = veroeffentlicht_match.group(1)
            working_text = working_text[:veroeffentlicht_match.start()] + working_text[veroeffentlicht_match.end():]

        # Extract Vergabestelle (awarding authority)
        # This comes after "Vergabestelle" and before "Veröffentlicht" or end of remaining text
        vergabestelle_match = re.search(
            r"Vergabestelle\s+(.+?)(?:\s*$)",
            working_text,
            re.IGNORECASE
        )
        if vergabestelle_match:
            vergabestelle = vergabestelle_match.group(1).strip()
            # Clean up any trailing ellipsis, pipes, or special characters (with optional spaces between)
            vergabestelle = re.sub(r'[\s…\.\|]+$', '', vergabestelle)
            result["vergabestelle"] = vergabestelle
            working_text = working_text[:vergabestelle_match.start()]

        # The remaining text is the title - clean it up
        titel = working_text.strip()
        # Remove "Ausschreibung" prefix if present
        titel = re.sub(r'^Ausschreibung\s*', '', titel, flags=re.IGNORECASE)
        # Clean up trailing ellipsis or special chars
        titel = re.sub(r'\s*[…]+\s*$', '', titel)
        titel = titel.strip()

        result["titel"] = titel

        return result

    def scrape(self) -> List[TenderResult]:
        """
        Execute scraping logic for service.bund.de portal.

        Returns:
            List of TenderResult objects
        """
        all_results = []

        try:
            self.logger.info(f"Navigating to: {self.PORTAL_URL}")
            self.driver.get(self.PORTAL_URL)
            time.sleep(4)

            # Accept cookies
            self.accept_cookies()
            time.sleep(2)

            # Wait for search results to load
            try:
                WebDriverWait(self.driver, 15).until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR, ".result-list, .search-results, .resultList, article.teaser")
                    )
                )
            except TimeoutException:
                self.logger.warning("Timeout waiting for search results, trying to continue...")

            # Try to set higher results per page
            self._try_expand_results()
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
            self.logger.error(f"service.bund.de scraping failed: {e}")
            raise ScraperError(self.PORTAL_NAME, str(e)) from e

        # Remove duplicates based on link
        seen = set()
        unique_results = []
        for r in all_results:
            key = r.link or r.titel
            if key and key not in seen:
                seen.add(key)
                unique_results.append(r)

        return unique_results

    def _try_expand_results(self):
        """Try to show more results per page."""
        try:
            # Look for results per page selector
            selectors = [
                "//select[contains(@id, 'pageSize')]//option[@value='50']",
                "//select[contains(@id, 'pageSize')]//option[@value='100']",
                "//a[contains(text(), '100')]",
                "//a[contains(text(), '50')]",
                ".page-size-select option[value='100']",
                ".page-size-select option[value='50']",
            ]

            for selector in selectors:
                try:
                    if selector.startswith("//"):
                        elem = self.driver.find_element(By.XPATH, selector)
                    else:
                        elem = self.driver.find_element(By.CSS_SELECTOR, selector)

                    if elem.is_displayed():
                        elem.click()
                        self.logger.debug("Expanded results per page")
                        time.sleep(2)
                        return
                except NoSuchElementException:
                    continue
        except Exception as e:
            self.logger.debug(f"Could not expand results per page: {e}")

    def _click_next_page(self) -> bool:
        """
        Click the next page link in pagination.

        Returns:
            True if successfully clicked next page, False otherwise
        """
        try:
            next_selectors = [
                "//a[contains(@class, 'next') or contains(@title, 'nächste') or contains(@title, 'Nächste')]",
                "//a[contains(@class, 'forward')]",
                "//li[contains(@class, 'next')]/a",
                ".pagination .next a",
                ".pagination a.next",
                "a[rel='next']",
                "//a[contains(@aria-label, 'nächste') or contains(@aria-label, 'Nächste')]",
                "//span[contains(@class, 'icon-forward')]/parent::a",
            ]

            for selector in next_selectors:
                try:
                    if selector.startswith("//"):
                        element = self.driver.find_element(By.XPATH, selector)
                    else:
                        element = self.driver.find_element(By.CSS_SELECTOR, selector)

                    if element.is_displayed() and element.is_enabled():
                        current_url = self.driver.current_url
                        element.click()
                        time.sleep(2)

                        # Verify page changed
                        if self.driver.current_url != current_url:
                            return True
                        # Check if content changed
                        return True
                except NoSuchElementException:
                    continue
                except Exception as e:
                    self.logger.debug(f"Next page click failed: {e}")
                    continue

        except Exception as e:
            self.logger.debug(f"Next page navigation failed: {e}")

        return False

    def _parse_results(self, soup: BeautifulSoup) -> List[TenderResult]:
        """
        Parse service.bund.de search results page HTML.

        Args:
            soup: BeautifulSoup object of page HTML

        Returns:
            List of TenderResult objects
        """
        results = []
        now = datetime.now()

        # Strategy 1: Look for article.teaser or div.teaser elements
        items = soup.select("article.teaser, div.teaser, .result-item, .search-result-item")
        self.logger.debug(f"Found {len(items)} teaser items")

        if items:
            for item in items:
                result = self._parse_teaser_item(item, now)
                if result:
                    results.append(result)
            if results:
                return results

        # Strategy 2: Look for result list items
        items = soup.select(".resultList li, .result-list li, ul.results > li")
        self.logger.debug(f"Found {len(items)} list items")

        if items:
            for item in items:
                result = self._parse_list_item(item, now)
                if result:
                    results.append(result)
            if results:
                return results

        # Strategy 3: Look for table-based results
        tables = soup.select("table.results, table.search-results, .data-table")
        for table in tables:
            rows = table.find_all("tr")
            self.logger.debug(f"Found table with {len(rows)} rows")
            for row in rows[1:]:  # Skip header
                result = self._parse_table_row(row, now)
                if result:
                    results.append(result)
            if results:
                return results

        # Strategy 4: Generic link extraction for tenders
        links = soup.select("a[href*='Ausschreibung'], a[href*='IMPORTE/Ausschreibungen']")
        self.logger.debug(f"Found {len(links)} tender links")

        for link in links:
            result = self._parse_link_item(link, now)
            if result:
                results.append(result)

        return results

    def _parse_teaser_item(self, item, now: datetime) -> TenderResult:
        """
        Parse a teaser-style result item.

        Args:
            item: BeautifulSoup element
            now: Current timestamp

        Returns:
            TenderResult object or None
        """
        try:
            link = ""
            vergabe_id = ""

            # Get the full text content of the item for metadata extraction
            full_text = clean_text(item.get_text())

            # Extract structured metadata from the concatenated text
            metadata = self._extract_metadata_from_text(full_text)

            titel = metadata["titel"]
            ausschreibungsstelle = metadata["vergabestelle"]
            veroeffentlicht = metadata["veroeffentlicht"]
            naechste_frist = metadata["angebotsfrist"]

            # Find link from heading or direct link
            title_elem = item.select_one("h2, h3, h4, .headline, .title")
            if title_elem:
                link_in_title = title_elem.find("a")
                if link_in_title and link_in_title.has_attr("href"):
                    link = urljoin(self.BASE_URL, link_in_title["href"])

            # Find link if not found in title
            if not link:
                link_elem = item.select_one("a[href]")
                if link_elem:
                    link = urljoin(self.BASE_URL, link_elem["href"])

            # Extract ID from link
            if link:
                id_match = re.search(r"/(\d{5,})[./]|[?&]id=(\d+)|/([A-Z]?\d{6,})\.", link)
                if id_match:
                    vergabe_id = id_match.group(1) or id_match.group(2) or id_match.group(3)

            # Skip if no valid title
            if not titel or len(titel) < 5:
                return None

            # Skip navigation items
            skip_words = ["suche", "filter", "login", "registrier", "kontakt", "impressum"]
            if any(word in titel.lower() for word in skip_words):
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
                ausschreibungsart="",
                naechste_frist=naechste_frist,
                veroeffentlicht=veroeffentlicht,
            )
        except Exception as e:
            self.logger.warning(f"Failed to parse teaser item: {e}")
            return None

    def _parse_list_item(self, item, now: datetime) -> TenderResult:
        """
        Parse a list-style result item.

        Args:
            item: BeautifulSoup element
            now: Current timestamp

        Returns:
            TenderResult object or None
        """
        try:
            link = ""
            vergabe_id = ""

            # Get the full text content and extract metadata
            full_text = clean_text(item.get_text())
            metadata = self._extract_metadata_from_text(full_text)

            titel = metadata["titel"]
            ausschreibungsstelle = metadata["vergabestelle"]
            veroeffentlicht = metadata["veroeffentlicht"]
            naechste_frist = metadata["angebotsfrist"]

            # Find link
            link_elem = item.find("a")
            if link_elem:
                link = urljoin(self.BASE_URL, link_elem.get("href", ""))

            # Extract ID
            if link:
                id_match = re.search(r"/(\d{5,})[./]|[?&]id=(\d+)|/([A-Z]?\d{6,})\.", link)
                if id_match:
                    vergabe_id = id_match.group(1) or id_match.group(2) or id_match.group(3)

            if not titel or len(titel) < 5:
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
                ausschreibungsart="",
                naechste_frist=naechste_frist,
                veroeffentlicht=veroeffentlicht,
            )
        except Exception as e:
            self.logger.warning(f"Failed to parse list item: {e}")
            return None

    def _parse_table_row(self, row, now: datetime) -> TenderResult:
        """
        Parse a table row result.

        Args:
            row: BeautifulSoup row element
            now: Current timestamp

        Returns:
            TenderResult object or None
        """
        try:
            cells = row.find_all("td")
            if len(cells) < 2:
                return None

            link = ""
            vergabe_id = ""

            # Get full text and extract metadata
            full_text = clean_text(row.get_text())
            metadata = self._extract_metadata_from_text(full_text)

            titel = metadata["titel"]
            ausschreibungsstelle = metadata["vergabestelle"]
            veroeffentlicht = metadata["veroeffentlicht"]
            naechste_frist = metadata["angebotsfrist"]

            # Look for link in cells
            for cell in cells:
                link_elem = cell.find("a")
                if link_elem:
                    link = urljoin(self.BASE_URL, link_elem.get("href", ""))
                    break

            if not titel or len(titel) < 5:
                return None

            # Extract ID
            if link:
                id_match = re.search(r"/(\d{5,})[./]|[?&]id=(\d+)|/([A-Z]?\d{6,})\.", link)
                if id_match:
                    vergabe_id = id_match.group(1) or id_match.group(2) or id_match.group(3)

            return TenderResult(
                portal=self.PORTAL_NAME,
                suchbegriff=None,
                suchzeitpunkt=now,
                vergabe_id=vergabe_id,
                link=link,
                titel=titel,
                ausschreibungsstelle=ausschreibungsstelle,
                ausfuehrungsort="",
                ausschreibungsart="",
                naechste_frist=naechste_frist,
                veroeffentlicht=veroeffentlicht,
            )
        except Exception as e:
            self.logger.warning(f"Failed to parse table row: {e}")
            return None

    def _parse_link_item(self, link_elem, now: datetime) -> TenderResult:
        """
        Parse a tender from a link element.

        Args:
            link_elem: BeautifulSoup link element
            now: Current timestamp

        Returns:
            TenderResult object or None
        """
        try:
            full_text = clean_text(link_elem.get_text())
            link = urljoin(self.BASE_URL, link_elem.get("href", ""))

            # Extract metadata from concatenated text
            metadata = self._extract_metadata_from_text(full_text)

            titel = metadata["titel"]
            ausschreibungsstelle = metadata["vergabestelle"]
            veroeffentlicht = metadata["veroeffentlicht"]
            naechste_frist = metadata["angebotsfrist"]

            if not titel or len(titel) < 5:
                return None

            # Skip navigation items
            skip_words = ["suche", "filter", "login", "mehr", "weitere"]
            if any(word in titel.lower() for word in skip_words):
                return None

            vergabe_id = ""
            id_match = re.search(r"/(\d{5,})[./]|[?&]id=(\d+)|/([A-Z]?\d{6,})\.", link)
            if id_match:
                vergabe_id = id_match.group(1) or id_match.group(2) or id_match.group(3)

            return TenderResult(
                portal=self.PORTAL_NAME,
                suchbegriff=None,
                suchzeitpunkt=now,
                vergabe_id=vergabe_id,
                link=link,
                titel=titel,
                ausschreibungsstelle=ausschreibungsstelle,
                ausfuehrungsort="",
                ausschreibungsart="",
                naechste_frist=naechste_frist,
                veroeffentlicht=veroeffentlicht,
            )
        except Exception as e:
            self.logger.warning(f"Failed to parse link item: {e}")
            return None
