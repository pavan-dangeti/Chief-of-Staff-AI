"""User-facing configuration errors and optional-dependency loading."""

from __future__ import annotations

import importlib
from types import ModuleType


class ConfigurationError(RuntimeError):
    """The environment cannot run the requested feature (missing key or extra)."""


def require_extra(module: str, extra: str) -> ModuleType:
    """Import an optional dependency, or explain exactly which extra installs it."""
    try:
        return importlib.import_module(module)
    except ImportError as exc:
        raise ConfigurationError(
            f"this feature needs the '{extra}' extra: pip install 'chief-of-staff-ai[{extra}]'"
        ) from exc
