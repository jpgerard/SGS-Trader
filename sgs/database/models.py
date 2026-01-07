"""
SQLAlchemy ORM models for SGS Trader database.
"""

from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Text, Float, DateTime, Date,
    UniqueConstraint, Index, create_engine
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

Base = declarative_base()


class EarningsEvent(Base):
    """Earnings calendar events."""
    __tablename__ = 'earnings_events'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(20), nullable=False, index=True)
    report_date = Column(Date, nullable=False, index=True)
    time_of_day = Column(String(20), nullable=True)  # 'bmo', 'amc', or None
    source = Column(String(50), nullable=False, default='FMP')
    ingested_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    # Index on (symbol, report_date) for fast lookups
    __table_args__ = (
        Index('ix_earnings_symbol_date', 'symbol', 'report_date'),
    )
    
    def __repr__(self):
        return f"<EarningsEvent(symbol={self.symbol}, date={self.report_date})>"


class Transcript(Base):
    """Earnings call transcripts."""
    __tablename__ = 'transcripts'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(20), nullable=False, index=True)
    year = Column(Integer, nullable=False)
    quarter = Column(Integer, nullable=False)
    transcript_date = Column(Date, nullable=True)
    raw_text = Column(Text, nullable=False)
    fetched_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    content_hash = Column(String(64), nullable=False)  # SHA-256 hash
    source = Column(String(50), nullable=False, default='FMP')
    
    # Unique constraint: one transcript per (symbol, year, quarter)
    __table_args__ = (
        UniqueConstraint('symbol', 'year', 'quarter', name='uq_transcript_symbol_year_quarter'),
        Index('ix_transcript_symbol_year_quarter', 'symbol', 'year', 'quarter'),
    )
    
    def __repr__(self):
        return f"<Transcript(symbol={self.symbol}, year={self.year}, quarter={self.quarter})>"


class SGSFeature(Base):
    """SGS features extracted from transcript pairs via LLM."""
    __tablename__ = 'sgs_features'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(20), nullable=False, index=True)
    year = Column(Integer, nullable=False)
    quarter = Column(Integer, nullable=False)
    prior_year = Column(Integer, nullable=False)
    prior_quarter = Column(Integer, nullable=False)
    llm_model = Column(String(100), nullable=False)  # e.g., 'gpt-4-turbo'
    llm_json = Column(Text, nullable=True)  # Exact JSON string from LLM
    trigger_flag = Column(Integer, nullable=False, default=0)  # 0=no, 1=yes
    trigger_reasons = Column(Text, nullable=True)  # JSON array of trigger reasons
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    # Unique constraint: one SGS per (symbol, year, quarter)
    __table_args__ = (
        UniqueConstraint('symbol', 'year', 'quarter', name='uq_sgs_symbol_year_quarter'),
        Index('ix_sgs_symbol_year_quarter', 'symbol', 'year', 'quarter'),
        Index('ix_sgs_trigger_flag', 'trigger_flag'),
    )
    
    def __repr__(self):
        return f"<SGSFeature(symbol={self.symbol}, year={self.year}, quarter={self.quarter}, trigger={self.trigger_flag})>"


class Alert(Base):
    """Alert delivery log (for idempotency)."""
    __tablename__ = 'alerts'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(20), nullable=False, index=True)
    year = Column(Integer, nullable=False)
    quarter = Column(Integer, nullable=False)
    alert_time = Column(DateTime, nullable=False, default=datetime.utcnow)
    channel = Column(String(50), nullable=False)  # 'slack', 'email', etc.
    payload_json = Column(Text, nullable=True)  # JSON of alert content
    delivered = Column(Integer, nullable=False, default=0)  # 0=failed, 1=delivered
    
    # Unique constraint: one alert per (symbol, year, quarter, channel)
    __table_args__ = (
        UniqueConstraint('symbol', 'year', 'quarter', 'channel', name='uq_alert_symbol_year_quarter_channel'),
        Index('ix_alert_symbol_year_quarter', 'symbol', 'year', 'quarter'),
    )
    
    def __repr__(self):
        return f"<Alert(symbol={self.symbol}, year={self.year}, quarter={self.quarter}, channel={self.channel})>"


class PriceDaily(Base):
    """Daily price data for stocks and ETFs."""
    __tablename__ = 'prices_daily'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(20), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)
    open = Column(Float, nullable=True)
    high = Column(Float, nullable=True)
    low = Column(Float, nullable=True)
    close = Column(Float, nullable=False)
    volume = Column(Float, nullable=True)
    
    # Unique constraint: one price per (symbol, date)
    __table_args__ = (
        UniqueConstraint('symbol', 'date', name='uq_price_symbol_date'),
        Index('ix_price_symbol_date', 'symbol', 'date'),
    )
    
    def __repr__(self):
        return f"<PriceDaily(symbol={self.symbol}, date={self.date}, close={self.close})>"


class TradeSim(Base):
    """Simulated trades for event study / backtest."""
    __tablename__ = 'trades_sim'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(20), nullable=False, index=True)
    year = Column(Integer, nullable=False)
    quarter = Column(Integer, nullable=False)
    sector_etf = Column(String(20), nullable=False)
    entry_date = Column(Date, nullable=False)
    exit_date = Column(Date, nullable=False)
    entry_price = Column(Float, nullable=True)
    exit_price = Column(Float, nullable=True)
    entry_hedge_price = Column(Float, nullable=True)
    exit_hedge_price = Column(Float, nullable=True)
    excess_return = Column(Float, nullable=False)
    mae = Column(Float, nullable=True)  # Max Adverse Excursion (optional)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    # Index for analysis queries
    __table_args__ = (
        Index('ix_trade_symbol_year_quarter', 'symbol', 'year', 'quarter'),
        Index('ix_trade_entry_date', 'entry_date'),
    )
    
    def __repr__(self):
        return f"<TradeSim(symbol={self.symbol}, year={self.year}, quarter={self.quarter}, excess_return={self.excess_return:.2%})>"
