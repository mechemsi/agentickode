# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

from datetime import datetime

from pydantic import BaseModel


class SSHKeyCreate(BaseModel):
    name: str
    comment: str | None = None


class SSHKeyOut(BaseModel):
    name: str
    public_key: str | None
    created_at: datetime
    is_default: bool = False


class GitProviderStatus(BaseModel):
    host: str
    name: str
    connected: bool
    username: str | None = None
    error: str | None = None


class UserGitAccessStatus(BaseModel):
    user: str
    has_key: bool
    public_key: str | None = None
    key_type: str | None = None
    providers: list[GitProviderStatus] = []


class GitAccessStatus(BaseModel):
    has_key: bool
    public_key: str | None = None
    key_type: str | None = None
    providers: list[GitProviderStatus] = []
    by_user: list[UserGitAccessStatus] = []


class GitAccessCheckRequest(BaseModel):
    custom_hosts: list[str] = []


class GitAccessGenerateKeyRequest(BaseModel):
    key_type: str = "ed25519"
    force: bool = False
