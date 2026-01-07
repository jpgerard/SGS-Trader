"""
SGS JSON schema, prompts, and validation logic.
Implements the exact prompt specifications from the user.
"""

import json
import re
from typing import Dict, Any, List


class SGSExtractionError(Exception):
    """Raised when SGS extraction fails."""
    pass


# ============================================================================
# SYSTEM PROMPT (STATIC) - Fixed for all calls
# ============================================================================

SYSTEM_PROMPT = """You are a financial analyst specializing in earnings-call interpretation.

Your task is to extract structured, forward-looking business signals from earnings call transcripts and to identify semantic changes between quarters.

You do NOT provide trading advice.
You do NOT summarize earnings calls.
You do NOT speculate beyond the provided text.

You analyze management language only.
Analyst questions are secondary and should only be used if management explicitly confirms or denies something.

Your output MUST be valid JSON and MUST conform exactly to the provided schema.
No prose, no explanations, no markdown."""


# ============================================================================
# USER PROMPT TEMPLATE (DYNAMIC) - Filled programmatically
# ============================================================================

USER_PROMPT_TEMPLATE = """You are given two earnings call transcripts for the same company.

CURRENT QUARTER TRANSCRIPT:
<<<
{CURRENT_TRANSCRIPT_TEXT}
>>>

PRIOR QUARTER TRANSCRIPT:
<<<
{PRIOR_TRANSCRIPT_TEXT}
>>>

OPTIONAL CONTEXT (may be empty):
- Headline result vs expectations: {HEADLINE_CONTEXT}

Task:
Compare the CURRENT quarter to the PRIOR quarter.
Focus ONLY on forward-looking language from management.

Detect:
- changes in demand outlook
- changes in margin outlook
- changes in guidance quality (explicit or implicit)
- changes in uncertainty language
- shifts in time horizon emphasis (forward vs backward)
- overall narrative inflection

If evidence is mixed or weak, mark fields as "unclear" and reduce confidence.

Return ONLY valid JSON matching the schema below.

REQUIRED OUTPUT SCHEMA:
{{
  "demand_trajectory": {{
    "classification": "improving|stable|softening|deteriorating|unclear",
    "confidence": 0.0
  }},
  "margin_outlook": {{
    "classification": "improving|stable|under_pressure|unclear",
    "drivers": [],
    "confidence": 0.0
  }},
  "guidance_quality": {{
    "explicit_change": "raised|reaffirmed|lowered|not_given|unclear",
    "implicit_shift": "positive|neutral|negative|unclear"
  }},
  "uncertainty_change": {{
    "direction": "increase|no_change|decrease|unclear",
    "confidence": 0.0
  }},
  "temporal_focus_shift": {{
    "direction": "more_forward|no_change|less_forward|unclear",
    "confidence": 0.0
  }},
  "narrative_shift": "same|subtle_deterioration|clear_deterioration|subtle_improvement|clear_improvement",
  "contradiction_with_headlines": "yes|no|ambiguous",
  "rationale_bullets": []
}}

Field rules:
- confidence must be a float in [0.0, 1.0]
- rationale_bullets: max 5 items, each ≤ 140 characters
- each bullet must cite specific language patterns, not opinions
- If uncertain → use "unclear" and lower confidence
- Never infer numbers, growth rates, or guidance not stated"""


# ============================================================================
# REPAIR PROMPT - Used on retry attempts
# ============================================================================

REPAIR_PROMPT = """Your previous response was invalid.

Fix the output to be valid JSON matching the schema exactly.
Do not add or remove fields.
Do not include explanations.
Return JSON only."""


# ============================================================================
# VALIDATION LOGIC
# ============================================================================

# Required schema keys
REQUIRED_KEYS = {
    'demand_trajectory', 'margin_outlook', 'guidance_quality',
    'uncertainty_change', 'temporal_focus_shift', 'narrative_shift',
    'contradiction_with_headlines', 'rationale_bullets'
}

# Valid enum values for each field
VALID_ENUMS = {
    'demand_trajectory.classification': ['improving', 'stable', 'softening', 'deteriorating', 'unclear'],
    'margin_outlook.classification': ['improving', 'stable', 'under_pressure', 'unclear'],
    'guidance_quality.explicit_change': ['raised', 'reaffirmed', 'lowered', 'not_given', 'unclear'],
    'guidance_quality.implicit_shift': ['positive', 'neutral', 'negative', 'unclear'],
    'uncertainty_change.direction': ['increase', 'no_change', 'decrease', 'unclear'],
    'temporal_focus_shift.direction': ['more_forward', 'no_change', 'less_forward', 'unclear'],
    'narrative_shift': ['same', 'subtle_deterioration', 'clear_deterioration', 'subtle_improvement', 'clear_improvement'],
    'contradiction_with_headlines': ['yes', 'no', 'ambiguous']
}

# Forbidden patterns (trading advice, price mentions, etc.)
# Only check for explicit buy/sell recommendations, not descriptive words
FORBIDDEN_PATTERNS = [
    r'\b(strong\s+buy|strong\s+sell)\b',
    r'\b(recommend|suggest|advise)\b.*\b(buy|sell)\b',
    r'\btarget\s+price\b',
]


def validate_sgs_json(json_str: str) -> Dict[str, Any]:
    """
    Validate SGS JSON string against schema.
    
    Args:
        json_str: JSON string from LLM
    
    Returns:
        Validated dict
    
    Raises:
        SGSExtractionError: If validation fails
    """
    # Parse JSON
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        raise SGSExtractionError(f"Invalid JSON: {e}")
    
    if not isinstance(data, dict):
        raise SGSExtractionError("JSON must be an object/dict")
    
    # Check required top-level keys
    missing_keys = REQUIRED_KEYS - set(data.keys())
    if missing_keys:
        raise SGSExtractionError(f"Missing required keys: {missing_keys}")
    
    # Validate demand_trajectory
    if not isinstance(data['demand_trajectory'], dict):
        raise SGSExtractionError("demand_trajectory must be an object")
    if 'classification' not in data['demand_trajectory'] or 'confidence' not in data['demand_trajectory']:
        raise SGSExtractionError("demand_trajectory missing classification or confidence")
    if data['demand_trajectory']['classification'] not in VALID_ENUMS['demand_trajectory.classification']:
        raise SGSExtractionError(f"Invalid demand_trajectory.classification: {data['demand_trajectory']['classification']}")
    if not isinstance(data['demand_trajectory']['confidence'], (int, float)):
        raise SGSExtractionError("demand_trajectory.confidence must be a number")
    if not (0.0 <= data['demand_trajectory']['confidence'] <= 1.0):
        raise SGSExtractionError(f"demand_trajectory.confidence must be in [0, 1]: {data['demand_trajectory']['confidence']}")
    
    # Validate margin_outlook
    if not isinstance(data['margin_outlook'], dict):
        raise SGSExtractionError("margin_outlook must be an object")
    if 'classification' not in data['margin_outlook'] or 'drivers' not in data['margin_outlook'] or 'confidence' not in data['margin_outlook']:
        raise SGSExtractionError("margin_outlook missing classification, drivers, or confidence")
    if data['margin_outlook']['classification'] not in VALID_ENUMS['margin_outlook.classification']:
        raise SGSExtractionError(f"Invalid margin_outlook.classification: {data['margin_outlook']['classification']}")
    if not isinstance(data['margin_outlook']['drivers'], list):
        raise SGSExtractionError("margin_outlook.drivers must be a list")
    if not isinstance(data['margin_outlook']['confidence'], (int, float)):
        raise SGSExtractionError("margin_outlook.confidence must be a number")
    if not (0.0 <= data['margin_outlook']['confidence'] <= 1.0):
        raise SGSExtractionError(f"margin_outlook.confidence must be in [0, 1]: {data['margin_outlook']['confidence']}")
    
    # Validate guidance_quality
    if not isinstance(data['guidance_quality'], dict):
        raise SGSExtractionError("guidance_quality must be an object")
    if 'explicit_change' not in data['guidance_quality'] or 'implicit_shift' not in data['guidance_quality']:
        raise SGSExtractionError("guidance_quality missing explicit_change or implicit_shift")
    if data['guidance_quality']['explicit_change'] not in VALID_ENUMS['guidance_quality.explicit_change']:
        raise SGSExtractionError(f"Invalid guidance_quality.explicit_change: {data['guidance_quality']['explicit_change']}")
    if data['guidance_quality']['implicit_shift'] not in VALID_ENUMS['guidance_quality.implicit_shift']:
        raise SGSExtractionError(f"Invalid guidance_quality.implicit_shift: {data['guidance_quality']['implicit_shift']}")
    
    # Validate uncertainty_change
    if not isinstance(data['uncertainty_change'], dict):
        raise SGSExtractionError("uncertainty_change must be an object")
    if 'direction' not in data['uncertainty_change'] or 'confidence' not in data['uncertainty_change']:
        raise SGSExtractionError("uncertainty_change missing direction or confidence")
    if data['uncertainty_change']['direction'] not in VALID_ENUMS['uncertainty_change.direction']:
        raise SGSExtractionError(f"Invalid uncertainty_change.direction: {data['uncertainty_change']['direction']}")
    if not isinstance(data['uncertainty_change']['confidence'], (int, float)):
        raise SGSExtractionError("uncertainty_change.confidence must be a number")
    if not (0.0 <= data['uncertainty_change']['confidence'] <= 1.0):
        raise SGSExtractionError(f"uncertainty_change.confidence must be in [0, 1]: {data['uncertainty_change']['confidence']}")
    
    # Validate temporal_focus_shift
    if not isinstance(data['temporal_focus_shift'], dict):
        raise SGSExtractionError("temporal_focus_shift must be an object")
    if 'direction' not in data['temporal_focus_shift'] or 'confidence' not in data['temporal_focus_shift']:
        raise SGSExtractionError("temporal_focus_shift missing direction or confidence")
    if data['temporal_focus_shift']['direction'] not in VALID_ENUMS['temporal_focus_shift.direction']:
        raise SGSExtractionError(f"Invalid temporal_focus_shift.direction: {data['temporal_focus_shift']['direction']}")
    if not isinstance(data['temporal_focus_shift']['confidence'], (int, float)):
        raise SGSExtractionError("temporal_focus_shift.confidence must be a number")
    if not (0.0 <= data['temporal_focus_shift']['confidence'] <= 1.0):
        raise SGSExtractionError(f"temporal_focus_shift.confidence must be in [0, 1]: {data['temporal_focus_shift']['confidence']}")
    
    # Validate narrative_shift
    if data['narrative_shift'] not in VALID_ENUMS['narrative_shift']:
        raise SGSExtractionError(f"Invalid narrative_shift: {data['narrative_shift']}")
    
    # Validate contradiction_with_headlines
    if data['contradiction_with_headlines'] not in VALID_ENUMS['contradiction_with_headlines']:
        raise SGSExtractionError(f"Invalid contradiction_with_headlines: {data['contradiction_with_headlines']}")
    
    # Validate rationale_bullets
    if not isinstance(data['rationale_bullets'], list):
        raise SGSExtractionError("rationale_bullets must be a list")
    if len(data['rationale_bullets']) > 5:
        raise SGSExtractionError(f"rationale_bullets must have at most 5 items, got {len(data['rationale_bullets'])}")
    for i, bullet in enumerate(data['rationale_bullets']):
        if not isinstance(bullet, str):
            raise SGSExtractionError(f"rationale_bullets[{i}] must be a string")
        if len(bullet) > 140:
            raise SGSExtractionError(f"rationale_bullets[{i}] exceeds 140 characters: {len(bullet)}")
    
    return data


def has_forbidden_content(json_str: str) -> bool:
    """
    Check if JSON contains forbidden trading advice or price mentions.
    
    Args:
        json_str: JSON string from LLM
    
    Returns:
        True if forbidden content detected
    """
    json_lower = json_str.lower()
    
    for pattern in FORBIDDEN_PATTERNS:
        if re.search(pattern, json_lower, re.IGNORECASE):
            return True
    
    return False
