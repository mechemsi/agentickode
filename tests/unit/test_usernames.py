# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Tests for backend.services.workspace.usernames.validate_username."""

import pytest

from backend.services.workspace.usernames import UsernameError, validate_username


class TestValidateUsername:
    def test_accepts_simple_lowercase(self):
        assert validate_username("domas") == "domas"

    def test_accepts_digits_after_first_char(self):
        assert validate_username("user1") == "user1"

    def test_accepts_underscore_start(self):
        assert validate_username("_systemd") == "_systemd"

    def test_accepts_trailing_dollar_for_machine_accounts(self):
        # Samba/AD-style machine accounts: ``MACHINE$``. The lowercase
        # form falls through the same pattern.
        assert validate_username("box$") == "box$"

    def test_accepts_hyphen_in_middle(self):
        assert validate_username("ci-runner") == "ci-runner"

    def test_rejects_empty_string(self):
        with pytest.raises(UsernameError, match="non-empty"):
            validate_username("")

    def test_rejects_none(self):
        with pytest.raises(UsernameError, match="non-empty"):
            validate_username(None)  # type: ignore[arg-type]

    def test_rejects_uppercase(self):
        # Linux allows uppercase but most distros normalize to lowercase
        # and many scripts choke on it — reject defensively.
        with pytest.raises(UsernameError, match="not a valid"):
            validate_username("Admin")

    def test_rejects_leading_digit(self):
        with pytest.raises(UsernameError, match="not a valid"):
            validate_username("1user")

    def test_rejects_shell_metacharacters(self):
        for bad in ["a;rm -rf /", "a b", "a`x`", "a$(x)", "a|b", "a&b", "a\nb", "a/b"]:
            with pytest.raises(UsernameError, match="not a valid"):
                validate_username(bad)

    def test_rejects_unicode(self):
        with pytest.raises(UsernameError, match="not a valid"):
            validate_username("café")

    def test_rejects_too_long(self):
        # 33 chars — one over the LOGIN_NAME_MAX cap.
        with pytest.raises(UsernameError, match="not a valid"):
            validate_username("a" + "b" * 32)

    def test_accepts_max_length(self):
        # 32 chars exactly.
        assert validate_username("a" + "b" * 31) == "a" + "b" * 31

    def test_field_name_appears_in_error(self):
        with pytest.raises(UsernameError, match="worker_user_override"):
            validate_username("BAD", field="worker_user_override")
