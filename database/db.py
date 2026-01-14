"""
Database connection and management for Tender Scraper System.

Provides SQLite database operations with context manager support.
"""

import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Database schema
SCHEMA = """
-- Tenders table: stores all scraped tender data
CREATE TABLE IF NOT EXISTS tenders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    portal TEXT NOT NULL,
    suchbegriff TEXT,
    suchzeitpunkt DATETIME NOT NULL,
    vergabe_id TEXT,
    link TEXT,
    titel TEXT NOT NULL,
    ausschreibungsstelle TEXT,
    ausfuehrungsort TEXT,
    ausschreibungsart TEXT,
    naechste_frist TEXT,
    veroeffentlicht TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(portal, vergabe_id, link, titel)
);

-- Scrape history table: tracks each scraping run
CREATE TABLE IF NOT EXISTS scrape_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    portal TEXT NOT NULL,
    scrape_start DATETIME NOT NULL,
    scrape_end DATETIME,
    status TEXT NOT NULL,
    records_found INTEGER DEFAULT 0,
    records_new INTEGER DEFAULT 0,
    error_message TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Email history table: tracks sent emails
CREATE TABLE IF NOT EXISTS email_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sent_at DATETIME NOT NULL,
    recipients TEXT NOT NULL,
    subject TEXT NOT NULL,
    new_tenders_count INTEGER DEFAULT 0,
    status TEXT NOT NULL,
    error_message TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_tenders_portal ON tenders(portal);
CREATE INDEX IF NOT EXISTS idx_tenders_created_at ON tenders(created_at);
CREATE INDEX IF NOT EXISTS idx_tenders_suchzeitpunkt ON tenders(suchzeitpunkt);
CREATE INDEX IF NOT EXISTS idx_scrape_history_portal ON scrape_history(portal);
CREATE INDEX IF NOT EXISTS idx_scrape_history_start ON scrape_history(scrape_start);
CREATE INDEX IF NOT EXISTS idx_email_history_sent ON email_history(sent_at);
"""


class Database:
    """SQLite database manager with connection pooling and context manager support."""

    def __init__(self, db_path: str = "data/tenders.db"):
        """
        Initialize database manager.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self._connection: Optional[sqlite3.Connection] = None

        # Ensure directory exists
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        """
        Get or create database connection.

        Returns:
            SQLite connection object
        """
        if self._connection is None:
            self._connection = sqlite3.connect(
                self.db_path,
                detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES,
            )
            self._connection.row_factory = sqlite3.Row

            # Enable WAL mode for better concurrency
            self._connection.execute("PRAGMA journal_mode=WAL")
            self._connection.execute("PRAGMA foreign_keys=ON")

            logger.debug(f"Connected to database: {self.db_path}")

        return self._connection

    def close(self) -> None:
        """Close database connection."""
        if self._connection:
            try:
                self._connection.close()
                logger.debug("Database connection closed")
            except Exception as e:
                logger.warning(f"Error closing database: {e}")
            finally:
                self._connection = None

    def __enter__(self) -> "Database":
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        self.close()

    @contextmanager
    def transaction(self) -> Generator[sqlite3.Cursor, None, None]:
        """
        Context manager for database transactions.

        Automatically commits on success or rolls back on error.

        Yields:
            Database cursor
        """
        conn = self.connect()
        cursor = conn.cursor()
        try:
            yield cursor
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Transaction rolled back: {e}")
            raise

    def initialize(self) -> None:
        """Initialize database schema."""
        conn = self.connect()
        cursor = conn.cursor()

        try:
            cursor.executescript(SCHEMA)
            conn.commit()
            logger.info(f"Database initialized: {self.db_path}")
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            raise

    def execute(
        self,
        query: str,
        params: Optional[Tuple] = None,
    ) -> sqlite3.Cursor:
        """
        Execute a SQL query.

        Args:
            query: SQL query string
            params: Query parameters

        Returns:
            Cursor with results
        """
        conn = self.connect()
        cursor = conn.cursor()

        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)

        return cursor

    def execute_many(
        self,
        query: str,
        params_list: List[Tuple],
    ) -> int:
        """
        Execute a SQL query with multiple parameter sets.

        Args:
            query: SQL query string
            params_list: List of parameter tuples

        Returns:
            Number of rows affected
        """
        conn = self.connect()
        cursor = conn.cursor()

        cursor.executemany(query, params_list)
        conn.commit()

        return cursor.rowcount

    def fetch_one(
        self,
        query: str,
        params: Optional[Tuple] = None,
    ) -> Optional[sqlite3.Row]:
        """
        Execute query and fetch one result.

        Args:
            query: SQL query string
            params: Query parameters

        Returns:
            Single row or None
        """
        cursor = self.execute(query, params)
        return cursor.fetchone()

    def fetch_all(
        self,
        query: str,
        params: Optional[Tuple] = None,
    ) -> List[sqlite3.Row]:
        """
        Execute query and fetch all results.

        Args:
            query: SQL query string
            params: Query parameters

        Returns:
            List of rows
        """
        cursor = self.execute(query, params)
        return cursor.fetchall()

    # =========================================================================
    # Tender Operations
    # =========================================================================

    def insert_tender(self, tender: Dict[str, Any]) -> bool:
        """
        Insert a single tender (ignore if duplicate).

        Args:
            tender: Tender data dictionary

        Returns:
            True if inserted, False if duplicate
        """
        query = """
        INSERT OR IGNORE INTO tenders (
            portal, suchbegriff, suchzeitpunkt, vergabe_id, link,
            titel, ausschreibungsstelle, ausfuehrungsort,
            ausschreibungsart, naechste_frist, veroeffentlicht
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

        params = (
            tender.get("portal"),
            tender.get("suchbegriff"),
            tender.get("suchzeitpunkt"),
            tender.get("vergabe_id"),
            tender.get("link"),
            tender.get("titel"),
            tender.get("ausschreibungsstelle"),
            tender.get("ausfuehrungsort"),
            tender.get("ausschreibungsart"),
            tender.get("naechste_frist"),
            tender.get("veroeffentlicht"),
        )

        cursor = self.execute(query, params)
        self.connect().commit()

        return cursor.rowcount > 0

    def insert_tenders(self, tenders: List[Dict[str, Any]]) -> int:
        """
        Insert multiple tenders (ignore duplicates).

        Args:
            tenders: List of tender data dictionaries

        Returns:
            Number of new tenders inserted
        """
        if not tenders:
            return 0

        query = """
        INSERT OR IGNORE INTO tenders (
            portal, suchbegriff, suchzeitpunkt, vergabe_id, link,
            titel, ausschreibungsstelle, ausfuehrungsort,
            ausschreibungsart, naechste_frist, veroeffentlicht
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

        params_list = [
            (
                t.get("portal"),
                t.get("suchbegriff"),
                t.get("suchzeitpunkt"),
                t.get("vergabe_id"),
                t.get("link"),
                t.get("titel"),
                t.get("ausschreibungsstelle"),
                t.get("ausfuehrungsort"),
                t.get("ausschreibungsart"),
                t.get("naechste_frist"),
                t.get("veroeffentlicht"),
            )
            for t in tenders
        ]

        # Get count before insert
        count_before = self.fetch_one("SELECT COUNT(*) as cnt FROM tenders")
        count_before = count_before["cnt"] if count_before else 0

        # Insert
        self.execute_many(query, params_list)

        # Get count after insert
        count_after = self.fetch_one("SELECT COUNT(*) as cnt FROM tenders")
        count_after = count_after["cnt"] if count_after else 0

        new_count = count_after - count_before
        logger.debug(f"Inserted {new_count} new tenders (of {len(tenders)} total)")

        return new_count

    def get_tenders_since(
        self,
        since: datetime,
        portal: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get tenders created since a given timestamp.

        Args:
            since: Cutoff datetime
            portal: Optional portal filter

        Returns:
            List of tender dictionaries
        """
        if portal:
            query = """
            SELECT * FROM tenders
            WHERE created_at > ? AND portal = ?
            ORDER BY created_at DESC
            """
            rows = self.fetch_all(query, (since, portal))
        else:
            query = """
            SELECT * FROM tenders
            WHERE created_at > ?
            ORDER BY created_at DESC
            """
            rows = self.fetch_all(query, (since,))

        return [dict(row) for row in rows]

    def get_new_tenders_since_last_email(self) -> List[Dict[str, Any]]:
        """
        Get tenders added since the last successful email.

        Returns:
            List of tender dictionaries
        """
        query = """
        SELECT t.* FROM tenders t
        WHERE t.created_at > (
            SELECT COALESCE(MAX(sent_at), '1970-01-01')
            FROM email_history
            WHERE status = 'success'
        )
        ORDER BY t.created_at DESC
        """

        rows = self.fetch_all(query)
        return [dict(row) for row in rows]

    def get_tender_count(self, portal: Optional[str] = None) -> int:
        """
        Get total tender count.

        Args:
            portal: Optional portal filter

        Returns:
            Number of tenders
        """
        if portal:
            row = self.fetch_one(
                "SELECT COUNT(*) as cnt FROM tenders WHERE portal = ?",
                (portal,),
            )
        else:
            row = self.fetch_one("SELECT COUNT(*) as cnt FROM tenders")

        return row["cnt"] if row else 0

    # =========================================================================
    # Scrape History Operations
    # =========================================================================

    def log_scrape_start(self, portal: str) -> int:
        """
        Log the start of a scraping operation.

        Args:
            portal: Portal name

        Returns:
            ID of the scrape history record
        """
        query = """
        INSERT INTO scrape_history (portal, scrape_start, status)
        VALUES (?, ?, 'in_progress')
        """

        cursor = self.execute(query, (portal, datetime.now()))
        self.connect().commit()

        return cursor.lastrowid

    def log_scrape_end(
        self,
        scrape_id: int,
        status: str,
        records_found: int = 0,
        records_new: int = 0,
        error_message: Optional[str] = None,
    ) -> None:
        """
        Log the end of a scraping operation.

        Args:
            scrape_id: ID from log_scrape_start
            status: 'success', 'failure', or 'partial'
            records_found: Total records found
            records_new: New records (not duplicates)
            error_message: Error message if failed
        """
        query = """
        UPDATE scrape_history
        SET scrape_end = ?, status = ?, records_found = ?,
            records_new = ?, error_message = ?
        WHERE id = ?
        """

        self.execute(
            query,
            (datetime.now(), status, records_found, records_new, error_message, scrape_id),
        )
        self.connect().commit()

    def get_scrape_history(
        self,
        portal: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Get scrape history records.

        Args:
            portal: Optional portal filter
            limit: Maximum records to return

        Returns:
            List of scrape history dictionaries
        """
        if portal:
            query = """
            SELECT * FROM scrape_history
            WHERE portal = ?
            ORDER BY scrape_start DESC
            LIMIT ?
            """
            rows = self.fetch_all(query, (portal, limit))
        else:
            query = """
            SELECT * FROM scrape_history
            ORDER BY scrape_start DESC
            LIMIT ?
            """
            rows = self.fetch_all(query, (limit,))

        return [dict(row) for row in rows]

    # =========================================================================
    # Email History Operations
    # =========================================================================

    def log_email_sent(
        self,
        recipients: str,
        subject: str,
        new_tenders_count: int,
        status: str = "success",
        error_message: Optional[str] = None,
    ) -> int:
        """
        Log a sent email.

        Args:
            recipients: Comma-separated recipient list
            subject: Email subject
            new_tenders_count: Number of new tenders in email
            status: 'success' or 'failure'
            error_message: Error message if failed

        Returns:
            ID of the email history record
        """
        query = """
        INSERT INTO email_history (
            sent_at, recipients, subject, new_tenders_count,
            status, error_message
        ) VALUES (?, ?, ?, ?, ?, ?)
        """

        cursor = self.execute(
            query,
            (
                datetime.now(),
                recipients,
                subject,
                new_tenders_count,
                status,
                error_message,
            ),
        )
        self.connect().commit()

        return cursor.lastrowid

    def get_last_successful_email_time(self) -> Optional[datetime]:
        """
        Get the timestamp of the last successfully sent email.

        Returns:
            Datetime of last email or None
        """
        row = self.fetch_one("""
            SELECT MAX(sent_at) as last_sent
            FROM email_history
            WHERE status = 'success'
        """)

        if row and row["last_sent"]:
            if isinstance(row["last_sent"], str):
                return datetime.fromisoformat(row["last_sent"])
            return row["last_sent"]

        return None

    def get_email_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get email history records.

        Args:
            limit: Maximum records to return

        Returns:
            List of email history dictionaries
        """
        rows = self.fetch_all("""
            SELECT * FROM email_history
            ORDER BY sent_at DESC
            LIMIT ?
        """, (limit,))

        return [dict(row) for row in rows]
