"""
Email alert sender (stub for MVP).
Can be implemented later using SMTP or email service APIs.
"""

from typing import Dict, List
from sgs.utils.logging import get_logger

logger = get_logger("email_alerts")


class EmailAlertSender:
    """Email alert sender (stub implementation)."""
    
    def __init__(self, smtp_host: str = None, smtp_port: int = None):
        """
        Initialize email alert sender.
        
        Args:
            smtp_host: SMTP server hostname
            smtp_port: SMTP server port
        """
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        logger.info("Email alert sender initialized (stub)")
    
    def send_alert(
        self,
        symbol: str,
        year: int,
        quarter: int,
        trigger_reasons: List[str],
        sgs_data: Dict,
        sector_etf: str,
        recipients: List[str] = None
    ) -> bool:
        """
        Send SGS trigger alert via email (stub).
        
        Args:
            symbol: Stock ticker
            year: Year
            quarter: Quarter
            trigger_reasons: List of trigger reason strings
            sgs_data: Full SGS JSON data
            sector_etf: Sector ETF symbol
            recipients: List of email addresses
        
        Returns:
            False (not implemented)
        """
        logger.warning(f"Email alert requested but not implemented: {symbol} {year} Q{quarter}")
        logger.info("To implement: Use SMTP or email service API (SendGrid, AWS SES, etc.)")
        return False
