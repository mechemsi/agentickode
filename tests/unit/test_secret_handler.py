# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Tests for SecretHandler encrypt/decrypt/redact."""

import pytest

from backend.services.backup.secret_handler import REDACTED, SecretHandler, SecretMode


class TestSecretHandlerPlaintext:
    def test_process_text_returns_unchanged(self):
        h = SecretHandler(SecretMode.plaintext)
        assert h.process_text("secret123") == "secret123"

    def test_process_text_none(self):
        h = SecretHandler(SecretMode.plaintext)
        assert h.process_text(None) is None

    def test_process_dict_values_returns_unchanged(self):
        h = SecretHandler(SecretMode.plaintext)
        d = {"KEY": "val1", "SECRET": "val2"}
        assert h.process_dict_values(d) == {"KEY": "val1", "SECRET": "val2"}


class TestSecretHandlerRedacted:
    def test_process_text_redacts(self):
        h = SecretHandler(SecretMode.redacted)
        assert h.process_text("secret123") == REDACTED

    def test_process_dict_values_redacts(self):
        h = SecretHandler(SecretMode.redacted)
        result = h.process_dict_values({"KEY": "val"})
        assert result == {"KEY": REDACTED}


class TestSecretHandlerEncrypted:
    def test_requires_password(self):
        with pytest.raises(ValueError, match="Password required"):
            SecretHandler(SecretMode.encrypted)

    def test_roundtrip_text(self):
        h = SecretHandler(SecretMode.encrypted, password="test123")
        encrypted = h.process_text("my-secret")
        assert encrypted != "my-secret"
        assert encrypted != REDACTED

        # Decrypt with same password + salt
        d = SecretHandler.for_decrypt("test123", h.salt_b64)
        assert d.decrypt_text(encrypted) == "my-secret"

    def test_roundtrip_dict(self):
        h = SecretHandler(SecretMode.encrypted, password="pw")
        original = {"API_KEY": "sk-123", "TOKEN": "abc"}
        encrypted = h.process_dict_values(original)

        assert encrypted["API_KEY"] != "sk-123"
        assert encrypted["TOKEN"] != "abc"

        d = SecretHandler.for_decrypt("pw", h.salt_b64)
        decrypted = d.decrypt_dict_values(encrypted)
        assert decrypted == {"API_KEY": "sk-123", "TOKEN": "abc"}

    def test_decrypt_none(self):
        h = SecretHandler(SecretMode.encrypted, password="pw")
        assert h.decrypt_text(None) is None

    def test_decrypt_redacted_passthrough(self):
        h = SecretHandler(SecretMode.encrypted, password="pw")
        assert h.decrypt_text(REDACTED) == REDACTED

    def test_salt_b64_present(self):
        h = SecretHandler(SecretMode.encrypted, password="pw")
        assert h.salt_b64 is not None
        assert len(h.salt_b64) > 10

    def test_plaintext_no_salt(self):
        h = SecretHandler(SecretMode.plaintext)
        assert h.salt_b64 is None