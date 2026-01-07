"""
Compute SGS features for a specific transcript pair.
Called both manually via CLI and automatically during polling.
"""

import json
from typing import Optional
from sgs.api.fmp_client import FMPClient
from sgs.database.db import get_session
from sgs.database.models import Transcript, SGSFeature
from sgs.llm.openai_client import OpenAIClient
from sgs.llm.schemas import SGSExtractionError
from sgs.triggers.rules import evaluate_trigger
from sgs.utils.logging import get_logger, LogContext

logger = get_logger("compute_sgs")


def compute_sgs_job(symbol: str, year: int, quarter: int, headline_context: Optional[str] = None) -> Optional[dict]:
    """
    Compute SGS features for a specific symbol/year/quarter.
    
    Args:
        symbol: Stock ticker
        year: Year
        quarter: Quarter (1-4)
        headline_context: Optional beat/miss context
    
    Returns:
        SGS data dict if successful, None otherwise
    """
    with LogContext(correlation_id=None, job="compute_sgs", symbol=symbol, year=year, quarter=quarter):
        logger.info(f"Computing SGS for {symbol} {year} Q{quarter}")
        
        session = get_session()
        
        try:
            # Fetch current transcript
            current_transcript = session.query(Transcript).filter(
                Transcript.symbol == symbol,
                Transcript.year == year,
                Transcript.quarter == quarter
            ).first()
            
            if not current_transcript:
                logger.error(f"Current transcript not found: {symbol} {year} Q{quarter}")
                return None
            
            # Find prior transcript using database ordering
            prior_transcript = _get_prior_transcript(session, symbol, year, quarter)
            
            if not prior_transcript:
                logger.warning(
                    f"No prior transcript found for {symbol} {year} Q{quarter}. "
                    f"Cannot compute SGS without prior quarter."
                )
                return None
            
            prior_year, prior_quarter = prior_transcript.year, prior_transcript.quarter
            
            logger.info(
                f"Found transcript pair: current={year} Q{quarter}, prior={prior_year} Q{prior_quarter}"
            )
            
            # Run LLM extraction
            llm_client = OpenAIClient()
            
            try:
                sgs_data = llm_client.extract_sgs(
                    current_transcript=current_transcript.raw_text,
                    prior_transcript=prior_transcript.raw_text,
                    headline_context=headline_context
                )
                
                logger.info(f"Successfully extracted SGS features for {symbol} {year} Q{quarter}")
            
            except SGSExtractionError as e:
                logger.error(f"SGS extraction failed: {symbol} {year} Q{quarter}, error: {e}")
                return None
            
            # Evaluate trigger
            trigger_flag, trigger_reasons = evaluate_trigger(sgs_data)
            
            logger.info(
                f"Trigger evaluation: {symbol} {year} Q{quarter} -> "
                f"triggered={trigger_flag}, reasons={len(trigger_reasons)}"
            )
            
            # Store SGS features
            existing_sgs = session.query(SGSFeature).filter(
                SGSFeature.symbol == symbol,
                SGSFeature.year == year,
                SGSFeature.quarter == quarter
            ).first()
            
            llm_json_str = json.dumps(sgs_data)
            trigger_reasons_str = json.dumps(trigger_reasons)
            model_name = llm_client.get_model_name()
            
            if existing_sgs:
                # Update existing
                existing_sgs.prior_year = prior_year
                existing_sgs.prior_quarter = prior_quarter
                existing_sgs.llm_model = model_name
                existing_sgs.llm_json = llm_json_str
                existing_sgs.trigger_flag = 1 if trigger_flag else 0
                existing_sgs.trigger_reasons = trigger_reasons_str if trigger_flag else None
                logger.info(f"Updated existing SGS feature: {symbol} {year} Q{quarter}")
            else:
                # Insert new
                sgs_feature = SGSFeature(
                    symbol=symbol,
                    year=year,
                    quarter=quarter,
                    prior_year=prior_year,
                    prior_quarter=prior_quarter,
                    llm_model=model_name,
                    llm_json=llm_json_str,
                    trigger_flag=1 if trigger_flag else 0,
                    trigger_reasons=trigger_reasons_str if trigger_flag else None
                )
                session.add(sgs_feature)
                logger.info(f"Inserted new SGS feature: {symbol} {year} Q{quarter}")
            
            session.commit()
            
            return {
                'symbol': symbol,
                'year': year,
                'quarter': quarter,
                'sgs_data': sgs_data,
                'trigger_flag': trigger_flag,
                'trigger_reasons': trigger_reasons
            }
        
        except Exception as e:
            logger.error(f"Error computing SGS: {symbol} {year} Q{quarter}, error: {e}")
            session.rollback()
            raise
        
        finally:
            session.close()


def _get_prior_transcript(session, symbol: str, year: int, quarter: int):
    """
    Find the prior transcript using database ordering.
    
    Args:
        session: Database session
        symbol: Stock ticker
        year: Current year
        quarter: Current quarter (1-4)
    
    Returns:
        Prior Transcript object or None
    """
    current = session.query(Transcript).filter(
        Transcript.symbol == symbol,
        Transcript.year == year,
        Transcript.quarter == quarter
    ).first()
    
    if not current:
        return None
    
    # Prefer transcript_date ordering when available
    if current.transcript_date:
        return session.query(Transcript).filter(
            Transcript.symbol == symbol,
            Transcript.transcript_date != None,
            Transcript.transcript_date < current.transcript_date
        ).order_by(Transcript.transcript_date.desc()).first()
    
    # Fallback to (year, quarter) ordering
    return session.query(Transcript).filter(
        Transcript.symbol == symbol,
        (Transcript.year < year) | ((Transcript.year == year) & (Transcript.quarter < quarter))
    ).order_by(Transcript.year.desc(), Transcript.quarter.desc()).first()


if __name__ == "__main__":
    import sys
    from sgs.utils.logging import setup_logging
    
    setup_logging()
    
    if len(sys.argv) < 4:
        print("Usage: python -m sgs.jobs.compute_sgs SYMBOL YEAR QUARTER [HEADLINE_CONTEXT]")
        sys.exit(1)
    
    symbol = sys.argv[1]
    year = int(sys.argv[2])
    quarter = int(sys.argv[3])
    headline = sys.argv[4] if len(sys.argv) > 4 else None
    
    result = compute_sgs_job(symbol, year, quarter, headline)
    
    if result:
        print(f"\nSGS computed successfully!")
        print(f"Triggered: {result['trigger_flag']}")
        if result['trigger_flag']:
            print(f"Reasons: {result['trigger_reasons']}")
    else:
        print("\nFailed to compute SGS")
        sys.exit(1)
