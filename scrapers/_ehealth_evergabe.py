"""
Scraper for eHealth eVergabe (Healthcare Procurement Portal).

URL: https://bieter.ehealth-evergabe.de
Healthcare sector procurement portal powered by Healy Hudson eVergabe 4.9 platform.

Selenium Required: Yes
- JavaScript-heavy SPA: Content loads dynamically via JS framework
- Cookie consent dialog: Requires interaction to dismiss
- Dynamic content: Tender listings rendered client-side
- Pagination: May use JavaScript-based pagination
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
class EhealthEvergabeScraper(BaseScraper):
    """Scraper for eHealth eVergabe healthcare procurement portal."""

    PORTAL_NAME = "ehealth_evergabe"
    PORTAL_URL = "https://bieter.ehealth-evergabe.de/bieter/eva/supplierportal/ehealth/tabs/home"
    REQUIRES_SELENIUM = True

    # Base URL for resolving relative links
    BASE_URL = "https://bieter.ehealth-evergabe.de"

    # Maximum pages to scrape
    MAX_PAGES = 5

    # Cookie consent selectors for eVergabe platform
    COOKIE_SELECTORS = [
        "//button[contains(text(), 'Alle akzeptieren')]",
        "//button[contains(text(), 'Akzeptieren')]",
        "//button[contains(text(), 'Zustimmen')]",
        "//button[contains(@class, 'cookie') and contains(@class, 'accept')]",
        ".cookie-consent__accept",
        "#cookie-accept-all",
        "button[data-action='accept-all']",
        ".cc-btn.cc-dismiss",
        "#onetrust-accept-btn-handler",
        "button.accept-cookies",
    ]

    def scrape(self) -> List[TenderResult]:
        """
        Execute scraping logic for eHealth eVergabe portal.

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

            # Wait for content to load (eVergabe platform specific selectors)
            try:
                WebDriverWait(self.driver, 15).until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR, ".eva-table, .tender-list, .ausschreibung, table, .eva-content, .list-item")
                    )
                )
            except TimeoutException:
                self.logger.warning("Timeout waiting for content, trying to continue...")

            # Try to navigate to tenders/publications page if we're on home
            self._navigate_to_tenders()
            time.sleep(2)

            # Scrape multiple pages
            for page in range(self.MAX_PAGES):
                self.logger.debug(f"Scraping page {page + 1}")

                # Get page HTML
                html = self.driver.page_source
                soup = BeautifulSoup(html, "lxml")

                # Save debug HTML on first page
                if page == 0:
                    self._save_debug_html(html)

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
            self.logger.error(f"eHealth eVergabe scraping failed: {e}")
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

    def _navigate_to_tenders(self) -> None:
        """
        Navigate to the tenders/publications listing page.

        eVergabe platforms often have different tabs or menu items for
        publications/tenders. Try to find and click the relevant link.
        """
        try:
            # Common navigation selectors for eVergabe platforms
            nav_selectors = [
                "//a[contains(text(), 'Veröffentlichungen')]",
                "//a[contains(text(), 'Ausschreibungen')]",
                "//a[contains(text(), 'Bekanntmachungen')]",
                "//a[contains(text(), 'Vergaben')]",
                "//a[contains(@href, 'publication')]",
                "//a[contains(@href, 'tender')]",
                "//a[contains(@href, 'vergabe')]",
                ".nav-link[href*='publication']",
                ".nav-link[href*='tender']",
                "a[href*='tabs/publication']",
            ]

            for selector in nav_selectors:
                try:
                    if selector.startswith("//"):
                        element = self.driver.find_element(By.XPATH, selector)
                    else:
                        element = self.driver.find_element(By.CSS_SELECTOR, selector)

                    if element.is_displayed():
                        self.logger.debug(f"Clicking navigation: {selector}")
                        element.click()
                        time.sleep(3)
                        return
                except NoSuchElementException:
                    continue
                except Exception as e:
                    self.logger.debug(f"Navigation click failed: {e}")
                    continue

            self.logger.debug("No navigation element found, using current page")

        except Exception as e:
            self.logger.debug(f"Navigation failed: {e}")

    def _save_debug_html(self, html: str) -> None:
        """Save HTML for debugging."""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            debug_path = f"data/ehealth_evergabe_debug_{timestamp}.html"
            with open(debug_path, "w", encoding="utf-8") as f:
                f.write(html)
            self.logger.debug(f"Debug HTML saved: {debug_path}")
        except Exception as e:
            self.logger.debug(f"Failed to save debug HTML: {e}")

    def _click_next_page(self) -> bool:
        """
        Click the next page link in pagination.

        Returns:
            True if successfully clicked next page, False otherwise
        """
        try:
            next_selectors = [
                "//a[contains(@class, 'next')]",
                "//a[contains(@rel, 'next')]",
                "//li[contains(@class, 'next')]/a",
                "//button[contains(@class, 'next')]",
                "//a[@aria-label='Nächste']",
                "//a[@aria-label='nächste Seite']",
                "//a[contains(text(), 'Weiter')]",
                "//a[contains(text(), '»')]",
                "//button[contains(text(), 'Weiter')]",
                ".pagination .next a",
                ".pagination a[rel='next']",
                "a.page-link[aria-label='Next']",
                ".eva-pagination .next",
            ]

            for selector in next_selectors:
                try:
                    if selector.startswith("//"):
                        element = self.driver.find_element(By.XPATH, selector)
                    else:
                        element = self.driver.find_element(By.CSS_SELECTOR, selector)

                    if element.is_displayed() and element.is_enabled():
                        current_url = self.driver.current_url
                        self.driver.execute_script("arguments[0].scrollIntoView(true);", element)
                        time.sleep(0.5)
                        element.click()
                        time.sleep(2)

                        # Verify page changed or content refreshed
                        if self.driver.current_url != current_url:
                            return True
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
        Parse eHealth eVergabe page HTML.

        Args:
            soup: BeautifulSoup object of page HTML

        Returns:
            List of TenderResult objects
        """
        results = []
        now = datetime.now()

        # Strategy 1: Look for table rows (common in eVergabe platforms)
        tables = soup.select("table.eva-table, table.tender-table, table.list-table, table")
        for table in tables:
            rows = table.select("tbody tr, tr")
            self.logger.debug(f"Found table with {len(rows)} rows")
            for row in rows:
                result = self._parse_table_row(row, now)
                if result:
                    results.append(result)

        if results:
            return results

        # Strategy 2: Look for list items / cards
        items = soup.select(".list-item, .tender-item, .ausschreibung-item, .eva-item, .publication-item, article")
        self.logger.debug(f"Found {len(items)} list items")

        for item in items:
            result = self._parse_list_item(item, now)
            if result:
                results.append(result)

        if results:
            return results

        # Strategy 3: Look for links to tender details
        tender_links = soup.select("a[href*='tender'], a[href*='vergabe'], a[href*='publication'], a[href*='detail']")
        self.logger.debug(f"Found {len(tender_links)} tender links")

        for link in tender_links:
            result = self._parse_link_item(link, now)
            if result:
                results.append(result)

        return results

    def _parse_table_row(self, row, now: datetime) -> TenderResult:
        """
        Parse a table row containing tender information.

        Args:
            row: BeautifulSoup element (tr)
            now: Current timestamp

        Returns:
            TenderResult object or None
        """
        try:
            # Skip header rows
            if row.find("th"):
                return None

            cells = row.find_all("td")
            if not cells:
                return None

            titel = ""
            link = ""
            vergabe_id = ""
            ausschreibungsstelle = ""
            ausfuehrungsort = ""
            ausschreibungsart = ""
            naechste_frist = ""
            veroeffentlicht = ""

            # Find link and title (usually in first cells)
            for cell in cells:
                link_elem = cell.find("a")
                if link_elem and link_elem.get("href"):
                    href = link_elem.get("href", "")
                    if "tender" in href.lower() or "vergabe" in href.lower() or "publication" in href.lower() or "detail" in href.lower():
                        link = urljoin(self.BASE_URL, href)
                        titel = clean_text(link_elem.get_text())
                        break

            # If no link found, try to get title from first cell
            if not titel and cells:
                titel = clean_text(cells[0].get_text())

            # Extract other fields from cells
            cell_texts = [clean_text(cell.get_text()) for cell in cells]

            for i, text in enumerate(cell_texts):
                # Skip title cell
                if text == titel:
                    continue

                # Date patterns
                date_match = re.search(r"(\d{1,2}\.\d{1,2}\.\d{4})", text)
                if date_match:
                    if not veroeffentlicht:
                        veroeffentlicht = date_match.group(1)
                    elif not naechste_frist:
                        naechste_frist = date_match.group(1)
                    continue

                # Type keywords
                type_keywords = ["verfahren", "vergabe", "ausschreibung", "öffentlich", "beschränkt", "verhandlung"]
                if any(kw in text.lower() for kw in type_keywords):
                    if not ausschreibungsart:
                        ausschreibungsart = text
                    continue

                # Short text might be location or organization
                if len(text) < 100 and not ausschreibungsstelle:
                    ausschreibungsstelle = text

            # Extract ID from link
            if link:
                id_match = re.search(r"[?&]id=(\d+)|/(\d+)/?$|vergabe[_-]?(\d+)", link, re.IGNORECASE)
                if id_match:
                    vergabe_id = id_match.group(1) or id_match.group(2) or id_match.group(3)

            # Skip if no valid title
            if not titel or len(titel) < 5:
                return None

            # Skip navigation/header items
            skip_words = ["suche", "filter", "login", "registrier", "kontakt", "newsletter", "menü", "navigation"]
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
                ausfuehrungsort=ausfuehrungsort,
                ausschreibungsart=ausschreibungsart,
                naechste_frist=naechste_frist,
                veroeffentlicht=veroeffentlicht,
            )
        except Exception as e:
            self.logger.warning(f"Failed to parse table row: {e}")
            return None

    def _parse_list_item(self, item, now: datetime) -> TenderResult:
        """
        Parse a list/card style tender item.

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
            ausfuehrungsort = ""
            ausschreibungsart = ""
            naechste_frist = ""
            veroeffentlicht = ""

            # Find title from heading or link
            title_elem = item.select_one("h2, h3, h4, h5, .title, .headline, .tender-title")
            if title_elem:
                titel = clean_text(title_elem.get_text())
                link_in_title = title_elem.find("a")
                if link_in_title and link_in_title.get("href"):
                    link = urljoin(self.BASE_URL, link_in_title.get("href"))

            # Find link if not in title
            if not link:
                link_elem = item.select_one("a[href*='tender'], a[href*='vergabe'], a[href*='detail'], a[href]")
                if link_elem:
                    link = urljoin(self.BASE_URL, link_elem.get("href", ""))
                    if not titel:
                        titel = clean_text(link_elem.get_text())

            # Find metadata
            meta_selectors = {
                "ausschreibungsstelle": ".organization, .auftraggeber, .client, .author",
                "ausfuehrungsort": ".location, .ort, .place",
                "ausschreibungsart": ".type, .art, .verfahrensart, .category",
                "naechste_frist": ".deadline, .frist, .end-date",
                "veroeffentlicht": ".date, .published, .created",
            }

            for field, selector in meta_selectors.items():
                elem = item.select_one(selector)
                if elem:
                    value = clean_text(elem.get_text())
                    if field in ["naechste_frist", "veroeffentlicht"]:
                        date_match = re.search(r"(\d{1,2}\.\d{1,2}\.\d{4})", value)
                        if date_match:
                            value = date_match.group(1)
                    if value:
                        locals()[field] = value

            # Extract dates from full item text if not found
            if not veroeffentlicht or not naechste_frist:
                item_text = item.get_text()
                dates = re.findall(r"(\d{1,2}\.\d{1,2}\.\d{4})", item_text)
                if dates and not veroeffentlicht:
                    veroeffentlicht = dates[0]
                if len(dates) > 1 and not naechste_frist:
                    naechste_frist = dates[-1]

            # Extract ID from link
            if link:
                id_match = re.search(r"[?&]id=(\d+)|/(\d+)/?$", link)
                if id_match:
                    vergabe_id = id_match.group(1) or id_match.group(2)

            # Skip if no valid title
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
                ausfuehrungsort=ausfuehrungsort,
                ausschreibungsart=ausschreibungsart,
                naechste_frist=naechste_frist,
                veroeffentlicht=veroeffentlicht,
            )
        except Exception as e:
            self.logger.warning(f"Failed to parse list item: {e}")
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
            skip_words = ["suche", "filter", "login", "mehr", "weitere", "zurück", "home", "menü"]
            if any(word in titel.lower() for word in skip_words):
                return None

            vergabe_id = ""
            id_match = re.search(r"[?&]id=(\d+)|/(\d+)/?$", link)
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
