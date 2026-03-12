# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Secret field encryption / redaction for backup export-import."""

from __future__ import annotations

import base64
import enum
import os

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

REDACTED = "***REDACTED***"


class SecretMode(str, enum.Enum):
    plaintext = "plaintext"
    redacted = "redacted"
    encrypted = "encrypted"


def _derive_key(password: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=480_000,
    )
    return base64.urlsafe_b64encode(kdf.derive(password.encode()))


class SecretHandler:
    """Handles encrypt / decrypt / redact of secret fields."""

    def __init__(self, mode: SecretMode, password: str | None = None):
        self.mode = mode
        self._fernet: Fernet | None = None
        self._salt: bytes | None = None

        if mode == SecretMode.encrypted:
            if not password:
                raise ValueError("Password required for encrypted mode")
            self._salt = os.urandom(16)
            key = _derive_key(password, self._salt)
            self._fernet = Fernet(key)

    @classmethod
    def for_decrypt(cls, password: str, salt_b64: str) -> SecretHandler:
        """Create a handler for decrypting an imported file."""
        handler = cls.__new__(cls)
        handler.mode = SecretMode.encrypted
        handler._salt = base64.b64decode(salt_b64)
        key = _derive_key(password, handler._salt)
        handler._fernet = Fernet(key)
        return handler

    @property
    def salt_b64(self) -> str | None:
        if self._salt is None:
            return None
        return base64.b64encode(self._salt).decode()

    # --- public API ---

    def process_text(self, value: str | None) -> str | None:
        """Process a single secret text field for export."""
        if value is None:
            return None
        if self.mode == SecretMode.plaintext:
            return value
        if self.mode == SecretMode.redacted:
            return REDACTED
        assert self._fernet is not None
        return self._fernet.encrypt(value.encode()).decode()

    def process_dict_values(self, d: dict | None) -> dict | None:
        """Encrypt/redact *values* of a dict, keeping keys visible."""
        if d is None:
            return None
        return {k: self.process_text(str(v)) for k, v in d.items()}

    def decrypt_text(self, value: str | None) -> str | None:
        """Decrypt a single secret text field on import."""
        if value is None or value == REDACTED:
            return value
        if self.mode != SecretMode.encrypted:
            return value
        assert self._fernet is not None
        return self._fernet.decrypt(value.encode()).decode()

    def decrypt_dict_values(self, d: dict | None) -> dict | None:
        """Decrypt values of a dict on import."""
        if d is None:
            return None
        return {k: self.decrypt_text(str(v)) for k, v in d.items()}