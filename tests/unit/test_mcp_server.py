# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

from unittest.mock import AsyncMock, patch

from fastmcp import Client

from backend.mcp.server import get_mcp_app


async def test_registered_tools_hide_injected_context():
    async with Client(get_mcp_app()) as client:
        tools = await client.list_tools()

    names = {tool.name for tool in tools}
    assert {"get_health", "create_run", "create_scheduled_task"} <= names
    for tool in tools:
        assert "ctx" not in tool.input_schema.get("properties", {})


async def test_tool_call_injects_context_and_serializes_result():
    api = AsyncMock(return_value={"status": "ok"})
    with patch("backend.mcp.tools.admin._api", api):
        async with Client(get_mcp_app()) as client:
            result = await client.call_tool("get_health", {})

    assert result.data == {"status": "ok"}
    api.assert_awaited_once()
    assert api.call_args.args[1:] == ("get", "/health")
