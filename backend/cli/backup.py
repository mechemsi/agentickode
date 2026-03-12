# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""CLI for backup export / import.

Usage:
    python -m backend.cli.backup export --output backup.json --secret-mode encrypted --password xxx
    python -m backend.cli.backup import --input backup.json --conflict-resolution skip --password xxx --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from backend.services.backup.secret_handler import SecretMode


async def _run_export(args: argparse.Namespace) -> None:
    from backend.database import async_session
    from backend.services.backup.export_service import ExportService

    mode = SecretMode(args.secret_mode)
    entity_types = args.entity_types.split(",") if args.entity_types else None

    async with async_session() as session:
        svc = ExportService(session)
        if args.project_id:
            envelope = await svc.export_project(
                project_id=args.project_id,
                secret_mode=mode,
                password=args.password,
            )
        else:
            envelope = await svc.export_config(
                entity_types=entity_types,
                secret_mode=mode,
                password=args.password,
            )

    output = json.dumps(envelope, indent=2, default=str)
    if args.output:
        with open(args.output, "w") as f:
            f.write(output)
        print(f"Exported to {args.output}")
    else:
        print(output)


async def _run_import(args: argparse.Namespace) -> None:
    from backend.database import async_session
    from backend.services.backup.import_service import ImportService

    with open(args.input) as f:
        data = json.load(f)

    entity_types = args.entity_types.split(",") if args.entity_types else None

    async with async_session() as session:
        svc = ImportService(session)
        if args.dry_run:
            result = await svc.preview(
                data=data,
                entity_types=entity_types,
                password=args.password,
            )
            print(json.dumps(result, indent=2))
        else:
            result = await svc.execute(
                data=data,
                entity_types=entity_types,
                conflict_resolution=args.conflict_resolution,
                password=args.password,
            )
            print(json.dumps(result, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="AutoDev backup CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    # Export
    exp = sub.add_parser("export", help="Export configuration")
    exp.add_argument("--output", "-o", help="Output file path")
    exp.add_argument(
        "--secret-mode", default="redacted", choices=["plaintext", "redacted", "encrypted"]
    )
    exp.add_argument("--password", "-p", help="Encryption password")
    exp.add_argument("--project-id", help="Export single project + deps")
    exp.add_argument("--entity-types", help="Comma-separated entity types")

    # Import
    imp = sub.add_parser("import", help="Import configuration")
    imp.add_argument("--input", "-i", required=True, help="Input file path")
    imp.add_argument("--conflict-resolution", default="skip", choices=["skip", "overwrite"])
    imp.add_argument("--password", "-p", help="Decryption password")
    imp.add_argument("--entity-types", help="Comma-separated entity types")
    imp.add_argument("--dry-run", action="store_true", help="Preview without importing")

    args = parser.parse_args()

    if args.command == "export":
        asyncio.run(_run_export(args))
    elif args.command == "import":
        asyncio.run(_run_import(args))
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()