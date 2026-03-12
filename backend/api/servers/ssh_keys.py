# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""SSH key management endpoints."""

from __future__ import annotations

import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException

from backend.config import settings
from backend.schemas import SSHKeyCreate, SSHKeyOut

router = APIRouter(tags=["ssh-keys"])

SSH_DIR = Path(settings.default_ssh_key_path).parent


def _key_info(name: str) -> SSHKeyOut | None:
    """Read key pair info from disk."""
    priv = SSH_DIR / name
    pub = SSH_DIR / f"{name}.pub"
    if not priv.is_file():
        return None
    pub_content = pub.read_text().strip() if pub.is_file() else None
    stat = priv.stat()
    created = datetime.fromtimestamp(stat.st_ctime, tz=UTC)
    default_name = Path(settings.default_ssh_key_path).name
    return SSHKeyOut(
        name=name,
        public_key=pub_content,
        created_at=created,
        is_default=name == default_name,
    )


@router.get("/ssh-keys")
async def list_ssh_keys() -> list[SSHKeyOut]:
    """List all SSH key pairs in the managed directory."""
    SSH_DIR.mkdir(parents=True, exist_ok=True)
    keys: list[SSHKeyOut] = []
    for f in sorted(SSH_DIR.iterdir()):
        if f.suffix == ".pub" or f.name.startswith("."):
            continue
        pub = f.with_suffix(".pub") if not f.name.endswith(".pub") else None
        if pub and pub.exists():
            info = _key_info(f.name)
            if info:
                keys.append(info)
    return keys


@router.post("/ssh-keys", status_code=201)
async def create_ssh_key(body: SSHKeyCreate) -> SSHKeyOut:
    """Generate a new SSH key pair."""
    SSH_DIR.mkdir(parents=True, exist_ok=True)
    priv = SSH_DIR / body.name
    if priv.exists():
        raise HTTPException(400, f"Key '{body.name}' already exists")

    comment = body.comment or f"autodev-{body.name}"
    try:
        subprocess.run(
            [
                "ssh-keygen",
                "-t",
                "ed25519",
                "-f",
                str(priv),
                "-N",
                "",
                "-C",
                comment,
            ],
            check=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError as exc:
        raise HTTPException(500, f"ssh-keygen failed: {exc.stderr.decode()}") from exc

    os.chmod(priv, 0o600)
    os.chmod(priv.with_suffix(".pub"), 0o644)

    info = _key_info(body.name)
    if not info:
        raise HTTPException(500, "Key generated but could not be read")
    return info


@router.delete("/ssh-keys/{name}", status_code=204, response_model=None)
async def delete_ssh_key(name: str) -> None:
    """Delete an SSH key pair."""
    priv = SSH_DIR / name
    pub = SSH_DIR / f"{name}.pub"
    if not priv.is_file():
        raise HTTPException(404, f"Key '{name}' not found")
    priv.unlink()
    if pub.is_file():
        pub.unlink()