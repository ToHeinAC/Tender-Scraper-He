"""
Scraper for iBau Portal.

URL: https://www.ibau.de
Construction and services tenders from Germany.
"""

import re
import time
from datetime import datetime
from typing import List

from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException

from scrapers.base import BaseScraper, TenderResult, ScraperError
from scrapers.registry import register_scraper
from scrapers.utils import clean_text


@register_scraper
class IBauScraper(BaseScraper):
    """Scraper for ibau.de portal."""

    PORTAL_NAME = "ibau"
    PORTAL_URL = "https://www.ibau.de/auftraege-nach-branche/dienstleistungen/"
    REQUIRES_SELENIUM = True

    # Maximum number of "Load More" clicks (12 tenders per click, ~240 total)
    MAX_LOAD_MORE_CLICKS = 20

    def scrape(self) -> List[TenderResult]:
        """
        Execute scraping logic for iBau portal.

        Returns:
            List of TenderResult objects
        """
        results = []

        try:
            # Navigate to tenders page
            self.logger.info(f"Navigating to: {self.PORTAL_URL}")
            self.driver.get(self.PORTAL_URL)
            time.sleep(3)

            # Accept cookies
            self.accept_cookies()
            time.sleep(2)

            # Click "Load More" button repeatedly to load more tenders
            self._load_more_tenders()

            # Scroll to ensure all content is loaded
            self.scroll_to_bottom(timeout=10, pause=1.0)

            # Get page HTML
            html = self.driver.page_source
            soup = BeautifulSoup(html, "lxml")

            # Parse results
            results = self._parse_results(soup)

            self.logger.info(f"Found {len(results)} total tenders")

        except Exception as e:
            self.logger.error(f"iBau scraping failed: {e}")
            raise ScraperError(self.PORTAL_NAME, str(e)) from e

        return results

    def _load_more_tenders(self) -> None:
        """
        Click "Weitere Ergebnisse laden" button repeatedly to load more tenders.
        """
        clicks = 0
        consecutive_failures = 0

        for _ in range(self.MAX_LOAD_MORE_CLICKS):
            if consecutive_failures >= 3:
                self.logger.debug("Stopping load more after 3 consecutive failures")
                break

            if self._click_load_more():
                clicks += 1
                consecutive_failures = 0
                self.logger.debug(f"Load more click {clicks} successful")
                time.sleep(2)
            else:
                consecutive_failures += 1
                time.sleep(1)

        self.logger.info(f"Completed {clicks} 'Load More' clicks")

    def _click_load_more(self) -> bool:
        """
        Click the "Weitere Ergebnisse laden" (Load More) button.

        Returns:
            True if successful, False if button not found or not clickable
        """
        load_more_selectors = [
            # German "Load More" button text
            "//a[contains(text(), 'Weitere Ergebnisse laden')]",
            "//button[contains(text(), 'Weitere Ergebnisse laden')]",
            "//a[contains(text(), 'Mehr laden')]",
            "//button[contains(text(), 'Mehr laden')]",
            "//a[contains(text(), 'Weitere')]",
            # Generic load more selectors
            "a.load-more",
            "button.load-more",
            ".load-more-button",
            "[data-action='load-more']",
            "a[href*='loadMore']",
        ]

        for selector in load_more_selectors:
            try:
                if selector.startswith("//"):
                    btn = self.driver.find_element(By.XPATH, selector)
                else:
                    btn = self.driver.find_element(By.CSS_SELECTOR, selector)

                if btn.is_displayed() and btn.is_enabled():
                    # Scroll element into view before clicking
                    self.driver.execute_script(
                        "arguments[0].scrollIntoView({block: 'center'});", btn
                    )
                    time.sleep(0.5)
                    btn.click()
                    return True
            except NoSuchElementException:
                continue
            except Exception as e:
                self.logger.debug(f"Load more click failed with selector {selector}: {e}")
                continue

        return False

    def _parse_results(self, soup: BeautifulSoup) -> List[TenderResult]:
        """
        Parse iBau tender page HTML.

        Args:
            soup: BeautifulSoup object of page HTML

        Returns:
            List of TenderResult objects
        """
        results = []
        now = datetime.now()

        # Strategy 1: Look for tender inner wrappers (from old notebook)
        tender_wrappers = soup.select("div.tender--inner-wrapper")
        self.logger.debug(f"Found {len(tender_wrappers)} tender wrappers")

        for wrapper in tender_wrappers:
            result = self._parse_tender_wrapper(wrapper, now)
            if result:
                results.append(result)

        # Strategy 2: Try alternative selectors if no results
        if not results:
            tender_items = soup.select(".tender-item, .tender, .ausschreibung")
            self.logger.debug(f"Trying alternative selectors: found {len(tender_items)}")
            for item in tender_items:
                result = self._parse_generic_item(item, now)
                if result:
                    results.append(result)

        # Strategy 3: Look for any tender cards
        if not results:
            cards = soup.select("[class*='tender'], [class*='auftrag']")
            self.logger.debug(f"Trying card selectors: found {len(cards)}")
            for card in cards:
                result = self._parse_generic_item(card, now)
                if result:
                    results.append(result)

        return results

    def _parse_tender_wrapper(self, wrapper, now: datetime) -> TenderResult:
        """
        Parse a tender wrapper element.

        Args:
            wrapper: BeautifulSoup element
            now: Current timestamp

        Returns:
            TenderResult object or None
        """
        try:
            # Extract title from headline
            titel = ""
            headline = wrapper.select_one("div.tender--headline")
            if headline:
                titel = clean_text(headline.get_text()).replace("\xad", "")

            # Extract factlist values
            factlist_values = wrapper.select("span.tender--factlist-item-value")

            # Index 0: Location (Ort)
            ausfuehrungsort = ""
            if len(factlist_values) > 0:
                ausfuehrungsort = clean_text(factlist_values[0].get_text())

            # Index 1: Organization (Stelle)
            ausschreibungsstelle = ""
            if len(factlist_values) > 1:
                ausschreibungsstelle = clean_text(factlist_values[1].get_text())

            # Index 2: Publication date
            veroeffentlicht = ""
            if len(factlist_values) > 2:
                veroeffentlicht = clean_text(factlist_values[2].get_text())

            # Index 3: Deadline
            naechste_frist = ""
            if len(factlist_values) > 3:
                naechste_frist = clean_text(factlist_values[3].get_text())

            # Extract ID from data-tender-id attribute
            vergabe_id = ""
            id_match = re.search(r'data-tender-id="(\d+)"', str(wrapper))
            if id_match:
                vergabe_id = id_match.group(1)

            # Try to find link
            link = self.PORTAL_URL
            link_elem = wrapper.find("a")
            if link_elem and link_elem.has_attr("href"):
                href = link_elem["href"]
                link = href if href.startswith("http") else f"https://www.ibau.de{href}"

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
                ausschreibungsart="",
                naechste_frist=naechste_frist,
                veroeffentlicht=veroeffentlicht,
            )
        except Exception as e:
            self.logger.warning(f"Failed to parse tender wrapper: {e}")
            return None

    def _parse_generic_item(self, item, now: datetime) -> TenderResult:
        """
        Parse a generic tender item element.

        Args:
            item: BeautifulSoup element
            now: Current timestamp

        Returns:
            TenderResult object or None
        """
        try:
            titel = ""
            link = self.PORTAL_URL

            # Find title
            title_elem = item.select_one(".headline, .title, h3, h4, .name")
            if title_elem:
                titel = clean_text(title_elem.get_text())

            # Find link
            link_elem = item.find("a")
            if link_elem:
                if not titel:
                    titel = clean_text(link_elem.get_text())
                href = link_elem.get("href", "")
                if href:
                    link = href if href.startswith("http") else f"https://www.ibau.de{href}"

            if not titel or len(titel) < 5:
                return None

            # Extract other fields from text
            text = item.get_text()
            ausfuehrungsort = ""
            veroeffentlicht = ""
            naechste_frist = ""

            # Try to find dates
            dates = re.findall(r"\d{2}\.\d{2}\.\d{4}", text)
            if len(dates) >= 2:
                veroeffentlicht = dates[0]
                naechste_frist = dates[1]
            elif len(dates) == 1:
                naechste_frist = dates[0]

            return TenderResult(
                portal=self.PORTAL_NAME,
                suchbegriff=None,
                suchzeitpunkt=now,
                vergabe_id="",
                link=link,
                titel=titel,
                ausschreibungsstelle="",
                ausfuehrungsort=ausfuehrungsort,
                ausschreibungsart="",
                naechste_frist=naechste_frist,
                veroeffentlicht=veroeffentlicht,
            )
        except Exception as e:
            self.logger.warning(f"Failed to parse generic item: {e}")
            return None
