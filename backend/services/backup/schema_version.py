# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Export envelope schema versioning."""

CURRENT_SCHEMA_VERSION = "1.0.0"

COMPATIBLE_VERSIONS = {"1.0.0"}


def validate_schema_version(version: str) -> None:
    """Raise ValueError if *version* is not importable."""
    if version not in COMPATIBLE_VERSIONS:
        supported = ", ".join(sorted(COMPATIBLE_VERSIONS))
        raise ValueError(
            f"Unsupported schema version '{version}'. " f"Compatible versions: {supported}"
        )