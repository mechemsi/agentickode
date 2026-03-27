# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Obsidian vault sync — read/write markdown knowledge to/from Obsidian vaults."""

import logging
import re

import httpx

logger = logging.getLogger("agentickode.memory.obsidian")

# Default Obsidian Local REST API port
_DEFAULT_OBSIDIAN_URL = "http://localhost:27124"


class ObsidianSyncService:
    """Read from and write to Obsidian vaults via the Local REST API plugin."""

    def __init__(self, client: httpx.AsyncClient, api_url: str = "", api_key: str = ""):
        self._client = client
        self._api_url = (api_url or _DEFAULT_OBSIDIAN_URL).rstrip("/")
        self._headers = {}
        if api_key:
            self._headers["Authorization"] = f"Bearer {api_key}"

    async def list_files(self, folder: str = "/") -> list[str]:
        """List markdown files in a vault folder."""
        try:
            resp = await self._client.get(
                f"{self._api_url}/vault/{folder.strip('/')}/",
                headers={**self._headers, "Accept": "application/json"},
            )
            if resp.status_code != 200:
                return []
            data = resp.json()
            files = data.get("files", [])
            return [f for f in files if f.endswith(".md")]
        except Exception:
            logger.exception("Failed to list Obsidian files")
            return []

    async def read_file(self, path: str) -> str:
        """Read a markdown file from the vault."""
        try:
            resp = await self._client.get(
                f"{self._api_url}/vault/{path.strip('/')}",
                headers={**self._headers, "Accept": "text/markdown"},
            )
            if resp.status_code != 200:
                return ""
            return resp.text
        except Exception:
            logger.exception("Failed to read Obsidian file %s", path)
            return ""

    async def write_file(self, path: str, content: str) -> bool:
        """Write/overwrite a markdown file in the vault."""
        try:
            resp = await self._client.put(
                f"{self._api_url}/vault/{path.strip('/')}",
                headers={**self._headers, "Content-Type": "text/markdown"},
                content=content,
            )
            return resp.status_code in (200, 201, 204)
        except Exception:
            logger.exception("Failed to write Obsidian file %s", path)
            return False

    async def append_to_file(self, path: str, content: str) -> bool:
        """Append content to an existing vault file."""
        try:
            resp = await self._client.post(
                f"{self._api_url}/vault/{path.strip('/')}",
                headers={
                    **self._headers,
                    "Content-Type": "text/markdown",
                    "X-Insert-Position": "end",
                },
                content=content,
            )
            return resp.status_code in (200, 201, 204)
        except Exception:
            logger.exception("Failed to append to Obsidian file %s", path)
            return False

    def split_by_headings(self, content: str, path: str = "") -> list[dict]:
        """Split markdown content into sections by headings.

        Returns list of {"heading": str, "content": str, "path": str, "level": int}.
        """
        sections: list[dict] = []
        current_heading = "Introduction"
        current_level = 0
        current_lines: list[str] = []

        for line in content.split("\n"):
            heading_match = re.match(r"^(#{1,6})\s+(.+)", line)
            if heading_match:
                # Save previous section
                if current_lines:
                    text = "\n".join(current_lines).strip()
                    if text:
                        sections.append(
                            {
                                "heading": current_heading,
                                "content": text,
                                "path": path,
                                "level": current_level,
                            }
                        )
                current_level = len(heading_match.group(1))
                current_heading = heading_match.group(2).strip()
                current_lines = []
            else:
                current_lines.append(line)

        # Save last section
        if current_lines:
            text = "\n".join(current_lines).strip()
            if text:
                sections.append(
                    {
                        "heading": current_heading,
                        "content": text,
                        "path": path,
                        "level": current_level,
                    }
                )

        return sections
