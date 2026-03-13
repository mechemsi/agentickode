# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Server-Sent Events endpoint for live run updates."""

import asyncio
import json

from fastapi import APIRouter
from starlette.responses import StreamingResponse

from backend.worker.broadcaster import broadcaster

router = APIRouter(tags=["sse"])


@router.get("/runs/stream")
async def stream_events():
    """SSE endpoint that streams global run events."""
    queue: asyncio.Queue = asyncio.Queue(maxsize=64)
    broadcaster.subscribe_global(queue)

    async def event_generator():
        try:
            while True:
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield f"data: {json.dumps(payload)}\n\n"
                except TimeoutError:
                    yield ": keepalive\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            broadcaster.unsubscribe_global(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
