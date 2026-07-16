"""Load heavyweight platform-specific dependencies only when a feature uses them."""

from __future__ import annotations

import importlib
from functools import lru_cache
from types import ModuleType


class OptionalDependencyError(RuntimeError):
    """A feature was invoked without its optional dependency installed."""


@lru_cache(maxsize=1)
def require_opencv() -> ModuleType:
    """Return ``cv2`` or raise an actionable feature-scoped error."""

    try:
        return importlib.import_module("cv2")
    except (ImportError, OSError) as exc:
        raise OptionalDependencyError(
            "OpenCV is only required for automatic slider image recognition. "
            "Install it with `uv sync --extra opencv` or "
            "`pip install -r requirements-opencv.txt`; otherwise complete "
            "slider verification manually in the headed/CDP browser."
        ) from exc
