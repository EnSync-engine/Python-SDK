"""
EnSync Core - Shared utilities for EnSync SDK packages.
Provides encryption, decryption, and error handling functionality.
"""

from .ecc_crypto import (
    encrypt_ed25519,
    decrypt_ed25519,
    hybrid_encrypt,
    hybrid_decrypt,
    decrypt_message_key,
    decrypt_with_message_key
)
from .error import EnSyncError, GENERIC_MESSAGE
from .payload_utils import get_payload_skeleton, get_payload_metadata

__version__ = "0.1.0"

__all__ = [
    'encrypt_ed25519',
    'decrypt_ed25519',
    'hybrid_encrypt',
    'hybrid_decrypt',
    'decrypt_message_key',
    'decrypt_with_message_key',
    'EnSyncError',
    'GENERIC_MESSAGE',
    'get_payload_skeleton',
    'get_payload_metadata'
]
