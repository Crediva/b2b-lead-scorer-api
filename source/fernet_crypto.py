"""Fernet encryption for PII at rest in CREDIVA products."""
import os
from pathlib import Path
from cryptography.fernet import Fernet

BASE = Path(__file__).parent.parent
KEY_PATH = BASE / ".crediva_secret.key"

# Load key once at import, never regenerate if exists
def _load_or_create_key() -> bytes:
    """Load existing key or create new one. Saves outside git."""
    if KEY_PATH.exists():
        return KEY_PATH.read_bytes()
    key = Fernet.generate_key()
    KEY_PATH.write_bytes(key)
    return key

_fernet = Fernet(_load_or_create_key())

def encrypt_field(value: str) -> str:
    """Encrypt a string field. Returns base64 encoded ciphertext."""
    if not value:
        return value
    return _fernet.encrypt(value.encode()).decode()

def decrypt_field(value: str) -> str:
    """Decrypt an encrypted string field. Returns original plaintext."""
    if not value:
        return value
    try:
        return _fernet.decrypt(value.encode()).decode()
    except Exception:
        return value  # Return as-is if not encrypted