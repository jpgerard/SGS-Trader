"""
Financial Modeling Prep (FMP) API client.
Handles earnings calendar, transcripts, and price data with retry logic.
"""

import requests
import hashlib
from datetime import datetime, date, timedelta
from typing import List, Dict, Optional, Any
from sgs.config import Config
from sgs.utils.logging import get_logger
from sgs.utils.retry import retry_with_backoff, is_retryable_http_error

logger = get_logger("fmp_client")


class FMPError(Exception):
    """Base exception for FMP API errors."""
    pass


class FMPClient:
    """Client for Financial Modeling Prep API."""
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize FMP client.
        
        Args:
            api_key: FMP API key (defaults to Config.FMP_API_KEY)
        """
        self.api_key = api_key or Config.FMP_API_KEY
        if not self.api_key:
            raise ValueError("FMP API key not provided")
        
        self.base_url = Config.FMP_BASE_URL
        self.timeout = 15  # seconds
        self.session = requests.Session()
    
    def _make_request(self, url: str, params: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Make an HTTP request to FMP API with retry logic.
        
        Args:
            url: Full URL to request
            params: Query parameters
        
        Returns:
            JSON response as dict
        
        Raises:
            FMPError: On API errors or HTTP errors
        """
        if params is None:
            params = {}
        
        # Add API key to all requests
        params['apikey'] = self.api_key
        
        @retry_with_backoff(
            max_attempts=3,
            initial_delay=1.0,
            backoff_factor=3.0,
            exceptions=(requests.exceptions.RequestException,)
        )
        def _request():
            try:
                response = self.session.get(url, params=params, timeout=self.timeout)
                
                # Check for retryable errors
                if is_retryable_http_error(response.status_code):
                    logger.warning(f"Retryable HTTP error {response.status_code}: {url}")
                    raise requests.exceptions.HTTPError(f"HTTP {response.status_code}")
                
                # Raise for other HTTP errors
                response.raise_for_status()
                
                # Parse JSON
                data = response.json()
                
                # FMP sometimes returns errors as JSON with "Error Message" key
                if isinstance(data, dict) and "Error Message" in data:
                    raise FMPError(f"FMP API error: {data['Error Message']}")
                
                return data
            
            except requests.exceptions.Timeout:
                logger.error(f"Request timeout: {url}")
                raise
            except requests.exceptions.RequestException as e:
                logger.error(f"Request failed: {url}, error: {e}")
                raise
        
        return _request()
    
    def get_earnings_calendar(
        self,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None
    ) -> List[Dict[str, Any]]:
        """
        Get earnings calendar with dual-endpoint fallback.
        
        Tries stable endpoint first, falls back to legacy endpoint with date range.
        
        Args:
            from_date: Start date (for legacy endpoint)
            to_date: End date (for legacy endpoint)
        
        Returns:
            List of earnings events
        """
        # Try stable endpoint first
        try:
            stable_url = f"{self.base_url}/stable/earnings-calendar"
            logger.debug(f"Attempting stable earnings calendar endpoint")
            
            data = self._make_request(stable_url)
            
            # Check if we got valid data
            if data and isinstance(data, list) and len(data) > 0:
                logger.info(f"Fetched {len(data)} earnings events from stable endpoint")
                return data
            else:
                logger.warning("Stable endpoint returned empty or invalid data, trying legacy")
        
        except Exception as e:
            logger.warning(f"Stable endpoint failed: {e}, trying legacy endpoint")
        
        # Fallback to legacy endpoint with date range
        if from_date is None:
            from_date = date.today() - timedelta(days=1)
        if to_date is None:
            to_date = date.today() + timedelta(days=14)
        
        legacy_url = f"{self.base_url}/api/v3/earning_calendar"
        params = {
            'from': from_date.strftime('%Y-%m-%d'),
            'to': to_date.strftime('%Y-%m-%d')
        }
        
        logger.debug(f"Attempting legacy earnings calendar endpoint: {from_date} to {to_date}")
        data = self._make_request(legacy_url, params)
        
        if isinstance(data, list):
            logger.info(f"Fetched {len(data)} earnings events from legacy endpoint")
            return data
        
        logger.warning("Both endpoints failed or returned no data")
        return []
    
    def get_latest_transcripts(self) -> List[Dict[str, Any]]:
        """
        Get latest earnings call transcripts.
        
        Returns:
            List of recently posted transcripts with symbol, year, quarter
        """
        url = f"{self.base_url}/stable/earning-call-transcript-latest"
        
        logger.debug("Fetching latest transcripts")
        data = self._make_request(url)
        
        if isinstance(data, list):
            logger.info(f"Fetched {len(data)} latest transcripts")
            return data
        
        return []
    
    def get_transcript(self, symbol: str, year: int, quarter: int) -> Optional[str]:
        """
        Get full earnings call transcript text.
        
        Args:
            symbol: Stock ticker
            year: Year (e.g., 2024)
            quarter: Quarter (1-4)
        
        Returns:
            Transcript text or None if not found
        """
        url = f"{self.base_url}/stable/earning-call-transcript"
        params = {
            'symbol': symbol,
            'year': year,
            'quarter': quarter
        }
        
        logger.debug(f"Fetching transcript: {symbol} {year} Q{quarter}")
        
        try:
            data = self._make_request(url, params)
            
            # FMP returns a list with single dict containing 'content' field
            if isinstance(data, list) and len(data) > 0:
                transcript = data[0].get('content', '')
                if transcript:
                    logger.info(f"Fetched transcript: {symbol} {year} Q{quarter} ({len(transcript)} chars)")
                    return transcript
            
            logger.warning(f"No transcript found: {symbol} {year} Q{quarter}")
            return None
        
        except Exception as e:
            logger.error(f"Failed to fetch transcript: {symbol} {year} Q{quarter}, error: {e}")
            return None
    
    def get_transcript_dates(self, symbol: str) -> List[Dict[str, Any]]:
        """
        Get available transcript dates for a symbol.
        
        Args:
            symbol: Stock ticker
        
        Returns:
            List of transcript metadata (year, quarter, date)
        """
        url = f"{self.base_url}/stable/earning-call-transcript-dates"
        params = {'symbol': symbol}
        
        logger.debug(f"Fetching transcript dates: {symbol}")
        
        try:
            data = self._make_request(url, params)
            
            if isinstance(data, list):
                logger.info(f"Fetched {len(data)} transcript dates for {symbol}")
                return data
            
            return []
        
        except Exception as e:
            logger.error(f"Failed to fetch transcript dates: {symbol}, error: {e}")
            return []
    
    def get_transcript_list(self) -> List[Dict[str, Any]]:
        """
        Get global list of all available transcripts.
        
        Returns:
            List of all transcript metadata
        """
        url = f"{self.base_url}/stable/earnings-transcript-list"
        
        logger.debug("Fetching global transcript list")
        data = self._make_request(url)
        
        if isinstance(data, list):
            logger.info(f"Fetched {len(data)} transcripts in global list")
            return data
        
        return []
    
    def get_daily_prices(
        self,
        symbol: str,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None
    ) -> List[Dict[str, Any]]:
        """
        Get daily historical prices.
        
        Args:
            symbol: Stock ticker
            from_date: Start date
            to_date: End date
        
        Returns:
            List of daily price records (date, open, high, low, close, volume)
        """
        url = f"{self.base_url}/api/v3/historical-price-full/{symbol}"
        params = {}
        
        if from_date:
            params['from'] = from_date.strftime('%Y-%m-%d')
        if to_date:
            params['to'] = to_date.strftime('%Y-%m-%d')
        
        logger.debug(f"Fetching daily prices: {symbol}")
        
        try:
            data = self._make_request(url, params)
            
            # FMP returns {"symbol": "AAPL", "historical": [...]}
            if isinstance(data, dict) and 'historical' in data:
                prices = data['historical']
                logger.info(f"Fetched {len(prices)} daily prices for {symbol}")
                return prices
            
            logger.warning(f"No price data found for {symbol}")
            return []
        
        except Exception as e:
            logger.error(f"Failed to fetch prices: {symbol}, error: {e}")
            return []
    
    @staticmethod
    def hash_transcript(text: str) -> str:
        """
        Generate SHA-256 hash of transcript text for change detection.
        
        Args:
            text: Transcript text
        
        Returns:
            Hex digest of SHA-256 hash
        """
        return hashlib.sha256(text.encode('utf-8')).hexdigest()
