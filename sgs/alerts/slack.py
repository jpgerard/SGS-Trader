"""
Slack alert sender using incoming webhooks.
Sends rich formatted messages with SGS trigger details and trade suggestions.
"""

import json
import requests
from typing import Dict, List, Optional
from datetime import datetime
from sgs.config import Config
from sgs.utils.logging import get_logger
from sgs.utils.retry import retry_with_backoff

logger = get_logger("slack_alerts")


class SlackAlertSender:
    """Send SGS alerts via Slack incoming webhook."""
    
    def __init__(self, webhook_url: Optional[str] = None):
        """
        Initialize Slack alert sender.
        
        Args:
            webhook_url: Slack webhook URL (defaults to Config.SLACK_WEBHOOK_URL)
        """
        self.webhook_url = webhook_url or Config.SLACK_WEBHOOK_URL
        if not self.webhook_url:
            raise ValueError("Slack webhook URL not configured")
        
        logger.info("Slack alert sender initialized")
    
    @retry_with_backoff(max_attempts=3, initial_delay=1.0, backoff_factor=2.0)
    def send_alert(
        self,
        symbol: str,
        year: int,
        quarter: int,
        trigger_reasons: List[str],
        sgs_data: Dict,
        sector_etf: str
    ) -> bool:
        """
        Send SGS trigger alert to Slack.
        
        Args:
            symbol: Stock ticker
            year: Year
            quarter: Quarter
            trigger_reasons: List of trigger reason strings
            sgs_data: Full SGS JSON data
            sector_etf: Sector ETF symbol for hedging
        
        Returns:
            True if sent successfully
        
        Raises:
            Exception: On send failure after retries
        """
        # Build message blocks
        blocks = self._build_message_blocks(
            symbol, year, quarter, trigger_reasons, sgs_data, sector_etf
        )
        
        # Build payload
        payload = {
            "blocks": blocks,
            "text": f"🚨 SGS Alert: {symbol} {year} Q{quarter}"  # Fallback text
        }
        
        # Send to Slack
        try:
            response = requests.post(
                self.webhook_url,
                json=payload,
                timeout=10
            )
            
            response.raise_for_status()
            
            logger.info(f"Slack alert sent: {symbol} {year} Q{quarter}")
            return True
        
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to send Slack alert: {symbol} {year} Q{quarter}, error: {e}")
            raise
    
    def _build_message_blocks(
        self,
        symbol: str,
        year: int,
        quarter: int,
        trigger_reasons: List[str],
        sgs_data: Dict,
        sector_etf: str
    ) -> List[Dict]:
        """Build Slack block message layout."""
        
        blocks = []
        
        # Header
        blocks.append({
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"🚨 SGS ALERT: {symbol}",
                "emoji": True
            }
        })
        
        # Event details
        blocks.append({
            "type": "section",
            "fields": [
                {
                    "type": "mrkdwn",
                    "text": f"*Symbol:*\n{symbol}"
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Quarter:*\n{year} Q{quarter}"
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Sector ETF:*\n{sector_etf}"
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Alert Time:*\n{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                }
            ]
        })
        
        blocks.append({"type": "divider"})
        
        # Trigger reasons
        reasons_text = "\n".join([f"• {reason}" for reason in trigger_reasons])
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Trigger Reasons:*\n{reasons_text}"
            }
        })
        
        blocks.append({"type": "divider"})
        
        # Key SGS metrics
        demand = sgs_data.get('demand_trajectory', {})
        margin = sgs_data.get('margin_outlook', {})
        uncertainty = sgs_data.get('uncertainty_change', {})
        guidance = sgs_data.get('guidance_quality', {})
        narrative = sgs_data.get('narrative_shift', '')
        
        metrics_text = (
            f"*Demand:* {demand.get('classification', 'N/A')} "
            f"(conf: {demand.get('confidence', 0):.2f})\n"
            f"*Margins:* {margin.get('classification', 'N/A')} "
            f"(conf: {margin.get('confidence', 0):.2f})\n"
            f"*Uncertainty:* {uncertainty.get('direction', 'N/A')} "
            f"(conf: {uncertainty.get('confidence', 0):.2f})\n"
            f"*Guidance:* {guidance.get('explicit_change', 'N/A')} / "
            f"{guidance.get('implicit_shift', 'N/A')}\n"
            f"*Narrative:* {narrative}"
        )
        
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Key SGS Metrics:*\n{metrics_text}"
            }
        })
        
        # Rationale bullets
        rationale = sgs_data.get('rationale_bullets', [])
        if rationale:
            rationale_text = "\n".join([f"• {bullet}" for bullet in rationale])
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*LLM Rationale:*\n{rationale_text}"
                }
            })
        
        blocks.append({"type": "divider"})
        
        # Trade suggestion
        trade_text = (
            f"*Suggested Trade Structure:*\n"
            f"• Entry: T+1 close (next trading day after earnings)\n"
            f"• Exit: T+7 close (7 trading days later)\n"
            f"• Hedge: Short {sector_etf} (sector ETF)\n"
            f"• Optional Stop: Relative +4% vs hedge"
        )
        
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": trade_text
            }
        })
        
        # Footer
        blocks.append({
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": "_SGS Trader MVP | This is not investment advice_"
                }
            ]
        })
        
        return blocks
