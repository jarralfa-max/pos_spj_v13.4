"""Signed permanent QR identity; payload contains no commercial data."""

from __future__ import annotations

import base64
import hashlib
import hmac

from backend.domain.logistics.entities import PhysicalContainer
from backend.domain.logistics.exceptions import LogisticsDomainError


class PermanentContainerQrService:
    def __init__(self, secret: bytes, *, base_url: str = "https://app.spj.mx/c") -> None:
        if len(secret) < 32:
            raise ValueError("QR signing secret must contain at least 32 bytes")
        self._secret = secret
        self._base_url = base_url.rstrip("/")

    def issue(self, container: PhysicalContainer) -> str:
        payload = f"{container.id}.{container.qr_version}"
        signature = hmac.new(self._secret, payload.encode(), hashlib.sha256).digest()
        encoded = base64.urlsafe_b64encode(signature).decode().rstrip("=")
        container.qr_signature = encoded
        return f"{self._base_url}/{payload}.{encoded}"

    def resolve(self, token_or_url: str) -> tuple[str, int]:
        token = token_or_url.rsplit("/", 1)[-1]
        try:
            container_id, version_text, signature = token.split(".", 2)
            version = int(version_text)
        except (ValueError, TypeError) as exc:
            raise LogisticsDomainError("QR de contenedor inválido") from exc
        payload = f"{container_id}.{version}"
        expected = base64.urlsafe_b64encode(
            hmac.new(self._secret, payload.encode(), hashlib.sha256).digest()
        ).decode().rstrip("=")
        if not hmac.compare_digest(expected, signature):
            raise LogisticsDomainError("Firma QR inválida")
        return container_id, version

    def validate(self, token_or_url: str, container: PhysicalContainer) -> bool:
        container_id, version = self.resolve(token_or_url)
        return (container_id == container.id and version == container.qr_version
                and token_or_url.rsplit(".", 1)[-1] == container.qr_signature)
