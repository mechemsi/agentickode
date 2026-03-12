# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Unit tests for SSH key management API."""

import os
from unittest.mock import patch

import pytest


@pytest.fixture()
def ssh_dir(tmp_path):
    """Provide a temporary SSH directory and patch config."""
    d = tmp_path / ".ssh"
    d.mkdir()
    with (
        patch("backend.api.servers.ssh_keys.SSH_DIR", d),
        patch("backend.api.servers.ssh_keys.settings") as mock_settings,
    ):
        mock_settings.default_ssh_key_path = str(d / "id_ed25519")
        yield d


class TestListSSHKeys:
    async def test_empty_dir(self, client, ssh_dir):
        resp = await client.get("/api/ssh-keys")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_lists_existing_keys(self, client, ssh_dir):
        # Create a fake key pair
        priv = ssh_dir / "test-key"
        pub = ssh_dir / "test-key.pub"
        priv.write_text("PRIVATE")
        pub.write_text("ssh-ed25519 AAAA test@host")
        os.chmod(priv, 0o600)

        resp = await client.get("/api/ssh-keys")
        assert resp.status_code == 200
        keys = resp.json()
        assert len(keys) == 1
        assert keys[0]["name"] == "test-key"
        assert keys[0]["public_key"] == "ssh-ed25519 AAAA test@host"

    async def test_skips_dotfiles(self, client, ssh_dir):
        (ssh_dir / ".gitkeep").write_text("")
        resp = await client.get("/api/ssh-keys")
        assert resp.status_code == 200
        assert resp.json() == []


class TestCreateSSHKey:
    async def test_creates_key(self, client, ssh_dir):
        resp = await client.post("/api/ssh-keys", json={"name": "my-key"})
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "my-key"
        assert data["public_key"] is not None
        assert "ssh-ed25519" in data["public_key"]
        # Files should exist on disk
        assert (ssh_dir / "my-key").is_file()
        assert (ssh_dir / "my-key.pub").is_file()

    async def test_duplicate_name_rejected(self, client, ssh_dir):
        (ssh_dir / "dup").write_text("exists")
        resp = await client.post("/api/ssh-keys", json={"name": "dup"})
        assert resp.status_code == 400

    async def test_with_comment(self, client, ssh_dir):
        resp = await client.post(
            "/api/ssh-keys",
            json={"name": "commented", "comment": "user@example"},
        )
        assert resp.status_code == 201
        pub = (ssh_dir / "commented.pub").read_text()
        assert "user@example" in pub


class TestDeleteSSHKey:
    async def test_deletes_key(self, client, ssh_dir):
        priv = ssh_dir / "del-me"
        pub = ssh_dir / "del-me.pub"
        priv.write_text("PRIVATE")
        pub.write_text("ssh-ed25519 AAAA test")

        resp = await client.delete("/api/ssh-keys/del-me")
        assert resp.status_code == 204
        assert not priv.exists()
        assert not pub.exists()

    async def test_not_found(self, client, ssh_dir):
        resp = await client.delete("/api/ssh-keys/nonexistent")
        assert resp.status_code == 404


class TestDefaultKeyFlag:
    async def test_default_key_flagged(self, client, ssh_dir):
        # Create the default key
        priv = ssh_dir / "id_ed25519"
        pub = ssh_dir / "id_ed25519.pub"
        priv.write_text("PRIVATE")
        pub.write_text("ssh-ed25519 AAAA default")

        resp = await client.get("/api/ssh-keys")
        keys = resp.json()
        assert len(keys) == 1
        assert keys[0]["is_default"] is True

    async def test_non_default_key(self, client, ssh_dir):
        priv = ssh_dir / "other"
        pub = ssh_dir / "other.pub"
        priv.write_text("PRIVATE")
        pub.write_text("ssh-ed25519 AAAA other")

        resp = await client.get("/api/ssh-keys")
        keys = resp.json()
        assert len(keys) == 1
        assert keys[0]["is_default"] is False