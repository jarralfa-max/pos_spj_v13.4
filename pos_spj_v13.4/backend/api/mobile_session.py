"""Short-lived signed mobile sessions; credentials remain in canonical AuthService."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import asdict, dataclass
from typing import Protocol

from fastapi import HTTPException, Request, status
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


def mobile_identity(request: Request,
                    credentials: HTTPAuthorizationCredentials | None = None) -> MobileIdentity:
    service = getattr(request.app.state, "mobile_session_service", None)
    if service is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Sesión móvil no configurada")
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Bearer token requerido")
    return service.verify(credentials.credentials)
