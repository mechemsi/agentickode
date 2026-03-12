# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Notification channel CRUD + test endpoint."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models import NotificationChannel
from backend.repositories.notification_channel_repo import NotificationChannelRepository
from backend.schemas import (
    VALID_CHANNEL_TYPES,
    VALID_NOTIFICATION_EVENTS,
    NotificationChannelCreate,
    NotificationChannelOut,
    NotificationChannelUpdate,
    NotificationTestResult,
)
from backend.services.http_client import get_http_client
from backend.services.notifications.service import NotificationService

router = APIRouter(tags=["notification-channels"])


def _get_repo(db: AsyncSession = Depends(get_db)) -> NotificationChannelRepository:
    return NotificationChannelRepository(db)


def _validate_channel_type(channel_type: str) -> None:
    if channel_type not in VALID_CHANNEL_TYPES:
        raise HTTPException(
            400, f"Invalid channel_type. Must be one of: {', '.join(sorted(VALID_CHANNEL_TYPES))}"
        )


def _validate_events(events: list[str]) -> None:
    invalid = set(events) - VALID_NOTIFICATION_EVENTS
    if invalid:
        raise HTTPException(400, f"Invalid events: {', '.join(sorted(invalid))}")


@router.get("/notification-channels", response_model=list[NotificationChannelOut])
async def list_channels(repo: NotificationChannelRepository = Depends(_get_repo)):
    return await repo.list_all()


@router.post("/notification-channels", response_model=NotificationChannelOut, status_code=201)
async def create_channel(
    body: NotificationChannelCreate,
    repo: NotificationChannelRepository = Depends(_get_repo),
):
    _validate_channel_type(body.channel_type)
    _validate_events(body.events)
    channel = NotificationChannel(**body.model_dump())
    return await repo.create(channel)


@router.put("/notification-channels/{channel_id}", response_model=NotificationChannelOut)
async def update_channel(
    channel_id: int,
    body: NotificationChannelUpdate,
    repo: NotificationChannelRepository = Depends(_get_repo),
):
    channel = await repo.get(channel_id)
    if not channel:
        raise HTTPException(404, "Notification channel not found")
    data = body.model_dump(exclude_unset=True)
    if "channel_type" in data:
        _validate_channel_type(data["channel_type"])
    if "events" in data:
        _validate_events(data["events"])
    return await repo.update(channel, data)


@router.delete("/notification-channels/{channel_id}", status_code=204)
async def delete_channel(
    channel_id: int,
    repo: NotificationChannelRepository = Depends(_get_repo),
):
    channel = await repo.get(channel_id)
    if not channel:
        raise HTTPException(404, "Notification channel not found")
    await repo.delete(channel)


@router.post(
    "/notification-channels/{channel_id}/test",
    response_model=NotificationTestResult,
)
async def test_channel(
    channel_id: int,
    repo: NotificationChannelRepository = Depends(_get_repo),
):
    channel = await repo.get(channel_id)
    if not channel:
        raise HTTPException(404, "Notification channel not found")
    client = get_http_client()
    service = NotificationService(client)
    success, error = await service.test(channel)
    return NotificationTestResult(success=success, error=error)