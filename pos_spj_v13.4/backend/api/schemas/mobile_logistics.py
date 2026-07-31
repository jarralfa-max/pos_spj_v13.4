from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field


UUID7 = r"^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
DECIMAL = r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$"
Uuid7 = Annotated[str, Field(pattern=UUID7)]
DecimalText = Annotated[str, Field(pattern=DECIMAL)]


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=300)
    deviceId: str = Field(min_length=1, max_length=200)


class ShipmentCreateRequest(BaseModel):
    shipmentId: Uuid7
    documentType: Literal["PURCHASE_ORDER", "DIRECT_PURCHASE", "PURCHASE_REQUISITION"]
    documentId: Uuid7
    supplierId: Uuid7 | None = None


class NodeAttachRequest(BaseModel):
    nodeId: Uuid7
    containerToken: str = Field(min_length=20, max_length=1000)
    parentNodeId: Uuid7 | None = None


class ContentAssignmentRequest(BaseModel):
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


class PhotoUploadRequest(BaseModel):
    assignmentId: Uuid7
    contentBase64: str
    fileName: str = Field(max_length=255)
    contentType: str


class SealRequest(BaseModel):
    sealCode: str = Field(min_length=1, max_length=200)
    sealType: str = Field(min_length=1, max_length=100)
