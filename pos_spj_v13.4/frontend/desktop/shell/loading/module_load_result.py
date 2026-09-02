"""ModuleLoadResult — SHELL-13."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from frontend.desktop.shell.loading.module_load_state import ModuleLoadState


@dataclass(frozen=True)
class ModuleLoadResult:
    module_id: str
    state: ModuleLoadState
    error: BaseException | None
    loaded_at: datetime | None
