"""
Encryption and decryption utilities for EnSync Python SDK.
Provides Ed25519 encryption and hybrid encryption functionality.
"""
import base64
import json
import os
from typing import Dict, List, Tuple, Union, Any

import nacl.secret
import nacl.utils
from nacl.public import PrivateKey, PublicKey, Box


def _ensure_bytes(data: Union[str, bytes]) -> bytes:
    """Convert string to bytes if needed."""
    if isinstance(data, str):
        return data.encode('utf-8')
    return data


def _ensure_base64(key: Union[str, bytes]) -> str:
    """Ensure key is a base64 string."""
    if isinstance(key, bytes):
        return base64.b64encode(key).decode('utf-8')
    return key


def _decode_base64(data: Union[str, bytes]) -> bytes:
    """Decode base64 data to bytes."""
    if isinstance(data, str):
        return base64.b64decode(data)
    return data


def encrypt_ed25519(message: bytes, public_key: Union[str, bytes]) -> Dict[str, str]:
    """
    Encrypt a message using Ed25519 public key.
    
    Args:
        message: The message to encrypt
        public_key: Recipient's Ed25519 public key (base64 string or bytes) - 32 bytes
        
    Returns:
        Dict containing nonce, ciphertext, and ephemeral public key
    """
    # Decode public key if it's base64
    if isinstance(public_key, str):
        public_key = base64.b64decode(public_key)
    
    # Convert Ed25519 public key to Curve25519 public key
    from nacl.bindings import crypto_sign_ed25519_pk_to_curve25519
    curve25519_public_key = crypto_sign_ed25519_pk_to_curve25519(public_key)
    
    # Create ephemeral key pair
    ephemeral_private = PrivateKey.generate()
    ephemeral_public = ephemeral_private.public_key
    
    # Create box for encryption
    recipient_public = PublicKey(curve25519_public_key)
    box = Box(ephemeral_private, recipient_public)
    
    # Generate nonce and encrypt
    nonce = nacl.utils.random(Box.NONCE_SIZE)
    ciphertext = box.encrypt(message, nonce).ciphertext
    
    # Return as dictionary with base64 encoded values
    return {
        'nonce': base64.b64encode(nonce).decode('utf-8'),
        'ciphertext': base64.b64encode(ciphertext).decode('utf-8'),
        'ephemeralPublicKey': base64.b64encode(bytes(ephemeral_public)).decode('utf-8')
    }


def decrypt_ed25519(encrypted_data: Dict[str, str], private_key: Union[str, bytes]) -> str:
    """
    Decrypt a message using Ed25519 private key.
    
    Args:
        encrypted_data: Dict with nonce, ciphertext, and ephemeral public key
        private_key: Recipient's private key (base64 string or bytes) - can be 32 or 64 bytes
        
    Returns:
        Decrypted message as string
    """
    try:
        # Decode private key if it's base64
        if isinstance(private_key, str):
            private_key = base64.b64decode(private_key)
        
        # If the key is 64 bytes (Ed25519 keypair), extract the first 32 bytes (seed)
        # and convert to Curve25519 secret key
        if len(private_key) == 64:
            # Extract the 32-byte seed from the 64-byte Ed25519 secret key
            ed25519_seed = private_key[:32]
            # Convert Ed25519 seed to Curve25519 secret key using nacl
            from nacl.bindings import crypto_sign_ed25519_sk_to_curve25519
            private_key = crypto_sign_ed25519_sk_to_curve25519(private_key)
        elif len(private_key) != 32:
            raise ValueError(f"Private key must be 32 or 64 bytes, got {len(private_key)} bytes")
        
        # Decode encrypted data components
        nonce = base64.b64decode(encrypted_data['nonce'])
        ciphertext = base64.b64decode(encrypted_data['ciphertext'])
        ephemeral_public_key = base64.b64decode(encrypted_data['ephemeralPublicKey'])
        
        # Create box for decryption
        recipient_private = PrivateKey(private_key)
        sender_public = PublicKey(ephemeral_public_key)
        box = Box(recipient_private, sender_public)
        
        # Decrypt
        decrypted = box.decrypt(ciphertext, nonce)
        return decrypted.decode('utf-8')
    except Exception as e:
        raise ValueError(f"Failed to decrypt: {str(e)}")


def generate_message_key() -> bytes:
    """
    Generate a random symmetric key for message encryption.
    
    Returns:
        Random bytes for symmetric encryption
    """
    return nacl.utils.random(nacl.secret.SecretBox.KEY_SIZE)


def encrypt_with_message_key(message: bytes, message_key: bytes) -> Dict[str, str]:
    """
    Encrypt a message using a symmetric key.
    
    Args:
        message: The message to encrypt
        message_key: Symmetric key for encryption
        
    Returns:
        Dict containing nonce and ciphertext
    """
    # Create secret box with the message key
    box = nacl.secret.SecretBox(message_key)
    
    # Generate nonce and encrypt
    nonce = nacl.utils.random(nacl.secret.SecretBox.NONCE_SIZE)
    ciphertext = box.encrypt(message, nonce).ciphertext
    
    # Return as dictionary with base64 encoded values
    return {
        'nonce': base64.b64encode(nonce).decode('utf-8'),
        'ciphertext': base64.b64encode(ciphertext).decode('utf-8')
    }


def decrypt_with_message_key(encrypted_data: Dict[str, str], message_key: bytes) -> str:
    """
    Decrypt a message using a symmetric key.
    
    Args:
        encrypted_data: Dict with nonce and ciphertext
        message_key: Symmetric key for decryption
        
    Returns:
        Decrypted message as string
    """
    try:
        # Decode encrypted data components
        nonce = base64.b64decode(encrypted_data['nonce'])
        ciphertext = base64.b64decode(encrypted_data['ciphertext'])
        
        # Create secret box with the message key
        box = nacl.secret.SecretBox(message_key)
        
        # Decrypt
        decrypted = box.decrypt(ciphertext, nonce)
        return decrypted.decode('utf-8')
    except Exception as e:
        raise ValueError(f"Failed to decrypt with message key: {str(e)}")


def encrypt_message_key(message_key: bytes, public_key: Union[str, bytes]) -> Dict[str, str]:
    """
    Encrypt a message key for a recipient using their public key.
    
    Args:
        message_key: The symmetric key to encrypt
        public_key: Recipient's public key
        
    Returns:
        Dict containing encrypted key information
    """
    # Use Ed25519 encryption for the message key
    return encrypt_ed25519(message_key, public_key)


def decrypt_message_key(encrypted_key: Dict[str, str], private_key: Union[str, bytes]) -> bytes:
    """
    Decrypt a message key using recipient's private key.
    
    Args:
        encrypted_key: Dict with encrypted key information
        private_key: Recipient's private key
        
    Returns:
        Decrypted message key as bytes
    """
    # Decrypt the message key using Ed25519
    decrypted_key_base64 = decrypt_ed25519(encrypted_key, private_key)
    return base64.b64decode(decrypted_key_base64)


def hybrid_encrypt(message: bytes, recipient_public_keys: List[Union[str, bytes]]) -> Dict[str, Any]:
    """
    Encrypt a message once with a symmetric key, then encrypt that key for each recipient.
    
    Args:
        message: The message to encrypt
        recipient_public_keys: List of recipient public keys
        
    Returns:
        Dict with encrypted payload and keys for each recipient
    """
    # Generate a random message key
    message_key = generate_message_key()
    
    # Encrypt the message with the message key
    encrypted_payload = encrypt_with_message_key(message, message_key)
    
    # Encrypt the message key for each recipient
    encrypted_keys = {}
    for public_key_bytes in recipient_public_keys:
        public_key_hex = public_key_bytes.hex()
        encrypted_key = encrypt_message_key(message_key, public_key_bytes)
        encrypted_keys[public_key_hex] = encrypted_key
    
    return {
        'encryptedPayload': encrypted_payload,
        'encryptedKeys': encrypted_keys
    }


def hybrid_decrypt(encrypted_data: Dict[str, Any], public_key: Union[str, bytes], 
                  private_key: Union[str, bytes]) -> str:
    """
    Decrypt a hybrid-encrypted message.
    
    Args:
        encrypted_data: Dict with encrypted payload and keys
        public_key: Recipient's public key (to find the right encrypted key)
        private_key: Recipient's private key (to decrypt the message key)
        
    Returns:
        Decrypted message as string
    """
    # Get the encrypted payload and keys
    encrypted_payload = encrypted_data['encryptedPayload']
    encrypted_keys = encrypted_data['encryptedKeys']
    
    # Find the encrypted key for this recipient
    public_key_str = _ensure_base64(public_key)
    if public_key_str not in encrypted_keys:
        raise ValueError("No encrypted key found for this recipient")
    
    # Decrypt the message key
    encrypted_key = encrypted_keys[public_key_str]
    message_key = decrypt_message_key(encrypted_key, private_key)
    
    # Decrypt the payload with the message key
    return decrypt_with_message_key(encrypted_payload, message_key)
