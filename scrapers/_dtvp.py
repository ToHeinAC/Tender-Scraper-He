"""
Scraper for DTVP (Deutsches Vergabeportal).

URL: https://www.dtvp.de
German public procurement portal.
"""

import re
import time
from datetime import datetime
from typing import List

from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

from scrapers.base import BaseScraper, TenderResult, ScraperError
from scrapers.registry import register_scraper
from scrapers.utils import clean_text


@register_scraper
class DTVPScraper(BaseScraper):
    """Scraper for dtvp.de procurement portal."""

    PORTAL_NAME = "dtvp"
    PORTAL_URL = "https://www.dtvp.de/Center/common/project/search.do?method=showExtendedSearch&fromExternal=true"
    REQUIRES_SELENIUM = True

    # Number of pages to scrape
    MAX_PAGES = 5

    def scrape(self) -> List[TenderResult]:
        """
        Execute scraping logic for DTVP portal.

        Returns:
            List of TenderResult objects
        """
        all_results = []

        try:
            # Navigate to search page
            self.logger.info(f"Navigating to: {self.PORTAL_URL}")
            self.driver.get(self.PORTAL_URL)
            time.sleep(3)

            # Accept cookies
            self.accept_cookies()
            time.sleep(2)

            # Wait for results to load
            try:
                WebDriverWait(self.driver, 15).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "#listTemplate, .listTemplate, table"))
                )
            except TimeoutException:
                self.logger.warning("Results container not found, trying to parse anyway")
                time.sleep(3)

            # Scrape multiple pages
            for page in range(self.MAX_PAGES):
                self.logger.debug(f"Scraping page {page + 1}")

                # Get page HTML
                html = self.driver.page_source
                soup = BeautifulSoup(html, "lxml")

                # Parse current page results
                results = self._parse_results(soup)
                if results:
                    all_results.extend(results)
                else:
                    self.logger.debug(f"No results found on page {page + 1}")

                # Try to go to next page
                if page < self.MAX_PAGES - 1:
                    if not self._click_next_page():
                        self.logger.debug("No more pages available")
                        break
                    time.sleep(2)

            self.logger.info(f"Found {len(all_results)} tenders total")

        except Exception as e:
            self.logger.error(f"DTVP scraping failed: {e}")
            raise ScraperError(self.PORTAL_NAME, str(e)) from e

        return all_results

    def _click_next_page(self) -> bool:
        """
        Click the next page button.

        Returns:
            True if successful, False if no more pages
        """
        try:
            next_selectors = [
                "#nextPage",
                "a.nextPage",
                "//a[@id='nextPage']",
                "//a[contains(@class, 'next')]",
                "//a[contains(text(), 'weiter')]",
                "//a[contains(text(), '>')]",
            ]

            for selector in next_selectors:
                try:
                    if selector.startswith("//"):
                        next_button = self.driver.find_element(By.XPATH, selector)
                    else:
                        next_button = self.driver.find_element(By.CSS_SELECTOR, selector)

                    if next_button.is_displayed() and next_button.is_enabled():
                        next_button.click()
                        time.sleep(2)
                        return True
                except NoSuchElementException:
                    continue

        except Exception as e:
            self.logger.debug(f"Next page click failed: {e}")

        return False

    def _parse_results(self, soup: BeautifulSoup) -> List[TenderResult]:
        """
        Parse DTVP tender page HTML.

        Args:
            soup: BeautifulSoup object of page HTML

        Returns:
            List of TenderResult objects
        """
        results = []
        now = datetime.now()

        # Strategy 1: Look for listTemplate div (from old notebook)
        list_template = soup.select_one("div[id=listTemplate]")
        if list_template:
            cells = list_template.find_all("td")
            if cells and len(cells) > 6:
                self.logger.debug(f"Found listTemplate with {len(cells)} cells")
                return self._parse_list_template(cells, now)

        # Strategy 2: Look for table rows with tender data
        tables = soup.find_all("table")
        for table in tables:
            rows = table.find_all("tr")
            if len(rows) > 1:
                result = self._parse_table_rows(rows, now)
                if result:
                    return result

        # Strategy 3: Look for any structured result items
        result_items = soup.select(".resultItem, .searchResultRow, .tender-item")
        if result_items:
            self.logger.debug(f"Found {len(result_items)} result items")
            for item in result_items:
                result = self._parse_result_item(item, now)
                if result:
                    results.append(result)

        # Strategy 4: Extract links with tender details
        tender_links = soup.find_all("a", href=re.compile(r"project|tender|detail|notice", re.IGNORECASE))
        if tender_links and not results:
            self.logger.debug(f"Found {len(tender_links)} tender links")
            for link in tender_links:
                result = self._parse_tender_link(link, now)
                if result:
                    results.append(result)

        return results

    def _parse_list_template(self, cells, now: datetime) -> List[TenderResult]:
        """
        Parse cells from listTemplate format (6 columns).

        Column order:
        0: Publication date (veröffentlicht)
        1: Deadline (nächste Frist)
        2: Title (Titel)
        3: Procurement type (Ausschreibungsart)
        4: Organization (Ausschreibungsstelle)
        5: Link/details

        Args:
            cells: List of table cells
            now: Current timestamp

        Returns:
            List of TenderResult objects
        """
        results = []

        # Skip header row cells
        cells = cells[1:] if len(cells) > 6 else cells
        cols = 6
        num_rows = len(cells) // cols

        self.logger.debug(f"Parsing {num_rows} rows from listTemplate")

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
                link_cell = cells[base_idx + 5] if base_idx + 5 < len(cells) else None
                if link_cell:
                    link_elem = link_cell.find("a")
                    if link_elem and link_elem.has_attr("href"):
                        href = link_elem["href"]
                        # Handle JavaScript popup links
                        popup_match = re.search(r"Popup\(['\"]([^'\"]+)['\"]", str(href))
                        if popup_match:
                            link = popup_match.group(1)
                        else:
                            link = href

                        if link and not link.startswith("http"):
                            link = f"https://www.dtvp.de/{link.lstrip('/')}"

                        # Extract ID
                        id_match = re.search(r"[?&]pid=(\d+)", link)
                        if id_match:
                            vergabe_id = id_match.group(1)
                        else:
                            id_match = re.search(r"project[/=](\d+)", link, re.IGNORECASE)
                            if id_match:
                                vergabe_id = id_match.group(1)

                # Skip rows without meaningful data
                if not titel or titel.lower() in ["titel", "title", "-"]:
                    continue

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

    def _parse_table_rows(self, rows, now: datetime) -> List[TenderResult]:
        """
        Parse table rows with tender data.

        Args:
            rows: List of table row elements
            now: Current timestamp

        Returns:
            List of TenderResult objects
        """
        results = []

        # Skip header row
        data_rows = rows[1:] if len(rows) > 1 else rows

        for row in data_rows:
            cells = row.find_all("td")
            if len(cells) < 4:
                continue

            try:
                # Try to extract based on cell count
                titel = ""
                link = ""
                vergabe_id = ""
                ausschreibungsstelle = ""
                ausschreibungsart = ""
                naechste_frist = ""
                veroeffentlicht = ""

                # Look for link first
                for cell in cells:
                    link_elem = cell.find("a")
                    if link_elem:
                        href = link_elem.get("href", "")
                        text = clean_text(link_elem.get_text())
                        if len(text) > len(titel):
                            titel = text
                            link = href
                            if link and not link.startswith("http"):
                                link = f"https://www.dtvp.de/{link.lstrip('/')}"
                            id_match = re.search(r"pid=(\d+)", link)
                            if id_match:
                                vergabe_id = id_match.group(1)

                # Extract other fields from cells
                for idx, cell in enumerate(cells):
                    text = clean_text(cell.get_text())

                    # Date pattern
                    date_match = re.search(r"\d{2}\.\d{2}\.\d{4}", text)
                    if date_match:
                        if not veroeffentlicht:
                            veroeffentlicht = date_match.group(0)
                        elif not naechste_frist:
                            naechste_frist = date_match.group(0)
                        continue

                    # Type keywords
                    if any(kw in text.lower() for kw in ["verfahren", "vergabe", "ausschreibung"]):
                        ausschreibungsart = text
                        continue

                if titel:
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
                self.logger.warning(f"Failed to parse table row: {e}")
                continue

        return results

    def _parse_result_item(self, item, now: datetime) -> TenderResult:
        """
        Parse a single result item div.

        Args:
            item: BeautifulSoup element
            now: Current timestamp

        Returns:
            TenderResult object or None
        """
        try:
            # Find link and title
            link_elem = item.find("a")
            if not link_elem:
                return None

            titel = clean_text(link_elem.get_text())
            href = link_elem.get("href", "")
            link = href if href.startswith("http") else f"https://www.dtvp.de/{href.lstrip('/')}"

            vergabe_id = ""
            id_match = re.search(r"pid=(\d+)", link)
            if id_match:
                vergabe_id = id_match.group(1)

            # Get text content for other fields
            text = clean_text(item.get_text())

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
            self.logger.warning(f"Failed to parse result item: {e}")
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

            if not titel or len(titel) < 5:
                return None

            full_link = href if href.startswith("http") else f"https://www.dtvp.de/{href.lstrip('/')}"

            vergabe_id = ""
            id_match = re.search(r"pid=(\d+)|project[/=](\d+)", full_link, re.IGNORECASE)
            if id_match:
                vergabe_id = id_match.group(1) or id_match.group(2)

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
