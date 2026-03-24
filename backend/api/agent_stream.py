# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""SSE endpoint for real-time autonomous agent activity streaming."""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter
from sqlalchemy import select
from starlette.responses import StreamingResponse

from backend.database import async_session
from backend.models import AgentLoopExecution, TaskRun
from backend.models.episodes import Episode
from backend.services.stream_monitor import poll_stream
from backend.worker.phases._helpers import get_ssh_for_run

router = APIRouter(tags=["agent-stream"])


@router.get("/runs/{run_id}/agent-stream")
async def stream_agent_output(run_id: int):
    """SSE endpoint streaming real-time agent activity from stream-json."""

    async def event_generator():
        offset = 1
        async with async_session() as session:
            run = await session.get(TaskRun, run_id)
            if not run:
                yield f"data: {json.dumps({'error': 'Run not found'})}\n\n"
                return

            try:
                ssh = await get_ssh_for_run(run, session)
            except Exception as exc:
                yield f"data: {json.dumps({'error': str(exc)})}\n\n"
                return

            workspace = run.workspace_path or ""

            # Find active episode
            ep_result = await session.execute(
                select(Episode)
                .join(AgentLoopExecution)
                .where(
                    AgentLoopExecution.task_run_id == run_id,
                    Episode.status == "running",
                )
                .order_by(Episode.episode_number.desc())
                .limit(1)
            )
            episode = ep_result.scalar_one_or_none()

            if episode:
                jsonl_path = f"{workspace}/.autodev/episode_{episode.episode_number}.jsonl"
            else:
                jsonl_path = f"{workspace}/.autodev/claude_output.jsonl"

        try:
            while True:
                try:
                    async with async_session() as session:
                        run = await session.get(TaskRun, run_id)
                        if not run or run.status not in ("running", "waiting_for_trigger"):
                            yield f"data: {json.dumps({'type': 'done', 'status': run.status if run else 'unknown'})}\n\n"
                            return

                        ssh = await get_ssh_for_run(run, session)
                        poll_result = await poll_stream(ssh, jsonl_path, offset)

                    if poll_result.new_lines > 0:
                        offset = poll_result.next_offset
                        yield f"data: {json.dumps({'type': 'progress', 'turns': poll_result.turn_count, 'context_pct': poll_result.context_usage_pct, 'completed': poll_result.completed})}\n\n"

                    if poll_result.completed:
                        yield f"data: {json.dumps({'type': 'done', 'result': poll_result.result_text[:500]})}\n\n"
                        return

                    await asyncio.sleep(3)
                except TimeoutError:
                    yield ": keepalive\n\n"
        except asyncio.CancelledError:
            pass

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/runs/{run_id}/episodes")
async def list_episodes(run_id: int):
    """List all episodes for a task run."""
    async with async_session() as session:
        result = await session.execute(
            select(Episode)
            .join(AgentLoopExecution)
            .where(AgentLoopExecution.task_run_id == run_id)
            .order_by(Episode.episode_number)
        )
        episodes = result.scalars().all()

        return [
            {
                "id": ep.id,
                "episode_number": ep.episode_number,
                "status": ep.status,
                "turn_count": ep.turn_count,
                "tokens_used": ep.tokens_used,
                "context_usage_pct": ep.context_usage_pct,
                "git_checkpoint_sha": ep.git_checkpoint_sha,
                "started_at": ep.started_at.isoformat() if ep.started_at else None,
                "completed_at": ep.completed_at.isoformat() if ep.completed_at else None,
                "exit_code": ep.exit_code,
                "summary": ep.summary,
            }
            for ep in episodes
        ]
