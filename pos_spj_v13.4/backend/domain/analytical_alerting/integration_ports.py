"""Outbound integration ports for analytical_alerting (§51-55/§118-120, BI-21).

BI never sends a WhatsApp message directly and never resolves recipients by
role-name comparison (`if rol == "..."`) — both violations the master
prompt calls out explicitly (§52/§54). The real notification stack already
in this repo (a role-based recipient resolver and a generic staff-dispatch
orchestrator under `core/services/notifications/`) is what an
infrastructure adapter implementing these two ports wraps — nothing in
`backend/domain/analytical_alerting` or
`backend/application/analytical_alerting` may import that delivery stack
concretely; see
`tests/architecture/test_analytical_alerting_never_imports_notification_infra_directly.py`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from backend.domain.analytical_alerting.enums import AlertType
from backend.domain.analytical_alerting.value_objects.alert import AnalyticalAlert
from backend.domain.notifications.enums import NotificationChannel


@dataclass(frozen=True, slots=True)
class AlertRecipient:
    user_id: str
    display_name: str
    phone_e164: str | None = None

    def __post_init__(self) -> None:
        if not self.user_id or not self.display_name:
            raise ValueError("AlertRecipient requires user_id and display_name")


class AlertRecipientResolverPort(Protocol):
    """§118 — resolves *candidates* by permission/role/scope. Never a
    hardcoded role-name comparison; a real adapter delegates to the
    existing role-based recipient-resolution service by alert type and
    branch."""

    def resolve(self, alert_type: AlertType, branch_id: str) -> tuple[AlertRecipient, ...]: ...


class AlertDispatchPort(Protocol):
    """A real adapter delegates to the existing generic staff-dispatch
    orchestrator for `IN_APP`/`WHATSAPP` and equivalents for other
    channels — this port never touches the WhatsApp delivery service
    itself."""

    def dispatch(
        self,
        alert: AnalyticalAlert,
        recipients: tuple[AlertRecipient, ...],
        channel: NotificationChannel,
    ) -> None: ...
