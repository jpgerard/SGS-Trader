"""
Abstract LLM client interface for SGS extraction.
Allows swapping LLM providers without changing business logic.
"""

from abc import ABC, abstractmethod
from typing import Dict, Optional


class LLMClient(ABC):
    """Abstract interface for LLM-based SGS extraction."""
    
    @abstractmethod
    def extract_sgs(
        self,
        current_transcript: str,
        prior_transcript: str,
        headline_context: Optional[str] = None
    ) -> Dict:
        """
        Extract SGS features from transcript pair.
        
        Args:
            current_transcript: Current quarter's transcript text
            prior_transcript: Prior quarter's transcript text
            headline_context: Optional beat/miss context
        
        Returns:
            Validated SGS JSON dict
        
        Raises:
            SGSExtractionError: If extraction fails after retries
        """
        pass
