"""
Scraper for Deutsche eVergabe.

URL: https://www.deutsche-evergabe.de
German electronic procurement portal.
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
class DeutscheEvergabeScraper(BaseScraper):
    """Scraper for deutsche-evergabe.de procurement portal."""

    PORTAL_NAME = "deutsche_evergabe"
    PORTAL_URL = "https://www.deutsche-evergabe.de/Dashboards/Dashboard_off"
    REQUIRES_SELENIUM = True

    # Number of pages to scrape
    MAX_PAGES = 5

    def scrape(self) -> List[TenderResult]:
        """
        Execute scraping logic for Deutsche eVergabe portal.

        Returns:
            List of TenderResult objects
        """
        all_results = []

        try:
            # Navigate to dashboard
            self.logger.info(f"Navigating to: {self.PORTAL_URL}")
            self.driver.get(self.PORTAL_URL)
            time.sleep(5)

            # Accept cookies
            self.accept_cookies()
            time.sleep(2)

            # Wait for grid to load
            try:
                WebDriverWait(self.driver, 20).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "#gridContainerATender, .dx-datagrid, .dx-scrollable-content"))
                )
                self.logger.debug("Grid container found")
            except TimeoutException:
                self.logger.warning("Grid container not found with primary selector")
                time.sleep(5)

            # Try to expand rows shown (if there's a page size selector)
            self._try_expand_page_size()

            # Scrape multiple pages
            for page in range(self.MAX_PAGES):
                self.logger.debug(f"Scraping page {page + 1}")

                # Give time for content to load
                time.sleep(2)

                # Get page HTML
                html = self.driver.page_source
                soup = BeautifulSoup(html, "lxml")

                # Parse current page results
                results = self._parse_results(soup)
                if results:
                    all_results.extend(results)
                    self.logger.debug(f"Page {page + 1}: found {len(results)} tenders")
                else:
                    self.logger.debug(f"No results found on page {page + 1}")

                # Try to go to next page
                if page < self.MAX_PAGES - 1:
                    if not self._click_next_page(page + 2):
                        self.logger.debug("No more pages available")
                        break
                    time.sleep(3)

            self.logger.info(f"Found {len(all_results)} tenders total")

        except Exception as e:
            self.logger.error(f"Deutsche eVergabe scraping failed: {e}")
            raise ScraperError(self.PORTAL_NAME, str(e)) from e

        return all_results

    def _try_expand_page_size(self):
        """Try to expand the number of rows shown per page."""
        try:
            # Look for page size selector
            selectors = [
                "//div[contains(@class, 'dx-page-size')]//div[contains(text(), '50') or contains(text(), '100')]",
                ".dx-page-size option[value='50']",
                ".dx-page-size option[value='100']",
            ]

            for selector in selectors:
                try:
                    if selector.startswith("//"):
                        elem = self.driver.find_element(By.XPATH, selector)
                    else:
                        elem = self.driver.find_element(By.CSS_SELECTOR, selector)

                    if elem.is_displayed():
                        elem.click()
                        time.sleep(2)
                        self.logger.debug("Expanded page size")
                        return
                except NoSuchElementException:
                    continue
        except Exception as e:
            self.logger.debug(f"Could not expand page size: {e}")

    def _click_next_page(self, page_number: int) -> bool:
        """
        Click to go to a specific page.

        Args:
            page_number: Target page number (1-indexed)

        Returns:
            True if successful, False if not possible
        """
        try:
            # DevExtreme pagination selectors
            next_selectors = [
                # Direct page number click
                f"//div[contains(@class, 'dx-page') and text()='{page_number}']",
                f"//div[contains(@class, 'dx-pages')]//div[text()='{page_number}']",
                # Next button
                "//div[contains(@class, 'dx-navigate-button') and contains(@class, 'dx-next-button')]",
                "//i[contains(@class, 'dx-icon-chevronright')]/..",
                ".dx-next-button",
                "//a[contains(@class, 'dx-link-next')]",
            ]

            for selector in next_selectors:
                try:
                    if selector.startswith("//"):
                        next_button = self.driver.find_element(By.XPATH, selector)
                    else:
                        next_button = self.driver.find_element(By.CSS_SELECTOR, selector)

                    if next_button.is_displayed() and next_button.is_enabled():
                        # Scroll element into view
                        self.driver.execute_script("arguments[0].scrollIntoView(true);", next_button)
                        time.sleep(0.5)
                        next_button.click()
                        self.logger.debug(f"Clicked pagination element: {selector[:50]}")
                        return True
                except NoSuchElementException:
                    continue
                except Exception as e:
                    self.logger.debug(f"Pagination click failed for {selector[:30]}: {e}")
                    continue

        except Exception as e:
            self.logger.debug(f"Next page navigation failed: {e}")

        return False

    def _parse_results(self, soup: BeautifulSoup) -> List[TenderResult]:
        """
        Parse Deutsche eVergabe tender page HTML.

        Args:
            soup: BeautifulSoup object of page HTML

        Returns:
            List of TenderResult objects
        """
        results = []
        now = datetime.now()

        # Strategy 1: DevExtreme scrollable content (from old notebook)
        scrollable = soup.select_one("div.dx-scrollable-content")
        if scrollable:
            cells = scrollable.find_all("td")
            if cells and len(cells) >= 7:
                self.logger.debug(f"Found dx-scrollable-content with {len(cells)} cells")
                return self._parse_dx_grid(cells, now)

        # Strategy 2: DevExtreme data rows
        data_rows = soup.select("tr.dx-data-row, .dx-row")
        if data_rows:
            self.logger.debug(f"Found {len(data_rows)} data rows")
            for row in data_rows:
                result = self._parse_dx_row(row, now)
                if result:
                    results.append(result)
            return results

        # Strategy 3: Grid container with table rows
        grid = soup.select_one("#gridContainerATender, .dx-datagrid")
        if grid:
            rows = grid.find_all("tr")
            self.logger.debug(f"Found grid with {len(rows)} rows")
            for row in rows[1:]:  # Skip header
                result = self._parse_table_row(row, now)
                if result:
                    results.append(result)
            return results

        # Strategy 4: Generic table parsing
        tables = soup.find_all("table")
        for table in tables:
            rows = table.find_all("tr")
            if len(rows) > 5:  # Likely a data table
                self.logger.debug(f"Found table with {len(rows)} rows")
                for row in rows[1:]:
                    result = self._parse_table_row(row, now)
                    if result:
                        results.append(result)
                if results:
                    return results

        return results

    def _parse_dx_grid(self, cells, now: datetime) -> List[TenderResult]:
        """
        Parse DevExtreme grid cells (7 columns).

        Column layout from old notebook:
        0-1: (checkbox/icon columns)
        2: Title (with <br> separator) + Art (in <small> tag)
        3: Organization (Ausschreibungsstelle)
        4: Publication date (veröffentlicht)
        5: Deadline (nächste Frist)
        6: (status/actions)

        Args:
            cells: List of td elements
            now: Current timestamp

        Returns:
            List of TenderResult objects
        """
        results = []
        cols = 7
        num_rows = (len(cells) - cols) // cols  # Skip header row

        self.logger.debug(f"Parsing {num_rows} rows from dx-grid")

        for row_idx in range(num_rows):
            try:
                base_idx = (row_idx + 1) * cols  # Skip header

                if base_idx + 5 >= len(cells):
                    break

                # Column 2: Title and type
                cell_2 = cells[base_idx + 2]
                cell_html = str(cell_2)

                # Extract title (text before <br> or main text)
                titel = ""
                title_match = re.search(r">([^<]+)<br", cell_html)
                if title_match:
                    titel = clean_text(title_match.group(1))
                else:
                    # Try getting direct text
                    titel = clean_text(cell_2.get_text())

                # Extract type from <small> tag
                ausschreibungsart = ""
                small = cell_2.find("small")
                if small:
                    ausschreibungsart = clean_text(small.get_text())

                # Column 3: Organization
                ausschreibungsstelle = clean_text(cells[base_idx + 3].get_text())

                # Column 4: Publication date
                veroeffentlicht = clean_text(cells[base_idx + 4].get_text())

                # Column 5: Deadline
                naechste_frist = clean_text(cells[base_idx + 5].get_text())

                # Try to extract link
                link = ""
                vergabe_id = ""
                link_elem = cell_2.find("a")
                if link_elem and link_elem.has_attr("href"):
                    href = link_elem["href"]
                    link = href if href.startswith("http") else f"https://www.deutsche-evergabe.de{href}"
                    # Extract ID
                    id_match = re.search(r"/(\d+)/?$|[?&]id=(\d+)", link)
                    if id_match:
                        vergabe_id = id_match.group(1) or id_match.group(2)

                # Skip empty or header rows
                if not titel or titel == "-" or "titel" in titel.lower():
                    continue

                results.append(TenderResult(
                    portal=self.PORTAL_NAME,
                    suchbegriff=None,
                    suchzeitpunkt=now,
                    vergabe_id=vergabe_id,
                    link=link if link else f"https://www.deutsche-evergabe.de/Dashboards/Dashboard_off",
                    titel=titel,
                    ausschreibungsstelle=ausschreibungsstelle,
                    ausfuehrungsort="",
                    ausschreibungsart=ausschreibungsart,
                    naechste_frist=naechste_frist,
                    veroeffentlicht=veroeffentlicht,
                ))
            except Exception as e:
                self.logger.warning(f"Failed to parse dx-grid row {row_idx}: {e}")
                continue

        return results

    def _parse_dx_row(self, row, now: datetime) -> TenderResult:
        """
        Parse a single DevExtreme data row.

        Args:
            row: BeautifulSoup row element
            now: Current timestamp

        Returns:
            TenderResult object or None
        """
        try:
            cells = row.find_all("td")
            if len(cells) < 4:
                return None

            titel = ""
            ausschreibungsart = ""
            ausschreibungsstelle = ""
            veroeffentlicht = ""
            naechste_frist = ""
            link = ""
            vergabe_id = ""

            for idx, cell in enumerate(cells):
                text = clean_text(cell.get_text())

                # Look for title (usually longest text with link)
                link_elem = cell.find("a")
                if link_elem:
                    title_text = clean_text(link_elem.get_text())
                    if len(title_text) > len(titel):
                        titel = title_text
                        href = link_elem.get("href", "")
                        link = href if href.startswith("http") else f"https://www.deutsche-evergabe.de{href}"

                # Date patterns
                date_match = re.search(r"\d{2}\.\d{2}\.\d{4}", text)
                if date_match:
                    if not veroeffentlicht:
                        veroeffentlicht = date_match.group(0)
                    elif not naechste_frist:
                        naechste_frist = date_match.group(0)

                # Type keywords
                if any(kw in text.lower() for kw in ["verfahren", "ausschreibung", "öffentlich"]):
                    if not ausschreibungsart:
                        ausschreibungsart = text

                # Check small tag for type
                small = cell.find("small")
                if small:
                    ausschreibungsart = clean_text(small.get_text())

            if not titel:
                return None

            return TenderResult(
                portal=self.PORTAL_NAME,
                suchbegriff=None,
                suchzeitpunkt=now,
                vergabe_id=vergabe_id,
                link=link if link else f"https://www.deutsche-evergabe.de/Dashboards/Dashboard_off",
                titel=titel,
                ausschreibungsstelle=ausschreibungsstelle,
                ausfuehrungsort="",
                ausschreibungsart=ausschreibungsart,
                naechste_frist=naechste_frist,
                veroeffentlicht=veroeffentlicht,
            )
        except Exception as e:
            self.logger.warning(f"Failed to parse dx-row: {e}")
            return None

    def _parse_table_row(self, row, now: datetime) -> TenderResult:
        """
        Parse a generic table row.

        Args:
            row: BeautifulSoup row element
            now: Current timestamp

        Returns:
            TenderResult object or None
        """
        try:
            cells = row.find_all("td")
            if len(cells) < 3:
                return None

            titel = ""
            link = ""
            vergabe_id = ""
            texts = []

            for cell in cells:
                text = clean_text(cell.get_text())
                if text:
                    texts.append(text)

                link_elem = cell.find("a")
                if link_elem:
                    title_text = clean_text(link_elem.get_text())
                    if len(title_text) > len(titel):
                        titel = title_text
                        href = link_elem.get("href", "")
                        link = href if href.startswith("http") else f"https://www.deutsche-evergabe.de{href}"

            if not titel and texts:
                # Use longest text as title
                titel = max(texts, key=len)

            if not titel or len(titel) < 5:
                return None

            # Extract dates from texts
            veroeffentlicht = ""
            naechste_frist = ""
            for text in texts:
                date_match = re.search(r"\d{2}\.\d{2}\.\d{4}", text)
                if date_match:
                    if not veroeffentlicht:
                        veroeffentlicht = date_match.group(0)
                    elif not naechste_frist:
                        naechste_frist = date_match.group(0)

            return TenderResult(
                portal=self.PORTAL_NAME,
                suchbegriff=None,
                suchzeitpunkt=now,
                vergabe_id=vergabe_id,
                link=link if link else f"https://www.deutsche-evergabe.de/Dashboards/Dashboard_off",
                titel=titel,
                ausschreibungsstelle="",
                ausfuehrungsort="",
                ausschreibungsart="",
                naechste_frist=naechste_frist,
                veroeffentlicht=veroeffentlicht,
            )
        except Exception as e:
            self.logger.warning(f"Failed to parse table row: {e}")
            return None
