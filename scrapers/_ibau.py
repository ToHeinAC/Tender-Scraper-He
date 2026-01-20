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

from scrapers.base import BaseScraper, TenderResult, ScraperError
from scrapers.registry import register_scraper
from scrapers.utils import clean_text


@register_scraper
class IBauScraper(BaseScraper):
    """Scraper for ibau.de portal."""

    PORTAL_NAME = "ibau"
    PORTAL_URL = "https://www.ibau.de/auftraege-nach-branche/dienstleistungen/"
    REQUIRES_SELENIUM = True

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

            # Scroll to load dynamic content
            self.scroll_to_bottom(timeout=15, pause=2.0)

            # Get page HTML
            html = self.driver.page_source
            soup = BeautifulSoup(html, "lxml")

            # Parse results
            results = self._parse_results(soup)

        except Exception as e:
            self.logger.error(f"iBau scraping failed: {e}")
            raise ScraperError(self.PORTAL_NAME, str(e)) from e

        return results

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
