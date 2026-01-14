"""
Email templates for Tender Scraper System.

Provides formatted email body generation for tender reports.
"""

from datetime import datetime
from typing import Any, Dict, List


class EmailTemplates:
    """Email template generator for tender reports."""

    # Header text
    HEADER = """Dies ist eine automatisch generierte E-Mail.
Bitte nicht direkt antworten.
Bei Rückfragen bitte an den Administrator wenden.

Stand: {timestamp}
"""

    # Portal list header
    PORTAL_HEADER = """
---------------------------------------------------------------
Durchsuchte Portale ({total} durchsucht, {success} erfolgreich, {failed} fehlgeschlagen)
---------------------------------------------------------------
"""

    # Results header
    RESULTS_HEADER = """
---------------------------------------------------------------
NEUE AUSSCHREIBUNGEN ({count} gefunden)
---------------------------------------------------------------
"""

    # No results message
    NO_RESULTS = """
---------------------------------------------------------------
Keine neuen Ausschreibungen gefunden
---------------------------------------------------------------
"""

    # Single tender format
    TENDER_FORMAT = """
Titel:\t {titel}
Ausschreibungsstelle:\t {ausschreibungsstelle}
Link:\t {link}
Nächste Frist:\t {naechste_frist}
Veröffentlicht:\t {veroeffentlicht}
Portal:\t {portal}
"""

    # Footer
    FOOTER = """
---------------------------------------------------------------
Tender Scraper System v1.0
---------------------------------------------------------------
"""

    @classmethod
    def format_tender_report(
        cls,
        tenders: List[Dict[str, Any]],
        portal_status: Dict[str, Dict[str, Any]],
        timestamp: datetime,
    ) -> str:
        """
        Format a complete tender report email body.

        Args:
            tenders: List of tender dictionaries
            portal_status: Dict mapping portal names to status info
                          Each entry should have: success (bool), records (int), error (str)
            timestamp: Timestamp of the report

        Returns:
            Formatted email body string
        """
        parts = []

        # Header
        parts.append(cls.HEADER.format(
            timestamp=timestamp.strftime("%d.%m.%Y %H:%M:%S")
        ))

        # Portal status summary
        total = len(portal_status)
        success = sum(1 for p in portal_status.values() if p.get("success", False))
        failed = total - success

        parts.append(cls.PORTAL_HEADER.format(
            total=total,
            success=success,
            failed=failed,
        ))

        # List each portal
        for portal, status in sorted(portal_status.items()):
            if status.get("success", False):
                records = status.get("records_new", 0)
                parts.append(f"✓ {portal} - {records} Ergebnisse")
            else:
                error = status.get("error", "Unbekannter Fehler")
                parts.append(f"✗ {portal} - Fehler: {error}")

        # Results
        if tenders:
            parts.append(cls.RESULTS_HEADER.format(count=len(tenders)))

            for tender in tenders:
                parts.append(cls.TENDER_FORMAT.format(
                    titel=tender.get("titel", "-"),
                    ausschreibungsstelle=tender.get("ausschreibungsstelle", "-"),
                    link=tender.get("link", "-"),
                    naechste_frist=tender.get("naechste_frist", "-"),
                    veroeffentlicht=tender.get("veroeffentlicht", "-"),
                    portal=tender.get("portal", "-"),
                ))
        else:
            parts.append(cls.NO_RESULTS)

        # Footer
        parts.append(cls.FOOTER)

        return "\n".join(parts)

    @classmethod
    def format_error_report(
        cls,
        errors: List[Dict[str, str]],
        timestamp: datetime,
    ) -> str:
        """
        Format an error report email body.

        Args:
            errors: List of error dictionaries with 'portal' and 'error' keys
            timestamp: Timestamp of the report

        Returns:
            Formatted email body string
        """
        parts = []

        parts.append(cls.HEADER.format(
            timestamp=timestamp.strftime("%d.%m.%Y %H:%M:%S")
        ))

        parts.append("""
---------------------------------------------------------------
FEHLER BEI DER AUSFÜHRUNG
---------------------------------------------------------------
""")

        for error in errors:
            portal = error.get("portal", "Unknown")
            msg = error.get("error", "Unknown error")
            parts.append(f"\n{portal}:\n  {msg}\n")

        parts.append(cls.FOOTER)

        return "\n".join(parts)

    @classmethod
    def format_simple_report(
        cls,
        tenders: List[Dict[str, Any]],
        portals_searched: List[str],
        timestamp: datetime,
    ) -> str:
        """
        Format a simple tender report without detailed portal status.

        Args:
            tenders: List of tender dictionaries
            portals_searched: List of portal names that were searched
            timestamp: Timestamp of the report

        Returns:
            Formatted email body string
        """
        parts = []

        # Header
        parts.append(cls.HEADER.format(
            timestamp=timestamp.strftime("%d.%m.%Y %H:%M:%S")
        ))

        # Portal list
        parts.append("\n********************************************************")
        parts.append("Durchsucht:")
        for portal in portals_searched:
            parts.append(f" - {portal}")
        parts.append("********************************************************\n")

        # Results
        if tenders:
            for tender in tenders:
                parts.append(cls.TENDER_FORMAT.format(
                    titel=tender.get("titel", "-"),
                    ausschreibungsstelle=tender.get("ausschreibungsstelle", "-"),
                    link=tender.get("link", "-"),
                    naechste_frist=tender.get("naechste_frist", "-"),
                    veroeffentlicht=tender.get("veroeffentlicht", "-"),
                    portal=tender.get("portal", "-"),
                ))
        else:
            parts.append("\nKeine neuen Ausschreibungen gefunden.\n")

        parts.append(cls.FOOTER)

        return "\n".join(parts)
