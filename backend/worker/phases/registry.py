# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Auto-discovery registry for pipeline phase modules.

Scans ``backend.worker.phases`` for modules that expose a ``run()`` coroutine
and collects optional ``PHASE_META`` metadata from each.
"""

from __future__ import annotations

import importlib
import logging
import pkgutil
from dataclasses import dataclass
from types import ModuleType

logger = logging.getLogger("agentickode.phases.registry")

# Modules whose file name starts with ``_`` are internal helpers, not phases.
# The registry itself is also excluded.
_SKIP_MODULES = {"registry"}

# Backward-compat: the *module* ``init_phase`` exposes phase name ``"init"``.
_NAME_OVERRIDES: dict[str, str] = {
    "init_phase": "init",
}


@dataclass(frozen=True)
class PhaseInfo:
    """Describes a discovered pipeline phase."""

    name: str
    module: ModuleType
    description: str = ""
    default_role: str | None = None
    default_agent_mode: str | None = None


_cache: dict[str, PhaseInfo] | None = None


def discover_phases() -> dict[str, PhaseInfo]:
    """Return ``{phase_name: PhaseInfo}`` for every valid phase module.

    Results are cached after the first call.
    """
    global _cache
    if _cache is not None:
        return _cache

    import backend.worker.phases as _pkg

    result: dict[str, PhaseInfo] = {}
    for _importer, mod_name, _ispkg in pkgutil.iter_modules(_pkg.__path__):
        if mod_name.startswith("_") or mod_name in _SKIP_MODULES:
            continue
        try:
            mod = importlib.import_module(f"backend.worker.phases.{mod_name}")
        except Exception:
            logger.warning("Failed to import phase module '%s'", mod_name, exc_info=True)
            continue

        run_fn = getattr(mod, "run", None)
        if not callable(run_fn):
            continue

        meta: dict = getattr(mod, "PHASE_META", {})
        phase_name = meta.get("name") or _NAME_OVERRIDES.get(mod_name, mod_name)

        result[phase_name] = PhaseInfo(
            name=phase_name,
            module=mod,
            description=meta.get("description", ""),
            default_role=meta.get("default_role"),
            default_agent_mode=meta.get("default_agent_mode"),
        )

    _cache = result
    logger.debug("Discovered %d phases: %s", len(result), sorted(result))
    return result


def _reset_cache() -> None:
    """Clear the cached registry (used by tests)."""
    global _cache
    _cache = None
