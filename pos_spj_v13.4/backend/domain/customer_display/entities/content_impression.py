"""ContentImpression — SET-18 "Metrics": one recorded instance of a
`CampaignPlacement` actually being shown on screen. Append-only, no
lifecycle of its own — mirrors the "record, don't mutate" shape
`backend.domain.device_management.entities.device_test_result.
DeviceTestResult` already established for diagnostic logs (SET-9).

No real customer display exists to generate real impressions yet (same
situation `gateway_ports.CustomerDisplayGatewayPort`, SET-17, is honest
about) — this entity is the recording capability a future gateway
consumer would call into, not a claim that real metrics exist today.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.customer_display.exceptions import CustomerDisplayInvalidValueError
from backend.shared.ids import new_uuid, validate_uuidv7


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class ContentImpression:
    id: str
    placement_id: str
    duration_shown_seconds: int
    displayed_at: str = field(default_factory=_utcnow)

    @classmethod
    def record(cls, *, placement_id: str, duration_shown_seconds: int) -> "ContentImpression":
        if (
            isinstance(duration_shown_seconds, bool) or not isinstance(duration_shown_seconds, int)
            or duration_shown_seconds < 0
        ):
            raise CustomerDisplayInvalidValueError(
                f"duration_shown_seconds debe ser un entero >= 0, recibido {duration_shown_seconds!r}"
            )
        return cls(id=new_uuid(), placement_id=validate_uuidv7(placement_id), duration_shown_seconds=duration_shown_seconds)
