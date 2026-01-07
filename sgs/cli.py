"""
Command-line interface for SGS Trader.
Entry point for all operations: backfill, poll, compute-sgs, event-study, init-db.
"""

import click
from sgs.utils.logging import setup_logging
from sgs.config import Config

# Setup logging on module import
setup_logging()


@click.group()
@click.version_option(version='0.1.0')
def cli():
    """
    SGS Trader - Semantic Guidance Shock Trading System
    
    MVP command-line interface for managing earnings transcripts,
    computing SGS signals, and running event studies.
    """
    pass


@cli.command()
def init_db():
    """Initialize database (create all tables)."""
    from sgs.database.db import init_db
    from sgs.utils.logging import get_logger
    
    logger = get_logger("cli")
    
    try:
        logger.info("Initializing database...")
        init_db()
        click.echo("✓ Database initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        click.echo(f"✗ Error: {e}", err=True)
        raise click.Abort()


@cli.command()
def backfill():
    """
    Backfill earnings calendar and transcripts.
    
    Fetches earnings events (yesterday to +14 days) and missing transcripts
    for all symbols in the universe.
    """
    from sgs.jobs.backfill import backfill_job
    from sgs.utils.logging import get_logger
    
    logger = get_logger("cli")
    
    try:
        logger.info("Starting backfill job...")
        click.echo("Running backfill job...")
        click.echo("This may take several minutes depending on universe size.\n")
        
        backfill_job()
        
        click.echo("\n✓ Backfill completed successfully")
    except Exception as e:
        logger.error(f"Backfill job failed: {e}")
        click.echo(f"\n✗ Backfill failed: {e}", err=True)
        raise click.Abort()


@cli.command()
@click.option('--days', default=730, type=int, help='Number of days of history to fetch (default: 730 = ~2 years)')
def backfill_prices(days):
    """
    Backfill price data for universe stocks and sector ETFs.
    
    Fetches daily price data from FMP for all symbols in universe
    plus all sector ETF tickers needed for hedging.
    """
    from datetime import date, timedelta
    from sgs.api.fmp_client import FMPClient
    from sgs.database.db import get_session
    from sgs.database.models import PriceDaily
    from sgs.config import Config
    from sgs.utils.logging import get_logger
    
    logger = get_logger("cli")
    
    try:
        click.echo(f"Backfilling {days} days of price data...\n")
        
        # Load universe symbols
        universe = Config.load_universe()
        
        # Get unique sector ETFs
        sector_etf_map = Config.load_sector_etf_mapping()
        sector_etfs = list(set(sector_etf_map.values()))
        
        # Combine all symbols
        all_symbols = set(universe + sector_etfs)
        
        click.echo(f"Symbols to fetch:")
        click.echo(f"  - Stocks: {len(universe)}")
        click.echo(f"  - Sector ETFs: {len(sector_etfs)}")
        click.echo(f"  - Total: {len(all_symbols)}\n")
        
        # Date range
        to_date = date.today()
        from_date = to_date - timedelta(days=days)
        
        click.echo(f"Date range: {from_date} to {to_date}\n")
        
        fmp_client = FMPClient()
        session = get_session()
        
        total_prices = 0
        failed_symbols = []
        
        for symbol in sorted(all_symbols):
            click.echo(f"Fetching {symbol}... ", nl=False)
            
            try:
                prices = fmp_client.get_daily_prices(symbol, from_date, to_date)
                
                if not prices:
                    click.echo(f"✗ No data")
                    failed_symbols.append(symbol)
                    continue
                
                # Store prices
                new_count = 0
                for price_record in prices:
                    import pandas as pd
                    price_date = pd.to_datetime(price_record['date']).date()
                    
                    # Check if exists
                    existing = session.query(PriceDaily).filter(
                        PriceDaily.symbol == symbol,
                        PriceDaily.date == price_date
                    ).first()
                    
                    if existing:
                        # Update
                        existing.open = price_record.get('open')
                        existing.high = price_record.get('high')
                        existing.low = price_record.get('low')
                        existing.close = price_record.get('close')
                        existing.volume = price_record.get('volume')
                    else:
                        # Insert
                        new_price = PriceDaily(
                            symbol=symbol,
                            date=price_date,
                            open=price_record.get('open'),
                            high=price_record.get('high'),
                            low=price_record.get('low'),
                            close=price_record.get('close'),
                            volume=price_record.get('volume')
                        )
                        session.add(new_price)
                        new_count += 1
                
                session.commit()
                total_prices += len(prices)
                
                click.echo(f"✓ {len(prices)} days ({new_count} new)")
            
            except Exception as e:
                logger.error(f"Failed to fetch prices for {symbol}: {e}")
                click.echo(f"✗ Error")
                failed_symbols.append(symbol)
                session.rollback()
        
        session.close()
        
        # Summary
        click.echo(f"\n{'='*60}")
        click.echo(f"Price Backfill Complete")
        click.echo(f"{'='*60}")
        click.echo(f"Symbols processed: {len(all_symbols)}")
        click.echo(f"Total price records: {total_prices}")
        click.echo(f"Failed symbols: {len(failed_symbols)}")
        if failed_symbols:
            click.echo(f"  {', '.join(failed_symbols)}")
        click.echo(f"{'='*60}")
    
    except Exception as e:
        logger.error(f"Price backfill failed: {e}")
        click.echo(f"\n✗ Error: {e}", err=True)
        raise click.Abort()


@cli.command()
@click.option(
    '--window',
    type=click.Choice(['am', 'pm'], case_sensitive=False),
    required=True,
    help='Polling window: am (07:00-10:00 ET) or pm (16:00-20:00 ET)'
)
def poll(window):
    """
    Poll for new transcripts and send alerts.
    
    Runs in specified time window, checking every 15 minutes for new transcripts.
    When a new transcript is detected, computes SGS and sends alerts if triggered.
    """
    from sgs.jobs.poll import poll_job
    from sgs.utils.logging import get_logger
    
    logger = get_logger("cli")
    
    try:
        logger.info(f"Starting poll job for {window.upper()} window...")
        click.echo(f"Starting {window.upper()} polling window...")
        click.echo("Checking for new transcripts every 15 minutes.\n")
        click.echo("Press Ctrl+C to stop.\n")
        
        poll_job(window.lower())
        
        click.echo("\n✓ Polling window completed")
    except KeyboardInterrupt:
        click.echo("\n\nPolling stopped by user")
    except Exception as e:
        logger.error(f"Poll job failed: {e}")
        click.echo(f"\n✗ Polling failed: {e}", err=True)
        raise click.Abort()


@cli.command()
@click.option('--limit', default=2000, type=int, help='Maximum number of transcripts to process')
@click.option('--workers', default=1, type=int, help='Number of parallel workers (keep at 1 for rate limiting)')
@click.option('--symbols-file', default=None, help='Filter to symbols from specific file (e.g., config/validation_universe.txt)')
@click.option('--recent-quarters', default=None, type=int, help='Only process last N quarters (e.g., 4 for last 4 quarters)')
def compute_sgs_batch(limit, workers, symbols_file, recent_quarters):
    """
    Batch compute SGS for all transcripts that don't have SGS features yet.
    
    Processes transcripts in order, skipping those that already have SGS
    or don't have a prior quarter transcript.
    """
    from sgs.database.db import get_session
    from sgs.database.models import Transcript, SGSFeature
    from sgs.jobs.compute_sgs import compute_sgs_job
    from sgs.utils.logging import get_logger
    from pathlib import Path
    from datetime import date
    
    logger = get_logger("cli")
    
    try:
        filter_desc = []
        if symbols_file:
            filter_desc.append(f"symbols from {symbols_file}")
        if recent_quarters:
            filter_desc.append(f"last {recent_quarters} quarters")
        
        filter_str = " AND ".join(filter_desc) if filter_desc else "all transcripts"
        click.echo(f"Starting batch SGS computation ({filter_str}, limit: {limit})...\n")
        
        # Load symbol filter if provided
        symbol_filter = None
        if symbols_file:
            path = Path(symbols_file)
            if not path.exists():
                click.echo(f"✗ Error: {symbols_file} not found", err=True)
                raise click.Abort()
            
            with open(path, 'r') as f:
                symbol_filter = set([line.strip() for line in f if line.strip() and not line.startswith('#')])
            
            click.echo(f"Loaded {len(symbol_filter)} symbols from {symbols_file}")
        
        # Calculate quarter filter if provided
        year_quarter_cutoff = None
        if recent_quarters:
            current_year = date.today().year
            current_quarter = (date.today().month - 1) // 3 + 1
            
            # Calculate cutoff (year, quarter) for last N quarters
            quarters_back = recent_quarters - 1
            cutoff_year = current_year - (quarters_back // 4)
            cutoff_quarter = current_quarter - (quarters_back % 4)
            
            if cutoff_quarter <= 0:
                cutoff_quarter += 4
                cutoff_year -= 1
            
            year_quarter_cutoff = (cutoff_year, cutoff_quarter)
            click.echo(f"Filtering to transcripts from {cutoff_year} Q{cutoff_quarter} onwards\n")
        
        session = get_session()
        
        # Build query with filters
        query = session.query(Transcript).order_by(
            Transcript.symbol,
            Transcript.year.desc(),
            Transcript.quarter.desc()
        )
        
        if symbol_filter:
            query = query.filter(Transcript.symbol.in_(symbol_filter))
        
        if year_quarter_cutoff:
            cutoff_year, cutoff_quarter = year_quarter_cutoff
            query = query.filter(
                (Transcript.year > cutoff_year) |
                ((Transcript.year == cutoff_year) & (Transcript.quarter >= cutoff_quarter))
            )
        
        all_transcripts = query.limit(limit).all()
        
        session.close()
        
        click.echo(f"Found {len(all_transcripts)} transcripts to check\n")
        
        processed_count = 0
        skipped_count = 0
        success_count = 0
        failed_count = 0
        
        for transcript in all_transcripts:
            symbol = transcript.symbol
            year = transcript.year
            quarter = transcript.quarter
            
            # Check if SGS already exists
            session = get_session()
            existing_sgs = session.query(SGSFeature).filter(
                SGSFeature.symbol == symbol,
                SGSFeature.year == year,
                SGSFeature.quarter == quarter
            ).first()
            session.close()
            
            if existing_sgs:
                logger.debug(f"Skipping {symbol} {year} Q{quarter} - SGS already exists")
                skipped_count += 1
                continue
            
            click.echo(f"Processing {symbol} {year} Q{quarter}...")
            
            # Try to compute SGS
            result = compute_sgs_job(symbol, year, quarter)
            
            if result:
                success_count += 1
                trigger_status = "TRIGGERED" if result['trigger_flag'] else "not triggered"
                click.echo(f"  ✓ Success - {trigger_status}")
            else:
                failed_count += 1
                click.echo(f"  ✗ Failed (likely missing prior quarter)")
            
            processed_count += 1
        
        # Summary
        click.echo(f"\n{'='*60}")
        click.echo(f"Batch SGS Computation Complete")
        click.echo(f"{'='*60}")
        click.echo(f"Total checked: {len(all_transcripts)}")
        click.echo(f"Skipped (already exists): {skipped_count}")
        click.echo(f"Processed: {processed_count}")
        click.echo(f"  - Successful: {success_count}")
        click.echo(f"  - Failed: {failed_count}")
        click.echo(f"{'='*60}")
    
    except Exception as e:
        logger.error(f"Batch compute-sgs failed: {e}")
        click.echo(f"\n✗ Error: {e}", err=True)
        raise click.Abort()


@cli.command()
@click.option('--symbol', required=True, help='Stock ticker symbol (e.g., AAPL)')
@click.option('--year', required=True, type=int, help='Year (e.g., 2024)')
@click.option('--quarter', required=True, type=click.IntRange(1, 4), help='Quarter (1-4)')
@click.option('--headline', default=None, help='Optional beat/miss context')
def compute_sgs(symbol, year, quarter, headline):
    """
    Compute SGS features for a specific transcript.
    
    Fetches current and prior quarter transcripts from database,
    runs LLM extraction, evaluates triggers, and stores results.
    """
    from sgs.jobs.compute_sgs import compute_sgs_job
    from sgs.utils.logging import get_logger
    
    logger = get_logger("cli")
    
    try:
        click.echo(f"Computing SGS for {symbol} {year} Q{quarter}...\n")
        
        result = compute_sgs_job(symbol, year, quarter, headline)
        
        if not result:
            click.echo(f"✗ Failed to compute SGS for {symbol} {year} Q{quarter}", err=True)
            click.echo("Check logs for details (missing prior quarter or extraction failed)")
            raise click.Abort()
        
        # Display results
        click.echo(f"✓ SGS computed successfully!\n")
        click.echo(f"Symbol: {symbol}")
        click.echo(f"Quarter: {year} Q{quarter}")
        click.echo(f"Triggered: {'YES' if result['trigger_flag'] else 'NO'}\n")
        
        if result['trigger_flag']:
            click.echo("Trigger Reasons:")
            for reason in result['trigger_reasons']:
                click.echo(f"  • {reason}")
            click.echo()
        
        # Show key metrics
        sgs_data = result['sgs_data']
        click.echo("Key Metrics:")
        click.echo(f"  Demand: {sgs_data['demand_trajectory']['classification']} "
                  f"(conf: {sgs_data['demand_trajectory']['confidence']:.2f})")
        click.echo(f"  Margins: {sgs_data['margin_outlook']['classification']} "
                  f"(conf: {sgs_data['margin_outlook']['confidence']:.2f})")
        click.echo(f"  Narrative: {sgs_data['narrative_shift']}")
        click.echo(f"  Contradiction: {sgs_data['contradiction_with_headlines']}")
    
    except Exception as e:
        logger.error(f"compute-sgs failed: {e}")
        click.echo(f"\n✗ Error: {e}", err=True)
        raise click.Abort()


@cli.command()
@click.option('--output', default='reports/latest.md', help='Output file path')
def event_study(output):
    """
    Run event study backtest on triggered SGS events.
    
    Computes T+1 to T+7 sector-hedged returns for all triggered events,
    calculates statistics, and generates a report.
    """
    from sgs.backtest.event_study import EventStudyEngine
    from sgs.utils.logging import get_logger
    from pathlib import Path
    
    logger = get_logger("cli")
    
    try:
        click.echo("Running event study analysis...\n")
        
        engine = EventStudyEngine()
        results = engine.run_event_study()
        
        if results['count'] == 0:
            click.echo("No triggered events found to analyze")
            return
        
        stats = results['statistics']
        
        # Display statistics
        click.echo(f"✓ Event Study Results\n")
        click.echo(f"Total Events: {stats['count']}")
        click.echo(f"Mean Excess Return: {stats['mean']:.2%}")
        click.echo(f"Median Excess Return: {stats['median']:.2%}")
        click.echo(f"Std Dev: {stats['std']:.2%}")
        click.echo(f"Hit Rate: {stats['hit_rate']:.1%}")
        click.echo(f"Min: {stats['min']:.2%}")
        click.echo(f"Max: {stats['max']:.2%}")
        click.echo(f"10th Percentile: {stats['percentile_10']:.2%}")
        click.echo(f"90th Percentile: {stats['percentile_90']:.2%}\n")
        
        # Generate markdown report
        report_path = Path(output)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(report_path, 'w') as f:
            f.write("# SGS Event Study Report\n\n")
            f.write(f"Generated: {click.utils.format_filename(str(report_path))}\n\n")
            f.write("## Summary Statistics\n\n")
            f.write(f"| Metric | Value |\n")
            f.write(f"|--------|-------|\n")
            f.write(f"| Count | {stats['count']} |\n")
            f.write(f"| Mean | {stats['mean']:.2%} |\n")
            f.write(f"| Median | {stats['median']:.2%} |\n")
            f.write(f"| Std Dev | {stats['std']:.2%} |\n")
            f.write(f"| Hit Rate | {stats['hit_rate']:.1%} |\n")
            f.write(f"| Min | {stats['min']:.2%} |\n")
            f.write(f"| Max | {stats['max']:.2%} |\n")
            f.write(f"| 10th %ile | {stats['percentile_10']:.2%} |\n")
            f.write(f"| 90th %ile | {stats['percentile_90']:.2%} |\n\n")
            
            f.write("## Individual Trades\n\n")
            f.write(f"| Symbol | Year | Quarter | Entry Date | Exit Date | Excess Return |\n")
            f.write(f"|--------|------|---------|------------|-----------|---------------|\n")
            for trade in results['trades']:
                f.write(f"| {trade['symbol']} | {trade['year']} | Q{trade['quarter']} | "
                       f"{trade['entry_date']} | {trade['exit_date']} | {trade['excess_return']:.2%} |\n")
        
        click.echo(f"✓ Report saved to: {report_path}")
    
    except Exception as e:
        logger.error(f"Event study failed: {e}")
        click.echo(f"\n✗ Error: {e}", err=True)
        raise click.Abort()


@cli.command()
@click.option('--symbol', default=None, help='Filter by symbol (optional)')
def list_transcripts(symbol):
    """List available transcripts in the database."""
    from sgs.database.db import get_session
    from sgs.database.models import Transcript
    from sgs.utils.logging import get_logger
    
    logger = get_logger("cli")
    session = get_session()
    
    try:
        query = session.query(Transcript)
        
        if symbol:
            query = query.filter(Transcript.symbol == symbol)
            click.echo(f"Transcripts for {symbol}:\n")
        else:
            click.echo("All available transcripts:\n")
        
        transcripts = query.order_by(
            Transcript.symbol, 
            Transcript.year.desc(), 
            Transcript.quarter.desc()
        ).all()
        
        if not transcripts:
            click.echo("No transcripts found in database.")
            click.echo("Run 'python -m sgs.cli backfill' to load transcripts.")
            return
        
        # Group by symbol
        from collections import defaultdict
        by_symbol = defaultdict(list)
        for t in transcripts:
            by_symbol[t.symbol].append(t)
        
        for sym in sorted(by_symbol.keys()):
            click.echo(f"\n{sym}:")
            for t in by_symbol[sym]:
                date_str = f" ({t.transcript_date})" if t.transcript_date else ""
                click.echo(f"  - {t.year} Q{t.quarter}{date_str}")
        
        click.echo(f"\nTotal: {len(transcripts)} transcripts across {len(by_symbol)} symbols")
    
    except Exception as e:
        logger.error(f"Failed to list transcripts: {e}")
        click.echo(f"\n✗ Error: {e}", err=True)
        raise click.Abort()
    
    finally:
        session.close()


@cli.command()
def validate_config():
    """Validate configuration and API keys."""
    from sgs.utils.logging import get_logger
    
    logger = get_logger("cli")
    
    click.echo("Validating configuration...\n")
    
    try:
        Config.validate()
        click.echo("✓ FMP API key: configured")
        click.echo("✓ OpenAI API key: configured")
        
        if Config.SLACK_WEBHOOK_URL:
            click.echo("✓ Slack webhook: configured")
        else:
            click.echo("⚠ Slack webhook: not configured (optional)")
        
        universe = Config.load_universe()
        click.echo(f"✓ Universe: {len(universe)} symbols loaded")
        
        sector_mapping = Config.load_symbol_sector_mapping()
        click.echo(f"✓ Sector mapping: {len(sector_mapping)} symbols")
        
        click.echo("\n✓ Configuration is valid")
    
    except ValueError as e:
        click.echo(f"\n✗ Configuration error: {e}", err=True)
        raise click.Abort()


if __name__ == '__main__':
    cli()
