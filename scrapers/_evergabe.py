"""
Scraper for evergabe.de (German Procurement Portal).

URL: https://www.evergabe.de/auftraege/auftrag-suchen
German public and private procurement portal with over 15,000 active tenders.

Selenium Required: Yes
- JavaScript-rendered search results: Content loads dynamically via JS
- Cookie consent dialog: Requires interaction to dismiss
- Pagination: URL-based pagination with dynamic content updates
- Filter interactions: Various filter options require JS
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
class EvergabeScraper(BaseScraper):
    """Scraper for evergabe.de procurement portal."""

    PORTAL_NAME = "evergabe"
    PORTAL_URL = "https://www.evergabe.de/auftraege/auftrag-suchen"
    REQUIRES_SELENIUM = True

    # Base URL for resolving relative links
    BASE_URL = "https://www.evergabe.de"

    # Maximum pages to scrape
    MAX_PAGES = 5

    # Cookie consent selectors for evergabe.de
    COOKIE_SELECTORS = [
        "//button[contains(text(), 'Alle akzeptieren')]",
        "//button[contains(text(), 'Akzeptieren')]",
        "//button[contains(@class, 'cookie') and contains(@class, 'accept')]",
        ".cookie-consent__accept",
        "#cookie-accept-all",
        "button[data-action='accept-all']",
        ".cc-btn.cc-dismiss",
    ]

    def scrape(self) -> List[TenderResult]:
        """
        Execute scraping logic for evergabe.de portal.

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
                        (By.CSS_SELECTOR, ".job-item, .tender-item, .auftrag-item, article, .search-result")
                    )
                )
            except TimeoutException:
                self.logger.warning("Timeout waiting for search results, trying to continue...")

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
                    if not self._click_next_page(page + 2):
                        self.logger.debug("No more pages available")
                        break
                    time.sleep(3)

            self.logger.info(f"Found {len(all_results)} total tenders")

        except Exception as e:
            self.logger.error(f"evergabe.de scraping failed: {e}")
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

    def _click_next_page(self, page_number: int) -> bool:
        """
        Click the next page link in pagination.

        Args:
            page_number: Target page number (1-indexed)

        Returns:
            True if successfully clicked next page, False otherwise
        """
        try:
            # evergabe.de uses URL-based pagination: ?page=N
            next_selectors = [
                f"//a[contains(@href, 'page={page_number}')]",
                "//a[contains(@class, 'next')]",
                "//a[contains(@rel, 'next')]",
                "//li[contains(@class, 'next')]/a",
                ".pagination .next a",
                ".pagination a[rel='next']",
                "//a[@aria-label='nächste Seite']",
                "//a[@aria-label='Nächste']",
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

                        # Verify page changed
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
        Parse evergabe.de search results page HTML.

        Args:
            soup: BeautifulSoup object of page HTML

        Returns:
            List of TenderResult objects
        """
        results = []
        now = datetime.now()

        # Strategy 1: Look for job/tender item cards (most likely structure)
        items = soup.select(".job-item, .tender-item, .auftrag-item, .ausschreibung-item")
        self.logger.debug(f"Found {len(items)} card items")

        if items:
            for item in items:
                result = self._parse_card_item(item, now)
                if result:
                    results.append(result)
            if results:
                return results

        # Strategy 2: Look for article elements
        articles = soup.select("article, .search-result, .result-item")
        self.logger.debug(f"Found {len(articles)} article items")

        if articles:
            for article in articles:
                result = self._parse_article_item(article, now)
                if result:
                    results.append(result)
            if results:
                return results

        # Strategy 3: Look for tender links directly
        links = soup.select("a[href*='/ausschreibung/'], a[href*='/auftrag/']")
        self.logger.debug(f"Found {len(links)} tender links")

        for link in links:
            result = self._parse_link_item(link, now)
            if result:
                results.append(result)

        return results

    def _parse_card_item(self, item, now: datetime) -> TenderResult:
        """
        Parse a card-style tender item.

        Based on evergabe.de structure:
        - Title and description
        - Trade category (Gewerk)
        - Deadline with remaining days
        - Location (postal code)
        - Contract type (öffentlich/public)

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
            veroeffentlicht = ""
            naechste_frist = ""

            # Find title from heading or link
            title_elem = item.select_one("h2, h3, h4, .title, .headline, a.job-title")
            if title_elem:
                titel = clean_text(title_elem.get_text())
                # Check for link
                if title_elem.name == "a" and title_elem.has_attr("href"):
                    link = urljoin(self.BASE_URL, title_elem["href"])
                else:
                    link_in_title = title_elem.find("a")
                    if link_in_title and link_in_title.has_attr("href"):
                        link = urljoin(self.BASE_URL, link_in_title["href"])

            # Find link if not in title
            if not link:
                link_elem = item.select_one("a[href*='/ausschreibung/'], a[href*='/auftrag/'], a[href]")
                if link_elem:
                    link = urljoin(self.BASE_URL, link_elem.get("href", ""))
                    if not titel:
                        titel = clean_text(link_elem.get_text())

            # Find metadata elements
            # Location (PLZ/postal code)
            location_elem = item.select_one(".location, .ort, .plz, [data-location]")
            if location_elem:
                ausfuehrungsort = clean_text(location_elem.get_text())

            # Contract type
            type_elem = item.select_one(".type, .art, .verfahrensart, .contract-type")
            if type_elem:
                ausschreibungsart = clean_text(type_elem.get_text())

            # Deadline
            deadline_elem = item.select_one(".deadline, .frist, .end-date, .bewerbungsfrist")
            if deadline_elem:
                deadline_text = clean_text(deadline_elem.get_text())
                # Extract date from text like "noch 5 Tage" or "15.01.2025"
                date_match = re.search(r"(\d{1,2}\.\d{1,2}\.\d{4})", deadline_text)
                if date_match:
                    naechste_frist = date_match.group(1)
                else:
                    naechste_frist = deadline_text

            # Publication date
            pub_elem = item.select_one(".date, .published, .veroeffentlicht")
            if pub_elem:
                pub_text = clean_text(pub_elem.get_text())
                date_match = re.search(r"(\d{1,2}\.\d{1,2}\.\d{4})", pub_text)
                if date_match:
                    veroeffentlicht = date_match.group(1)

            # Organization/Client (may be behind login wall on evergabe.de)
            org_elem = item.select_one(".organization, .auftraggeber, .client, .company")
            if org_elem:
                ausschreibungsstelle = clean_text(org_elem.get_text())

            # Trade/Gewerk
            trade_elem = item.select_one(".trade, .gewerk, .category, .branche")
            if trade_elem:
                trade_text = clean_text(trade_elem.get_text())
                if not ausschreibungsart:
                    ausschreibungsart = trade_text

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
                # evergabe.de links: /ausschreibung/[slug]-[plz]-[ID]
                id_match = re.search(r"-(\d{5,})(?:\?|$)", link)
                if id_match:
                    vergabe_id = id_match.group(1)
                else:
                    # Try other patterns
                    id_match = re.search(r"/(\d+)/?$|[?&]id=(\d+)", link)
                    if id_match:
                        vergabe_id = id_match.group(1) or id_match.group(2)

            # Skip if no valid title
            if not titel or len(titel) < 5:
                return None

            # Skip navigation items
            skip_words = ["suche", "filter", "login", "registrier", "kontakt", "newsletter"]
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
            self.logger.warning(f"Failed to parse card item: {e}")
            return None

    def _parse_article_item(self, item, now: datetime) -> TenderResult:
        """
        Parse an article-style tender item.

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

            # Find title
            title_elem = item.select_one("h2, h3, h4, .title")
            if title_elem:
                titel = clean_text(title_elem.get_text())

            # Find link
            link_elem = item.select_one("a[href]")
            if link_elem:
                link = urljoin(self.BASE_URL, link_elem.get("href", ""))
                if not titel:
                    titel = clean_text(link_elem.get_text())

            # Extract dates
            item_text = item.get_text()
            dates = re.findall(r"(\d{1,2}\.\d{1,2}\.\d{4})", item_text)
            veroeffentlicht = dates[0] if dates else ""
            naechste_frist = dates[-1] if len(dates) > 1 else ""

            # Extract ID from link
            if link:
                id_match = re.search(r"-(\d{5,})(?:\?|$)|/(\d+)/?$", link)
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
            self.logger.warning(f"Failed to parse article item: {e}")
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
            skip_words = ["suche", "filter", "login", "mehr", "weitere", "zurück"]
            if any(word in titel.lower() for word in skip_words):
                return None

            vergabe_id = ""
            id_match = re.search(r"-(\d{5,})(?:\?|$)|/(\d+)/?$", link)
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
