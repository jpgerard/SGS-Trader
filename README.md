# SGS Trader - Semantic Guidance Shock Trading System

**MVP Version 0.1.0**

An automated system that monitors earnings call transcripts, detects semantic guidance shifts using LLM extraction, and generates trading signals based on deterministic trigger rules.

## Overview

SGS Trader identifies earnings calls where management's forward-looking language contradicts positive headlines, potentially indicating a hidden deterioration in business fundamentals. The system:

1. **Monitors** upcoming earnings and transcript availability (FMP API)
2. **Extracts** semantic features using GPT-4 (demand, margins, uncertainty, guidance quality)
3. **Triggers** alerts when specific conditions are met (contradiction + 2 of 5 secondary signals)
4. **Backtests** via event studies (T+1 to T+7 sector-hedged returns)

## Quick Start

### 1. Installation

```powershell
# Create virtual environment
python -m venv venv
.\venv\Scripts\Activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configuration

Copy `.env.example` to `.env` and fill in your API keys:

```bash
FMP_API_KEY=your_fmp_api_key_here
OPENAI_API_KEY=your_openai_api_key_here
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
```

Customize your universe in `config/universe.txt` (one ticker per line).

### 3. Initialize Database

```powershell
python -m sgs.cli init-db
```

### 4. Backfill Data

```powershell
python -m sgs.cli backfill
```

This fetches:
- Earnings calendar (yesterday to +14 days)
- Available transcripts for your universe

## Usage

### CLI Commands

#### Validate Configuration
```powershell
python -m sgs.cli validate-config
```

#### Backfill Transcripts
```powershell
python -m sgs.cli backfill
```

#### Poll for New Transcripts
```powershell
# AM window (07:00-10:00 ET)
python -m sgs.cli poll --window am

# PM window (16:00-20:00 ET)
python -m sgs.cli poll --window pm
```

#### Compute SGS for Specific Transcript
```powershell
python -m sgs.cli compute-sgs --symbol AAPL --year 2024 --quarter 4
```

#### Run Event Study Backtest
```powershell
python -m sgs.cli event-study
```

Generates report at `reports/latest.md` with statistics on triggered events.

## Architecture

### Directory Structure

```
SGS_Trader/
├── config/              # Universe & sector mappings
├── logs/                # Structured logs (auto-created)
├── reports/             # Event study outputs
├── sgs/
│   ├── api/            # FMP client + price provider
│   ├── llm/            # OpenAI client + prompt schemas
│   ├── triggers/       # Deterministic trigger rules
│   ├── alerts/         # Slack/email senders
│   ├── backtest/       # Event study engine
│   ├── jobs/           # Backfill, poll, compute_sgs
│   ├── database/       # SQLAlchemy models + DB init
│   └── utils/          # Logging, retry logic
├── cli.py              # Command-line interface
└── sgs.db              # SQLite database (auto-created)
```

### Data Flow

1. **Backfill Job** (nightly 02:00 ET):
   - Fetch earnings calendar
   - Download missing transcripts
   - Store in `transcripts` table

2. **Poll Job** (AM/PM windows):
   - Check `/transcript-latest` endpoint every 15 min
   - Detect new transcripts
   - Compute SGS → Trigger check → Alert if triggered

3. **SGS Computation**:
   - Load current + prior quarter transcripts
   - Call GPT-4 with exact prompt
   - Validate JSON schema (3 retry attempts)
   - Store in `sgs_features` table

4. **Trigger Evaluation**:
   - Primary: `contradiction_with_headlines == "yes"`
   - Secondary (need 2 of 5):
     1. Demand softening/deteriorating (conf ≥ 0.70)
     2. Margins under pressure (conf ≥ 0.65)
     3. Uncertainty increasing (conf ≥ 0.70)
     4. Guidance implicit shift = negative
     5. Narrative deterioration

5. **Alert**:
   - Send to Slack with rich formatting
   - Idempotent (unique constraint on symbol/year/quarter/channel)

6. **Event Study**:
   - Entry: T+1 close (next trading day after earnings)
   - Exit: T+7 close
   - Hedge: Short sector ETF
   - Store excess returns in `trades_sim`

## Database Schema

- **earnings_events**: Earnings calendar data
- **transcripts**: Raw transcript text with content hash
- **sgs_features**: LLM-extracted features + trigger flags
- **alerts**: Alert delivery log (idempotency)
- **prices_daily**: Daily OHLC data
- **trades_sim**: Event study results

## LLM Prompts

The system uses strict, deterministic prompts for GPT-4:

- **System Prompt**: Defines role as financial analyst (no trading advice)
- **User Prompt**: Provides current + prior transcripts, requests structured JSON
- **Schema**: 8 required fields (demand, margins, guidance, uncertainty, etc.)
- **Validation**: 3 retry attempts with repair prompts if invalid

See `sgs/llm/schemas.py` for exact prompts.

## Trigger Rules

**Primary Condition:**
- `contradiction_with_headlines == "yes"`

**Secondary Conditions (need ≥2):**
1. Demand classification in {softening, deteriorating} AND confidence ≥ 0.70
2. Margin classification = under_pressure AND confidence ≥ 0.65
3. Uncertainty direction = increase AND confidence ≥ 0.70
4. Guidance implicit_shift = negative
5. Narrative shift in {subtle_deterioration, clear_deterioration}

## Scheduling

### Windows Scheduler (Windows)

Create scheduled tasks for:

**Nightly Backfill** (02:00 ET):
```
Program: C:\path\to\venv\Scripts\python.exe
Arguments: -m sgs.cli backfill
Start in: C:\Users\jpg02\SGS_Trader
```

**AM Poll** (07:00 ET):
```
Program: C:\path\to\venv\Scripts\python.exe
Arguments: -m sgs.cli poll --window am
Start in: C:\Users\jpg02\SGS_Trader
```

**PM Poll** (16:00 ET):
```
Program: C:\path\to\venv\Scripts\python.exe
Arguments: -m sgs.cli poll --window pm
Start in: C:\Users\jpg02\SGS_Trader
```

### Alternative: Manual Scheduling

Run commands manually or use `apscheduler` (included in requirements.txt).

## Reliability Features

- **Retry Logic**: Exponential backoff (1s, 3s, 9s) on HTTP 429/5xx errors
- **Idempotency**: Unique constraints on transcripts, SGS features, alerts
- **Content Hashing**: Detects transcript updates via SHA-256
- **Graceful Failures**: LLM extraction failures don't crash system
- **Structured Logging**: Correlation IDs + JSON logs for debugging

## MVP Limitations

- No live trading execution
- No intraday pricing
- No options strategies
- Manual sector classification (CSV file)
- Single LLM provider (OpenAI)
- Email alerts stubbed

## Future Enhancements

- Automated sector classification via FMP fundamentals
- Multi-model LLM ensemble
- Intraday price updates
- Options overlay (vol analysis)
- Web dashboard for monitoring
- MAE (Max Adverse Excursion) tracking
- Portfolio-level exposure management

## Troubleshooting

### Database Issues
```powershell
# Reset database (WARNING: deletes all data)
python
>>> from sgs.database.db import reset_db
>>> reset_db()
```

### API Rate Limits
- FMP free tier: 250 calls/day
- Adjust polling frequency if needed
- Use backfill sparingly on large universes

### LLM Costs
- GPT-4-turbo: ~$0.01-0.03 per transcript pair
- For 100 earnings/quarter: ~$1-3
- Monitor OpenAI usage dashboard

### Logs
Check `logs/sgs_YYYYMMDD.log` for detailed debugging:
```powershell
Get-Content logs/sgs_*.log | Select-String "ERROR"
```

## Support

This is an MVP research system. Use for educational purposes only.

**Not financial advice. No warranty provided.**

## License

Proprietary - Internal Use Only
