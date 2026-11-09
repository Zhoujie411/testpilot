import base64
import hashlib
import os

from cryptography.fernet import Fernet


def _cipher() -> Fernet:
    secret = os.getenv("TESTPILOT_SECRET_KEY", "testpilot-dev-key-change-in-production")
    key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode("utf-8")).digest())
    return Fernet(key)


def encrypt_api_key(value: str) -> str:
    return _cipher().encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_api_key(value: str) -> str:
    return _cipher().decrypt(value.encode("utf-8")).decode("utf-8")
