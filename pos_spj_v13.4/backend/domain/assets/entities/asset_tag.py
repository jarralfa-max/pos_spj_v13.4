"""AssetTag — physical/QR/barcode tag attached to an asset (ASSET-13, §14, §49-51).

The QR never exposes the internal UUID directly (§14, §50) — ``qr_public_token``
is a distinct opaque identifier from ``asset_id``, generated the same
canonical way (``new_uuid()``) but never used to look up the asset by anyone
outside the tag-resolution path. ``tag_number`` is the human/commercial
identifier printed on the label; the entity's own ``id`` is the internal
UUIDv7, also never printed (§13's asset_number vs UUID distinction applies
here too).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.assets.enums import AssetTagStatus, AssetTagType
from backend.domain.assets.exceptions import AssetDomainError, AssetTagStateInvalidError
from backend.shared.ids import new_uuid

_TERMINAL = frozenset({AssetTagStatus.REPLACED, AssetTagStatus.VOID})


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class AssetTag:
    id: str
    asset_id: str
    tag_number: str
    qr_public_token: str
    tag_type: AssetTagType
    operation_id: str
    barcode_value: str | None = None
    status: AssetTagStatus = AssetTagStatus.ISSUED
    replaces_tag_id: str | None = None
    notes: str = ""
    issued_at: str = field(default_factory=_utcnow)
    printed_at: str | None = None
    replaced_at: str | None = None
    voided_at: str | None = None

    @classmethod
    def create(cls, asset_id: str, tag_number: str, operation_id: str, *,
               tag_type: AssetTagType = AssetTagType.QR,
               barcode_value: str | None = None,
               replaces_tag_id: str | None = None) -> "AssetTag":
        if not asset_id:
            raise AssetDomainError("AssetTag.asset_id is required")
        if not tag_number or not tag_number.strip():
            raise AssetDomainError("AssetTag.tag_number is required")
        return cls(
            id=new_uuid(), asset_id=asset_id, tag_number=tag_number.strip(),
            qr_public_token=new_uuid(), tag_type=tag_type, operation_id=operation_id,
            barcode_value=barcode_value, replaces_tag_id=replaces_tag_id,
        )

    def _assert_status(self, *allowed: AssetTagStatus) -> None:
        if self.status not in allowed:
            raise AssetTagStateInvalidError(
                f"No se puede continuar la etiqueta en estado {self.status.value}")

    def mark_printed(self) -> None:
        self._assert_status(AssetTagStatus.ISSUED, AssetTagStatus.PRINTED)
        self.status = AssetTagStatus.PRINTED
        self.printed_at = _utcnow()

    def activate(self) -> None:
        self._assert_status(AssetTagStatus.PRINTED)
        self.status = AssetTagStatus.ACTIVE

    def replace(self, reason: str = "") -> None:
        self._assert_status(AssetTagStatus.ACTIVE, AssetTagStatus.PRINTED, AssetTagStatus.ISSUED)
        self.status = AssetTagStatus.REPLACED
        self.replaced_at = _utcnow()
        if reason:
            self.notes = f"{self.notes}\n[REPLACED] {reason}".strip()

    def void(self, reason: str = "") -> None:
        if self.status in _TERMINAL:
            raise AssetTagStateInvalidError(
                f"No se puede anular una etiqueta en estado {self.status.value}")
        self.status = AssetTagStatus.VOID
        self.voided_at = _utcnow()
        if reason:
            self.notes = f"{self.notes}\n[VOID] {reason}".strip()

    def is_active(self) -> bool:
        return self.status is AssetTagStatus.ACTIVE
