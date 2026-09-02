"""Shared request-schema building blocks for every mobile PWA router
(`backend/api/routers/*.py`) — extracted from `mobile_logistics.py` (the
first mobile router built) once a second one (`driver_logistics.py`, ORD-25)
needed the exact same `MobileCommand`/`LoginRequest`/`Uuid7`/`DecimalText`
shapes. None of these carry any procurement-specific field, so duplicating
them per bounded context would have been drift waiting to happen.
"""

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


class MobileCommand(BaseModel):
    clientOperationId: Uuid7
    deviceId: str = Field(min_length=1, max_length=200)
    userId: Uuid7
    createdAt: str
    payloadVersion: Literal[1]
