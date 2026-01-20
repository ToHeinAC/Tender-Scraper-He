"""
Scraper for GermanyTenders.com.

URL: https://www.germanytenders.com/tenders/search
German-language tender listings aggregator portal.

Selenium Required: Yes
- JavaScript-enhanced content loading
- Cookie consent/analytics (Google Analytics)
- Pagination via URL parameters (?page=N)
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
class GermanyTendersScraper(BaseScraper):
    """Scraper for germanytenders.com procurement portal."""

    PORTAL_NAME = "germanytenders"
    PORTAL_URL = "https://www.germanytenders.com/tenders/search"
    REQUIRES_SELENIUM = True

    # Base URL for resolving relative links
    BASE_URL = "https://www.germanytenders.com"

    # Maximum pages to scrape
    MAX_PAGES = 5

    # Cookie consent selectors
    COOKIE_SELECTORS = [
        "//button[contains(text(), 'Accept')]",
        "//button[contains(text(), 'Akzeptieren')]",
        "//button[contains(@class, 'cookie')]",
        ".cookie-accept",
        "#cookie-consent-accept",
    ]

    def scrape(self) -> List[TenderResult]:
        """
        Execute scraping logic for germanytenders.com portal.

        Uses URL-based pagination (?page=N).

        Returns:
            List of TenderResult objects
        """
        all_results = []

        try:
            self.logger.info(f"Navigating to: {self.PORTAL_URL}")
            self.driver.get(self.PORTAL_URL)
            time.sleep(3)

            # Accept cookies
            self.accept_cookies()
            time.sleep(2)

            # Wait for page to load
            try:
                WebDriverWait(self.driver, 15).until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR, "a[href*='/tenders/'], .tender-item, .search-result")
                    )
                )
            except TimeoutException:
                self.logger.warning("Timeout waiting for search results, trying to continue...")

            # Scrape multiple pages using URL-based pagination
            for page in range(1, self.MAX_PAGES + 1):
                self.logger.debug(f"Scraping page {page}")

                # Navigate to page (page 1 is default, no parameter needed)
                if page > 1:
                    page_url = f"{self.PORTAL_URL}?page={page}"
                    self.driver.get(page_url)
                    time.sleep(3)

                # Get page HTML
                html = self.driver.page_source
                soup = BeautifulSoup(html, "lxml")

                # Parse current page results
                page_results = self._parse_results(soup)
                self.logger.debug(f"Page {page}: found {len(page_results)} results")

                if not page_results:
                    self.logger.debug("No results on page, stopping pagination")
                    break

                all_results.extend(page_results)

                # Check if there are more pages
                if not self._has_next_page(soup, page):
                    self.logger.debug("No more pages available")
                    break

            self.logger.info(f"Found {len(all_results)} total tenders")

        except Exception as e:
            self.logger.error(f"GermanyTenders scraping failed: {e}")
            raise ScraperError(self.PORTAL_NAME, str(e)) from e

        # Remove duplicates based on link or title
        seen = set()
        unique_results = []
        for r in all_results:
            key = r.link or r.titel
            if key and key not in seen:
                seen.add(key)
                unique_results.append(r)

        return unique_results

    def _has_next_page(self, soup: BeautifulSoup, current_page: int) -> bool:
        """
        Check if there's a next page available.

        Args:
            soup: BeautifulSoup object of current page
            current_page: Current page number

        Returns:
            True if next page exists, False otherwise
        """
        # Look for pagination links
        next_page = current_page + 1

        # Check for "Next" link
        next_link = soup.select_one(
            f"a[href*='page={next_page}'], "
            f"a.next, "
            f".pagination a:contains('Next'), "
            f".pagination a:contains('{next_page}')"
        )

        if next_link:
            return True

        # Check for pagination text indicating more pages
        pagination = soup.select_one(".pagination, .pager, nav[aria-label*='pagination']")
        if pagination:
            text = pagination.get_text()
            # Look for next page number in pagination
            if str(next_page) in text or "Next" in text or "»" in text:
                return True

        return False

    def _parse_results(self, soup: BeautifulSoup) -> List[TenderResult]:
        """
        Parse germanytenders.com search results page HTML.

        Args:
            soup: BeautifulSoup object of page HTML

        Returns:
            List of TenderResult objects
        """
        results = []
        now = datetime.now()

        # Strategy 1: Look for tender links with detail pages
        # Based on the website structure: anchor elements linking to tender details
        tender_links = soup.select("a[href*='/tenders/']")
        self.logger.debug(f"Found {len(tender_links)} tender links")

        processed_links = set()
        for link in tender_links:
            href = link.get("href", "")

            # Skip if already processed or if it's a search/category link
            if href in processed_links:
                continue
            if "/tenders/search" in href or "/tenders/category" in href:
                continue

            processed_links.add(href)

            result = self._parse_tender_link(link, now)
            if result:
                results.append(result)

        if results:
            return results

        # Strategy 2: Look for card/item containers
        items = soup.select(".tender-item, .tender-card, .search-result, .result-item")
        self.logger.debug(f"Found {len(items)} tender items")

        for item in items:
            result = self._parse_tender_item(item, now)
            if result:
                results.append(result)

        return results

    def _parse_tender_link(self, link_elem, now: datetime) -> TenderResult:
        """
        Parse a tender from a link element.

        Expected format from website:
        - Title text in the link
        - DET Reference Number nearby (e.g., "DET Ref No.: 134002779")
        - Deadline nearby (e.g., "Deadline: 24 Feb 2026")

        Args:
            link_elem: BeautifulSoup link element
            now: Current timestamp

        Returns:
            TenderResult object or None
        """
        try:
            # Get link URL
            href = link_elem.get("href", "")
            if not href:
                return None

            link = urljoin(self.BASE_URL, href)

            # Get title from link text
            titel = clean_text(link_elem.get_text())

            if not titel or len(titel) < 5:
                return None

            # Skip navigation/filter links
            skip_words = ["search", "filter", "login", "register", "subscribe", "category"]
            if any(word in titel.lower() for word in skip_words):
                return None

            # Try to get parent container for additional info
            parent = link_elem.find_parent(["div", "li", "article", "tr"])

            vergabe_id = ""
            naechste_frist = ""
            veroeffentlicht = ""

            if parent:
                parent_text = parent.get_text()

                # Extract DET Reference Number
                ref_match = re.search(r"DET\s*Ref\s*No\.?:?\s*(\d+)", parent_text, re.IGNORECASE)
                if ref_match:
                    vergabe_id = ref_match.group(1)

                # Extract Deadline - format: "DD Mon YYYY" (e.g., "24 Feb 2026")
                deadline_match = re.search(
                    r"Deadline:?\s*(\d{1,2}\s+[A-Za-z]{3}\s+\d{4})",
                    parent_text,
                    re.IGNORECASE
                )
                if deadline_match:
                    naechste_frist = deadline_match.group(1)

                # Try alternative date format DD.MM.YYYY
                if not naechste_frist:
                    deadline_match = re.search(
                        r"Deadline:?\s*(\d{1,2}\.\d{1,2}\.\d{4})",
                        parent_text,
                        re.IGNORECASE
                    )
                    if deadline_match:
                        naechste_frist = deadline_match.group(1)

            # Extract ID from URL if not found
            if not vergabe_id:
                id_match = re.search(r"/tenders/(\d+)", link)
                if id_match:
                    vergabe_id = id_match.group(1)

            return TenderResult(
                portal=self.PORTAL_NAME,
                suchbegriff=None,
                suchzeitpunkt=now,
                vergabe_id=vergabe_id,
                link=link,
                titel=titel,
                ausschreibungsstelle="",  # Not available on listing page
                ausfuehrungsort="",
                ausschreibungsart="",
                naechste_frist=naechste_frist,
                veroeffentlicht=veroeffentlicht,
            )
        except Exception as e:
            self.logger.warning(f"Failed to parse tender link: {e}")
            return None

    def _parse_tender_item(self, item, now: datetime) -> TenderResult:
        """
        Parse a tender item container.

        Args:
            item: BeautifulSoup element
            now: Current timestamp

        Returns:
            TenderResult object or None
        """
        try:
            link = ""
            titel = ""
            vergabe_id = ""
            naechste_frist = ""

            # Find link and title
            link_elem = item.select_one("a[href*='/tenders/']")
            if link_elem:
                link = urljoin(self.BASE_URL, link_elem.get("href", ""))
                titel = clean_text(link_elem.get_text())

            # If no title from link, try heading elements
            if not titel:
                heading = item.select_one("h2, h3, h4, .title, .heading")
                if heading:
                    titel = clean_text(heading.get_text())

            if not titel or len(titel) < 5:
                return None

            # Get full text for metadata extraction
            full_text = item.get_text()

            # Extract DET Reference Number
            ref_match = re.search(r"DET\s*Ref\s*No\.?:?\s*(\d+)", full_text, re.IGNORECASE)
            if ref_match:
                vergabe_id = ref_match.group(1)

            # Extract Deadline
            deadline_match = re.search(
                r"Deadline:?\s*(\d{1,2}\s+[A-Za-z]{3}\s+\d{4})",
                full_text,
                re.IGNORECASE
            )
            if deadline_match:
                naechste_frist = deadline_match.group(1)

            # Extract ID from URL if not found
            if not vergabe_id and link:
                id_match = re.search(r"/tenders/(\d+)", link)
                if id_match:
                    vergabe_id = id_match.group(1)

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
                veroeffentlicht="",
            )
        except Exception as e:
            self.logger.warning(f"Failed to parse tender item: {e}")
            return None
