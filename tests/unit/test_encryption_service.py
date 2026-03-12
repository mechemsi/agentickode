# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Tests for the encryption service."""

from unittest.mock import patch


def test_encrypt_decrypt_roundtrip():
    """Encrypt then decrypt should return original value."""
    from cryptography.fernet import Fernet

    key = Fernet.generate_key().decode()
    with patch("backend.services.encryption.settings") as mock_settings:
        mock_settings.encryption_key = key
        # Reset the cached fernet instance
        import backend.services.encryption as enc_mod

        enc_mod._fernet = None

        from backend.services.encryption import decrypt_value, encrypt_value

        plaintext = "super-secret-api-key-123"
        encrypted = encrypt_value(plaintext)

        assert encrypted != plaintext
        assert decrypt_value(encrypted) == plaintext

        # Reset for other tests
        enc_mod._fernet = None


def test_encrypt_produces_different_ciphertexts():
    """Fernet uses random IV, so same plaintext produces different ciphertexts."""
    from cryptography.fernet import Fernet

    key = Fernet.generate_key().decode()
    with patch("backend.services.encryption.settings") as mock_settings:
        mock_settings.encryption_key = key
        import backend.services.encryption as enc_mod

        enc_mod._fernet = None

        from backend.services.encryption import encrypt_value

        e1 = encrypt_value("same-value")
        e2 = encrypt_value("same-value")
        assert e1 != e2

        enc_mod._fernet = None


def test_ephemeral_key_on_missing_config(caplog):
    """When encryption_key is empty, an ephemeral key is generated with a warning."""
    with patch("backend.services.encryption.settings") as mock_settings:
        mock_settings.encryption_key = ""
        import backend.services.encryption as enc_mod

        enc_mod._fernet = None

        from backend.services.encryption import decrypt_value, encrypt_value

        encrypted = encrypt_value("test")
        assert decrypt_value(encrypted) == "test"

        enc_mod._fernet = None