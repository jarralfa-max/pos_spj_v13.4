"""OfflinePolicy — SHELL-9 §45.

§45 lists `offline_policy` as a required `RouteDefinition` field but the
master plan doesn't enumerate its values anywhere in the sections
available — these three are a reasonable, minimal reading consistent with
the app's offline-first stance (§2) and `ApplicationContext.offline_status`
(SHELL-6): a route either works with no connectivity, requires it outright
(e.g. a WhatsApp-integration screen), or works with visibly reduced
functionality. Enforcing this against actual connectivity is
`DesktopRouter`'s job (SHELL-10) — this is only the declarative value.
"""
from __future__ import annotations

from enum import Enum


class OfflinePolicy(str, Enum):
    AVAILABLE_OFFLINE = "AVAILABLE_OFFLINE"
    DEGRADED_OFFLINE = "DEGRADED_OFFLINE"
    REQUIRES_ONLINE = "REQUIRES_ONLINE"
