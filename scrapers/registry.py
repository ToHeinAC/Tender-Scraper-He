"""
Scraper registry for Tender Scraper System.

Provides automatic discovery and registration of scraper classes.
"""

import importlib
import logging
from pathlib import Path
from typing import Dict, List, Optional, Type

from scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

# Global registry of scraper classes
_SCRAPER_REGISTRY: Dict[str, Type[BaseScraper]] = {}


def register_scraper(cls: Type[BaseScraper]) -> Type[BaseScraper]:
    """
    Decorator to register a scraper class.

    Usage:
        @register_scraper
        class MyScraper(BaseScraper):
            PORTAL_NAME = "my_portal"
            ...

    Args:
        cls: Scraper class to register

    Returns:
        The same class (unchanged)
    """
    portal_name = cls.PORTAL_NAME
    if portal_name in _SCRAPER_REGISTRY:
        logger.warning(f"Overwriting scraper registration: {portal_name}")

    _SCRAPER_REGISTRY[portal_name] = cls
    logger.debug(f"Registered scraper: {portal_name} -> {cls.__name__}")

    return cls


def get_scraper(portal_name: str) -> Optional[Type[BaseScraper]]:
    """
    Get a scraper class by portal name.

    Args:
        portal_name: Name of the portal

    Returns:
        Scraper class or None if not found
    """
    return _SCRAPER_REGISTRY.get(portal_name)


def get_all_scrapers() -> Dict[str, Type[BaseScraper]]:
    """
    Get all registered scrapers.

    Returns:
        Dictionary mapping portal names to scraper classes
    """
    return _SCRAPER_REGISTRY.copy()


def get_scraper_names() -> List[str]:
    """
    Get list of all registered scraper names.

    Returns:
        List of portal names
    """
    return list(_SCRAPER_REGISTRY.keys())


def discover_scrapers(scrapers_dir: Optional[str] = None) -> None:
    """
    Discover and import all scraper modules.

    This function imports all Python files in the scrapers directory,
    which triggers the @register_scraper decorators.

    Args:
        scrapers_dir: Path to scrapers directory (default: auto-detect)
    """
    if scrapers_dir is None:
        scrapers_dir = Path(__file__).parent

    scrapers_path = Path(scrapers_dir)

    # Import all .py files except __init__.py, base.py, registry.py, utils.py
    excluded = {"__init__", "base", "registry", "utils"}

    for py_file in scrapers_path.glob("*.py"):
        module_name = py_file.stem
        if module_name in excluded:
            continue

        try:
            module = f"scrapers.{module_name}"
            importlib.import_module(module)
            logger.debug(f"Imported scraper module: {module}")
        except ImportError as e:
            logger.warning(f"Failed to import {module_name}: {e}")
        except Exception as e:
            logger.error(f"Error importing {module_name}: {e}")


def create_scraper(
    portal_name: str,
    config: dict,
    logger_instance: Optional[logging.Logger] = None,
) -> Optional[BaseScraper]:
    """
    Create a scraper instance by portal name.

    Args:
        portal_name: Name of the portal
        config: Configuration dictionary
        logger_instance: Logger instance for the scraper

    Returns:
        Scraper instance or None if not found
    """
    scraper_cls = get_scraper(portal_name)
    if scraper_cls is None:
        logger.warning(f"Scraper not found: {portal_name}")
        return None

    return scraper_cls(config, logger_instance)


def get_enabled_scrapers(config: dict) -> List[str]:
    """
    Get list of enabled scrapers from config.

    Args:
        config: Configuration dictionary

    Returns:
        List of enabled portal names
    """
    scrapers_config = config.get("scrapers", {})
    enabled = scrapers_config.get("enabled", [])
    disabled = set(scrapers_config.get("disabled", []))

    # Filter out disabled scrapers
    return [s for s in enabled if s not in disabled]


def create_enabled_scrapers(
    config: dict,
) -> List[BaseScraper]:
    """
    Create instances of all enabled scrapers.

    Args:
        config: Configuration dictionary

    Returns:
        List of scraper instances
    """
    # First, discover all scrapers
    discover_scrapers()

    enabled = get_enabled_scrapers(config)
    scrapers = []

    for portal_name in enabled:
        scraper = create_scraper(portal_name, config)
        if scraper:
            scrapers.append(scraper)
        else:
            logger.warning(f"Could not create scraper: {portal_name}")

    logger.info(f"Created {len(scrapers)} scrapers")
    return scrapers


class ScraperRegistry:
    """
    Object-oriented interface to the scraper registry.

    Provides methods for discovering, creating, and managing scrapers.
    """

    def __init__(self, config: dict):
        """
        Initialize registry.

        Args:
            config: Configuration dictionary
        """
        self.config = config
        self._discovered = False

    def discover(self) -> None:
        """Discover and register all scraper modules."""
        if not self._discovered:
            discover_scrapers()
            self._discovered = True

    def get(self, portal_name: str) -> Optional[BaseScraper]:
        """
        Get a scraper instance by portal name.

        Args:
            portal_name: Name of the portal

        Returns:
            Scraper instance or None
        """
        self.discover()
        return create_scraper(portal_name, self.config)

    def get_all(self) -> List[BaseScraper]:
        """
        Get instances of all registered scrapers.

        Returns:
            List of scraper instances
        """
        self.discover()
        scrapers = []
        for portal_name in get_scraper_names():
            scraper = create_scraper(portal_name, self.config)
            if scraper:
                scrapers.append(scraper)
        return scrapers

    def get_enabled(self) -> List[BaseScraper]:
        """
        Get instances of all enabled scrapers.

        Returns:
            List of enabled scraper instances
        """
        self.discover()
        return create_enabled_scrapers(self.config)

    @property
    def registered_names(self) -> List[str]:
        """Get list of all registered portal names."""
        self.discover()
        return get_scraper_names()

    @property
    def enabled_names(self) -> List[str]:
        """Get list of enabled portal names."""
        return get_enabled_scrapers(self.config)
