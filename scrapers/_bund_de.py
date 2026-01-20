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
            titel = ""
            link = ""
            vergabe_id = ""
            ausschreibungsstelle = ""
            veroeffentlicht = ""
            naechste_frist = ""

            # Find title from heading
            title_elem = item.select_one("h2, h3, h4, .headline, .title")
            if title_elem:
                titel = clean_text(title_elem.get_text())
                # Check for link in title
                link_in_title = title_elem.find("a")
                if link_in_title and link_in_title.has_attr("href"):
                    link = urljoin(self.BASE_URL, link_in_title["href"])

            # Find link if not found in title
            if not link:
                link_elem = item.select_one("a[href]")
                if link_elem:
                    link = urljoin(self.BASE_URL, link_elem["href"])
                    if not titel:
                        titel = clean_text(link_elem.get_text())

            # Find metadata
            meta_elems = item.select(".meta, .info, .details, p, span")
            for meta in meta_elems:
                text = clean_text(meta.get_text())

                # Look for dates
                date_match = re.search(r"(\d{1,2}\.\d{1,2}\.\d{4})", text)
                if date_match:
                    if "frist" in text.lower() or "ende" in text.lower():
                        naechste_frist = date_match.group(1)
                    elif not veroeffentlicht:
                        veroeffentlicht = date_match.group(1)

                # Look for organization
                if any(kw in text.lower() for kw in ["vergabestelle", "auftraggeber", "behörde"]):
                    ausschreibungsstelle = text

            # Extract ID from link
            if link:
                id_match = re.search(r"/(\d{5,})[./]|[?&]id=(\d+)", link)
                if id_match:
                    vergabe_id = id_match.group(1) or id_match.group(2)

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
            titel = ""
            link = ""
            vergabe_id = ""
            veroeffentlicht = ""
            naechste_frist = ""

            # Find link and title
            link_elem = item.find("a")
            if link_elem:
                link = urljoin(self.BASE_URL, link_elem.get("href", ""))
                titel = clean_text(link_elem.get_text())

            # If no link, try to get text directly
            if not titel:
                titel = clean_text(item.get_text())[:200]

            # Extract dates from text
            item_text = item.get_text()
            dates = re.findall(r"(\d{1,2}\.\d{1,2}\.\d{4})", item_text)
            if dates:
                veroeffentlicht = dates[0]
                if len(dates) > 1:
                    naechste_frist = dates[1]

            # Extract ID
            if link:
                id_match = re.search(r"/(\d{5,})[./]|[?&]id=(\d+)", link)
                if id_match:
                    vergabe_id = id_match.group(1) or id_match.group(2)

            if not titel or len(titel) < 5:
                return None

            return TenderResult(
                portal=self.PORTAL_NAME,
                suchbegriff=None,
                suchzeitpunkt=now,
                vergabe_id=vergabe_id,
                link=link,
                titel=titel,
                ausschreibungsstelle="",
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

            titel = ""
            link = ""
            vergabe_id = ""
            ausschreibungsstelle = ""
            veroeffentlicht = ""
            naechste_frist = ""

            for cell in cells:
                text = clean_text(cell.get_text())

                # Look for link
                link_elem = cell.find("a")
                if link_elem:
                    candidate_title = clean_text(link_elem.get_text())
                    if len(candidate_title) > len(titel):
                        titel = candidate_title
                        link = urljoin(self.BASE_URL, link_elem.get("href", ""))

                # Look for dates
                date_match = re.search(r"(\d{1,2}\.\d{1,2}\.\d{4})", text)
                if date_match:
                    if not veroeffentlicht:
                        veroeffentlicht = date_match.group(1)
                    elif not naechste_frist:
                        naechste_frist = date_match.group(1)

            if not titel or len(titel) < 5:
                return None

            # Extract ID
            if link:
                id_match = re.search(r"/(\d{5,})[./]|[?&]id=(\d+)", link)
                if id_match:
                    vergabe_id = id_match.group(1) or id_match.group(2)

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
            titel = clean_text(link_elem.get_text())
            link = urljoin(self.BASE_URL, link_elem.get("href", ""))

            if not titel or len(titel) < 5:
                return None

            # Skip navigation items
            skip_words = ["suche", "filter", "login", "mehr", "weitere"]
            if any(word in titel.lower() for word in skip_words):
                return None

            vergabe_id = ""
            id_match = re.search(r"/(\d{5,})[./]|[?&]id=(\d+)", link)
            if id_match:
                vergabe_id = id_match.group(1) or id_match.group(2)

            return TenderResult(
                portal=self.PORTAL_NAME,
                suchbegriff=None,
                suchzeitpunkt=now,
                vergabe_id=vergabe_id,
                link=link,
                titel=titel,
                ausschreibungsstelle="",
                ausfuehrungsort="",
                ausschreibungsart="",
                naechste_frist="",
                veroeffentlicht="",
            )
        except Exception as e:
            self.logger.warning(f"Failed to parse link item: {e}")
            return None
