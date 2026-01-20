"""
Scraper for Vergabe Rheinland-Pfalz.

URL: https://www.vergabe.rlp.de
Government tenders from Rhineland-Palatinate, Germany.
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
class VergabeRLPScraper(BaseScraper):
    """Scraper for vergabe.rlp.de procurement portal."""

    PORTAL_NAME = "vergabe_rlp"
    PORTAL_URL = "https://www.vergabe.rlp.de/VMPCenter/company/welcome.do"
    REQUIRES_SELENIUM = True

    def scrape(self) -> List[TenderResult]:
        """
        Execute scraping logic for Vergabe RLP portal.

        Returns:
            List of TenderResult objects
        """
        results = []

        try:
            # Navigate to main page
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
            self.logger.error(f"Vergabe RLP scraping failed: {e}")
            raise ScraperError(self.PORTAL_NAME, str(e)) from e

        return results

    def _parse_results(self, soup: BeautifulSoup) -> List[TenderResult]:
        """
        Parse Vergabe RLP tender page HTML.

        Args:
            soup: BeautifulSoup object of page HTML

        Returns:
            List of TenderResult objects
        """
        results = []
        now = datetime.now()

        # Strategy 1: Find contentContainer with table cells (from notebook)
        content_container = soup.select_one("div#contentContainer")
        if content_container:
            cells = content_container.find_all("td")
            # Skip first cell (usually header)
            cells = cells[1:] if len(cells) > 1 else cells
            self.logger.debug(f"Found {len(cells)} table cells")

            # Process cells in groups of 6 (6 columns per row)
            cols = 6
            num_rows = len(cells) // cols

            for row_idx in range(num_rows):
                try:
                    result = self._parse_row_cells(cells, row_idx, cols, now)
                    if result:
                        results.append(result)
                except Exception as e:
                    self.logger.warning(f"Failed to parse row {row_idx}: {e}")
                    continue

            if results:
                return results

        # Strategy 2: Try finding table rows directly
        table_rows = soup.select("table tr")
        self.logger.debug(f"Trying table rows: found {len(table_rows)}")
        for row in table_rows:
            cells = row.find_all("td")
            if len(cells) >= 5:
                result = self._parse_table_row(row, now)
                if result:
                    results.append(result)

        # Strategy 3: Look for any tender links
        if not results:
            tender_links = soup.find_all("a", href=re.compile(r"Popup|pid=|tender"))
            self.logger.debug(f"Found {len(tender_links)} tender links")
            for link in tender_links:
                result = self._parse_tender_link(link, now)
                if result:
                    results.append(result)

        return results

    def _parse_row_cells(self, cells, row_idx: int, cols: int, now: datetime) -> TenderResult:
        """
        Parse a row from cells array.

        Args:
            cells: List of all td elements
            row_idx: Row index
            cols: Number of columns per row
            now: Current timestamp

        Returns:
            TenderResult object or None
        """
        base = row_idx * cols

        # Column 0: Publication date
        veroeffentlicht = ""
        if base < len(cells):
            veroeffentlicht = clean_text(cells[base].get_text())

        # Column 1: Deadline
        naechste_frist = ""
        if base + 1 < len(cells):
            naechste_frist = clean_text(cells[base + 1].get_text())

        # Column 2: Title
        titel = ""
        if base + 2 < len(cells):
            titel = clean_text(cells[base + 2].get_text())

        # Column 3: Type
        ausschreibungsart = ""
        if base + 3 < len(cells):
            ausschreibungsart = clean_text(cells[base + 3].get_text())

        # Column 4: Organization
        ausschreibungsstelle = ""
        if base + 4 < len(cells):
            ausschreibungsstelle = clean_text(cells[base + 4].get_text())

        # Column 5: Link
        link = ""
        vergabe_id = ""
        if base + 5 < len(cells):
            link_elem = cells[base + 5].find("a")
            if link_elem and link_elem.has_attr("href"):
                href = link_elem["href"]
                # Extract link from Popup() JavaScript call
                popup_match = re.search(r"Popup\(['\"]([^'\"]+)['\"]", href)
                if popup_match:
                    link = f"https://www.vergabe.rlp.de/{popup_match.group(1)}"
                else:
                    link = href if href.startswith("http") else f"https://www.vergabe.rlp.de/{href.lstrip('/')}"

                # Extract pid from link
                pid_match = re.search(r"pid=([^&]+)", link)
                if pid_match:
                    vergabe_id = pid_match.group(1)

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
            ausschreibungsart=ausschreibungsart,
            naechste_frist=naechste_frist,
            veroeffentlicht=veroeffentlicht,
        )

    def _parse_table_row(self, row, now: datetime) -> TenderResult:
        """
        Parse a table row element.

        Args:
            row: BeautifulSoup tr element
            now: Current timestamp

        Returns:
            TenderResult object or None
        """
        cells = row.find_all("td")
        if len(cells) < 5:
            return None

        try:
            veroeffentlicht = clean_text(cells[0].get_text())
            naechste_frist = clean_text(cells[1].get_text()) if len(cells) > 1 else ""
            titel = clean_text(cells[2].get_text()) if len(cells) > 2 else ""
            ausschreibungsart = clean_text(cells[3].get_text()) if len(cells) > 3 else ""
            ausschreibungsstelle = clean_text(cells[4].get_text()) if len(cells) > 4 else ""

            link = ""
            vergabe_id = ""
            link_elem = row.find("a")
            if link_elem and link_elem.has_attr("href"):
                href = link_elem["href"]
                popup_match = re.search(r"Popup\(['\"]([^'\"]+)['\"]", href)
                if popup_match:
                    link = f"https://www.vergabe.rlp.de/{popup_match.group(1)}"
                else:
                    link = href if href.startswith("http") else f"https://www.vergabe.rlp.de/{href.lstrip('/')}"

                pid_match = re.search(r"pid=([^&]+)", link)
                if pid_match:
                    vergabe_id = pid_match.group(1)

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
                ausschreibungsart=ausschreibungsart,
                naechste_frist=naechste_frist,
                veroeffentlicht=veroeffentlicht,
            )
        except Exception as e:
            self.logger.warning(f"Failed to parse table row: {e}")
            return None

    def _parse_tender_link(self, link, now: datetime) -> TenderResult:
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
            if any(skip in titel.lower() for skip in ["seite", "weiter", "zurück", "mehr", "login", "suche"]):
                return None

            # Extract link from Popup() if present
            popup_match = re.search(r"Popup\(['\"]([^'\"]+)['\"]", href)
            if popup_match:
                full_link = f"https://www.vergabe.rlp.de/{popup_match.group(1)}"
            else:
                full_link = href if href.startswith("http") else f"https://www.vergabe.rlp.de/{href.lstrip('/')}"

            # Extract pid
            vergabe_id = ""
            pid_match = re.search(r"pid=([^&]+)", full_link)
            if pid_match:
                vergabe_id = pid_match.group(1)

            return TenderResult(
                portal=self.PORTAL_NAME,
                suchbegriff=None,
                suchzeitpunkt=now,
                vergabe_id=vergabe_id,
                link=full_link,
                titel=titel,
                ausschreibungsstelle="",
                ausfuehrungsort="",
                ausschreibungsart="",
                naechste_frist="",
                veroeffentlicht="",
            )
        except Exception as e:
            self.logger.warning(f"Failed to parse tender link: {e}")
            return None
