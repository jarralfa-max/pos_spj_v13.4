"""Short-lived signed mobile sessions; credentials remain in canonical AuthService."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import time
from dataclasses import asdict, dataclass
from typing import Protocol

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer


@dataclass(frozen=True, slots=True)
class MobileIdentity:
    user_id: str
    display_name: str
    branch_id: str
    branch_name: str
    warehouse_id: str
    warehouse_name: str
    device_id: str
    permissions: tuple[str, ...]


class CredentialVerifier(Protocol):
    def authenticate_mobile(self, username: str, password: str,
                            device_id: str) -> MobileIdentity | None: ...


class MobileSessionTokenService:
    def __init__(self, secret: bytes, verifier: CredentialVerifier,
                 *, lifetime_seconds: int = 900) -> None:
        if len(secret) < 32:
            raise ValueError("Mobile session secret must contain at least 32 bytes")
        self._secret = secret
        self._verifier = verifier
        self._lifetime = lifetime_seconds

    def login(self, username: str, password: str, device_id: str) -> tuple[str, MobileIdentity]:
        identity = self._verifier.authenticate_mobile(username, password, device_id)
        if identity is None or not identity.user_id or not identity.branch_id or not identity.warehouse_id:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Credenciales o contexto inválidos")
        now = int(time.time())
        payload = {**asdict(identity), "permissions": list(identity.permissions),
                   "iat": now, "exp": now + self._lifetime}
        encoded = self._encode(json.dumps(payload, separators=(",", ":")).encode())
        signature = self._encode(hmac.new(self._secret, encoded.encode(), hashlib.sha256).digest())
        return f"{encoded}.{signature}", identity

    def verify(self, token: str) -> MobileIdentity:
        try:
            encoded, signature = token.split(".", 1)
            expected = self._encode(hmac.new(
                self._secret, encoded.encode(), hashlib.sha256).digest())
            if not hmac.compare_digest(expected, signature):
                raise ValueError("signature")
            payload = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
            if int(payload["exp"]) <= int(time.time()):
                raise ValueError("expired")
            return MobileIdentity(
                payload["user_id"], payload["display_name"], payload["branch_id"],
                payload["branch_name"], payload["warehouse_id"], payload["warehouse_name"],
                payload["device_id"], tuple(payload["permissions"]))
        except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sesión móvil inválida") from exc

    @staticmethod
    def _encode(value: bytes) -> str:
        return base64.urlsafe_b64encode(value).decode().rstrip("=")


bearer = HTTPBearer(auto_error=False)


def mobile_identity(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> MobileIdentity:
    """The shared `Depends(mobile_identity)` every mobile router should use.

    Fixed a real, previously-dormant bug here: `credentials` used to default
    to a plain `None` instead of `Depends(bearer)`, which means FastAPI
    never actually extracted the `Authorization` header for it — nothing
    caught this because no router used `mobile_identity` directly yet;
    `routers/mobile_logistics.py` worked around it by defining its own
    private, correctly-wired copy of this same function instead."""
    service = getattr(request.app.state, "mobile_session_service", None)
    if service is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Sesión móvil no configurada")
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Bearer token requerido")
    return service.verify(credentials.credentials)


_UUID7_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")


def mutation_headers(idempotency_key: str = Header(alias="Idempotency-Key"),
                     if_match: str = Header(alias="If-Match")) -> tuple[str, int]:
    """Shared `Idempotency-Key`/`If-Match` validation for any mobile router's
    mutating endpoints — extracted from `routers/mobile_logistics.py` once
    `routers/driver_logistics.py` (ORD-25) needed the identical check."""
    if not _UUID7_RE.fullmatch(idempotency_key):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Idempotency-Key debe ser UUIDv7 minúscula")
    try:
        version = int(if_match)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "If-Match debe contener la versión del agregado") from exc
    if version < 0:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Versión inválida")
    return idempotency_key, version


def idempotency_key_header(idempotency_key: str = Header(alias="Idempotency-Key")) -> str:
    """`Idempotency-Key`-only validation, for mobile routers whose domain
    has no optimistic-concurrency `version` field to pair it with an
    `If-Match` header (Pedidos/Delivery's aggregates don't carry one, unlike
    the shipment/container aggregates `mutation_headers` was built for)."""
    if not _UUID7_RE.fullmatch(idempotency_key):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Idempotency-Key debe ser UUIDv7 minúscula")
    return idempotency_key


def command_payload(command, user: MobileIdentity, operation_id: str) -> dict:
    """Shared mutation-command validation: the body's own
    `clientOperationId` must match the `Idempotency-Key` header, and
    `userId`/`deviceId` must match the signed session — a command can never
    silently act on behalf of a different session. Extracted from
    `routers/mobile_logistics.py` for the same reason as `mutation_headers`."""
    payload = command.model_dump()
    if payload["clientOperationId"] != operation_id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "clientOperationId no coincide con Idempotency-Key")
    if payload["userId"] != user.user_id or payload["deviceId"] != user.device_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "El comando no pertenece a la sesión móvil")
    return payload
