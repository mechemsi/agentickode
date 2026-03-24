# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Output formatters for the CLI — table, JSON, and quiet modes."""

from __future__ import annotations

import json
import sys

import click


def _ctx() -> dict:
    ctx = click.get_current_context()
    return ctx.obj or {}


def output_json(data) -> None:
    """Print data as formatted JSON."""
    click.echo(json.dumps(data, indent=2, default=str))


def output_quiet(value) -> None:
    """Print a single value (ID, status, etc.)."""
    click.echo(value)


def output_table(rows: list[dict], columns: list[tuple[str, str, int]]) -> None:
    """Print a simple aligned table.

    columns: list of (key, header, width) tuples.
    """
    # Header
    header = "  ".join(h.ljust(w) for _, h, w in columns)
    click.echo(header)
    click.echo("-" * len(header))

    for row in rows:
        parts = []
        for key, _, width in columns:
            val = str(row.get(key, ""))
            if len(val) > width:
                val = val[: width - 1] + "\u2026"
            parts.append(val.ljust(width))
        click.echo("  ".join(parts))


def output_item(data: dict, fields: list[tuple[str, str]]) -> None:
    """Print a single item with labeled fields.

    fields: list of (key, label) tuples.
    """
    max_label = max(len(label) for _, label in fields) if fields else 0
    for key, label in fields:
        val = data.get(key, "")
        click.echo(f"  {label.ljust(max_label)}  {val}")


def output(data, *, columns=None, fields=None, quiet_key=None) -> None:
    """Smart output dispatcher based on CLI flags."""
    opts = _ctx()

    if opts.get("json"):
        output_json(data)
        return

    if opts.get("quiet") and quiet_key:
        if isinstance(data, list):
            for item in data:
                output_quiet(item.get(quiet_key, ""))
        else:
            output_quiet(data.get(quiet_key, ""))
        return

    if isinstance(data, list) and columns:
        output_table(data, columns)
    elif isinstance(data, dict) and fields:
        output_item(data, fields)
    else:
        output_json(data)


def error(msg: str) -> None:
    """Print an error message and exit."""
    click.echo(f"Error: {msg}", err=True)
    sys.exit(1)
