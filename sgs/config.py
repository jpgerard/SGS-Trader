"""
Configuration management for SGS Trader.
Loads environment variables and configuration files.
"""

import os
import json
from pathlib import Path
from typing import Dict, List
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class Config:
    """Central configuration class for SGS Trader."""
    
    # Project root directory
    ROOT_DIR = Path(__file__).parent.parent.resolve()
    
    # API Keys
    FMP_API_KEY = os.getenv("FMP_API_KEY")
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4-turbo")
    SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")
    
    # Database
    DB_PATH = os.getenv("DB_PATH", "sgs.db")
    DB_FULL_PATH = ROOT_DIR / DB_PATH
    
    # Timezone
    TIMEZONE = os.getenv("TIMEZONE", "America/New_York")
    
    # Logging
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    LOG_DIR = ROOT_DIR / "logs"
    
    # Config file paths
    CONFIG_DIR = ROOT_DIR / "config"
    UNIVERSE_FILE = CONFIG_DIR / "universe.txt"
    SECTOR_ETF_FILE = CONFIG_DIR / "sector_etf.json"
    SYMBOL_SECTOR_FILE = CONFIG_DIR / "symbol_sector.csv"
    
    # Reports directory
    REPORTS_DIR = ROOT_DIR / "reports"
    
    # FMP API endpoints
    FMP_BASE_URL = "https://financialmodelingprep.com"
    
    @classmethod
    def validate(cls) -> None:
        """Validate that required configuration is present."""
        errors = []
        
        if not cls.FMP_API_KEY:
            errors.append("FMP_API_KEY not set in .env")
        
        if not cls.OPENAI_API_KEY:
            errors.append("OPENAI_API_KEY not set in .env")
        
        # Slack is optional for MVP; warn at runtime in CLI instead
        
        if not cls.UNIVERSE_FILE.exists():
            errors.append(f"Universe file not found: {cls.UNIVERSE_FILE}")
        
        if not cls.SECTOR_ETF_FILE.exists():
            errors.append(f"Sector ETF mapping not found: {cls.SECTOR_ETF_FILE}")
        
        if errors:
            raise ValueError(f"Configuration errors:\n" + "\n".join(f"  - {e}" for e in errors))
    
    @classmethod
    def load_universe(cls) -> List[str]:
        """Load ticker symbols from universe.txt."""
        if not cls.UNIVERSE_FILE.exists():
            return []
        
        symbols = []
        with open(cls.UNIVERSE_FILE, 'r') as f:
            for line in f:
                line = line.strip()
                # Skip comments and empty lines
                if line and not line.startswith('#'):
                    symbols.append(line)
        
        return symbols
    
    @classmethod
    def load_sector_etf_mapping(cls) -> Dict[str, str]:
        """Load sector to ETF mapping from JSON file."""
        if not cls.SECTOR_ETF_FILE.exists():
            return {}
        
        with open(cls.SECTOR_ETF_FILE, 'r') as f:
            return json.load(f)
    
    @classmethod
    def load_symbol_sector_mapping(cls) -> Dict[str, str]:
        """Load symbol to sector mapping from CSV file."""
        if not cls.SYMBOL_SECTOR_FILE.exists():
            return {}
        
        mapping = {}
        with open(cls.SYMBOL_SECTOR_FILE, 'r') as f:
            # Skip header
            next(f)
            for line in f:
                line = line.strip()
                if line:
                    parts = line.split(',')
                    if len(parts) == 2:
                        symbol, sector = parts
                        mapping[symbol.strip()] = sector.strip()
        
        return mapping
    
    @classmethod
    def get_sector_etf(cls, symbol: str) -> str:
        """Get the sector ETF for a given symbol."""
        symbol_sector_map = cls.load_symbol_sector_mapping()
        sector_etf_map = cls.load_sector_etf_mapping()
        
        sector = symbol_sector_map.get(symbol)
        if not sector:
            return "SPY"  # Default to S&P 500 if sector unknown
        
        return sector_etf_map.get(sector, "SPY")
    
    @classmethod
    def ensure_directories(cls) -> None:
        """Ensure all required directories exist."""
        cls.LOG_DIR.mkdir(exist_ok=True)
        cls.REPORTS_DIR.mkdir(exist_ok=True)
        cls.CONFIG_DIR.mkdir(exist_ok=True)


# Ensure directories exist on import
Config.ensure_directories()
