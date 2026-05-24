#!/usr/bin/env python3
# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Host bridge daemon for AgenticKode.

Run this on your host (e.g. inside WSL) under your normal user account.
The dockerized backend talks to it over host.docker.internal so chat /
terminal / workflow commands actually run on the host.

Usage:
    pip install -r requirements-host.txt
    python scripts/host_bridge.py            # listens on 127.0.0.1:17777

On first start a random bearer token is written to
~/.agentickode/host-bridge.token (mode 0600). Paste it into the
"Bridge Token" field on the Platform server card.

Endpoints:
    GET  /health        — unauth ping
    POST /run           — one-shot subprocess (chat invocations)
    WS   /pty           — PTY session (terminal attach)

All non-/health endpoints require Authorization: Bearer <token>.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import logging
import os
import pty
import secrets
import struct
import sys
from pathlib import Path

import fcntl
import termios
import uvicorn
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

LOG_FMT = "%(asctime)s %(levelname)-7s %(name)s  %(message)s"
logging.basicConfig(level=logging.INFO, format=LOG_FMT)
logger = logging.getLogger("agentickode.host-bridge")


TOKEN_PATH = Path.home() / ".agentickode" / "host-bridge.token"


def load_or_create_token() -> str:
    """Read the bearer token, generating it on first start."""
    if TOKEN_PATH.exists():
        return TOKEN_PATH.read_text(encoding="utf-8").strip()
    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    token = secrets.token_urlsafe(32)
    TOKEN_PATH.write_text(token, encoding="utf-8")
    TOKEN_PATH.chmod(0o600)
    return token


class RunRequest(BaseModel):
    cmd: str
    env: dict[str, str] | None = None
    cwd: str | None = None
    timeout: int = 600
    stdin: str | None = None  # piped to the subprocess if set


class WriteTempfileRequest(BaseModel):
    content: str
    suffix: str = ""
    prefix: str = "agentickode-"


class WriteTempfileResponse(BaseModel):
    path: str


class RunResponse(BaseModel):
    stdout: str
    stderr: str
    exit_code: int


def create_app(token: str) -> FastAPI:
    app = FastAPI(title="AgenticKode Host Bridge", docs_url=None, redoc_url=None)

    def _require_token(request: Request) -> None:
        auth = request.headers.get("Authorization") or ""
        if not auth.startswith("Bearer "):
            raise HTTPException(401, "Missing bearer token")
        if not secrets.compare_digest(auth[len("Bearer ") :], token):
            raise HTTPException(401, "Invalid bearer token")

    @app.get("/health")
    async def health() -> dict[str, object]:
        return {
            "ok": True,
            "user": os.environ.get("USER") or os.environ.get("LOGNAME") or "?",
            "uid": os.getuid(),
            "home": str(Path.home()),
        }

    @app.post("/run", response_model=RunResponse)
    async def run_(req: RunRequest, request: Request) -> RunResponse:
        # Token-gated host-side command invocation. The cmd string is
        # interpolated via `bash -lc` so the host's login PATH is set
        # up (~/.bashrc) and Claude / agent binaries can be found.
        # Trust comes from the bearer token; the backend is the only
        # caller, and shell features are required for the agent CLIs.
        _require_token(request)

        full_env = {**os.environ, **(req.env or {})}
        argv = ["bash", "-lc", req.cmd]

        try:
            proc = await asyncio.create_subprocess_exec(
                *argv,
                stdin=asyncio.subprocess.PIPE if req.stdin is not None else None,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=req.cwd,
                env=full_env,
            )
        except FileNotFoundError as e:
            raise HTTPException(500, f"bash not found on host: {e}") from e

        try:
            stdin_b = req.stdin.encode("utf-8") if req.stdin is not None else None
            out_b, err_b = await asyncio.wait_for(
                proc.communicate(input=stdin_b), timeout=req.timeout
            )
        except TimeoutError:
            proc.kill()
            await proc.wait()
            raise HTTPException(504, f"command timed out after {req.timeout}s") from None

        return RunResponse(
            stdout=out_b.decode("utf-8", errors="replace"),
            stderr=err_b.decode("utf-8", errors="replace"),
            exit_code=proc.returncode or 0,
        )

    @app.post("/write_tempfile", response_model=WriteTempfileResponse)
    async def write_tempfile_(
        req: WriteTempfileRequest, request: Request
    ) -> WriteTempfileResponse:
        """Write content to a host-side temp file; return the path.

        Chat needs to drop the MCP config JSON on the host before invoking
        Claude (``claude --mcp-config <path>`` requires a file). We can't
        share a tempdir between container and host, so the backend posts
        the JSON here and the daemon writes it locally as the host user.
        """
        _require_token(request)
        import tempfile

        fd, path = tempfile.mkstemp(suffix=req.suffix, prefix=req.prefix)
        try:
            with os.fdopen(fd, "w") as f:
                f.write(req.content)
        except Exception as exc:
            raise HTTPException(500, f"failed to write tempfile: {exc}") from exc
        return WriteTempfileResponse(path=path)

    @app.websocket("/pty")
    async def pty_ws(websocket: WebSocket) -> None:
        # Token via query string — WebSocket headers from the backend
        # would work but query-string keeps things uniform.
        provided = websocket.query_params.get("token") or ""
        if not secrets.compare_digest(provided, token):
            await websocket.close(code=4401)
            return

        await websocket.accept()
        try:
            raw = await websocket.receive_text()
            spec = json.loads(raw)
        except Exception:
            await websocket.close(code=4400)
            return

        cmd = spec.get("cmd") or "bash --login"
        cols = int(spec.get("cols") or 120)
        rows = int(spec.get("rows") or 40)
        extra_env: dict[str, str] = spec.get("env") or {}

        pid, fd = pty.fork()
        if pid == 0:  # child
            full_env = {**os.environ, **extra_env}
            for k, v in full_env.items():
                os.environ[k] = v
            os.execvp("bash", ["bash", "-lc", cmd])

        def _set_size(c: int, r: int) -> None:
            with contextlib.suppress(Exception):
                fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", r, c, 0, 0))

        _set_size(cols, rows)

        loop = asyncio.get_running_loop()

        async def pty_to_ws() -> None:
            while True:
                try:
                    data = await loop.run_in_executor(None, os.read, fd, 4096)
                except OSError:
                    break
                if not data:
                    break
                try:
                    await websocket.send_text(
                        json.dumps({"type": "output", "data": data.decode("utf-8", "replace")})
                    )
                except Exception:
                    break

        async def ws_to_pty() -> None:
            try:
                while True:
                    raw_in = await websocket.receive_text()
                    msg = json.loads(raw_in)
                    if msg.get("type") == "input":
                        os.write(fd, msg["data"].encode("utf-8"))
                    elif msg.get("type") == "resize":
                        _set_size(int(msg.get("cols", cols)), int(msg.get("rows", rows)))
            except WebSocketDisconnect:
                pass
            except Exception:
                pass

        r_task = asyncio.create_task(pty_to_ws())
        w_task = asyncio.create_task(ws_to_pty())
        try:
            await asyncio.gather(r_task, w_task, return_exceptions=True)
        finally:
            r_task.cancel()
            w_task.cancel()
            with contextlib.suppress(OSError):
                os.close(fd)
            try:
                os.kill(pid, 9)
                os.waitpid(pid, 0)
            except (OSError, ChildProcessError):
                pass

    return app


def main() -> int:
    parser = argparse.ArgumentParser(description="AgenticKode host bridge daemon")
    parser.add_argument("--host", default="127.0.0.1", help="bind address")
    parser.add_argument("--port", type=int, default=17777, help="bind port")
    parser.add_argument(
        "--print-token", action="store_true", help="print the current token and exit"
    )
    args = parser.parse_args()

    token = load_or_create_token()

    if args.print_token:
        print(token)
        return 0

    logger.info(
        "Host bridge starting on %s:%d (user=%s, uid=%d)",
        args.host, args.port,
        os.environ.get("USER", "?"), os.getuid(),
    )
    logger.info("Token stored at %s — paste into the Platform server card", TOKEN_PATH)

    app = create_app(token)
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    sys.exit(main())
