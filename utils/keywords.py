"""
Keyword loading and matching for Tender Scraper System.

Handles loading keywords from file and matching against tender data.
"""

import logging
import re
from pathlib import Path
from typing import List, Optional, Set

logger = logging.getLogger(__name__)


class KeywordMatcher:
    """Handles keyword loading and matching for tender filtering."""

    def __init__(
        self,
        keywords_file: str,
        case_sensitive: bool = False,
        exclusions: Optional[List[str]] = None,
    ):
        """
        Initialize keyword matcher.

        Args:
            keywords_file: Path to file containing keywords (one per line)
            case_sensitive: Whether matching should be case-sensitive
            exclusions: List of keywords that exclude a match
        """
        self.keywords_file = keywords_file
        self.case_sensitive = case_sensitive
        self.exclusions = exclusions or []

        self.keywords: Set[str] = set()
        self.keyword_patterns: List[re.Pattern] = []
        self.exclusion_patterns: List[re.Pattern] = []

        self._load_keywords()
        self._compile_patterns()

    def _load_keywords(self) -> None:
        """Load keywords from file."""
        path = Path(self.keywords_file)

        if not path.exists():
            logger.warning(f"Keywords file not found: {self.keywords_file}")
            return

        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                # Skip empty lines and comments
                if not line or line.startswith("#"):
                    continue
                self.keywords.add(line)

        # Generate case variants if not case-sensitive
        if not self.case_sensitive:
            variants = set()
            for kw in self.keywords:
                variants.add(kw.lower())
                variants.add(kw.capitalize())
                variants.add(kw.upper())
            self.keywords.update(variants)

        logger.info(f"Loaded {len(self.keywords)} keywords from {self.keywords_file}")

    def _compile_patterns(self) -> None:
        """Compile regex patterns for efficient matching."""
        flags = 0 if self.case_sensitive else re.IGNORECASE

        # Compile keyword patterns
        for kw in self.keywords:
            try:
                # Escape special regex characters
                pattern = re.compile(re.escape(kw), flags)
                self.keyword_patterns.append(pattern)
            except re.error as e:
                logger.warning(f"Invalid keyword pattern '{kw}': {e}")

        # Compile exclusion patterns
        for exc in self.exclusions:
            try:
                pattern = re.compile(re.escape(exc), flags)
                self.exclusion_patterns.append(pattern)
            except re.error as e:
                logger.warning(f"Invalid exclusion pattern '{exc}': {e}")

    def matches(self, text: str) -> bool:
        """
        Check if text matches any keyword.

        Args:
            text: Text to check

        Returns:
            True if text matches a keyword and no exclusion
        """
        if not text:
            return False

        # Check exclusions first
        for pattern in self.exclusion_patterns:
            if pattern.search(text):
                return False

        # Check keywords
        for pattern in self.keyword_patterns:
            if pattern.search(text):
                return True

        return False

    def get_matching_keyword(self, text: str) -> Optional[str]:
        """
        Get the first matching keyword from text.

        Args:
            text: Text to search

        Returns:
            Matching keyword or None
        """
        if not text:
            return None

        # Check exclusions first
        for pattern in self.exclusion_patterns:
            if pattern.search(text):
                return None

        # Find first matching keyword
        for pattern in self.keyword_patterns:
            match = pattern.search(text)
            if match:
                return match.group()

        return None

    def matches_any_field(self, fields: List[Optional[str]]) -> bool:
        """
        Check if any of the given fields match a keyword.

        Args:
            fields: List of text fields to check

        Returns:
            True if any field matches
        """
        for field in fields:
            if field and self.matches(field):
                return True
        return False

    def get_first_match(self, fields: List[Optional[str]]) -> Optional[str]:
        """
        Get the first matching keyword from any field.

        Args:
            fields: List of text fields to check

        Returns:
            First matching keyword or None
        """
        for field in fields:
            if field:
                match = self.get_matching_keyword(field)
                if match:
                    return match
        return None


def load_keywords(filepath: str) -> List[str]:
    """
    Simple function to load keywords from a file.

    Args:
        filepath: Path to keywords file

    Returns:
        List of keywords
    """
    keywords = []
    path = Path(filepath)

    if not path.exists():
        logger.warning(f"Keywords file not found: {filepath}")
        return keywords

    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                keywords.append(line)

    return keywords
