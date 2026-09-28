"""
Scraper for oeffentlichevergabe.de (Bekanntmachungsservice des Bundes).

URL: https://oeffentlichevergabe.de
Central German notice service. It collects notices from all German e-procurement
platforms (including service.bund.de) and offers daily bulk exports via an open API.

Selenium Required: No
- The public API /api/notice-exports?pubDay=YYYY-MM-DD returns a ZIP per publication day
- OCDS JSON export provides title, buyer, place of performance and procedure type
- eForms XML export provides the submission deadline (not contained in OCDS)
"""

import io
import json
import re
import zipfile
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional

import requests

from scrapers.base import BaseScraper, TenderResult, ScraperError
from scrapers.registry import register_scraper
from scrapers.utils import clean_text


@register_scraper
class OeffentlicheVergabeScraper(BaseScraper):
    """Scraper for the oeffentlichevergabe.de daily notice exports."""

    PORTAL_NAME = "oeffentlichevergabe"
    PORTAL_URL = "https://oeffentlichevergabe.de"
    REQUIRES_SELENIUM = False

    EXPORT_URL = "https://oeffentlichevergabe.de/api/notice-exports"
    DETAIL_URL = "https://oeffentlichevergabe.de/ui/de/search/details"

    # Number of past publication days to fetch (today's export is not available yet).
    # Overlapping days are deduplicated by the database.
    DAYS_BACK = 3

    REQUEST_TIMEOUT = 120

    # OCDS release tags that represent open or planned procurements (awards are skipped)
    RELEVANT_TAGS = {"tender", "planning", "tenderUpdate", "planningUpdate"}

    # Lot titles without own information, e.g. "Los 1", "Lot 2"
    GENERIC_LOT_TITLE = re.compile(r"^(Los|Lot|Teillos)\s*\d+\.?$", re.IGNORECASE)

    DEADLINE_PATTERN = re.compile(
        r"TenderSubmissionDeadlinePeriod>\s*<[^>]*EndDate>(\d{4}-\d{2}-\d{2})",
    )

    def scrape(self) -> List[TenderResult]:
        """
        Download the daily exports of the last days and convert them to results.

        Returns:
            List of TenderResult objects
        """
        days_back = self.config.get("oeffentlichevergabe", {}).get("days_back", self.DAYS_BACK)
        session = requests.Session()
        if self.user_agent:
            session.headers["User-Agent"] = self.user_agent

        results = []
        failed_days = 0
        today = date.today()

        for offset in range(1, days_back + 1):
            pub_day = (today - timedelta(days=offset)).isoformat()
            try:
                ocds_zip = self._download_export(session, pub_day, "ocds.zip")
            except requests.RequestException as e:
                self.logger.warning(f"OCDS export for {pub_day} failed: {e}")
                failed_days += 1
                continue

            try:
                deadlines = self._parse_deadlines(
                    self._download_export(session, pub_day, "eforms.zip")
                )
            except (requests.RequestException, zipfile.BadZipFile) as e:
                self.logger.warning(f"eForms export for {pub_day} failed, no deadlines: {e}")
                deadlines = {}

            day_results = self._parse_ocds_export(ocds_zip, deadlines)
            self.logger.info(f"{pub_day}: {len(day_results)} notices")
            results.extend(day_results)

        if failed_days == days_back:
            raise ScraperError(self.PORTAL_NAME, "All export downloads failed")

        return results

    def _download_export(self, session: requests.Session, pub_day: str, fmt: str) -> bytes:
        """Download the export ZIP of one publication day."""
        response = session.get(
            self.EXPORT_URL,
            params={"pubDay": pub_day, "format": fmt},
            timeout=self.REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        return response.content

    def _parse_deadlines(self, eforms_zip: bytes) -> Dict[str, str]:
        """
        Extract submission deadlines from the eForms export.

        Returns:
            Dict mapping file stem (e.g. "25855874-1") to deadline "DD.MM.YYYY"
        """
        deadlines = {}
        with zipfile.ZipFile(io.BytesIO(eforms_zip)) as zf:
            for name in zf.namelist():
                xml = zf.read(name).decode("utf-8", errors="replace")
                dates = self.DEADLINE_PATTERN.findall(xml)
                if dates:
                    # Earliest deadline over all lots
                    deadlines[name.rsplit(".", 1)[0]] = self._format_date(min(dates))
        return deadlines

    def _parse_ocds_export(self, ocds_zip: bytes, deadlines: Dict[str, str]) -> List[TenderResult]:
        """Parse all OCDS release packages of one export ZIP."""
        results = []
        now = datetime.now()

        with zipfile.ZipFile(io.BytesIO(ocds_zip)) as zf:
            for name in zf.namelist():
                try:
                    package = json.loads(zf.read(name))
                except (ValueError, UnicodeDecodeError) as e:
                    self.logger.warning(f"Invalid JSON in {name}: {e}")
                    continue

                deadline = deadlines.get(name.rsplit(".", 1)[0], "")
                for release in package.get("releases", []):
                    try:
                        results.extend(self._parse_release(release, deadline, now))
                    except Exception as e:
                        self.logger.warning(f"Failed to parse {name}: {e}")

        return results

    def _parse_release(
        self, release: dict, deadline: str, now: datetime
    ) -> List[TenderResult]:
        """Convert one OCDS release into a result (one per notice, empty if irrelevant)."""
        if not self._is_relevant(release):
            return []

        tender = release.get("tender", {})
        notice_id = release.get("id", "")
        titel = clean_text(tender.get("title", ""))
        if not notice_id or not titel:
            return []

        buyer = release.get("buyer", {}).get("name") or tender.get("procuringEntity", {}).get(
            "name", ""
        )
        lots = tender.get("lots", [])
        first_lot = lots[0].get("id") if lots else None

        return [
            TenderResult(
                portal=self.PORTAL_NAME,
                suchbegriff=None,
                suchzeitpunkt=now,
                vergabe_id=notice_id,
                link=self._build_link(notice_id, first_lot),
                titel=self._build_title(titel, lots),
                ausschreibungsstelle=clean_text(buyer),
                ausfuehrungsort=self._get_place(tender),
                ausschreibungsart=tender.get("procurementMethodDetails", "") or "",
                naechste_frist=deadline,
                veroeffentlicht=self._format_date(release.get("date", "")),
            )
        ]

    def _build_title(self, titel: str, lots: List[dict]) -> str:
        """
        Append lot titles that add information to the notice title.

        Keyword matching only checks the title, so keywords that appear only
        in a lot title would otherwise be missed.
        """
        extra = []
        for lot in lots:
            lot_title = clean_text(lot.get("title", ""))
            # Lot titles often repeat the notice title: keep only the additional part
            if lot_title.lower().startswith(titel.lower()):
                lot_title = lot_title[len(titel):].strip(" -–:,;")
            if (
                not lot_title
                or self.GENERIC_LOT_TITLE.match(lot_title)
                or lot_title.lower() in titel.lower()
                or lot_title in extra
            ):
                continue
            extra.append(lot_title)

        return " | ".join([titel] + extra)

    def _is_relevant(self, release: dict) -> bool:
        """Keep competition and prior information notices, skip award notices."""
        tags = set(release.get("tag", []))
        if tags:
            return bool(tags & self.RELEVANT_TAGS)
        return not release.get("awards")

    def _build_link(self, notice_id: str, lot_id: Optional[str]) -> str:
        """Build the public detail page URL."""
        link = f"{self.DETAIL_URL}?noticeId={notice_id}"
        if lot_id:
            link += f"&lotId={lot_id}"
        return link

    @staticmethod
    def _get_place(tender: dict) -> str:
        """Collect distinct delivery localities from the tender items."""
        places = []
        for item in tender.get("items", []):
            locality = item.get("deliveryAddress", {}).get("locality")
            if locality and locality not in places:
                places.append(locality)
        return ", ".join(places)

    @staticmethod
    def _format_date(value: str) -> str:
        """Convert an ISO date (YYYY-MM-DD...) to DD.MM.YYYY."""
        match = re.match(r"(\d{4})-(\d{2})-(\d{2})", value or "")
        if not match:
            return ""
        return f"{match.group(3)}.{match.group(2)}.{match.group(1)}"
