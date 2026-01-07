"""
Abstract price provider interface.
Allows swapping price data sources without changing business logic.
"""

from abc import ABC, abstractmethod
from datetime import date
from typing import List, Dict, Any
from sgs.api.fmp_client import FMPClient


class PriceProvider(ABC):
    """Abstract interface for price data providers."""
    
    @abstractmethod
    def get_daily_prices(
        self,
        symbol: str,
        from_date: date,
        to_date: date
    ) -> List[Dict[str, Any]]:
        """
        Get daily price data.
        
        Args:
            symbol: Stock ticker
            from_date: Start date
            to_date: End date
        
        Returns:
            List of price records with at minimum: date, close
        """
        pass


class FMPPriceProvider(PriceProvider):
    """FMP implementation of price provider."""
    
    def __init__(self, fmp_client: FMPClient = None):
        """
        Initialize FMP price provider.
        
        Args:
            fmp_client: FMPClient instance (creates new if not provided)
        """
        self.fmp_client = fmp_client or FMPClient()
    
    def get_daily_prices(
        self,
        symbol: str,
        from_date: date,
        to_date: date
    ) -> List[Dict[str, Any]]:
        """Get daily prices from FMP."""
        return self.fmp_client.get_daily_prices(symbol, from_date, to_date)


# Default provider for MVP
def get_default_price_provider() -> PriceProvider:
    """Get the default price provider (FMP for MVP)."""
    return FMPPriceProvider()
