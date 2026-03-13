# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Webhook callback CRUD endpoints for per-run callbacks."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models import WebhookCallback
from backend.schemas import (
    WebhookCallbackCreate,
    WebhookCallbackOut,
    WebhookCallbackUpdate,
)

router = APIRouter(tags=["webhook-callbacks"])


@router.get("/runs/{run_id}/webhooks", response_model=list[WebhookCallbackOut])
async def list_webhooks(run_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(WebhookCallback).where(WebhookCallback.run_id == run_id))
    return list(result.scalars().all())


@router.post("/runs/{run_id}/webhooks", response_model=WebhookCallbackOut, status_code=201)
async def create_webhook(
    run_id: int,
    body: WebhookCallbackCreate,
    db: AsyncSession = Depends(get_db),
):
    cb = WebhookCallback(
        run_id=run_id,
        url=body.url,
        events=body.events,
        headers=body.headers,
        active=body.active,
    )
    db.add(cb)
    await db.commit()
    await db.refresh(cb)
    return cb


@router.put("/webhooks/{webhook_id}", response_model=WebhookCallbackOut)
async def update_webhook(
    webhook_id: int,
    body: WebhookCallbackUpdate,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(WebhookCallback).where(WebhookCallback.id == webhook_id))
    cb = result.scalar_one_or_none()
    if not cb:
        raise HTTPException(404, "Webhook callback not found")
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(cb, key, value)
    await db.commit()
    await db.refresh(cb)
    return cb


@router.delete("/webhooks/{webhook_id}", status_code=204)
async def delete_webhook(
    webhook_id: int,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(WebhookCallback).where(WebhookCallback.id == webhook_id))
    cb = result.scalar_one_or_none()
    if not cb:
        raise HTTPException(404, "Webhook callback not found")
    await db.delete(cb)
    await db.commit()
