"""
Tender Scraper - Email Sender Package

This package handles email generation and sending via Microsoft Outlook.
"""

from email_sender.sender import OutlookSender, OutlookError
from email_sender.templates import EmailTemplates

__all__ = ["OutlookSender", "OutlookError", "EmailTemplates"]
