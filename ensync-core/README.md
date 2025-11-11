# EnSync Core

Core utilities for EnSync SDK packages. This package provides shared functionality including encryption, error handling, and common utilities.

## Features

- **End-to-End Encryption**: Ed25519 elliptic curve cryptography
- **Hybrid Encryption**: AES-GCM with Ed25519 key exchange for multi-recipient scenarios
- **Error Handling**: Unified error classes for EnSync operations
- **Type Safety**: Full type hints for better IDE support

## Installation

```bash
pip install ensync-core
```

**Note:** This package is automatically installed as a dependency of `ensync-sdk` and `ensync-sdk-ws`. You typically don't need to install it directly.

## Usage

### Error Handling

```python
from ensync_core import EnSyncError

try:
    # Your EnSync operations
    pass
except EnSyncError as e:
    print(f"EnSync error: {e}")
    print(f"Error type: {e.error_type}")
```

### Encryption Utilities

For advanced use cases, you can use the encryption utilities directly:

```python
from ensync_core.ecc_crypto import (
    encrypt_ed25519,
    decrypt_ed25519,
    hybrid_encrypt,
    hybrid_decrypt
)

# Traditional Ed25519 encryption (single recipient)
encrypted_data = encrypt_ed25519(payload_bytes, recipient_public_key)
decrypted_data = decrypt_ed25519(encrypted_data, private_key)

# Hybrid encryption (multiple recipients)
encrypted = hybrid_encrypt(payload_bytes, [recipient_key1, recipient_key2])
# Returns: {"encryptedPayload": "...", "encryptedKeys": {"recipientId": "..."}}
```

## API Reference

### EnSyncError

Custom exception class for EnSync operations.

```python
class EnSyncError(Exception):
    def __init__(self, message: str, error_type: str = "EnSyncGenericError"):
        self.message = message
        self.error_type = error_type
```

**Common Error Types:**

- `EnSyncConnectionError`: Connection failures
- `EnSyncAuthError`: Authentication failures
- `EnSyncPublishError`: Event publishing failures
- `EnSyncSubscriptionError`: Subscription failures
- `EnSyncValidationError`: Input validation errors

### Encryption Functions

#### `encrypt_ed25519(data: bytes, recipient_public_key: bytes) -> dict`

Encrypts data using Ed25519 public key cryptography.

**Parameters:**

- `data` (`bytes`): Data to encrypt
- `recipient_public_key` (`bytes`): Recipient's public key

**Returns:** Dictionary with encrypted data structure

#### `decrypt_ed25519(encrypted_data: dict, private_key: str) -> str`

Decrypts Ed25519 encrypted data.

**Parameters:**

- `encrypted_data` (`dict`): Encrypted data structure
- `private_key` (`str`): Private key for decryption

**Returns:** Decrypted data as string

#### `hybrid_encrypt(data: bytes, recipient_keys: list[bytes]) -> dict`

Encrypts data for multiple recipients using hybrid encryption (AES-GCM + Ed25519).

**Parameters:**

- `data` (`bytes`): Data to encrypt
- `recipient_keys` (`list[bytes]`): List of recipient public keys

**Returns:** Dictionary with encrypted payload and per-recipient keys

#### `hybrid_decrypt(encrypted_payload: str, encrypted_key: str, private_key: str) -> str`

Decrypts hybrid encrypted data.

**Parameters:**

- `encrypted_payload` (`str`): Encrypted payload
- `encrypted_key` (`str`): Encrypted message key for this recipient
- `private_key` (`str`): Private key for decryption

**Returns:** Decrypted data as string

## Security

### Encryption Details

- **Algorithm**: Ed25519 (Curve25519) for asymmetric encryption
- **Hybrid Mode**: AES-256-GCM for payload, Ed25519 for key exchange
- **Key Size**: 32 bytes (256 bits)
- **Nonce**: Randomly generated for each encryption

### Best Practices

- Never log or expose private keys
- Store keys securely (use environment variables or key management systems)
- Validate all inputs before encryption/decryption
- Use hybrid encryption for multi-recipient scenarios to improve performance

## Related Packages

- **ensync-sdk**: Main SDK with gRPC client (recommended)
- **ensync-sdk-ws**: WebSocket alternative client

## Documentation

For complete documentation, visit:

- [Python SDK Documentation](https://docs.ensync.cloud/sdk/python)
- [EnSync Cloud](https://ensync.cloud)

## License

MIT License - see LICENSE file for details
