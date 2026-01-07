"""
Retry utilities with exponential backoff for API calls.
"""

import time
import functools
from typing import Callable, Tuple, Type, Optional
from sgs.utils.logging import get_logger

logger = get_logger("retry")


def retry_with_backoff(
    max_attempts: int = 3,
    initial_delay: float = 1.0,
    backoff_factor: float = 3.0,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    on_retry: Optional[Callable] = None
):
    """
    Decorator to retry function calls with exponential backoff.
    
    Args:
        max_attempts: Maximum number of attempts (default: 3)
        initial_delay: Initial delay in seconds (default: 1.0)
        backoff_factor: Multiplier for delay on each retry (default: 3.0)
        exceptions: Tuple of exception types to catch and retry
        on_retry: Optional callback function called on each retry
    
    Example:
        @retry_with_backoff(max_attempts=3, initial_delay=1.0, backoff_factor=3.0)
        def fetch_data():
            # This will retry up to 3 times with delays: 1s, 3s, 9s
            return api.get("/data")
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            delay = initial_delay
            last_exception = None
            
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    
                    if attempt == max_attempts:
                        logger.error(
                            f"{func.__name__} failed after {max_attempts} attempts",
                            extra={"error": str(e)}
                        )
                        raise
                    
                    logger.warning(
                        f"{func.__name__} failed (attempt {attempt}/{max_attempts}), "
                        f"retrying in {delay}s: {str(e)}"
                    )
                    
                    if on_retry:
                        on_retry(attempt, e)
                    
                    time.sleep(delay)
                    delay *= backoff_factor
            
            # Should never reach here, but just in case
            raise last_exception
        
        return wrapper
    return decorator


def is_retryable_http_error(status_code: int) -> bool:
    """
    Determine if an HTTP status code should be retried.
    
    Args:
        status_code: HTTP status code
    
    Returns:
        True if the error is retryable (429, 5xx), False otherwise
    """
    # 429 = Too Many Requests (rate limit)
    # 5xx = Server errors
    return status_code == 429 or (500 <= status_code < 600)
