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
