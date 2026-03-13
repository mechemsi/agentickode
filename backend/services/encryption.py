# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Fernet symmetric encryption for project secrets."""

import logging

from cryptography.fernet import Fernet

from backend.config import settings

logger = logging.getLogger("agentickode.encryption")

_fernet: Fernet | None = None


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        key = settings.encryption_key
        if not key:
            logger.warning(
                "ENCRYPTION_KEY not set — generating ephemeral key (secrets will not survive restart)"
            )
            key = Fernet.generate_key().decode()
        _fernet = Fernet(key.encode() if isinstance(key, str) else key)
    return _fernet


def encrypt_value(plaintext: str) -> str:
    return _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt_value(ciphertext: str) -> str:
    return _get_fernet().decrypt(ciphertext.encode()).decode()
