"""
Scraper for Vergabeportal Baden-Wuerttemberg (Satellite).

URL: https://www.vergabeportal-bw.de/Satellite/company/welcome.do
Alternative government tender portal for Baden-Wuerttemberg, Germany.
"""

import re
import time
from datetime import datetime
from typing import List
import logging

from bs4 import BeautifulSoup

from scrapers.base import BaseScraper, TenderResult, ScraperError
from scrapers.registry import register_scraper
from scrapers.utils import clean_text


@register_scraper
class VergabeplattformBWScraper(BaseScraper):
    """Scraper for vergabeportal-bw.de procurement portal (Satellite)."""

    PORTAL_NAME = "vergabeplattform_bw"
    PORTAL_URL = "https://www.vergabeportal-bw.de/Satellite/company/welcome.do"
    REQUIRES_SELENIUM = True

    # Alternative URL that may redirect here
    ALT_URL = "https://ausschreibungen.landbw.de/Center/company/welcome.do"

    def scrape(self) -> List[TenderResult]:
        """
        Execute scraping logic for Vergabeportal BW.

        Returns:
            List of TenderResult objects
        """
        results = []

        try:
            # Navigate to portal
            self.driver.get(self.PORTAL_URL)
            self.accept_cookies()
            time.sleep(3)

            # Get page HTML
            html = self.driver.page_source
            soup = BeautifulSoup(html, "lxml")

            # Log current URL in case of redirect
            current_url = self.driver.current_url
            self.logger.debug(f"Current URL after navigation: {current_url}")

            # Parse results
            results = self._parse_results(soup)

        except Exception as e:
            self.logger.error(f"Vergabeportal BW scraping failed: {e}")
            raise ScraperError(self.PORTAL_NAME, str(e)) from e

        return results

    def _parse_results(self, soup: BeautifulSoup) -> List[TenderResult]:
        """
        Parse Vergabeportal BW tender page HTML.

        Tries multiple parsing strategies based on page structure.

        Args:
            soup: BeautifulSoup object of page HTML

        Returns:
            List of TenderResult objects
        """
        results = []
        now = datetime.now()

        # Strategy 1: Try NetServer-style table rows (same as vergabe_bw)
        rows = soup.select("tr.tableRow.clickable-row.publicationDetail")
        if rows:
            self.logger.debug(f"Found {len(rows)} rows using NetServer pattern")
            return self._parse_netserver_rows(rows, now)

        # Strategy 2: Try contentContainer table pattern
        content_container = soup.select_one("div[id=contentContainer]")
        if content_container:
            cells = content_container.find_all("td")
            if cells:
                self.logger.debug(f"Found {len(cells)} cells in contentContainer")
                return self._parse_content_container(cells, now)

        # Strategy 3: Try listTemplate pattern (like NRW)
        list_template = soup.select_one("div[id=listTemplate]")
        if list_template:
            cells = list_template.find_all("td")
            if cells:
                self.logger.debug(f"Found {len(cells)} cells in listTemplate")
                return self._parse_list_template(cells, now)

        # Strategy 4: Try generic table pattern
        tables = soup.find_all("table")
        for table in tables:
            rows = table.find_all("tr")
            if len(rows) > 1:  # At least header + one data row
                self.logger.debug(f"Trying generic table with {len(rows)} rows")
                result = self._parse_generic_table(table, now)
                if result:
                    return result

        self.logger.warning("Could not find tender data using any parsing strategy")
        return results

    def _parse_netserver_rows(self, rows, now: datetime) -> List[TenderResult]:
        """
        Parse rows in NetServer format (same as vergabe_bw).

        Args:
            rows: List of row elements
            now: Current timestamp

        Returns:
            List of TenderResult objects
        """
        results = []

        for row in rows:
            try:
                cells = row.find_all("td")
                if len(cells) < 5:
                    continue

                veroeffentlicht = clean_text(cells[0].get_text())
                titel = clean_text(cells[1].get_text())
                ausschreibungsstelle = clean_text(cells[2].get_text())
                ausschreibungsart = clean_text(cells[3].get_text())
                naechste_frist = clean_text(cells[4].get_text())

                vergabe_id = row.get("data-oid", "")
                category = row.get("data-category", "")

                link = ""
                if vergabe_id and category:
                    link = (
                        f"https://www.vergabeportal-bw.de/Satellite/"
                        f"PublicationControllerServlet?function=Detail"
                        f"&TOID={vergabe_id}&Category={category}"
                    )

                results.append(TenderResult(
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
                ))
            except Exception as e:
                self.logger.warning(f"Failed to parse NetServer row: {e}")
                continue

        return results

    def _parse_content_container(self, cells, now: datetime) -> List[TenderResult]:
        """
        Parse cells in contentContainer format.

        Expected column order (6 columns):
        0: Publication date
        1: Deadline
        2: Title
        3: Procurement type
        4: Organization
        5: Link

        Args:
            cells: List of table cells
            now: Current timestamp

        Returns:
            List of TenderResult objects
        """
        results = []

        # Skip header row (first 6 cells)
        cells = cells[1:] if len(cells) > 6 else cells
        cols = 6
        num_rows = len(cells) // cols

        for row_idx in range(num_rows):
            try:
                base_idx = row_idx * cols

                veroeffentlicht = clean_text(cells[base_idx + 0].get_text())
                naechste_frist = clean_text(cells[base_idx + 1].get_text())
                titel = clean_text(cells[base_idx + 2].get_text())
                ausschreibungsart = clean_text(cells[base_idx + 3].get_text())
                ausschreibungsstelle = clean_text(cells[base_idx + 4].get_text())

                # Extract link from column 5
                link = ""
                vergabe_id = ""
                link_cell = cells[base_idx + 5]
                link_elem = link_cell.find("a")
                if link_elem and link_elem.has_attr("href"):
                    href = link_elem["href"]
                    # Handle JavaScript popup links
                    popup_match = re.search(r"Popup\(['\"]([^'\"]+)['\"]", str(href))
                    if popup_match:
                        link = popup_match.group(1)
                        if not link.startswith("http"):
                            link = f"https://www.vergabeportal-bw.de/{link.lstrip('/')}"
                    else:
                        link = href
                        if not link.startswith("http"):
                            link = f"https://www.vergabeportal-bw.de/{link.lstrip('/')}"

                    # Try to extract ID from link
                    id_match = re.search(r"[?&]pid=(\d+)", link)
                    if id_match:
                        vergabe_id = id_match.group(1)
                    else:
                        id_match = re.search(r"TOID=([^&]+)", link)
                        if id_match:
                            vergabe_id = id_match.group(1)

                results.append(TenderResult(
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
                ))
            except Exception as e:
                self.logger.warning(f"Failed to parse contentContainer row {row_idx}: {e}")
                continue

        return results

    def _parse_list_template(self, cells, now: datetime) -> List[TenderResult]:
        """
        Parse cells in listTemplate format (like NRW portal).

        Args:
            cells: List of table cells
            now: Current timestamp

        Returns:
            List of TenderResult objects
        """
        results = []
        cells = cells[1:]  # Skip header
        cols = 6
        num_rows = len(cells) // cols

        for row_idx in range(num_rows):
            try:
                base_idx = row_idx * cols

                veroeffentlicht = clean_text(cells[base_idx + 0].get_text())
                naechste_frist = clean_text(cells[base_idx + 1].get_text())
                titel = clean_text(cells[base_idx + 2].get_text())
                ausschreibungsart = clean_text(cells[base_idx + 3].get_text())
                ausschreibungsstelle = clean_text(cells[base_idx + 4].get_text())

                # Extract link
                link = ""
                vergabe_id = ""
                link_cell = cells[base_idx + 5]
                link_elem = link_cell.find("a")
                if link_elem and link_elem.has_attr("href"):
                    href = link_elem["href"]
                    popup_match = re.search(r"Popup\(['\"]([^'\"]+)['\"]", str(href))
                    if popup_match:
                        link = popup_match.group(1)
                        if not link.startswith("http"):
                            link = f"https://www.vergabeportal-bw.de/{link.lstrip('/')}"
                    else:
                        link = href

                    id_match = re.search(r"[?&]pid=(\d+)", link)
                    if id_match:
                        vergabe_id = id_match.group(1)

                results.append(TenderResult(
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
                ))
            except Exception as e:
                self.logger.warning(f"Failed to parse listTemplate row {row_idx}: {e}")
                continue

        return results

    def _parse_generic_table(self, table, now: datetime) -> List[TenderResult]:
        """
        Try to parse a generic table structure.

        Args:
            table: BeautifulSoup table element
            now: Current timestamp

        Returns:
            List of TenderResult objects or empty list if structure not recognized
        """
        results = []
        rows = table.find_all("tr")

        if len(rows) < 2:
            return results

        # Skip header row
        for row in rows[1:]:
            cells = row.find_all("td")
            if len(cells) < 4:
                continue

            try:
                # Try to extract at least title and link
                titel = ""
                link = ""
                vergabe_id = ""
                ausschreibungsstelle = ""
                ausschreibungsart = ""
                naechste_frist = ""
                veroeffentlicht = ""

                # Look for link in any cell
                for cell in cells:
                    link_elem = cell.find("a")
                    if link_elem:
                        if link_elem.has_attr("href"):
                            link = link_elem["href"]
                        text = clean_text(link_elem.get_text())
                        if len(text) > len(titel):
                            titel = text

                # If we have at least a title, create result
                if titel or link:
                    results.append(TenderResult(
                        portal=self.PORTAL_NAME,
                        suchbegriff=None,
                        suchzeitpunkt=now,
                        vergabe_id=vergabe_id,
                        link=link,
                        titel=titel or "Unknown",
                        ausschreibungsstelle=ausschreibungsstelle,
                        ausfuehrungsort="",
                        ausschreibungsart=ausschreibungsart,
                        naechste_frist=naechste_frist,
                        veroeffentlicht=veroeffentlicht,
                    ))
            except Exception as e:
                self.logger.warning(f"Failed to parse generic table row: {e}")
                continue

        return results
