# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Tests for webhook HMAC signature verification."""

import hashlib
import hmac

from backend.services.webhook_security import verify_hmac_sha256, verify_shared_secret


def _sign(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


class TestVerifyHmacSha256:
    def test_accepts_matching_signature_without_prefix(self):
        body = b'{"action":"opened"}'
        sig = _sign("topsecret", body)
        assert verify_hmac_sha256("topsecret", body, sig) is True

    def test_accepts_matching_signature_with_sha256_prefix(self):
        body = b'{"action":"opened"}'
        sig = "sha256=" + _sign("topsecret", body)
        assert verify_hmac_sha256("topsecret", body, sig) is True

    def test_rejects_wrong_signature(self):
        body = b'{"action":"opened"}'
        assert verify_hmac_sha256("topsecret", body, "deadbeef") is False

    def test_rejects_signature_for_tampered_body(self):
        sig = _sign("topsecret", b'{"action":"opened"}')
        assert verify_hmac_sha256("topsecret", b'{"action":"closed"}', sig) is False

    def test_rejects_missing_signature_header(self):
        assert verify_hmac_sha256("topsecret", b"body", None) is False
        assert verify_hmac_sha256("topsecret", b"body", "") is False

    def test_non_ascii_signature_returns_false_not_raises(self):
        # A crafted non-ASCII header must fail verification, not raise (→ 500).
        assert verify_hmac_sha256("topsecret", b"body", "sha256=ñoñascii") is False

    def test_rejects_when_secret_empty(self):
        body = b"body"
        # An empty secret cannot meaningfully verify anything.
        assert verify_hmac_sha256("", body, _sign("", body)) is False


class TestVerifySharedSecret:
    def test_accepts_matching_token(self):
        assert verify_shared_secret("ci-token", "ci-token") is True

    def test_rejects_wrong_token(self):
        assert verify_shared_secret("ci-token", "nope") is False

    def test_rejects_missing_token(self):
        assert verify_shared_secret("ci-token", None) is False
        assert verify_shared_secret("ci-token", "") is False

    def test_rejects_when_secret_empty(self):
        assert verify_shared_secret("", "anything") is False
