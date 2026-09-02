from __future__ import annotations

from typing import Literal

from pydantic import Field

from backend.api.schemas.mobile_common import (
    DECIMAL,
    UUID7,
    DecimalText,
    LoginRequest,
    MobileCommand,
    Uuid7,
)

__all__ = [
    "DECIMAL", "UUID7", "DecimalText", "LoginRequest", "MobileCommand", "Uuid7",
    "ShipmentCreateRequest", "NodeAttachRequest", "ContentAssignmentRequest",
    "PhotoUploadRequest", "SealRequest", "DispatchRequest",
]


class ShipmentCreateRequest(MobileCommand):
    shipmentId: Uuid7
    documentType: Literal["PURCHASE_ORDER", "DIRECT_PURCHASE", "PURCHASE_REQUISITION"]
    documentId: Uuid7
    supplierId: Uuid7 | None = None


class NodeAttachRequest(MobileCommand):
    nodeId: Uuid7
    containerToken: str = Field(min_length=20, max_length=1000)
    parentNodeId: Uuid7 | None = None


class ContentAssignmentRequest(MobileCommand):
    id: Uuid7
    nodeId: Uuid7
    productId: Uuid7
    sourceLineId: Uuid7
    quantity: DecimalText
    netWeight: DecimalText
    unitCost: DecimalText
    lotNumber: str | None = None
    expirationDate: str | None = None
    temperature: DecimalText | None = None
    photoIds: list[Uuid7] = Field(default_factory=list)


class PhotoUploadRequest(MobileCommand):
    assignmentId: Uuid7
    contentBase64: str
    fileName: str = Field(max_length=255)
    contentType: str


class SealRequest(MobileCommand):
    sealCode: str = Field(min_length=1, max_length=200)
    sealType: str = Field(min_length=1, max_length=100)


class DispatchRequest(MobileCommand):
    pass
