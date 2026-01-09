"""
ZINC-FUSION-V15 Pulse Validators
================================

Validates Intel Drop JSON against the pulse.v1 schema.
Ensures all AI outputs meet the strict contract requirements.
"""

import json
from typing import Dict, Any, List, Tuple
from .schema import PULSE_JSON_SCHEMA, Domain, Horizon


class PulseValidationError(Exception):
    """Raised when pulse validation fails"""
    def __init__(self, errors: List[str]):
        self.errors = errors
        super().__init__(f"Pulse validation failed: {errors}")


def validate_pulse(pulse_data: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    Validate a pulse against the schema.
    
    Returns:
        Tuple of (is_valid, list_of_errors)
    """
    errors = []
    
    # Check required fields
    required = ["schema_version", "as_of_ts", "instrument", "domain", "horizons"]
    for field in required:
        if field not in pulse_data:
            errors.append(f"Missing required field: {field}")
    
    if errors:
        return False, errors
    
    # Check schema version
    if pulse_data.get("schema_version") != "pulse.v1":
        errors.append(f"Invalid schema_version: {pulse_data.get('schema_version')} (expected pulse.v1)")
    
    # Check domain
    valid_domains = [d.value for d in Domain]
    if pulse_data.get("domain") not in valid_domains:
        errors.append(f"Invalid domain: {pulse_data.get('domain')} (expected one of {valid_domains})")
    
    # Check horizons
    horizons = pulse_data.get("horizons", [])
    if len(horizons) != 4:
        errors.append(f"Must have exactly 4 horizons, got {len(horizons)}")
    
    expected_horizons = ["1W", "1M", "3M", "6M"]
    for i, h in enumerate(horizons):
        if i < len(expected_horizons):
            if h.get("horizon") != expected_horizons[i]:
                errors.append(f"Horizon {i} should be {expected_horizons[i]}, got {h.get('horizon')}")
        
        # Validate driver weights sum to 1.0
        weights = h.get("driver_weights", {})
        weight_sum = sum([
            weights.get("technical", 0),
            weights.get("flows", 0),
            weights.get("macro", 0),
            weights.get("policy", 0),
            weights.get("weather", 0),
            weights.get("positioning", 0),
            weights.get("sentiment", 0)
        ])
        if abs(weight_sum - 1.0) > 0.01:
            errors.append(f"Horizon {h.get('horizon')}: driver_weights sum to {weight_sum:.3f}, must be 1.0 ± 0.01")
        
        # Validate edge in range
        edge = h.get("edge", 0)
        if not 0 <= edge <= 1:
            errors.append(f"Horizon {h.get('horizon')}: edge {edge} must be between 0 and 1")
        
        # Validate direction
        direction = h.get("direction")
        if direction not in [-1, 0, 1]:
            errors.append(f"Horizon {h.get('horizon')}: direction {direction} must be -1, 0, or 1")
        
        # Validate top_drivers
        for driver in h.get("top_drivers", []):
            if driver.get("sign") not in [-1, 1]:
                errors.append(f"Driver {driver.get('driver_id')}: sign must be -1 or 1")
            if not 0 <= driver.get("weight", 0) <= 1:
                errors.append(f"Driver {driver.get('driver_id')}: weight must be between 0 and 1")
    
    return len(errors) == 0, errors


def validate_and_raise(pulse_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate pulse and raise exception if invalid.
    Returns the validated data if valid.
    """
    is_valid, errors = validate_pulse(pulse_data)
    if not is_valid:
        raise PulseValidationError(errors)
    return pulse_data


def parse_pulse_response(response_text: str) -> Dict[str, Any]:
    """
    Parse AI response text into pulse data.
    Handles common issues like markdown code blocks.
    """
    # Strip markdown code blocks if present
    text = response_text.strip()
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()
    
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise PulseValidationError([f"Invalid JSON: {str(e)}"])


def create_retry_prompt(errors: List[str]) -> str:
    """
    Generate a retry prompt when validation fails.
    """
    error_list = "\n".join([f"- {e}" for e in errors])
    return f"""Your previous response had validation errors:

{error_list}

Please fix these issues and return ONLY valid JSON that matches the pulse.v1 schema.
Remember:
- driver_weights must sum to exactly 1.0
- edge must be between 0 and 1
- direction must be -1, 0, or 1
- exactly 4 horizons in order: 1W, 1M, 3M, 6M

Return JSON only, no markdown, no commentary."""
