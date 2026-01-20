"""
Scraper for Austrian auftrag.at procurement portal.

URL: https://suche.auftrag.at
Austria's leading platform for public procurement.
"""

import re
import time
from datetime import datetime
from typing import List
from urllib.parse import urlencode

from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

from scrapers.base import BaseScraper, TenderResult, ScraperError
from scrapers.registry import register_scraper
from scrapers.utils import clean_text, normalize_url


@register_scraper
class AuftragATScraper(BaseScraper):
    """Scraper for auftrag.at procurement portal."""

    PORTAL_NAME = "auftrag_at"
    PORTAL_URL = "https://suche.auftrag.at/suche"
    BASE_URL = "https://suche.auftrag.at"
    REQUIRES_SELENIUM = True

    # Maximum pages to scrape
    MAX_PAGES = 5

    # Cookie consent selectors specific to this portal
    COOKIE_SELECTORS = [
        "#cookie-accept",
        "button.accept-all",
        "//button[contains(text(), 'Alle akzeptieren')]",
        "//button[contains(text(), 'Akzeptieren')]",
        "//a[contains(text(), 'Alle akzeptieren')]",
        ".cookie-consent-accept",
        "#acceptAllCookies",
        ".cc-btn.cc-accept",
    ]

    def scrape(self) -> List[TenderResult]:
        """
        Execute scraping logic for auftrag.at portal.

        Returns:
            List of TenderResult objects
        """
        all_results = []
        seen_ids = set()

        try:
            # Navigate to search page
            self.logger.info(f"Navigating to: {self.PORTAL_URL}")
            self.driver.get(self.PORTAL_URL)

            # Wait for page load
            time.sleep(4)

            # Accept cookies
            self.accept_cookies()
            time.sleep(2)

            # Wait for content to load (JavaScript-rendered)
            try:
                WebDriverWait(self.driver, 20).until(
                    lambda d: d.execute_script("return document.readyState") == "complete"
                )
                # Additional wait for dynamic content
                time.sleep(3)
            except TimeoutException:
                self.logger.warning("Page load timeout, proceeding anyway")

            # Try to wait for results container
            result_selectors = [
                ".search-results",
                ".tender-list",
                ".result-item",
                ".ausschreibung",
                "table",
                "[class*='result']",
                "[class*='tender']",
                "[class*='ausschreibung']",
            ]

            for selector in result_selectors:
                try:
                    WebDriverWait(self.driver, 5).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                    )
                    self.logger.debug(f"Found results with selector: {selector}")
                    break
                except TimeoutException:
                    continue

            # Scrape pages
            for page in range(1, self.MAX_PAGES + 1):
                self.logger.debug(f"Scraping page {page}")

                # Get page HTML
                html = self.driver.page_source
                soup = BeautifulSoup(html, "lxml")

                # Parse results
                results = self._parse_results(soup)

                if not results:
                    if page == 1:
                        self.logger.warning("No results found on first page")
                        # Save debug HTML
                        self._save_debug_html(soup)
                    break

                # Deduplicate
                new_count = 0
                for result in results:
                    if result.vergabe_id and result.vergabe_id in seen_ids:
                        continue
                    if result.vergabe_id:
                        seen_ids.add(result.vergabe_id)
                    all_results.append(result)
                    new_count += 1

                self.logger.info(f"Page {page}: found {new_count} new tenders")

                # Try next page
                if page < self.MAX_PAGES:
                    if not self._click_next_page():
                        self.logger.debug("No more pages available")
                        break
                    time.sleep(3)

            self.logger.info(f"Found {len(all_results)} total tenders")

        except Exception as e:
            self.logger.error(f"auftrag.at scraping failed: {e}")
            raise ScraperError(self.PORTAL_NAME, str(e)) from e

        return all_results

    def _click_next_page(self) -> bool:
        """
        Click the next page button.

        Returns:
            True if successful, False if no more pages
        """
        next_selectors = [
            "a[rel='next']",
            ".pagination-next:not(.disabled) a",
            ".next-page:not(.disabled)",
            "//a[contains(@class, 'next')]",
            "//a[contains(text(), 'Weiter')]",
            "//a[contains(text(), '›')]",
            "//a[contains(text(), '»')]",
            "//button[contains(text(), 'Weiter')]",
            ".pagination a:last-child",
        ]

        for selector in next_selectors:
            try:
                if selector.startswith("//"):
                    next_btn = self.driver.find_element(By.XPATH, selector)
                else:
                    next_btn = self.driver.find_element(By.CSS_SELECTOR, selector)

                if next_btn.is_displayed() and next_btn.is_enabled():
                    # Check if it's actually a "next" button
                    text = next_btn.text.lower()
                    href = next_btn.get_attribute("href") or ""
                    classes = next_btn.get_attribute("class") or ""

                    if any(x in text + href + classes for x in ["next", "weiter", "›", "»"]):
                        next_btn.click()
                        time.sleep(2)
                        return True
            except NoSuchElementException:
                continue
            except Exception as e:
                self.logger.debug(f"Next page click failed with selector {selector}: {e}")
                continue

        return False

    def _parse_results(self, soup: BeautifulSoup) -> List[TenderResult]:
        """
        Parse auftrag.at tender page HTML.

        Uses multiple parsing strategies to handle different page structures.

        Args:
            soup: BeautifulSoup object of page HTML

        Returns:
            List of TenderResult objects
        """
        results = []
        now = datetime.now()

        # Strategy 1: Look for structured result items
        item_selectors = [
            ".search-result-item",
            ".tender-item",
            ".result-item",
            ".ausschreibung-item",
            "[class*='SearchResult']",
            "[class*='TenderItem']",
            "article.tender",
            ".card.tender",
        ]

        for selector in item_selectors:
            items = soup.select(selector)
            if items:
                self.logger.debug(f"Found {len(items)} items with selector: {selector}")
                for item in items:
                    result = self._parse_result_item(item, now)
                    if result and result.titel:
                        results.append(result)
                if results:
                    return results

        # Strategy 2: Look for table rows
        table_selectors = [
            "table.search-results tbody tr",
            "table.tender-list tbody tr",
            "table tbody tr",
        ]

        for selector in table_selectors:
            rows = soup.select(selector)
            if rows:
                self.logger.debug(f"Found {len(rows)} rows with selector: {selector}")
                for row in rows:
                    result = self._parse_table_row(row, now)
                    if result and result.titel:
                        results.append(result)
                if results:
                    return results

        # Strategy 3: Look for links with tender-like attributes
        tender_links = soup.find_all("a", href=re.compile(
            r"detail|ausschreibung|tender|vergabe|notice",
            re.IGNORECASE
        ))
        if tender_links:
            self.logger.debug(f"Found {len(tender_links)} tender links")
            for link in tender_links:
                result = self._parse_tender_link(link, now)
                if result and result.titel and len(result.titel) > 10:
                    results.append(result)

        # Strategy 4: Look for any div/article containing tender data
        content_selectors = [
            "div[class*='tender']",
            "div[class*='result']",
            "div[class*='ausschreibung']",
            "article",
        ]

        for selector in content_selectors:
            items = soup.select(selector)
            for item in items:
                # Check if this looks like a tender item
                text = item.get_text()
                if any(kw in text.lower() for kw in ["ausschreibung", "vergabe", "frist", "tender"]):
                    result = self._parse_generic_item(item, now)
                    if result and result.titel and len(result.titel) > 10:
                        # Avoid duplicates
                        if not any(r.titel == result.titel for r in results):
                            results.append(result)

        return results

    def _parse_result_item(self, item, now: datetime) -> TenderResult:
        """
        Parse a structured result item.

        Args:
            item: BeautifulSoup element
            now: Current timestamp

        Returns:
            TenderResult object or None
        """
        try:
            # Find title and link
            title_selectors = [
                "h2 a", "h3 a", "h4 a",
                ".title a", ".titel a",
                "a.title", "a.titel",
                ".search-result-title a",
                "a[class*='title']",
            ]

            titel = ""
            link = ""
            vergabe_id = ""

            for selector in title_selectors:
                elem = item.select_one(selector)
                if elem:
                    titel = clean_text(elem.get_text())
                    href = elem.get("href", "")
                    if href:
                        link = normalize_url(href, self.BASE_URL)
                        vergabe_id = self._extract_id(link)
                    break

            if not titel:
                # Try to find any prominent text
                for tag in ["h2", "h3", "h4", ".title", ".titel"]:
                    elem = item.select_one(tag)
                    if elem:
                        titel = clean_text(elem.get_text())
                        break

            if not link:
                # Find first meaningful link
                link_elem = item.find("a", href=True)
                if link_elem:
                    link = normalize_url(link_elem.get("href", ""), self.BASE_URL)
                    vergabe_id = self._extract_id(link)

            # Extract organization
            org_selectors = [
                ".organization", ".organisation", ".issuer",
                ".ausschreibungsstelle", ".auftraggeber",
                "[class*='organization']", "[class*='issuer']",
            ]
            ausschreibungsstelle = ""
            for selector in org_selectors:
                elem = item.select_one(selector)
                if elem:
                    ausschreibungsstelle = clean_text(elem.get_text())
                    break

            # Extract dates
            naechste_frist = ""
            veroeffentlicht = ""

            date_pattern = r"\d{1,2}\.\d{1,2}\.\d{4}"
            text = item.get_text()
            dates = re.findall(date_pattern, text)
            if dates:
                veroeffentlicht = dates[0]
                if len(dates) > 1:
                    naechste_frist = dates[1]

            # Look for specific date labels
            for elem in item.find_all(["span", "div", "p"]):
                text_lower = elem.get_text().lower()
                if "frist" in text_lower or "deadline" in text_lower:
                    date_match = re.search(date_pattern, elem.get_text())
                    if date_match:
                        naechste_frist = date_match.group()
                elif "veröffentlicht" in text_lower or "published" in text_lower:
                    date_match = re.search(date_pattern, elem.get_text())
                    if date_match:
                        veroeffentlicht = date_match.group()

            if not titel:
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
                ausschreibungsart="",
                naechste_frist=naechste_frist,
                veroeffentlicht=veroeffentlicht,
            )

        except Exception as e:
            self.logger.warning(f"Failed to parse result item: {e}")
            return None

    def _parse_table_row(self, row, now: datetime) -> TenderResult:
        """
        Parse a table row with tender data.

        Args:
            row: BeautifulSoup element for table row
            now: Current timestamp

        Returns:
            TenderResult object or None
        """
        try:
            cells = row.find_all("td")
            if len(cells) < 2:
                return None

            titel = ""
            link = ""
            vergabe_id = ""
            ausschreibungsstelle = ""
            naechste_frist = ""
            veroeffentlicht = ""

            # Look for link in cells
            for cell in cells:
                link_elem = cell.find("a")
                if link_elem:
                    text = clean_text(link_elem.get_text())
                    if len(text) > len(titel):
                        titel = text
                        href = link_elem.get("href", "")
                        if href:
                            link = normalize_url(href, self.BASE_URL)
                            vergabe_id = self._extract_id(link)

            # Extract dates and other info from cells
            date_pattern = r"\d{1,2}\.\d{1,2}\.\d{4}"
            for idx, cell in enumerate(cells):
                text = clean_text(cell.get_text())

                # Check for dates
                date_match = re.search(date_pattern, text)
                if date_match:
                    if not veroeffentlicht:
                        veroeffentlicht = date_match.group()
                    elif not naechste_frist:
                        naechste_frist = date_match.group()
                    continue

                # Check for organization (usually longer text without dates)
                if len(text) > 10 and not date_match and text != titel:
                    if not ausschreibungsstelle:
                        ausschreibungsstelle = text

            if not titel:
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
                ausschreibungsart="",
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

            if not titel or len(titel) < 5:
                return None

            full_link = normalize_url(href, self.BASE_URL)
            vergabe_id = self._extract_id(full_link)

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

    def _parse_generic_item(self, item, now: datetime) -> TenderResult:
        """
        Parse a generic content item that might contain tender data.

        Args:
            item: BeautifulSoup element
            now: Current timestamp

        Returns:
            TenderResult object or None
        """
        try:
            # Find first meaningful link
            link_elem = item.find("a", href=True)
            if not link_elem:
                return None

            titel = clean_text(link_elem.get_text())
            href = link_elem.get("href", "")
            link = normalize_url(href, self.BASE_URL)
            vergabe_id = self._extract_id(link)

            if not titel or len(titel) < 10:
                return None

            # Try to extract dates
            text = item.get_text()
            date_pattern = r"\d{1,2}\.\d{1,2}\.\d{4}"
            dates = re.findall(date_pattern, text)

            veroeffentlicht = dates[0] if dates else ""
            naechste_frist = dates[1] if len(dates) > 1 else ""

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
                veroeffentlicht=veroeffentlicht,
            )
        except Exception as e:
            self.logger.warning(f"Failed to parse generic item: {e}")
            return None

    def _extract_id(self, url: str) -> str:
        """
        Extract tender ID from URL.

        Args:
            url: URL string

        Returns:
            Extracted ID or empty string
        """
        if not url:
            return ""

        # Try various ID patterns
        patterns = [
            r"[?&]id=(\d+)",
            r"/detail/(\d+)",
            r"/ausschreibung/(\d+)",
            r"/tender/(\d+)",
            r"/(\d{6,})",  # 6+ digit number in path
        ]

        for pattern in patterns:
            match = re.search(pattern, url, re.IGNORECASE)
            if match:
                return match.group(1)

        return ""

    def _save_debug_html(self, soup: BeautifulSoup) -> None:
        """Save HTML for debugging purposes."""
        try:
            debug_path = f"data/auftrag_at_debug_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
            with open(debug_path, "w", encoding="utf-8") as f:
                f.write(str(soup))
            self.logger.debug(f"Saved debug HTML to: {debug_path}")
        except Exception as e:
            self.logger.debug(f"Could not save debug HTML: {e}")
