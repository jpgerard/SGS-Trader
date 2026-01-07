"""
Structured logging setup for SGS Trader.
Provides correlation IDs and contextual logging.
"""

import logging
import sys
import uuid
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime

from sgs.config import Config


class CorrelationIdFilter(logging.Filter):
    """Add correlation ID to log records."""
    
    def __init__(self):
        super().__init__()
        self._correlation_id = None
    
    def set_correlation_id(self, correlation_id: str):
        """Set the correlation ID for this context."""
        self._correlation_id = correlation_id
    
    def filter(self, record):
        """Add correlation_id to record."""
        record.correlation_id = self._correlation_id or "none"
        return True


# Global correlation filter instance
correlation_filter = CorrelationIdFilter()


def setup_logging(name: str = "sgs", level: Optional[str] = None) -> logging.Logger:
    """
    Setup structured logging with console and file handlers.
    
    Args:
        name: Logger name
        level: Log level (DEBUG, INFO, WARNING, ERROR)
    
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    
    # Set log level
    log_level = level or Config.LOG_LEVEL
    logger.setLevel(getattr(logging, log_level.upper()))
    
    # Avoid duplicate handlers
    if logger.handlers:
        return logger
    
    # Create formatters
    console_format = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(correlation_id)s | %(name)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    file_format = logging.Formatter(
        '{"timestamp": "%(asctime)s", "level": "%(levelname)s", "correlation_id": "%(correlation_id)s", '
        '"logger": "%(name)s", "message": "%(message)s"}',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(console_format)
    console_handler.addFilter(correlation_filter)
    
    # File handler with rotation
    log_file = Config.LOG_DIR / f"sgs_{datetime.now().strftime('%Y%m%d')}.log"
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(file_format)
    file_handler.addFilter(correlation_filter)
    
    # Add handlers
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    
    return logger


def set_correlation_id(correlation_id: Optional[str] = None):
    """Set correlation ID for current context."""
    if correlation_id is None:
        correlation_id = str(uuid.uuid4())[:8]
    correlation_filter.set_correlation_id(correlation_id)
    return correlation_id


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance with the SGS configuration."""
    return logging.getLogger(f"sgs.{name}")


class LogContext:
    """Context manager for scoped correlation IDs."""
    
    def __init__(self, correlation_id: Optional[str] = None, **kwargs):
        self.correlation_id = correlation_id
        self.context = kwargs
        self.logger = get_logger("context")
    
    def __enter__(self):
        self.correlation_id = set_correlation_id(self.correlation_id)
        if self.context:
            self.logger.info(f"Starting operation", extra=self.context)
        return self.correlation_id
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self.logger.error(f"Operation failed: {exc_val}", extra=self.context)
        else:
            self.logger.info(f"Operation completed", extra=self.context)
        return False
