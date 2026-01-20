"""
Scraper for KTE (Kerntechnische Entsorgung Karlsruhe).

URL: https://www.kte-karlsruhe.de/ausschreibungen
Nuclear decommissioning tenders from KTE, Germany.
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
class KTEScraper(BaseScraper):
    """Scraper for KTE Karlsruhe tenders portal."""

    PORTAL_NAME = "kte"
    PORTAL_URL = "https://www.kte-karlsruhe.de/ausschreibungen"
    REQUIRES_SELENIUM = True

    def scrape(self) -> List[TenderResult]:
        """
        Execute scraping logic for KTE portal.

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

            # Get page HTML
            html = self.driver.page_source
            soup = BeautifulSoup(html, "lxml")

            # Parse results
            results = self._parse_results(soup)

        except Exception as e:
            self.logger.error(f"KTE scraping failed: {e}")
            raise ScraperError(self.PORTAL_NAME, str(e)) from e

        return results

    def _parse_results(self, soup: BeautifulSoup) -> List[TenderResult]:
        """
        Parse KTE tender page HTML.

        Args:
            soup: BeautifulSoup object of page HTML

        Returns:
            List of TenderResult objects
        """
        results = []
        now = datetime.now()

        # Strategy 1: Look for announcements table (same structure as JEN)
        announcements_tables = soup.select("table.announcements")

        if announcements_tables:
            self.logger.debug(f"Found {len(announcements_tables)} announcements tables")
            for table in announcements_tables:
                table_results = self._parse_announcements_table(table, now)
                results.extend(table_results)

        # Strategy 2: Look for tender divs/cards
        if not results:
            tender_items = soup.select(".tender-item, .ausschreibung, .announcement")
            self.logger.debug(f"Trying tender items: found {len(tender_items)}")
            for item in tender_items:
                result = self._parse_tender_item(item, now)
                if result:
                    results.append(result)

        # Strategy 3: Look for any links to deutsche-evergabe
        if not results:
            evergabe_links = soup.find_all("a", href=re.compile(r"deutsche-evergabe|bieterzugang"))
            self.logger.debug(f"Found {len(evergabe_links)} evergabe links")
            for link in evergabe_links:
                result = self._parse_evergabe_link(link, now)
                if result:
                    results.append(result)

        return results

    def _parse_announcements_table(self, table, now: datetime) -> List[TenderResult]:
        """
        Parse announcements table structure.

        Divs come in pairs: info div + button div

        Args:
            table: BeautifulSoup table element
            now: Current timestamp

        Returns:
            List of TenderResult objects
        """
        results = []
        divs = table.find_all("div")
        self.logger.debug(f"Found {len(divs)} divs in announcements table")

        # Process divs in pairs
        i = 0
        while i < len(divs) - 1:
            try:
                info_div = divs[i]
                button_div = divs[i + 1]

                # Extract ID from tender--identifier span
                vergabe_id = ""
                id_elem = info_div.select_one("span.tender--identifier")
                if id_elem:
                    vergabe_id = clean_text(id_elem.get_text())

                # Extract title from title span
                titel = ""
                title_elem = info_div.select_one("span.title")
                if title_elem:
                    titel = clean_text(title_elem.get_text())

                # Extract type and deadline from category paragraph
                ausschreibungsart = ""
                naechste_frist = ""
                category_elem = info_div.select_one("p.category")
                if category_elem:
                    category_text = category_elem.get_text()

                    # Extract Vergabeart
                    art_match = re.search(r"Vergabeart:\s*([^\n]+)", category_text)
                    if art_match:
                        ausschreibungsart = clean_text(art_match.group(1))

                    # Extract deadline
                    deadline_match = re.search(r"Angebotsschlusstermin:\s*(\d{2}\.\d{2}\.\d{4})", category_text)
                    if deadline_match:
                        naechste_frist = deadline_match.group(1)

                # Extract link from button div
                link = ""
                link_elem = button_div.select_one("a.button, a")
                if link_elem and link_elem.has_attr("href"):
                    link = link_elem["href"]

                if titel:
                    results.append(TenderResult(
                        portal=self.PORTAL_NAME,
                        suchbegriff=None,
                        suchzeitpunkt=now,
                        vergabe_id=vergabe_id,
                        link=link,
                        titel=titel,
                        ausschreibungsstelle="KTE",
                        ausfuehrungsort="Karlsruhe",
                        ausschreibungsart=ausschreibungsart,
                        naechste_frist=naechste_frist,
                        veroeffentlicht="",
                    ))

                i += 2
            except Exception as e:
                self.logger.warning(f"Failed to parse div pair at index {i}: {e}")
                i += 1
                continue

        return results

    def _parse_tender_item(self, item, now: datetime) -> TenderResult:
        """
        Parse a tender item element.

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
            title_elem = item.select_one(".title, h3, h4, .name")
            if title_elem:
                titel = clean_text(title_elem.get_text())

            # Find link
            link_elem = item.find("a")
            if link_elem and link_elem.has_attr("href"):
                link = link_elem["href"]
                if not titel:
                    titel = clean_text(link_elem.get_text())

            # Find ID
            id_elem = item.select_one(".tender--identifier, .id, .nummer")
            if id_elem:
                vergabe_id = clean_text(id_elem.get_text())

            if not titel or len(titel) < 5:
                return None

            return TenderResult(
                portal=self.PORTAL_NAME,
                suchbegriff=None,
                suchzeitpunkt=now,
                vergabe_id=vergabe_id,
                link=link,
                titel=titel,
                ausschreibungsstelle="KTE",
                ausfuehrungsort="Karlsruhe",
                ausschreibungsart="",
                naechste_frist="",
                veroeffentlicht="",
            )
        except Exception as e:
            self.logger.warning(f"Failed to parse KTE item: {e}")
            return None

    def _parse_evergabe_link(self, link, now: datetime) -> TenderResult:
        """
        Parse a link to deutsche-evergabe.

        Args:
            link: BeautifulSoup anchor element
            now: Current timestamp

        Returns:
            TenderResult object or None
        """
        try:
            href = link.get("href", "")
            titel = clean_text(link.get_text())

            if not titel or len(titel) < 5:
                # Try parent element
                parent = link.find_parent(["div", "tr", "li"])
                if parent:
                    titel = clean_text(parent.get_text())[:200]

            if not titel or len(titel) < 5:
                return None

            # Extract ID from URL
            vergabe_id = ""
            id_match = re.search(r"/(\d+)/?$|[?&]id=(\d+)", href)
            if id_match:
                vergabe_id = id_match.group(1) or id_match.group(2)

            return TenderResult(
                portal=self.PORTAL_NAME,
                suchbegriff=None,
                suchzeitpunkt=now,
                vergabe_id=vergabe_id,
                link=href,
                titel=titel,
                ausschreibungsstelle="KTE",
                ausfuehrungsort="Karlsruhe",
                ausschreibungsart="",
                naechste_frist="",
                veroeffentlicht="",
            )
        except Exception as e:
            self.logger.warning(f"Failed to parse evergabe link: {e}")
            return None
