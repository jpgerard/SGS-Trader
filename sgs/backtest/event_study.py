"""
Event study backtesting engine.
Computes T+1 to T+7 excess returns for triggered SGS events.
"""

import pandas as pd
from datetime import date, timedelta
from typing import List, Dict, Optional, Tuple
from sqlalchemy.orm import Session
from sgs.database.models import SGSFeature, EarningsEvent, PriceDaily, TradeSim
from sgs.database.db import get_session
from sgs.api.price_provider import get_default_price_provider
from sgs.config import Config
from sgs.utils.logging import get_logger

logger = get_logger("event_study")


class EventStudyEngine:
    """Engine for computing event study returns on triggered SGS events."""
    
    def __init__(self, session: Optional[Session] = None):
        """
        Initialize event study engine.
        
        Args:
            session: Database session (creates new if not provided)
        """
        self.session = session or get_session()
        self.price_provider = get_default_price_provider()
        self.own_session = session is None
    
    def __del__(self):
        """Close session if we created it."""
        if self.own_session and self.session:
            self.session.close()
    
    def run_event_study(self) -> Dict:
        """
        Run event study on all triggered SGS features.
        
        Returns:
            Dict with statistics and results
        """
        logger.info("Starting event study analysis")
        
        # Get all triggered SGS features
        triggered_features = self.session.query(SGSFeature).filter(
            SGSFeature.trigger_flag == 1
        ).all()
        
        logger.info(f"Found {len(triggered_features)} triggered SGS events")
        
        if len(triggered_features) == 0:
            logger.warning("No triggered events to analyze")
            return {
                'count': 0,
                'trades': [],
                'statistics': {}
            }
        
        # Process each triggered event
        trades = []
        for feature in triggered_features:
            try:
                trade = self._process_event(feature)
                if trade:
                    trades.append(trade)
            except Exception as e:
                logger.error(
                    f"Failed to process event: {feature.symbol} {feature.year} Q{feature.quarter}, error: {e}"
                )
        
        logger.info(f"Successfully processed {len(trades)} trades")
        
        # Compute statistics
        stats = self._compute_statistics(trades)
        
        return {
            'count': len(trades),
            'trades': trades,
            'statistics': stats
        }
    
    def _process_event(self, feature: SGSFeature) -> Optional[Dict]:
        """
        Process single SGS event and compute returns.
        
        Args:
            feature: SGSFeature instance
        
        Returns:
            Trade dict or None if data insufficient
        """
        symbol = feature.symbol
        year = feature.year
        quarter = feature.quarter
        
        logger.debug(f"Processing event: {symbol} {year} Q{quarter}")
        
        # Find earnings event to get report date
        earnings_event = self.session.query(EarningsEvent).filter(
            EarningsEvent.symbol == symbol,
            EarningsEvent.report_date != None
        ).order_by(
            EarningsEvent.report_date.desc()
        ).first()
        
        if not earnings_event or not earnings_event.report_date:
            logger.warning(f"No earnings date found for {symbol} {year} Q{quarter}")
            return None
        
        report_date = earnings_event.report_date
        
        # Calculate entry and exit dates
        entry_date, exit_date = self._calculate_trade_dates(report_date)
        
        if not entry_date or not exit_date:
            logger.warning(f"Could not calculate valid trade dates for {symbol}")
            return None
        
        # Get sector ETF
        sector_etf = Config.get_sector_etf(symbol)
        
        # Fetch prices
        stock_prices = self._get_prices_for_dates(symbol, entry_date, exit_date)
        etf_prices = self._get_prices_for_dates(sector_etf, entry_date, exit_date)
        
        if not stock_prices or not etf_prices:
            logger.warning(f"Missing price data for {symbol} or {sector_etf}")
            return None
        
        entry_price = stock_prices.get(entry_date)
        exit_price = stock_prices.get(exit_date)
        entry_hedge_price = etf_prices.get(entry_date)
        exit_hedge_price = etf_prices.get(exit_date)
        
        if not all([entry_price, exit_price, entry_hedge_price, exit_hedge_price]):
            logger.warning(f"Missing price points for {symbol}")
            return None
        
        # Calculate returns
        stock_return = (exit_price - entry_price) / entry_price
        hedge_return = (exit_hedge_price - entry_hedge_price) / entry_hedge_price
        excess_return = stock_return - hedge_return
        
        logger.info(
            f"{symbol} {year} Q{quarter}: "
            f"stock={stock_return:.2%}, hedge={hedge_return:.2%}, excess={excess_return:.2%}"
        )
        
        # Store in database
        trade_sim = TradeSim(
            symbol=symbol,
            year=year,
            quarter=quarter,
            sector_etf=sector_etf,
            entry_date=entry_date,
            exit_date=exit_date,
            entry_price=entry_price,
            exit_price=exit_price,
            entry_hedge_price=entry_hedge_price,
            exit_hedge_price=exit_hedge_price,
            excess_return=excess_return
        )
        
        # Check if already exists
        existing = self.session.query(TradeSim).filter(
            TradeSim.symbol == symbol,
            TradeSim.year == year,
            TradeSim.quarter == quarter
        ).first()
        
        if existing:
            # Update existing
            existing.excess_return = excess_return
            existing.entry_date = entry_date
            existing.exit_date = exit_date
            existing.entry_price = entry_price
            existing.exit_price = exit_price
            existing.entry_hedge_price = entry_hedge_price
            existing.exit_hedge_price = exit_hedge_price
            logger.debug(f"Updated existing trade: {symbol} {year} Q{quarter}")
        else:
            # Insert new
            self.session.add(trade_sim)
            logger.debug(f"Inserted new trade: {symbol} {year} Q{quarter}")
        
        self.session.commit()
        
        return {
            'symbol': symbol,
            'year': year,
            'quarter': quarter,
            'entry_date': entry_date,
            'exit_date': exit_date,
            'excess_return': excess_return,
            'stock_return': stock_return,
            'hedge_return': hedge_return
        }
    
    def _calculate_trade_dates(self, report_date: date) -> Tuple[Optional[date], Optional[date]]:
        """
        Calculate T+1 entry and T+7 exit dates.
        
        Args:
            report_date: Earnings report date
        
        Returns:
            Tuple of (entry_date, exit_date) or (None, None) if invalid
        """
        try:
            # Use pandas for business day arithmetic
            report_dt = pd.Timestamp(report_date)
            
            # T+1: Next business day
            entry_dt = report_dt + pd.tseries.offsets.BDay(1)
            
            # T+7: 7 business days after entry
            exit_dt = entry_dt + pd.tseries.offsets.BDay(7)
            
            entry_date = entry_dt.date()
            exit_date = exit_dt.date()
            
            return (entry_date, exit_date)
        
        except Exception as e:
            logger.error(f"Error calculating trade dates from {report_date}: {e}")
            return (None, None)
    
    def _get_prices_for_dates(self, symbol: str, entry_date: date, exit_date: date) -> Dict[date, float]:
        """
        Get close prices for entry and exit dates.
        
        Args:
            symbol: Stock ticker
            entry_date: Entry date
            exit_date: Exit date
        
        Returns:
            Dict mapping date -> close price
        """
        # Query database first
        prices = self.session.query(PriceDaily).filter(
            PriceDaily.symbol == symbol,
            PriceDaily.date.in_([entry_date, exit_date])
        ).all()
        
        price_dict = {p.date: p.close for p in prices}
        
        # If missing data, try to fetch from API
        if len(price_dict) < 2:
            logger.debug(f"Fetching prices for {symbol} from API")
            
            from_date = entry_date - timedelta(days=5)  # Buffer for weekends
            to_date = exit_date + timedelta(days=5)
            
            api_prices = self.price_provider.get_daily_prices(symbol, from_date, to_date)
            
            # Store in database
            for price_record in api_prices:
                price_date = pd.to_datetime(price_record['date']).date()
                close_price = float(price_record['close'])
                
                # Upsert
                existing = self.session.query(PriceDaily).filter(
                    PriceDaily.symbol == symbol,
                    PriceDaily.date == price_date
                ).first()
                
                if existing:
                    existing.close = close_price
                else:
                    new_price = PriceDaily(
                        symbol=symbol,
                        date=price_date,
                        open=price_record.get('open'),
                        high=price_record.get('high'),
                        low=price_record.get('low'),
                        close=close_price,
                        volume=price_record.get('volume')
                    )
                    self.session.add(new_price)
                
                if price_date in [entry_date, exit_date]:
                    price_dict[price_date] = close_price
            
            self.session.commit()
        
        return price_dict
    
    def _compute_statistics(self, trades: List[Dict]) -> Dict:
        """
        Compute summary statistics on trades.
        
        Args:
            trades: List of trade dicts
        
        Returns:
            Statistics dict
        """
        if not trades:
            return {}
        
        excess_returns = [t['excess_return'] for t in trades]
        
        # Convert to Series for easier stats
        returns_series = pd.Series(excess_returns)
        
        stats = {
            'count': len(excess_returns),
            'mean': returns_series.mean(),
            'median': returns_series.median(),
            'std': returns_series.std(),
            'min': returns_series.min(),
            'max': returns_series.max(),
            'hit_rate': (returns_series > 0).sum() / len(returns_series),
            'percentile_10': returns_series.quantile(0.10),
            'percentile_25': returns_series.quantile(0.25),
            'percentile_75': returns_series.quantile(0.75),
            'percentile_90': returns_series.quantile(0.90)
        }
        
        logger.info(
            f"Event study statistics: count={stats['count']}, "
            f"mean={stats['mean']:.2%}, median={stats['median']:.2%}, "
            f"hit_rate={stats['hit_rate']:.2%}"
        )
        
        return stats
