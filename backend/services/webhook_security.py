# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""HMAC signature verification for inbound webhooks.

GitHub sends ``X-Hub-Signature-256: sha256=<hexdigest>`` and Gitea sends
``X-Gitea-Signature: <hexdigest>`` — both are HMAC-SHA256 of the raw request
body keyed by a shared secret. ``verify_hmac_sha256`` tolerates the optional
``sha256=`` prefix and compares in constant time.
"""

import hashlib
import hmac


def verify_hmac_sha256(secret: str, raw_body: bytes, signature_header: str | None) -> bool:
    """Return True iff *signature_header* is a valid HMAC-SHA256 of *raw_body*.

    An empty *secret* or missing *signature_header* always fails — the caller is
    expected to skip verification entirely when no secret is configured.
    """
    if not secret or not signature_header:
        return False
    provided = signature_header.split("=", 1)[1] if "=" in signature_header else signature_header
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    try:
        return hmac.compare_digest(expected, provided)
    except TypeError:
        # A non-ASCII signature header makes compare_digest raise — treat as invalid.
        return False


def verify_shared_secret(secret: str, provided: str | None) -> bool:
    """Constant-time compare a shared secret against a provided token.

    An empty *secret* or missing *provided* token always fails — callers skip
    the check entirely when no secret is configured.
    """
    if not secret or not provided:
        return False
    return hmac.compare_digest(secret, provided)
