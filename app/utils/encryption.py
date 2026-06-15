"""
AES-128 symmetric encryption of connection credentials via Fernet.
Fernet guarantees authenticated encryption — tampered ciphertext raises
an exception on decrypt, preventing silent data corruption.
"""

import json
from base64 import urlsafe_b64encode
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings


def _get_fernet() -> Fernet:
    key = settings.ENCRYPTION_KEY
    # Accept raw 32-byte keys and auto-encode them
    if len(key) == 32:
        key = urlsafe_b64encode(key.encode()).decode()
    return Fernet(key.encode())


def encrypt_credentials(data: dict[str, Any]) -> str:
    """Serialize and encrypt a credentials dict; returns a ciphertext string."""
    plaintext = json.dumps(data, default=str).encode()
    return _get_fernet().encrypt(plaintext).decode()


def decrypt_credentials(ciphertext: str) -> dict[str, Any]:
    """Decrypt and deserialize credentials; raises ValueError on invalid token."""
    try:
        plaintext = _get_fernet().decrypt(ciphertext.encode())
        return json.loads(plaintext)
    except (InvalidToken, json.JSONDecodeError) as exc:
        raise ValueError("Failed to decrypt credentials") from exc
