"""
Browser/WebDriver utilities for Tender Scraper System.

Provides Selenium WebDriver management with automatic cleanup.
"""

import logging
import time
from contextlib import contextmanager
from typing import Generator, Optional

from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import (
    NoSuchElementException,
    TimeoutException,
    WebDriverException,
)

try:
    from webdriver_manager.chrome import ChromeDriverManager
except ImportError:
    ChromeDriverManager = None

try:
    import undetected_chromedriver as uc
except ImportError:
    uc = None

logger = logging.getLogger(__name__)


class BrowserManager:
    """Manages Selenium WebDriver instances with automatic cleanup."""

    # Common cookie consent selectors
    COOKIE_SELECTORS = [
        "#cookie-accept",
        ".cookie-consent-accept",
        ".cookie-accept-btn",
        "button[data-action='accept']",
        "button[data-consent='accept']",
        ".accept-cookies",
        "#accept-cookies",
        "//button[contains(text(), 'Akzeptieren')]",
        "//button[contains(text(), 'Accept')]",
        "//button[contains(text(), 'Alle akzeptieren')]",
        "//a[contains(text(), 'Akzeptieren')]",
    ]

    def __init__(
        self,
        headless: bool = True,
        user_agent: Optional[str] = None,
        use_undetected: bool = False,
        implicit_wait: int = 10,
    ):
        """
        Initialize browser manager.

        Args:
            headless: Run browser in headless mode
            user_agent: Custom user agent string
            use_undetected: Use undetected-chromedriver
            implicit_wait: Default implicit wait time in seconds
        """
        self.headless = headless
        self.user_agent = user_agent or (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
        self.use_undetected = use_undetected
        self.implicit_wait = implicit_wait
        self.driver: Optional[webdriver.Chrome] = None

    def _create_chrome_options(self) -> ChromeOptions:
        """Create Chrome options with standard settings."""
        options = ChromeOptions()

        if self.headless:
            options.add_argument("--headless=new")

        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")
        options.add_argument(f"--user-agent={self.user_agent}")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)

        # Disable images for faster loading (optional)
        # prefs = {"profile.managed_default_content_settings.images": 2}
        # options.add_experimental_option("prefs", prefs)

        return options

    def create_driver(self) -> webdriver.Chrome:
        """
        Create and return a new WebDriver instance.

        Returns:
            Chrome WebDriver instance
        """
        try:
            if self.use_undetected and uc is not None:
                logger.debug("Creating undetected Chrome driver")
                options = uc.ChromeOptions()
                if self.headless:
                    options.add_argument("--headless=new")
                options.add_argument("--no-sandbox")
                options.add_argument("--disable-dev-shm-usage")

                self.driver = uc.Chrome(options=options)
            else:
                logger.debug("Creating standard Chrome driver")
                options = self._create_chrome_options()

                if ChromeDriverManager is not None:
                    service = ChromeService(ChromeDriverManager().install())
                    self.driver = webdriver.Chrome(service=service, options=options)
                else:
                    self.driver = webdriver.Chrome(options=options)

            self.driver.implicitly_wait(self.implicit_wait)
            logger.debug("WebDriver created successfully")
            return self.driver

        except WebDriverException as e:
            logger.error(f"Failed to create WebDriver: {e}")
            raise

    def close_driver(self) -> None:
        """Close the current WebDriver instance."""
        if self.driver:
            try:
                self.driver.quit()
                logger.debug("WebDriver closed")
            except Exception as e:
                logger.warning(f"Error closing WebDriver: {e}")
            finally:
                self.driver = None

    @contextmanager
    def get_driver(self) -> Generator[webdriver.Chrome, None, None]:
        """
        Context manager for WebDriver usage.

        Yields:
            Chrome WebDriver instance

        Example:
            with browser_manager.get_driver() as driver:
                driver.get("https://example.com")
        """
        try:
            yield self.create_driver()
        finally:
            self.close_driver()

    def accept_cookies(self, driver: Optional[webdriver.Chrome] = None) -> bool:
        """
        Try to accept cookie consent dialog.

        Args:
            driver: WebDriver instance (uses self.driver if not provided)

        Returns:
            True if cookies were accepted, False otherwise
        """
        driver = driver or self.driver
        if not driver:
            return False

        for selector in self.COOKIE_SELECTORS:
            try:
                if selector.startswith("//"):
                    element = driver.find_element(By.XPATH, selector)
                else:
                    element = driver.find_element(By.CSS_SELECTOR, selector)

                if element.is_displayed() and element.is_enabled():
                    element.click()
                    logger.debug(f"Accepted cookies using selector: {selector}")
                    time.sleep(1)  # Wait for dialog to close
                    return True
            except NoSuchElementException:
                continue
            except Exception as e:
                logger.debug(f"Failed to click cookie selector {selector}: {e}")
                continue

        logger.debug("No cookie consent dialog found or could not accept")
        return False

    def scroll_to_bottom(
        self,
        driver: Optional[webdriver.Chrome] = None,
        timeout: int = 30,
        scroll_pause: float = 2.0,
    ) -> None:
        """
        Scroll to bottom of page for infinite scroll pages.

        Args:
            driver: WebDriver instance
            timeout: Maximum time to spend scrolling
            scroll_pause: Time to wait between scrolls
        """
        driver = driver or self.driver
        if not driver:
            return

        start_time = time.time()
        last_height = driver.execute_script("return document.body.scrollHeight")

        while time.time() - start_time < timeout:
            # Scroll down
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(scroll_pause)

            # Check if page height changed
            new_height = driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                logger.debug("Reached bottom of page")
                break
            last_height = new_height

        logger.debug(f"Scrolling completed in {time.time() - start_time:.1f}s")

    def wait_for_element(
        self,
        selector: str,
        by: str = By.CSS_SELECTOR,
        timeout: int = 10,
        driver: Optional[webdriver.Chrome] = None,
    ):
        """
        Wait for an element to be present.

        Args:
            selector: Element selector
            by: Selector type (By.CSS_SELECTOR, By.XPATH, etc.)
            timeout: Maximum wait time
            driver: WebDriver instance

        Returns:
            WebElement if found

        Raises:
            TimeoutException: If element not found within timeout
        """
        driver = driver or self.driver
        if not driver:
            raise ValueError("No driver available")

        wait = WebDriverWait(driver, timeout)
        return wait.until(EC.presence_of_element_located((by, selector)))

    def safe_click(
        self,
        selector: str,
        by: str = By.CSS_SELECTOR,
        driver: Optional[webdriver.Chrome] = None,
    ) -> bool:
        """
        Safely click an element.

        Args:
            selector: Element selector
            by: Selector type
            driver: WebDriver instance

        Returns:
            True if click succeeded, False otherwise
        """
        driver = driver or self.driver
        if not driver:
            return False

        try:
            element = driver.find_element(by, selector)
            if element.is_displayed() and element.is_enabled():
                element.click()
                return True
        except Exception as e:
            logger.debug(f"Safe click failed for {selector}: {e}")

        return False

    def get_page_html(self, driver: Optional[webdriver.Chrome] = None) -> str:
        """
        Get the current page HTML.

        Args:
            driver: WebDriver instance

        Returns:
            Page HTML as string
        """
        driver = driver or self.driver
        if not driver:
            return ""

        return driver.page_source
