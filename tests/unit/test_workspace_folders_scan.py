# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Unit tests for multi-root workspace scanning (workspace_folders)."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

from backend.api.servers.workspace_servers_discovery import _all_roots, _scan_all_roots


class TestAllRoots:
    def test_no_extra_folders(self):
        server = SimpleNamespace(workspace_root="/a", workspace_folders=None)
        assert _all_roots(server) == ["/a"]

    def test_extra_folders_appended(self):
        server = SimpleNamespace(workspace_root="/a", workspace_folders=["/b", "/c"])
        assert _all_roots(server) == ["/a", "/b", "/c"]

    def test_dedupes_root_in_extra_list(self):
        server = SimpleNamespace(workspace_root="/a", workspace_folders=["/a", "/b"])
        assert _all_roots(server) == ["/a", "/b"]

    def test_skips_empty_strings(self):
        server = SimpleNamespace(workspace_root="/a", workspace_folders=["", "/b"])
        assert _all_roots(server) == ["/a", "/b"]


class TestScanAllRoots:
    async def test_accumulates_across_roots(self):
        server = SimpleNamespace(workspace_root="/a", workspace_folders=["/b"])
        proj_discovery = SimpleNamespace(
            scan_workspace=AsyncMock(side_effect=[["repo1"], ["repo2", "repo3"]])
        )
        result = await _scan_all_roots(proj_discovery, server)
        assert result == ["repo1", "repo2", "repo3"]
        assert proj_discovery.scan_workspace.await_count == 2

    async def test_single_root(self):
        server = SimpleNamespace(workspace_root="/a", workspace_folders=None)
        proj_discovery = SimpleNamespace(scan_workspace=AsyncMock(return_value=["repo1"]))
        result = await _scan_all_roots(proj_discovery, server)
        assert result == ["repo1"]
        assert proj_discovery.scan_workspace.await_count == 1
