"""
Scraper for Bauportal Deutschland.

URL: https://www.bauportal-deutschland.de
Construction tenders from Germany.
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
class BauportalDeutschlandScraper(BaseScraper):
    """Scraper for bauportal-deutschland.de portal."""

    PORTAL_NAME = "bauportal_deutschland"
    PORTAL_URL = "https://www.bauportal-deutschland.de/aktuelle_ausschreibungen_seite_1.html"
    REQUIRES_SELENIUM = True

    # Number of pages to scrape
    MAX_PAGES = 10

    def scrape(self) -> List[TenderResult]:
        """
        Execute scraping logic for Bauportal Deutschland.

        Returns:
            List of TenderResult objects
        """
        all_results = []

        try:
            # Scrape multiple pages
            for page in range(1, self.MAX_PAGES + 1):
                url = f"https://www.bauportal-deutschland.de/aktuelle_ausschreibungen_seite_{page}.html"
                self.logger.debug(f"Scraping page {page}: {url}")

                self.driver.get(url)

                if page == 1:
                    time.sleep(3)
                    self.accept_cookies()
                    time.sleep(2)
                else:
                    time.sleep(2)

                # Scroll to load all content
                self.scroll_to_bottom(timeout=10, pause=1.0)

                # Get page HTML
                html = self.driver.page_source
                soup = BeautifulSoup(html, "lxml")

                # Parse results
                results = self._parse_results(soup)
                if results:
                    all_results.extend(results)
                    self.logger.debug(f"Page {page}: found {len(results)} tenders")
                else:
                    self.logger.debug(f"Page {page}: no results, stopping")
                    break

        except Exception as e:
            self.logger.error(f"Bauportal Deutschland scraping failed: {e}")
            raise ScraperError(self.PORTAL_NAME, str(e)) from e

        # Remove duplicates
        seen = set()
        unique_results = []
        for r in all_results:
            key = (r.titel, r.link)
            if key not in seen:
                seen.add(key)
                unique_results.append(r)

        self.logger.info(f"Found {len(unique_results)} unique tenders")
        return unique_results

    def _parse_results(self, soup: BeautifulSoup) -> List[TenderResult]:
        """
        Parse Bauportal Deutschland page HTML.

        Args:
            soup: BeautifulSoup object of page HTML

        Returns:
            List of TenderResult objects
        """
        results = []
        now = datetime.now()

        # Strategy 1: Look for the specific td style (from old notebook)
        items = soup.select("td[style='width:90%; float:left;border:none;']")
        if items:
            # Skip first item if it's header
            items = items[1:] if len(items) > 1 else items
            self.logger.debug(f"Found {len(items)} items with td selector")

            for item in items:
                result = self._parse_item(item, now)
                if result:
                    results.append(result)

            if results:
                return results

        # Strategy 2: Look for links to ausschreibungen
        tender_links = soup.find_all("a", href=re.compile(r"oeffentliche.*ausschreibung|ausschreibungen"))
        self.logger.debug(f"Found {len(tender_links)} tender links")

        for link in tender_links:
            result = self._parse_link(link, now)
            if result:
                results.append(result)

        # Strategy 3: Look for any structured tender items
        if not results:
            tender_items = soup.select(".ausschreibung, .tender, .item")
            for item in tender_items:
                link_elem = item.find("a")
                if link_elem:
                    result = self._parse_link(link_elem, now)
                    if result:
                        results.append(result)

        return results

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
            # Extract link and title
            link = ""
            titel = ""
            link_elem = item.find("a")
            if link_elem:
                href = link_elem.get("href", "")
                link = href if href.startswith("http") else f"https://www.bauportal-deutschland.de/{href.lstrip('/')}"
                titel = clean_text(link_elem.get_text())

            # Extract location from HTML
            ausfuehrungsort = ""
            ort_match = re.search(r"Ort:</b>\s*([^<]+)", str(item))
            if ort_match:
                ausfuehrungsort = clean_text(ort_match.group(1))

            if not titel or len(titel) < 5:
                return None

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
                naechste_frist="",
                veroeffentlicht="",
            )
        except Exception as e:
            self.logger.warning(f"Failed to parse item: {e}")
            return None

    def _parse_link(self, link, now: datetime) -> TenderResult:
        """
        Parse a tender link element.

        Args:
            link: BeautifulSoup anchor element
            now: Current timestamp

        Returns:
            TenderResult object or None
        """
        try:
            href = link.get("href", "")
            titel = clean_text(link.get_text())

            if not titel or len(titel) < 10:
                return None

            # Skip navigation links
            if any(skip in titel.lower() for skip in ["seite", "weiter", "zurück", "mehr", "login"]):
                return None

            full_link = href if href.startswith("http") else f"https://www.bauportal-deutschland.de/{href.lstrip('/')}"

            # Try to extract location from parent
            ausfuehrungsort = ""
            parent = link.find_parent(["td", "div", "li"])
            if parent:
                ort_match = re.search(r"Ort:</b>\s*([^<]+)|PLZ\s+\d+\s*-\s*([^<,]+)", str(parent))
                if ort_match:
                    ausfuehrungsort = clean_text(ort_match.group(1) or ort_match.group(2))

            return TenderResult(
                portal=self.PORTAL_NAME,
                suchbegriff=None,
                suchzeitpunkt=now,
                vergabe_id="",
                link=full_link,
                titel=titel,
                ausschreibungsstelle="",
                ausfuehrungsort=ausfuehrungsort,
                ausschreibungsart="",
                naechste_frist="",
                veroeffentlicht="",
            )
        except Exception as e:
            self.logger.warning(f"Failed to parse link: {e}")
            return None
