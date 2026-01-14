"""
Base scraper class for Tender Scraper System.

Provides abstract base class and common functionality for all portal scrapers.
"""

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Any, Dict, List, Optional

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.common.exceptions import (
    NoSuchElementException,
    TimeoutException,
    WebDriverException,
)

from utils.browser import BrowserManager


@dataclass
class TenderResult:
    """Data class representing a single tender result."""

    portal: str
    suchbegriff: Optional[str]
    suchzeitpunkt: datetime
    vergabe_id: Optional[str]
    link: Optional[str]
    titel: str
    ausschreibungsstelle: Optional[str]
    ausfuehrungsort: Optional[str]
    ausschreibungsart: Optional[str]
    naechste_frist: Optional[str]
    veroeffentlicht: Optional[str]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for database insertion."""
        return asdict(self)


class ScraperError(Exception):
    """Base exception for scraper errors."""

    def __init__(self, portal: str, message: str):
        self.portal = portal
        self.message = message
        super().__init__(f"[{portal}] {message}")


class ScraperTimeoutError(ScraperError):
    """Raised when scraper times out."""

    pass


class ScraperParseError(ScraperError):
    """Raised when scraper fails to parse results."""

    pass


class BaseScraper(ABC):
    """
    Abstract base class for all portal scrapers.

    Provides common functionality for browser management, cookie handling,
    scrolling, and error handling. Subclasses must implement the scrape() method.
    """

    # Class attributes to be overridden by subclasses
    PORTAL_NAME: str = "base"
    PORTAL_URL: str = ""
    REQUIRES_SELENIUM: bool = True

    # Cookie consent selectors (can be extended by subclasses)
    COOKIE_SELECTORS: List[str] = [
        "#cookie-accept",
        ".cookie-consent-accept",
        "button[data-action='accept']",
        "//button[contains(text(), 'Akzeptieren')]",
        "//button[contains(text(), 'Alle akzeptieren')]",
    ]

    def __init__(
        self,
        config: Dict[str, Any],
        logger: Optional[logging.Logger] = None,
    ):
        """
        Initialize scraper.

        Args:
            config: Configuration dictionary
            logger: Logger instance (creates one if not provided)
        """
        self.config = config
        self.logger = logger or logging.getLogger(f"scrapers.{self.PORTAL_NAME}")
        self.driver: Optional[webdriver.Chrome] = None
        self.browser_manager: Optional[BrowserManager] = None

        # Extract scraping config
        scraping_config = config.get("scraping", {})
        self.timeout = scraping_config.get("timeout_per_scraper", 300)
        self.headless = scraping_config.get("headless", True)
        self.user_agent = scraping_config.get("user_agent")

    def setup_driver(self) -> None:
        """Initialize Selenium WebDriver."""
        if not self.REQUIRES_SELENIUM:
            return

        self.browser_manager = BrowserManager(
            headless=self.headless,
            user_agent=self.user_agent,
        )
        self.driver = self.browser_manager.create_driver()
        self.logger.debug("WebDriver initialized")

    def teardown_driver(self) -> None:
        """Clean up WebDriver resources."""
        if self.browser_manager:
            self.browser_manager.close_driver()
            self.browser_manager = None
            self.driver = None
            self.logger.debug("WebDriver closed")

    def accept_cookies(self) -> bool:
        """
        Try to accept cookie consent dialog.

        Returns:
            True if cookies were accepted
        """
        if not self.driver:
            return False

        for selector in self.COOKIE_SELECTORS:
            try:
                if selector.startswith("//"):
                    element = self.driver.find_element(By.XPATH, selector)
                else:
                    element = self.driver.find_element(By.CSS_SELECTOR, selector)

                if element.is_displayed() and element.is_enabled():
                    element.click()
                    self.logger.debug(f"Accepted cookies: {selector}")
                    time.sleep(1)
                    return True
            except NoSuchElementException:
                continue
            except Exception as e:
                self.logger.debug(f"Cookie click failed: {e}")
                continue

        self.logger.debug("No cookie dialog found")
        return False

    def scroll_to_bottom(self, timeout: int = 30, pause: float = 2.0) -> None:
        """
        Scroll page to load all dynamic content.

        Args:
            timeout: Maximum time to spend scrolling
            pause: Time between scrolls
        """
        if not self.driver:
            return

        start_time = time.time()
        last_height = self.driver.execute_script(
            "return document.body.scrollHeight"
        )

        while time.time() - start_time < timeout:
            self.driver.execute_script(
                "window.scrollTo(0, document.body.scrollHeight)"
            )
            time.sleep(pause)

            new_height = self.driver.execute_script(
                "return document.body.scrollHeight"
            )
            if new_height == last_height:
                break
            last_height = new_height

        self.logger.debug(f"Scrolling completed in {time.time() - start_time:.1f}s")

    def get_page_html(self) -> str:
        """Get current page HTML."""
        if not self.driver:
            return ""
        return self.driver.page_source

    def safe_get_text(
        self,
        element,
        selector: str,
        default: str = "",
    ) -> str:
        """
        Safely extract text from an element.

        Args:
            element: Parent element
            selector: CSS selector
            default: Default value if not found

        Returns:
            Extracted text or default
        """
        try:
            found = element.select_one(selector)
            if found:
                return found.get_text(strip=True)
        except Exception:
            pass
        return default

    def safe_get_attr(
        self,
        element,
        selector: str,
        attr: str,
        default: str = "",
    ) -> str:
        """
        Safely extract attribute from an element.

        Args:
            element: Parent element
            selector: CSS selector
            attr: Attribute name
            default: Default value if not found

        Returns:
            Attribute value or default
        """
        try:
            found = element.select_one(selector)
            if found and found.has_attr(attr):
                return found[attr]
        except Exception:
            pass
        return default

    def run(self) -> List[TenderResult]:
        """
        Execute the full scraping workflow.

        This is the main entry point that handles setup, execution, and cleanup.

        Returns:
            List of TenderResult objects
        """
        self.logger.info(f"Starting scrape of {self.PORTAL_NAME}")
        start_time = time.time()
        results = []

        try:
            self.setup_driver()
            results = self.scrape()
            elapsed = time.time() - start_time
            self.logger.info(
                f"Completed {self.PORTAL_NAME}: {len(results)} results in {elapsed:.1f}s"
            )
        except Exception as e:
            elapsed = time.time() - start_time
            self.logger.error(
                f"Failed {self.PORTAL_NAME} after {elapsed:.1f}s: {e}",
                exc_info=True,
            )
            raise ScraperError(self.PORTAL_NAME, str(e)) from e
        finally:
            self.teardown_driver()

        return results

    @abstractmethod
    def scrape(self) -> List[TenderResult]:
        """
        Execute the scraping logic for this portal.

        This method must be implemented by each scraper subclass.

        Returns:
            List of TenderResult objects

        Raises:
            ScraperError: If scraping fails
        """
        pass

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(portal={self.PORTAL_NAME})"
