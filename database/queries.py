"""
Common database queries for Tender Scraper System.

Provides query builders and common query patterns.
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from database.db import Database


class TenderQueries:
    """Helper class for common tender-related queries."""

    def __init__(self, db: Database):
        """
        Initialize query helper.

        Args:
            db: Database instance
        """
        self.db = db

    def get_tenders_by_portal(
        self,
        portal: str,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Get tenders from a specific portal.

        Args:
            portal: Portal name
            limit: Maximum results

        Returns:
            List of tender dictionaries
        """
        query = """
        SELECT * FROM tenders
        WHERE portal = ?
        ORDER BY created_at DESC
        LIMIT ?
        """

        rows = self.db.fetch_all(query, (portal, limit))
        return [dict(row) for row in rows]

    def get_tenders_by_keyword(
        self,
        keyword: str,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Get tenders matching a specific keyword.

        Args:
            keyword: Keyword to search
            limit: Maximum results

        Returns:
            List of tender dictionaries
        """
        query = """
        SELECT * FROM tenders
        WHERE suchbegriff = ? OR titel LIKE ?
        ORDER BY created_at DESC
        LIMIT ?
        """

        pattern = f"%{keyword}%"
        rows = self.db.fetch_all(query, (keyword, pattern, limit))
        return [dict(row) for row in rows]

    def get_tenders_last_n_hours(
        self,
        hours: int = 24,
    ) -> List[Dict[str, Any]]:
        """
        Get tenders from the last N hours.

        Args:
            hours: Number of hours to look back

        Returns:
            List of tender dictionaries
        """
        cutoff = datetime.now() - timedelta(hours=hours)

        query = """
        SELECT * FROM tenders
        WHERE created_at > ?
        ORDER BY created_at DESC
        """

        rows = self.db.fetch_all(query, (cutoff,))
        return [dict(row) for row in rows]

    def get_portal_statistics(self) -> List[Dict[str, Any]]:
        """
        Get statistics per portal.

        Returns:
            List of portal statistics
        """
        query = """
        SELECT
            portal,
            COUNT(*) as total_tenders,
            COUNT(DISTINCT DATE(created_at)) as days_active,
            MAX(created_at) as last_tender,
            MIN(created_at) as first_tender
        FROM tenders
        GROUP BY portal
        ORDER BY total_tenders DESC
        """

        rows = self.db.fetch_all(query)
        return [dict(row) for row in rows]

    def get_scraper_success_rate(
        self,
        days: int = 7,
    ) -> List[Dict[str, Any]]:
        """
        Get scraper success rates over the last N days.

        Args:
            days: Number of days to analyze

        Returns:
            List of success rate data per portal
        """
        cutoff = datetime.now() - timedelta(days=days)

        query = """
        SELECT
            portal,
            COUNT(*) as total_runs,
            SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as successful,
            SUM(CASE WHEN status = 'failure' THEN 1 ELSE 0 END) as failed,
            AVG(records_new) as avg_new_records,
            ROUND(
                100.0 * SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) / COUNT(*),
                2
            ) as success_rate
        FROM scrape_history
        WHERE scrape_start > ?
        GROUP BY portal
        ORDER BY success_rate DESC
        """

        rows = self.db.fetch_all(query, (cutoff,))
        return [dict(row) for row in rows]

    def get_daily_tender_counts(
        self,
        days: int = 30,
    ) -> List[Dict[str, Any]]:
        """
        Get daily new tender counts.

        Args:
            days: Number of days to analyze

        Returns:
            List of daily counts
        """
        cutoff = datetime.now() - timedelta(days=days)

        query = """
        SELECT
            DATE(created_at) as date,
            COUNT(*) as tender_count,
            COUNT(DISTINCT portal) as portals_active
        FROM tenders
        WHERE created_at > ?
        GROUP BY DATE(created_at)
        ORDER BY date DESC
        """

        rows = self.db.fetch_all(query, (cutoff,))
        return [dict(row) for row in rows]

    def search_tenders(
        self,
        search_term: str,
        portal: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Search tenders by title or organization.

        Args:
            search_term: Search term
            portal: Optional portal filter
            limit: Maximum results

        Returns:
            List of matching tenders
        """
        pattern = f"%{search_term}%"

        if portal:
            query = """
            SELECT * FROM tenders
            WHERE portal = ? AND (titel LIKE ? OR ausschreibungsstelle LIKE ?)
            ORDER BY created_at DESC
            LIMIT ?
            """
            rows = self.db.fetch_all(query, (portal, pattern, pattern, limit))
        else:
            query = """
            SELECT * FROM tenders
            WHERE titel LIKE ? OR ausschreibungsstelle LIKE ?
            ORDER BY created_at DESC
            LIMIT ?
            """
            rows = self.db.fetch_all(query, (pattern, pattern, limit))

        return [dict(row) for row in rows]

    def get_upcoming_deadlines(
        self,
        days: int = 7,
    ) -> List[Dict[str, Any]]:
        """
        Get tenders with upcoming deadlines.

        Note: This relies on naechste_frist being parseable as a date.

        Args:
            days: Days to look ahead

        Returns:
            List of tenders with upcoming deadlines
        """
        # This is a best-effort query since deadline format varies by portal
        query = """
        SELECT * FROM tenders
        WHERE naechste_frist IS NOT NULL
        AND naechste_frist != ''
        ORDER BY created_at DESC
        LIMIT 100
        """

        rows = self.db.fetch_all(query)
        return [dict(row) for row in rows]

    def cleanup_old_tenders(
        self,
        days: int = 365,
    ) -> int:
        """
        Delete tenders older than N days.

        Args:
            days: Age threshold in days

        Returns:
            Number of deleted records
        """
        cutoff = datetime.now() - timedelta(days=days)

        query = """
        DELETE FROM tenders
        WHERE created_at < ?
        """

        cursor = self.db.execute(query, (cutoff,))
        self.db.connect().commit()

        return cursor.rowcount

    def vacuum_database(self) -> None:
        """Run VACUUM to optimize database size."""
        self.db.execute("VACUUM")

    def check_integrity(self) -> bool:
        """
        Check database integrity.

        Returns:
            True if database is healthy
        """
        row = self.db.fetch_one("PRAGMA integrity_check")
        return row and row[0] == "ok"
