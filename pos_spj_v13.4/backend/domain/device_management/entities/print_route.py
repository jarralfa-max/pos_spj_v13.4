"""PrintRoute — SET-8 (§25): which printer a given document_type prints
to, in a given context (empresa/sucursal/estación/módulo/canal), with an
ordered failover chain if the primary printer is unavailable.

Deliberately keeps `document_type` as a plain validated string rather
than importing an enum from a `document_output` bounded context that
doesn't exist yet (SET-11 owns the full `DocumentType` taxonomy) — this
avoids a premature cross-context dependency in the wrong direction.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.device_management.exceptions import DeviceInvalidValueError
from backend.shared.ids import new_uuid, validate_uuidv7


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _validate_fallback_chain(primary_device_id: str, fallback_device_ids: tuple[str, ...]) -> tuple[str, ...]:
    validated = tuple(validate_uuidv7(device_id) for device_id in dict.fromkeys(fallback_device_ids))
    if primary_device_id in validated:
        raise DeviceInvalidValueError("primary_device_id no puede repetirse en fallback_device_ids")
    return validated


@dataclass(slots=True)
class PrintRoute:
    id: str
    document_type: str
    primary_device_id: str
    fallback_device_ids: tuple[str, ...] = ()
    branch_id: str | None = None
    workstation_id: str | None = None
    module: str | None = None
    channel: str | None = None
    active: bool = True
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    # construction ------------------------------------------------------------
    @classmethod
    def create(
        cls, *, document_type: str, primary_device_id: str, fallback_device_ids: tuple[str, ...] = (),
        branch_id: str | None = None, workstation_id: str | None = None, module: str | None = None,
        channel: str | None = None,
    ) -> "PrintRoute":
        if not document_type.strip():
            raise DeviceInvalidValueError("document_type es obligatorio")
        validated_primary = validate_uuidv7(primary_device_id)
        return cls(
            id=new_uuid(), document_type=document_type.strip().upper(), primary_device_id=validated_primary,
            fallback_device_ids=_validate_fallback_chain(validated_primary, fallback_device_ids),
            branch_id=validate_uuidv7(branch_id) if branch_id else None,
            workstation_id=validate_uuidv7(workstation_id) if workstation_id else None,
            module=module.strip() if module else None, channel=channel.strip() if channel else None,
        )

    def _touch(self) -> None:
        self.updated_at = _utcnow()

    # behavior ------------------------------------------------------------------
    def specificity(self) -> int:
        """How many routing dimensions this route pins down — used by
        `PrintRoutingService` to prefer the most specific match (§25)."""
        return sum(
            1 for value in (self.branch_id, self.workstation_id, self.module, self.channel)
            if value is not None
        )

    def matches(
        self, document_type: str, *, branch_id: str | None = None, workstation_id: str | None = None,
        module: str | None = None, channel: str | None = None,
    ) -> bool:
        if not self.active or self.document_type != document_type.strip().upper():
            return False
        return (
            (self.branch_id is None or self.branch_id == branch_id)
            and (self.workstation_id is None or self.workstation_id == workstation_id)
            and (self.module is None or self.module == module)
            and (self.channel is None or self.channel == channel)
        )

    def set_primary_device(self, device_id: str) -> None:
        validated = validate_uuidv7(device_id)
        if validated in self.fallback_device_ids:
            raise DeviceInvalidValueError("El nuevo primary_device_id no puede estar en fallback_device_ids")
        self.primary_device_id = validated
        self._touch()

    def set_fallback_chain(self, fallback_device_ids: tuple[str, ...]) -> None:
        self.fallback_device_ids = _validate_fallback_chain(self.primary_device_id, fallback_device_ids)
        self._touch()

    def activate(self) -> None:
        self.active = True
        self._touch()

    def deactivate(self) -> None:
        self.active = False
        self._touch()
