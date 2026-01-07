"""
Polling job: Monitor for new transcripts and trigger alerts.
Runs in AM (07:00-10:00 ET) and PM (16:00-20:00 ET) windows.
"""

import json
import time
from datetime import datetime, timedelta
from typing import Set, Tuple
import pytz
from sgs.api.fmp_client import FMPClient
from sgs.database.db import get_session
from sgs.database.models import Transcript, Alert
from sgs.jobs.compute_sgs import compute_sgs_job
from sgs.alerts.slack import SlackAlertSender
from sgs.config import Config
from sgs.utils.logging import get_logger, LogContext

logger = get_logger("poll")


def poll_job(window: str = 'am'):
    """
    Poll for new transcripts during specified window.
    
    Args:
        window: 'am' (07:00-10:00 ET) or 'pm' (16:00-20:00 ET)
    """
    with LogContext(correlation_id=None, job="poll", window=window):
        logger.info(f"Starting polling job for {window.upper()} window")
        
        # Define window times
        tz = pytz.timezone(Config.TIMEZONE)
        
        if window == 'am':
            start_hour, end_hour = 7, 10
        elif window == 'pm':
            start_hour, end_hour = 16, 20
        else:
            logger.error(f"Invalid window: {window}. Use 'am' or 'pm'")
            return
        
        poll_interval = 15 * 60  # 15 minutes in seconds
        
        logger.info(f"Poll window: {start_hour}:00 - {end_hour}:00 ET, interval: {poll_interval}s")
        
        # Track seen transcripts to avoid reprocessing
        seen_keys: Set[Tuple[str, int, int]] = set()
        
        # Initialize clients
        fmp_client = FMPClient()
        
        try:
            slack_sender = SlackAlertSender()
        except ValueError:
            logger.warning("Slack webhook not configured, alerts will be logged only")
            slack_sender = None
        
        # Polling loop
        while True:
            now = datetime.now(tz)
            current_hour = now.hour
            
            # Check if still within window
            if not (start_hour <= current_hour < end_hour):
                logger.info(f"Outside of polling window (current hour: {current_hour}). Exiting.")
                break
            
            logger.info(f"Polling iteration at {now.strftime('%H:%M:%S')}")
            
            try:
                # Fetch latest transcripts
                latest_transcripts = fmp_client.get_latest_transcripts()
                
                logger.info(f"Found {len(latest_transcripts)} latest transcripts from API")
                
                # Process each new transcript
                new_count = 0
                for transcript_info in latest_transcripts:
                    symbol = transcript_info.get('symbol')
                    year = transcript_info.get('year')
                    quarter = transcript_info.get('quarter')
                    
                    if not all([symbol, year, quarter]):
                        continue
                    
                    transcript_key = (symbol, year, quarter)
                    
                    # Skip if already seen in this session
                    if transcript_key in seen_keys:
                        continue
                    
                    # Check if transcript exists in database
                    session = get_session()
                    existing = session.query(Transcript).filter(
                        Transcript.symbol == symbol,
                        Transcript.year == year,
                        Transcript.quarter == quarter
                    ).first()
                    session.close()
                    
                    if existing:
                        logger.debug(f"Transcript already in DB: {symbol} {year} Q{quarter}")
                        seen_keys.add(transcript_key)
                        continue
                    
                    # New transcript found!
                    logger.info(f"NEW TRANSCRIPT DETECTED: {symbol} {year} Q{quarter}")
                    new_count += 1
                    
                    # Fetch and store transcript
                    _fetch_and_store_transcript(fmp_client, symbol, year, quarter)
                    
                    # Compute SGS and send alert if triggered
                    _process_new_transcript(symbol, year, quarter, slack_sender)
                    
                    # Mark as seen
                    seen_keys.add(transcript_key)
                
                logger.info(f"Processed {new_count} new transcripts")
            
            except Exception as e:
                logger.error(f"Error during polling iteration: {e}")
            
            # Sleep until next poll
            logger.info(f"Sleeping for {poll_interval}s until next poll")
            time.sleep(poll_interval)
        
        logger.info("Polling job completed")


def _fetch_and_store_transcript(fmp_client: FMPClient, symbol: str, year: int, quarter: int):
    """Fetch transcript from API and store in database."""
    try:
        transcript_text = fmp_client.get_transcript(symbol, year, quarter)
        
        if not transcript_text:
            logger.warning(f"Failed to fetch transcript: {symbol} {year} Q{quarter}")
            return
        
        # Store in database
        session = get_session()
        
        content_hash = FMPClient.hash_transcript(transcript_text)
        
        transcript = Transcript(
            symbol=symbol,
            year=year,
            quarter=quarter,
            raw_text=transcript_text,
            content_hash=content_hash,
            source='FMP'
        )
        
        session.add(transcript)
        session.commit()
        session.close()
        
        logger.info(f"Stored transcript: {symbol} {year} Q{quarter}")
    
    except Exception as e:
        logger.error(f"Error fetching/storing transcript: {symbol} {year} Q{quarter}, error: {e}")


def _process_new_transcript(symbol: str, year: int, quarter: int, slack_sender: SlackAlertSender):
    """Compute SGS and send alert if triggered."""
    try:
        # Compute SGS
        result = compute_sgs_job(symbol, year, quarter)
        
        if not result:
            logger.info(f"SGS computation skipped or failed: {symbol} {year} Q{quarter}")
            return
        
        # Check if triggered
        if not result['trigger_flag']:
            logger.info(f"No trigger for {symbol} {year} Q{quarter}")
            return
        
        # Triggered! Send alert
        logger.info(f"TRIGGER ACTIVATED: {symbol} {year} Q{quarter}")
        
        # Check for duplicate alert
        session = get_session()
        existing_alert = session.query(Alert).filter(
            Alert.symbol == symbol,
            Alert.year == year,
            Alert.quarter == quarter,
            Alert.channel == 'slack'
        ).first()
        
        if existing_alert and existing_alert.delivered == 1:
            logger.info(f"Alert already sent for {symbol} {year} Q{quarter}, skipping")
            session.close()
            return
        
        # Get sector ETF
        sector_etf = Config.get_sector_etf(symbol)
        
        # Prepare alert record
        alert = Alert(
            symbol=symbol,
            year=year,
            quarter=quarter,
            channel='slack',
            payload_json=json.dumps(result['sgs_data']),
            delivered=0
        )
        
        if existing_alert:
            # Update existing
            existing_alert.payload_json = alert.payload_json
            existing_alert.delivered = 0
        else:
            # Insert new
            session.add(alert)
        
        session.commit()
        
        # Send Slack alert
        if slack_sender:
            try:
                slack_sender.send_alert(
                    symbol=symbol,
                    year=year,
                    quarter=quarter,
                    trigger_reasons=result['trigger_reasons'],
                    sgs_data=result['sgs_data'],
                    sector_etf=sector_etf
                )
                
                # Mark as delivered
                if existing_alert:
                    existing_alert.delivered = 1
                else:
                    alert.delivered = 1
                session.commit()
                
                logger.info(f"Alert sent successfully: {symbol} {year} Q{quarter}")
            
            except Exception as e:
                logger.error(f"Failed to send Slack alert: {symbol} {year} Q{quarter}, error: {e}")
        else:
            logger.warning(f"Slack sender not available, alert logged only: {symbol} {year} Q{quarter}")
        
        session.close()
    
    except Exception as e:
        logger.error(f"Error processing new transcript: {symbol} {year} Q{quarter}, error: {e}")


if __name__ == "__main__":
    import sys
    from sgs.utils.logging import setup_logging
    
    setup_logging()
    
    window = sys.argv[1] if len(sys.argv) > 1 else 'am'
    
    if window not in ['am', 'pm']:
        print("Usage: python -m sgs.jobs.poll [am|pm]")
        sys.exit(1)
    
    poll_job(window)
