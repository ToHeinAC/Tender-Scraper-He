"""
Email sender for Tender Scraper System using Microsoft Outlook.

Uses Windows COM interface to send emails through Outlook.
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


class OutlookError(Exception):
    """Raised when Outlook operations fail."""
    pass


class OutlookSender:
    """
    Sends emails via Microsoft Outlook using COM interface.

    Requires Microsoft Outlook to be installed and configured.
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize Outlook sender.

        Args:
            config: Email configuration dictionary
        """
        self.config = config
        self.sender = config.get("sender", "")
        self.recipients_to = config.get("recipients", {}).get("to", [])
        self.recipients_cc = config.get("recipients", {}).get("cc", [])
        self.recipients_bcc = config.get("recipients", {}).get("bcc", [])
        self.subject_template = config.get("subject_template", "Ausschreibungen {date}")
        self.outlook = None

    def _get_outlook(self):
        """
        Get or create Outlook application instance.

        Returns:
            Outlook application object

        Raises:
            OutlookError: If Outlook cannot be accessed
        """
        if self.outlook is None:
            try:
                import win32com.client
                self.outlook = win32com.client.Dispatch("Outlook.Application")
                logger.debug("Connected to Outlook")
            except ImportError:
                raise OutlookError(
                    "pywin32 not installed. Install with: pip install pywin32"
                )
            except Exception as e:
                raise OutlookError(f"Failed to connect to Outlook: {e}")

        return self.outlook

    def send_email(
        self,
        subject: str,
        body: str,
        to: Optional[List[str]] = None,
        cc: Optional[List[str]] = None,
        bcc: Optional[List[str]] = None,
    ) -> bool:
        """
        Send an email via Outlook.

        Args:
            subject: Email subject
            body: Email body text
            to: List of recipient addresses (uses config if not provided)
            cc: List of CC addresses (uses config if not provided)
            bcc: List of BCC addresses (uses config if not provided)

        Returns:
            True if email was sent successfully

        Raises:
            OutlookError: If sending fails
        """
        try:
            outlook = self._get_outlook()
            mail = outlook.CreateItem(0)  # 0 = MailItem

            # Set recipients
            to_addrs = to or self.recipients_to
            cc_addrs = cc or self.recipients_cc
            bcc_addrs = bcc or self.recipients_bcc

            mail.To = "; ".join(to_addrs) if to_addrs else ""
            mail.CC = "; ".join(cc_addrs) if cc_addrs else ""
            mail.BCC = "; ".join(bcc_addrs) if bcc_addrs else ""

            mail.Subject = subject
            mail.Body = body

            # Send
            mail.Send()

            logger.info(f"Email sent: {subject}")
            logger.debug(f"Recipients: To={to_addrs}, CC={cc_addrs}")

            return True

        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            raise OutlookError(f"Failed to send email: {e}") from e

    def send_tender_report(
        self,
        tenders: List[Dict[str, Any]],
        portal_status: Dict[str, Dict[str, Any]],
    ) -> bool:
        """
        Send a tender report email.

        Args:
            tenders: List of tender dictionaries
            portal_status: Dictionary mapping portal names to status info

        Returns:
            True if sent successfully
        """
        from email_sender.templates import EmailTemplates

        # Generate subject
        today = datetime.now()
        subject = self.subject_template.format(
            date=today.strftime("%d.%m.%Y"),
            count=len(tenders),
        )

        # Generate body
        body = EmailTemplates.format_tender_report(
            tenders=tenders,
            portal_status=portal_status,
            timestamp=today,
        )

        return self.send_email(subject=subject, body=body)


def send_email_simple(
    to: List[str],
    subject: str,
    body: str,
    cc: Optional[List[str]] = None,
) -> bool:
    """
    Simple function to send an email via Outlook.

    Args:
        to: List of recipient addresses
        subject: Email subject
        body: Email body
        cc: Optional CC addresses

    Returns:
        True if sent successfully
    """
    try:
        import win32com.client

        outlook = win32com.client.Dispatch("Outlook.Application")
        mail = outlook.CreateItem(0)

        mail.To = "; ".join(to)
        if cc:
            mail.CC = "; ".join(cc)
        mail.Subject = subject
        mail.Body = body

        mail.Send()
        logger.info(f"Email sent: {subject}")
        return True

    except Exception as e:
        logger.error(f"Failed to send email: {e}")
        return False
