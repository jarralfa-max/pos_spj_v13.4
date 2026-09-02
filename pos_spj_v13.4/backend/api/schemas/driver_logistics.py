"""Request schemas for the driver PWA API (ORD-25 §1 "API"). Mirrors
`backend/api/schemas/mobile_logistics.py`'s own `MobileCommand`-per-mutation
shape, now via the shared `mobile_common` base extracted for this."""

from __future__ import annotations

from pydantic import Field

from backend.api.schemas.mobile_common import DecimalText, MobileCommand

__all__ = [
    "AcceptAssignmentRequest", "RejectAssignmentRequest", "DispatchRequest", "DepartRequest",
    "ArriveRequest", "RecordAttemptRequest", "RecordCashCollectionRequest",
]


class AcceptAssignmentRequest(MobileCommand):
    pass


class RejectAssignmentRequest(MobileCommand):
    pass


class DispatchRequest(MobileCommand):
    pass


class DepartRequest(MobileCommand):
    pass


class ArriveRequest(MobileCommand):
    pass


class RecordAttemptRequest(MobileCommand):
    successful: bool
    recipientName: str | None = None
    signatureReference: str | None = None
    photoReference: str | None = None
    pinVerified: bool = False
    latitude: float | None = None
    longitude: float | None = None
    notes: str | None = None
    failureReason: str | None = None


class RecordCashCollectionRequest(MobileCommand):
    collectedAmount: DecimalText
    reference: str | None = Field(default=None, max_length=200)
