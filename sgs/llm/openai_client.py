"""
OpenAI implementation of LLM client for SGS extraction.
Uses GPT-4 with exact prompts and 3-attempt validation retry logic.
"""

import json
from typing import Dict, Optional
from openai import OpenAI
from sgs.config import Config
from sgs.llm.client import LLMClient
from sgs.llm.schemas import (
    SYSTEM_PROMPT,
    USER_PROMPT_TEMPLATE,
    REPAIR_PROMPT,
    validate_sgs_json,
    has_forbidden_content,
    SGSExtractionError
)
from sgs.utils.logging import get_logger

logger = get_logger("openai_client")


class OpenAIClient(LLMClient):
    """OpenAI GPT-4 implementation for SGS extraction."""
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gpt-4-turbo",
        temperature: float = 0.2
    ):
        """
        Initialize OpenAI client.
        
        Args:
            api_key: OpenAI API key (defaults to Config.OPENAI_API_KEY)
            model: Model name (default: gpt-4-turbo)
            temperature: Sampling temperature (default: 0.2 for deterministic)
        """
        self.api_key = api_key or Config.OPENAI_API_KEY
        if not self.api_key:
            raise ValueError("OpenAI API key not provided")
        
        self.model = model
        self.temperature = temperature
        self.client = OpenAI(api_key=self.api_key)
        
        logger.info(f"OpenAI client initialized with model: {model}")
    
    def extract_sgs(
        self,
        current_transcript: str,
        prior_transcript: str,
        headline_context: Optional[str] = None
    ) -> Dict:
        """
        Extract SGS features from transcript pair with 3-attempt validation.
        
        Args:
            current_transcript: Current quarter's transcript text
            prior_transcript: Prior quarter's transcript text  
            headline_context: Optional beat/miss context
        
        Returns:
            Validated SGS JSON dict
        
        Raises:
            SGSExtractionError: If extraction fails after 3 attempts
        """
        # Prepare user prompt
        user_prompt = USER_PROMPT_TEMPLATE.format(
            CURRENT_TRANSCRIPT_TEXT=current_transcript,
            PRIOR_TRANSCRIPT_TEXT=prior_transcript,
            HEADLINE_CONTEXT=headline_context or "Not provided"
        )
        
        # Track conversation for repair attempts
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt}
        ]
        
        last_error = None
        
        for attempt in range(1, 4):  # 3 attempts total
            try:
                logger.debug(f"SGS extraction attempt {attempt}/3")
                
                # Make API call
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=self.temperature,
                    response_format={"type": "json_object"}  # Force JSON mode
                )
                
                # Extract JSON content
                json_str = response.choices[0].message.content
                
                logger.debug(f"LLM response length: {len(json_str)} chars")
                
                # Check for forbidden content
                if has_forbidden_content(json_str):
                    raise SGSExtractionError("Output contains forbidden trading advice or price mentions")
                
                # Validate schema
                sgs_data = validate_sgs_json(json_str)
                
                # Success!
                logger.info(f"SGS extraction succeeded on attempt {attempt}")
                logger.debug(f"SGS data: {json.dumps(sgs_data, indent=2)}")
                
                return sgs_data
            
            except SGSExtractionError as e:
                last_error = e
                logger.warning(f"Attempt {attempt}/3 failed: {e}")
                
                if attempt < 3:
                    # Add repair instruction for retry
                    messages.append({"role": "assistant", "content": json_str if 'json_str' in locals() else "{}"})
                    messages.append({"role": "user", "content": REPAIR_PROMPT})
                    logger.debug("Adding repair prompt for retry")
                else:
                    # Final attempt failed
                    logger.error(f"SGS extraction failed after 3 attempts: {e}")
            
            except Exception as e:
                last_error = e
                logger.error(f"Unexpected error on attempt {attempt}/3: {e}")
                
                if attempt == 3:
                    break
        
        # All attempts failed
        raise SGSExtractionError(f"Failed to extract valid SGS after 3 attempts. Last error: {last_error}")
    
    def get_model_name(self) -> str:
        """Get the model name being used."""
        return self.model
