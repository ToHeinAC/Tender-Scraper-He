"""
Keyword loading and matching for Tender Scraper System.

Handles loading keywords from file and matching against tender data.

## Keyword Matching Behavior

Each keyword automatically matches:
- Exact match: "Rückstand" matches "Rückstand"
- Lowercase first letter: "Rückstand" matches "rückstand"
- Full lowercase/uppercase: "Rückstand" matches "RÜCKSTAND"
- Compound words (substring): "Rückstand" matches "Produktionsrückstand", "Rückstandskonzept"

Keywords ≤2 characters use word boundaries to prevent false positives.

## Two Scraping Strategies

**Strategy 1: "First Scrape, then check"** (All portals)
- Scrapers return all tenders with suchbegriff=None
- KeywordMatcher filters results in main.py

**Strategy 2: "Directly put item via URL"** (2 portals only)
- Keywords passed directly in portal search URL
- Supported: USP Austria (q=), Fraunhofer (Searchkey=)
- Use get_search_terms() to get original keywords for URL parameters
"""

import logging
import re
from pathlib import Path
from typing import List, Optional, Set

logger = logging.getLogger(__name__)


class KeywordMatcher:
    """
    Handles keyword loading and matching for tender filtering.

    Matching behavior:
    - Case variants are generated automatically (lowercase first letter, full lowercase, uppercase)
    - Keywords >2 chars match as substrings (no word boundaries) for German compound words
    - Keywords ≤2 chars use word boundaries to prevent false positives
    """

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

        self._original_keywords: Set[str] = set()  # Original keywords from file
        self.keywords: Set[str] = set()  # Keywords with case variants
        self.keyword_patterns: List[re.Pattern] = []
        self.exclusion_patterns: List[re.Pattern] = []

        self._load_keywords()
        self._compile_patterns()

    @staticmethod
    def _should_use_word_boundaries(keyword: str) -> bool:
        """
        Return True if keyword should match as a whole word/token.

        Short keywords (≤2 chars, alphabetic only) use word boundaries
        to prevent false positives (e.g., "KI" shouldn't match "Kinder").
        """
        kw = keyword.strip()
        return len(kw) <= 2 and kw.isalpha()

    @staticmethod
    def _generate_case_variants(keyword: str) -> Set[str]:
        """
        Generate case variants for a keyword to enable flexible matching.

        For keyword "Rückstand", generates:
        - "Rückstand" (original)
        - "rückstand" (lowercase first letter)
        - "RÜCKSTAND" (all uppercase)

        Combined with NO word boundaries for keywords >2 chars, this enables:
        - Exact match: "Rückstand"
        - Lowercase: "rückstand"
        - Compound words: "Produktionsrückstand", "Rückstandskonzept"

        Args:
            keyword: Original keyword from config file

        Returns:
            Set of case variants
        """
        variants = {keyword}
        if keyword:
            # Lowercase first letter variant (common in German compound words)
            if len(keyword) > 1:
                variants.add(keyword[0].lower() + keyword[1:])
            else:
                variants.add(keyword.lower())
            # Full lowercase (covers compound word matching)
            variants.add(keyword.lower())
            # Full uppercase
            variants.add(keyword.upper())
        return variants

    def _compile_keyword_pattern(self, keyword: str, flags: int) -> re.Pattern:
        """Compile a regex for a keyword with special handling for short tokens."""
        escaped = re.escape(keyword)
        if self._should_use_word_boundaries(keyword):
            escaped = rf"\b{escaped}\b"
        return re.compile(escaped, flags)

    def _load_keywords(self) -> None:
        """
        Load keywords from file and generate case variants.

        Original keywords are stored in _original_keywords for get_search_terms().
        Expanded keywords with case variants are stored in self.keywords for matching.
        """
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
                self._original_keywords.add(line)

        # Generate case variants if not case-sensitive
        if not self.case_sensitive:
            for kw in self._original_keywords:
                variants = self._generate_case_variants(kw)
                self.keywords.update(variants)
        else:
            self.keywords = self._original_keywords.copy()

        logger.info(
            f"Loaded {len(self._original_keywords)} keywords "
            f"({len(self.keywords)} with variants) from {self.keywords_file}"
        )

    def _compile_patterns(self) -> None:
        """Compile regex patterns for efficient matching."""
        flags = 0 if self.case_sensitive else re.IGNORECASE

        # Compile keyword patterns
        for kw in self.keywords:
            try:
                pattern = self._compile_keyword_pattern(kw, flags)
                self.keyword_patterns.append(pattern)
            except re.error as e:
                logger.warning(f"Invalid keyword pattern '{kw}': {e}")

        # Compile exclusion patterns
        for exc in self.exclusions:
            try:
                pattern = self._compile_keyword_pattern(exc, flags)
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

    def get_search_terms(self) -> List[str]:
        """
        Get original keywords for portal search queries ("Directly put item" strategy).

        Returns keywords as-is from the config file, suitable for URL parameters
        on portals that support keyword search via URL:
        - USP Austria: q={keyword}
        - Fraunhofer: Searchkey={keyword}

        These are the original keywords without case variants, as the portal
        search typically handles case-insensitivity on its own.

        Returns:
            List of original keywords from config file
        """
        return list(self._original_keywords)


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
