"""
Backfill job: Load earnings calendar and transcripts for universe.
Runs nightly at 02:00 ET.
"""

from datetime import date, timedelta
from tqdm import tqdm
from sgs.api.fmp_client import FMPClient
from sgs.config import Config
from sgs.database.db import get_session
from sgs.database.models import EarningsEvent, Transcript
from sgs.utils.logging import get_logger, LogContext

logger = get_logger("backfill")


def backfill_job():
    """
    Backfill earnings calendar and transcripts for universe.
    
    Steps:
    1. Load universe symbols
    2. Fetch earnings calendar (yesterday to +14 days)
    3. Upsert to earnings_events table
    4. For each symbol in last 90 days of events:
       - Fetch transcript dates
       - Fetch missing transcripts
       - Store with content hash
    """
    with LogContext(correlation_id=None, job="backfill"):
        logger.info("Starting backfill job")
        
        # Load universe
        universe = Config.load_universe()
        logger.info(f"Loaded {len(universe)} symbols from universe")
        
        if not universe:
            logger.error("Universe is empty, aborting backfill")
            return
        
        # Initialize FMP client and database session
        fmp_client = FMPClient()
        session = get_session()
        
        try:
            # Step 1: Fetch earnings calendar
            from_date = date.today() - timedelta(days=1)
            to_date = date.today() + timedelta(days=14)
            
            logger.info(f"Fetching earnings calendar: {from_date} to {to_date}")
            calendar_events = fmp_client.get_earnings_calendar(from_date, to_date)
            
            # Filter to universe
            universe_set = set(universe)
            universe_events = [
                e for e in calendar_events
                if e.get('symbol') in universe_set
            ]
            
            logger.info(f"Found {len(universe_events)} earnings events for universe")
            
            # Upsert earnings events
            events_upserted = 0
            for event in universe_events:
                symbol = event.get('symbol')
                event_date = event.get('date')
                
                if not symbol or not event_date:
                    continue
                
                # Parse date
                try:
                    report_date = date.fromisoformat(event_date)
                except:
                    logger.warning(f"Invalid date format: {event_date} for {symbol}")
                    continue
                
                # Check if exists
                existing = session.query(EarningsEvent).filter(
                    EarningsEvent.symbol == symbol,
                    EarningsEvent.report_date == report_date
                ).first()
                
                if not existing:
                    earnings_event = EarningsEvent(
                        symbol=symbol,
                        report_date=report_date,
                        time_of_day=event.get('time'),
                        source='FMP'
                    )
                    session.add(earnings_event)
                    events_upserted += 1
            
            session.commit()
            logger.info(f"Upserted {events_upserted} new earnings events")
            
            # Step 2: Backfill transcripts for symbols with recent earnings
            logger.info("Backfilling transcripts for universe symbols")
            
            transcripts_fetched = 0
            for symbol in tqdm(universe, desc="Fetching transcripts"):
                try:
                    # Get transcript dates for this symbol
                    transcript_dates = fmp_client.get_transcript_dates(symbol)
                    
                    if not transcript_dates:
                        logger.debug(f"No transcript dates found for {symbol}")
                        continue
                    
                    # Fetch each missing transcript
                    for td in transcript_dates:
                        year = td.get('year')
                        quarter = td.get('quarter')
                        
                        if not year or not quarter:
                            continue
                        
                        # Check if already in database
                        existing_transcript = session.query(Transcript).filter(
                            Transcript.symbol == symbol,
                            Transcript.year == year,
                            Transcript.quarter == quarter
                        ).first()
                        
                        if existing_transcript:
                            logger.debug(f"Transcript already exists: {symbol} {year} Q{quarter}")
                            continue
                        
                        # Fetch transcript text
                        transcript_text = fmp_client.get_transcript(symbol, year, quarter)
                        
                        if not transcript_text:
                            logger.warning(f"Failed to fetch transcript: {symbol} {year} Q{quarter}")
                            continue
                        
                        # Compute content hash
                        content_hash = FMPClient.hash_transcript(transcript_text)
                        
                        # Store transcript
                        transcript = Transcript(
                            symbol=symbol,
                            year=year,
                            quarter=quarter,
                            transcript_date=td.get('date'),
                            raw_text=transcript_text,
                            content_hash=content_hash,
                            source='FMP'
                        )
                        session.add(transcript)
                        transcripts_fetched += 1
                        
                        logger.info(f"Fetched transcript: {symbol} {year} Q{quarter}")
                    
                    # Commit per symbol to avoid losing work on errors
                    session.commit()
                
                except Exception as e:
                    logger.error(f"Error backfilling transcripts for {symbol}: {e}")
                    session.rollback()
            
            logger.info(f"Backfill complete: {transcripts_fetched} new transcripts fetched")
        
        except Exception as e:
            logger.error(f"Backfill job failed: {e}")
            session.rollback()
            raise
        
        finally:
            session.close()
        
        logger.info("Backfill job completed successfully")


if __name__ == "__main__":
    from sgs.utils.logging import setup_logging
    setup_logging()
    backfill_job()
