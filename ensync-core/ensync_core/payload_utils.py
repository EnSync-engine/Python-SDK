"""
Payload utility functions for EnSync SDK.
Provides shared functionality for payload processing across gRPC and WebSocket clients.
"""
import json
from typing import Any, Dict


def get_payload_skeleton(payload: Dict[str, Any], use_float: bool = False) -> Dict[str, str]:
    """
    Extract top-level skeleton with datatypes matching EnSync engine validation.
    
    Supported types: string, integer, long, double, float, boolean, object, array, null
    
    Args:
        payload: Dictionary payload to analyze
        use_float: If True, use "float" instead of "double" for Python float values.
                   Note: Python floats are always 64-bit, so this is just a type hint.
        
    Returns:
        Dictionary mapping field names to type strings
    """
    skeleton = {}
    for key, value in payload.items():
        if isinstance(value, bool):  # Check bool before int (bool is subclass of int)
            skeleton[key] = "boolean"
        elif isinstance(value, str):
            skeleton[key] = "string"
        elif isinstance(value, int):
            # Python int can represent both integer and long
            # Use long for values outside 32-bit integer range
            if -2147483648 <= value <= 2147483647:
                skeleton[key] = "integer"
            else:
                skeleton[key] = "long"
        elif isinstance(value, float):
            # Python floats are always 64-bit (double precision)
            # Use "float" if explicitly requested, otherwise "double"
            skeleton[key] = "float" if use_float else "double"
        elif isinstance(value, dict):
            skeleton[key] = "object"
        elif isinstance(value, list):
            skeleton[key] = "array"
        elif value is None:
            skeleton[key] = "null"
        else:
            # Fallback for unknown types
            skeleton[key] = "string"
    return skeleton


def get_payload_metadata(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get payload metadata including byte size and type skeleton.
    
    Args:
        payload: Dictionary payload to analyze
        
    Returns:
        Dictionary with 'byte_size' and 'skeleton' keys
    """
    payload_bytes = json.dumps(payload).encode('utf-8')
    return {
        "byte_size": len(payload_bytes),
        "skeleton": get_payload_skeleton(payload) if isinstance(payload, dict) else {}
    }
