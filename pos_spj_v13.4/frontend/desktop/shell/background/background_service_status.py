"""BackgroundServiceStatus — SHELL-14.

`BackgroundServiceSupervisor`'s per-service snapshot — presentation/inspection
shape, same role `NavigationResult` (SHELL-10) and `SidebarItemViewModel`
(SHELL-12) play for their own subsystems. Holds no live reference back to
the supervisor.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from frontend.desktop.shell.background.background_service_state import BackgroundServiceState
from frontend.desktop.shell.background.service_crash import ServiceCrash


@dataclass(frozen=True)
class BackgroundServiceStatus:
    service_id: str
    state: BackgroundServiceState
    crashes: tuple[ServiceCrash, ...]
    last_error: BaseException | None
    started_at: datetime | None
