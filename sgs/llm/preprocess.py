"""
Transcript preprocessing and token budgeting.
Cleans transcripts and truncates to fit OpenAI token limits.
"""

import re
from typing import Optional
from sgs.config import Config
from sgs.utils.logging import get_logger

logger = get_logger("preprocess")


def clean_transcript(text: str) -> str:
    """
    Remove common headers, footers, and boilerplate from transcript.
    
    Args:
        text: Raw transcript text
    
    Returns:
        Cleaned transcript text
    """
    if not text:
        return ""
    
    # Remove common transcript headers/footers
    patterns_to_remove = [
        r'(?i)^.*?Earnings\s+Call\s+Transcript.*?$',  # Header line
        r'(?i)Copyright.*?All\s+rights\s+reserved.*?$',  # Copyright
        r'(?i)This\s+transcript.*?informational\s+purposes.*?$',  # Disclaimers
        r'(?i)Forward[- ]looking\s+statements.*?(?=\n\n|\Z)',  # Forward-looking disclaimer
        r'^\s*={3,}\s*$',  # Separator lines
        r'^\s*-{3,}\s*$',  # Dash separators
        r'(?i)^Operator\s*$',  # Standalone "Operator" lines
        r'\[.*?\]',  # Stage directions like [pause], [applause]
    ]
    
    cleaned = text
    for pattern in patterns_to_remove:
        cleaned = re.sub(pattern, '', cleaned, flags=re.MULTILINE)
    
    # Normalize whitespace
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)  # Max 2 newlines
    cleaned = re.sub(r'[ \t]+', ' ', cleaned)  # Normalize spaces
    cleaned = cleaned.strip()
    
    return cleaned


def extract_management_sections(text: str, include_qa: bool = False) -> str:
    """
    Extract management sections from transcript, optionally including Q&A.
    
    Transcripts typically have:
    1. Prepared remarks (management)
    2. Q&A session (analysts + management)
    
    For SGS analysis, we primarily want management language.
    
    Args:
        text: Cleaned transcript text
        include_qa: If True, include Q&A session; if False, only prepared remarks
    
    Returns:
        Extracted text
    """
    if not text:
        return ""
    
    # Maximum chars per transcript (hard cap)
    MAX_CHARS = 40000
    
    # Find Q&A section start with multiple markers
    qa_patterns = [
        r'(?i)Question[- ]and[- ]Answer\s+Session',
        r'(?i)Q&A\s+Session',
        r'(?i)Questions?\s+and\s+Answers?',
        r'(?i)Operator.*?(?:first question|questions?|Q&A)',
        r'(?i)We\s+will\s+now\s+begin\s+the\s+question',
        r'(?i)Now\s+I\s+would\s+like\s+to\s+turn\s+the.*?questions?',
    ]
    
    qa_start = None
    for pattern in qa_patterns:
        match = re.search(pattern, text)
        if match:
            qa_start = match.start()
            break
    
    if qa_start is None:
        # No Q&A section found - take first MAX_CHARS
        if len(text) > MAX_CHARS:
            logger.debug(f"No Q&A found, truncating to {MAX_CHARS} chars")
            return text[:MAX_CHARS].strip()
        return text
    
    if include_qa:
        # Return everything (with cap)
        if len(text) > MAX_CHARS:
            return text[:MAX_CHARS].strip()
        return text
    else:
        # Return only prepared remarks (before Q&A)
        prepared_remarks = text[:qa_start].strip()
        
        # If prepared remarks are too short, take first MAX_CHARS as fallback
        MIN_PREPARED_REMARKS = 2000
        if len(prepared_remarks) < MIN_PREPARED_REMARKS:
            logger.warning(
                f"Prepared remarks too short ({len(prepared_remarks)} chars), "
                f"using first {MAX_CHARS} chars as fallback"
            )
            return text[:MAX_CHARS].strip()
        
        # Apply hard cap even to prepared remarks
        if len(prepared_remarks) > MAX_CHARS:
            return prepared_remarks[:MAX_CHARS].strip()
        
        return prepared_remarks


def truncate_to_token_budget(text: str, max_tokens: int = 9000) -> str:
    """
    Truncate text to fit within token budget.
    
    Uses character-based approximation: ~4 chars per token (conservative).
    For more accurate budgeting, could use tiktoken library.
    
    Args:
        text: Text to truncate
        max_tokens: Maximum tokens allowed
    
    Returns:
        Truncated text
    """
    if not text:
        return ""
    
    # Conservative estimate: 4 characters per token
    chars_per_token = 4
    max_chars = max_tokens * chars_per_token
    
    if len(text) <= max_chars:
        return text
    
    # Truncate and add indicator
    truncated = text[:max_chars - 100]  # Leave room for ellipsis message
    
    # Try to truncate at sentence boundary
    last_period = truncated.rfind('.')
    last_newline = truncated.rfind('\n')
    boundary = max(last_period, last_newline)
    
    if boundary > max_chars * 0.9:  # Only use boundary if we're keeping >90%
        truncated = truncated[:boundary + 1]
    
    truncated += "\n\n[TRANSCRIPT TRUNCATED TO FIT TOKEN BUDGET]"
    
    logger.debug(f"Truncated transcript from {len(text)} to {len(truncated)} chars (~{len(truncated) // chars_per_token} tokens)")
    
    return truncated


def preprocess_transcript(text: str, max_tokens: Optional[int] = None, include_qa: Optional[bool] = None) -> str:
    """
    Full preprocessing pipeline for a transcript.
    
    Args:
        text: Raw transcript text
        max_tokens: Maximum tokens (uses config default if None)
        include_qa: Include Q&A section (uses config default if None)
    
    Returns:
        Cleaned, extracted, and truncated transcript
    """
    if max_tokens is None:
        max_tokens = Config.MAX_TOKENS_PER_TRANSCRIPT
    
    if include_qa is None:
        include_qa = Config.INCLUDE_QA
    
    # Step 1: Clean
    cleaned = clean_transcript(text)
    
    # Step 2: Extract management sections
    extracted = extract_management_sections(cleaned, include_qa=include_qa)
    
    # Step 3: Truncate to budget
    final = truncate_to_token_budget(extracted, max_tokens=max_tokens)
    
    return final
