"""
Scraper for RWE Supplier Portal.

URL: https://www.rwe.com/produkte-und-dienstleistungen/lieferantenportal/ausschreibungen/
Energy company tenders from RWE, Germany.
"""

import time
from datetime import datetime
from typing import List

from bs4 import BeautifulSoup

from scrapers.base import BaseScraper, TenderResult, ScraperError
from scrapers.registry import register_scraper
from scrapers.utils import clean_text


@register_scraper
class RWEScraper(BaseScraper):
    """Scraper for RWE supplier portal."""

    PORTAL_NAME = "rwe"
    PORTAL_URL = "https://www.rwe.com/produkte-und-dienstleistungen/lieferantenportal/ausschreibungen/ausschreibung-rwe"
    REQUIRES_SELENIUM = True

    # Cookie consent button class
    COOKIE_SELECTORS = [
        ".cb__button.cb__button--select-all",
        "button.cb__button--select-all",
        "#cb__button--select-all",
        "//button[contains(@class, 'cb__button--select-all')]",
        "//button[contains(text(), 'Alle akzeptieren')]",
        "//button[contains(text(), 'Accept')]",
    ]

    def scrape(self) -> List[TenderResult]:
        """
        Execute scraping logic for RWE portal.

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
            self.logger.error(f"RWE scraping failed: {e}")
            raise ScraperError(self.PORTAL_NAME, str(e)) from e

        return results

    def _parse_results(self, soup: BeautifulSoup) -> List[TenderResult]:
        """
        Parse RWE tender page HTML.

        Args:
            soup: BeautifulSoup object of page HTML

        Returns:
            List of TenderResult objects
        """
        results = []
        now = datetime.now()

        # Strategy 1: Look for tables with class rt--table--bordered (from old notebook)
        containers = soup.select("div.container")
        tables = []

        for container in containers:
            found_tables = container.select("table.rt--table--bordered")
            tables.extend(found_tables)

        if not tables:
            # Try alternative selectors
            tables = soup.select("table.rt--table--bordered")

        if not tables:
            # Try any table in main content
            tables = soup.select("main table, .content table, article table")

        self.logger.debug(f"Found {len(tables)} tender tables")

        for table in tables:
            try:
                result = self._parse_table(table, now)
                if result:
                    results.append(result)
            except Exception as e:
                self.logger.warning(f"Failed to parse table: {e}")
                continue

        # Strategy 2: Look for tender cards/items if no tables found
        if not results:
            tender_items = soup.select(".tender-item, .ausschreibung-item, .rt--item")
            self.logger.debug(f"Trying tender items: found {len(tender_items)}")
            for item in tender_items:
                result = self._parse_item(item, now)
                if result:
                    results.append(result)

        return results

    def _parse_table(self, table, now: datetime) -> TenderResult:
        """
        Parse a single tender table.

        Args:
            table: BeautifulSoup table element
            now: Current timestamp

        Returns:
            TenderResult object or None
        """
        try:
            paragraphs = table.find_all("p")
            tds = table.find_all("td")
            links = table.find_all("a")

            # Extract ID (usually in second paragraph)
            vergabe_id = ""
            if len(paragraphs) > 1:
                vergabe_id = clean_text(paragraphs[1].get_text())

            # Extract title (usually in fourth paragraph)
            titel = ""
            if len(paragraphs) > 3:
                titel = clean_text(paragraphs[3].get_text())
            elif len(paragraphs) > 0:
                # Fallback: use first non-empty paragraph
                for p in paragraphs:
                    text = clean_text(p.get_text())
                    if text and len(text) > 10:
                        titel = text
                        break

            # Extract organization (usually in 6th td)
            ausschreibungsstelle = ""
            if len(tds) > 5:
                ausschreibungsstelle = clean_text(tds[5].get_text())
            elif len(tds) > 0:
                # Try to find org in any td
                for td in tds:
                    text = clean_text(td.get_text())
                    if "RWE" in text or "Power" in text or "Nuclear" in text:
                        ausschreibungsstelle = text
                        break

            # Extract link
            link = ""
            if links:
                href = links[0].get("href", "")
                if href:
                    link = href if href.startswith("http") else f"https://www.rwe.com{href}"

            if not titel:
                return None

            return TenderResult(
                portal=self.PORTAL_NAME,
                suchbegriff=None,
                suchzeitpunkt=now,
                vergabe_id=vergabe_id,
                link=link,
                titel=titel,
                ausschreibungsstelle=ausschreibungsstelle or "RWE",
                ausfuehrungsort="",
                ausschreibungsart="",
                naechste_frist="",
                veroeffentlicht="",
            )
        except Exception as e:
            self.logger.warning(f"Failed to parse RWE table: {e}")
            return None

    def _parse_item(self, item, now: datetime) -> TenderResult:
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

            # Find link and title
            link_elem = item.find("a")
            if link_elem:
                titel = clean_text(link_elem.get_text())
                href = link_elem.get("href", "")
                link = href if href.startswith("http") else f"https://www.rwe.com{href}"

            # Find ID
            id_elem = item.select_one(".id, .identifier, .nummer")
            if id_elem:
                vergabe_id = clean_text(id_elem.get_text())

            if not titel:
                titel = clean_text(item.get_text())[:200]

            if not titel or len(titel) < 5:
                return None

            return TenderResult(
                portal=self.PORTAL_NAME,
                suchbegriff=None,
                suchzeitpunkt=now,
                vergabe_id=vergabe_id,
                link=link,
                titel=titel,
                ausschreibungsstelle="RWE",
                ausfuehrungsort="",
                ausschreibungsart="",
                naechste_frist="",
                veroeffentlicht="",
            )
        except Exception as e:
            self.logger.warning(f"Failed to parse RWE item: {e}")
            return None
