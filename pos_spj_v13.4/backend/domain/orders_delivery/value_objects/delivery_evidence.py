"""DeliveryEvidence (master prompt §38) — what a delivery attempt captures
to prove hand-over. Which fields are mandatory is a policy decision
(`DeliveryConfirmationPolicy`, ORD-19+/§72 configuration), not enforced by
this plain value object itself — it only holds whatever was captured.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DeliveryEvidence:
    recipient_name: str | None = None
    signature_reference: str | None = None
    photo_reference: str | None = None
    pin_verified: bool = False
    latitude: float | None = None
    longitude: float | None = None
    notes: str | None = None

    @property
    def is_empty(self) -> bool:
        return not any((
            self.recipient_name, self.signature_reference, self.photo_reference,
            self.pin_verified, self.latitude is not None, self.notes,
        ))
