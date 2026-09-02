"""ModuleLoadState — SHELL-13."""
from __future__ import annotations

from enum import Enum


class ModuleLoadState(str, Enum):
    NOT_LOADED = "NOT_LOADED"
    LOADING = "LOADING"
    LOADED = "LOADED"
    FAILED = "FAILED"
