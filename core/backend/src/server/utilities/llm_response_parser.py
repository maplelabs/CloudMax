"""
Utility functions for parsing LLM responses.

This module provides helper functions to extract and parse structured data
from LLM responses that may be wrapped in markdown code blocks or other formats.
"""

import json
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def extract_json_from_markdown(content: str) -> str:
    """
    Extract JSON content from LLM response that may be wrapped in markdown code blocks.
    
    LLMs often return JSON wrapped in markdown code blocks like:
    ```json
    {"key": "value"}
    ```
    
    This function extracts the JSON content from such blocks.
    
    Args:
        content: Raw LLM response content (string)
        
    Returns:
        Cleaned JSON string without markdown code block wrappers
        
    Examples:
        >>> extract_json_from_markdown('```json\\n{"key": "value"}\\n```')
        '{"key": "value"}'
        
        >>> extract_json_from_markdown('```\\n{"key": "value"}\\n```')
        '{"key": "value"}'
        
        >>> extract_json_from_markdown('{"key": "value"}')
        '{"key": "value"}'
    """
    content = content.strip()
    
    # Extract from ```json blocks
    if "```json" in content:
        return content.split("```json")[1].split("```")[0].strip()
    
    # Extract from generic ``` blocks
    elif "```" in content:
        return content.split("```")[1].split("```")[0].strip()
    
    # Return as-is if no code blocks
    return content


def parse_llm_json_response(content: str, default: Optional[Any] = None) -> Any:
    """
    Parse JSON from LLM response, handling markdown code blocks.
    
    This is a convenience function that combines extract_json_from_markdown()
    and json.loads() with error handling.
    
    Args:
        content: Raw LLM response content
        default: Default value to return if parsing fails (default: None)
        
    Returns:
        Parsed JSON object (dict, list, etc.) or default value if parsing fails
        
    Examples:
        >>> parse_llm_json_response('```json\\n{"key": "value"}\\n```')
        {'key': 'value'}
        
        >>> parse_llm_json_response('invalid json', default={})
        {}
    """
    try:
        json_str = extract_json_from_markdown(content)
        return json.loads(json_str)
    except (json.JSONDecodeError, ValueError, AttributeError) as e:
        logger.warning(f"Failed to parse JSON from LLM response: {e}")
        return default


def extract_content_from_response(response: Any) -> str:
    """
    Extract string content from various LLM response formats.
    
    Different LLM libraries return responses in different formats:
    - Some return objects with a .content attribute
    - Some return strings directly
    - Some return lists of content blocks
    
    This function handles these variations.
    
    Args:
        response: LLM response object (can be various types)
        
    Returns:
        Extracted string content
        
    Examples:
        >>> class MockResponse:
        ...     content = "Hello"
        >>> extract_content_from_response(MockResponse())
        'Hello'
        
        >>> extract_content_from_response("Direct string")
        'Direct string'
    """
    if hasattr(response, 'content'):
        content = response.content
        
        # Handle list of content blocks (e.g., ChatBedrockConverse)
        if isinstance(content, list):
            text_parts = []
            for block in content:
                if isinstance(block, dict) and 'text' in block:
                    text_parts.append(block['text'])
                elif isinstance(block, str):
                    text_parts.append(block)
            return ' '.join(text_parts).strip()
        
        # Handle string content
        return str(content).strip()
    
    # Fallback: convert to string
    return str(response).strip()


def parse_llm_response_with_fallback(
    response: Any,
    expected_keys: Optional[list] = None,
    default: Optional[Dict] = None
) -> Dict[str, Any]:
    """
    Parse LLM JSON response with validation and fallback.
    
    This function:
    1. Extracts content from the response object
    2. Parses JSON from markdown code blocks
    3. Validates expected keys are present
    4. Returns default value if parsing or validation fails
    
    Args:
        response: LLM response object
        expected_keys: List of keys that must be present in the parsed JSON
        default: Default dict to return if parsing/validation fails
        
    Returns:
        Parsed and validated JSON dict, or default value
        
    Examples:
        >>> class MockResponse:
        ...     content = '```json\\n{"decisions": []}\\n```'
        >>> parse_llm_response_with_fallback(MockResponse(), expected_keys=['decisions'])
        {'decisions': []}
    """
    if default is None:
        default = {}
    
    try:
        # Extract content from response object
        content = extract_content_from_response(response)
        
        # Parse JSON
        result = parse_llm_json_response(content, default=None)
        
        if result is None:
            logger.warning("Failed to parse JSON from LLM response")
            return default
        
        # Validate expected keys
        if expected_keys:
            missing_keys = [key for key in expected_keys if key not in result]
            if missing_keys:
                logger.warning(f"Missing expected keys in LLM response: {missing_keys}")
                return default
        
        return result
        
    except Exception as e:
        logger.exception(f"Error parsing LLM response: {e}")
        return default

