"""Identidad QR permanente del contenedor; el contenido no lleva datos comerciales.

Contenido impreso: ``SPJC/<id>.<versión>.<firma>`` (versión 2026-10-17). La
firma es un HMAC que se genera UNA vez al emitir y se GUARDA en el contenedor
(`qr_signature`). Validar una etiqueta es compararla con lo guardado
(`matches`), no recalcular el HMAC: el secreto vive en el almacén de secretos
de Windows, que es POR USUARIO, así que el servicio de la API (otra cuenta) u
otro usuario del equipo tendría otro secreto y rechazaría etiquetas legítimas.
El HMAC sigue sirviendo para que la firma sea impredecible.

Contenido COMPACTO: id en mayúsculas y firma de 128 bits en base32, así todo
cabe en el modo alfanumérico del QR (menos módulos → módulos más grandes → se
lee con la cámara del teléfono aun en la etiqueta de 50 × 30 mm).

Las etiquetas antiguas (``https://…/c/<id>.<v>.<firma base64>``) siguen
leyéndose: sólo cuenta lo que va después de la última ``/`` y el id se compara
sin distinguir mayúsculas.
"""

from __future__ import annotations

import base64
import hashlib
import hmac

from backend.domain.logistics.entities import PhysicalContainer
from backend.domain.logistics.exceptions import LogisticsDomainError

QR_PREFIX = "SPJC"


class PermanentContainerQrService:
    def __init__(self, secret: bytes, *, base_url: str = QR_PREFIX) -> None:
        if len(secret) < 32:
            raise ValueError("QR signing secret must contain at least 32 bytes")
        self._secret = secret
        self._base_url = base_url.rstrip("/")

    def _sign(self, payload: str) -> str:
        signature = hmac.new(self._secret, payload.encode(), hashlib.sha256).digest()[:16]
        return base64.b32encode(signature).decode().rstrip("=")

    def _legacy_sign(self, payload: str) -> str:
        signature = hmac.new(self._secret, payload.encode(), hashlib.sha256).digest()
        return base64.urlsafe_b64encode(signature).decode().rstrip("=")

    @staticmethod
    def is_compact_signature(signature: str | None) -> bool:
        return bool(signature) and signature == signature.upper() and len(signature) <= 26

    def issue(self, container: PhysicalContainer) -> str:
        """Firma NUEVA para la versión vigente; sólo al registrar o al rotar."""
        container.qr_signature = self._sign(f"{container.id}.{container.qr_version}")
        return self.token_for(container, prefix=self._base_url)

    @staticmethod
    def token_for(container: PhysicalContainer, *, prefix: str = QR_PREFIX) -> str:
        """El contenido de la etiqueta a partir de la firma GUARDADA (reimprimir
        no cambia la identidad ni necesita el secreto)."""
        if not container.qr_signature:
            raise LogisticsDomainError(
                f"El contenedor {container.container_code} no tiene QR emitido")
        return (f"{prefix.rstrip('/')}/{container.id.upper()}.{container.qr_version}."
                f"{container.qr_signature}")

    @staticmethod
    def parse(token_or_url: str) -> tuple[str, int, str]:
        token = str(token_or_url or "").strip().rsplit("/", 1)[-1]
        try:
            container_id, version_text, signature = token.split(".", 2)
            version = int(version_text)
        except (ValueError, TypeError) as exc:
            raise LogisticsDomainError("QR de contenedor inválido") from exc
        if not container_id or not signature:
            raise LogisticsDomainError("QR de contenedor inválido")
        return container_id.lower(), version, signature

    @staticmethod
    def looks_like_token(reference: str) -> bool:
        try:
            PermanentContainerQrService.parse(reference)
        except LogisticsDomainError:
            return False
        return True

    @classmethod
    def matches(cls, token_or_url: str, container: PhysicalContainer) -> bool:
        """¿Esta etiqueta es la VIGENTE de este contenedor? (una rotada no)."""
        try:
            container_id, version, signature = cls.parse(token_or_url)
        except LogisticsDomainError:
            return False
        return (container_id == container.id and version == container.qr_version
                and bool(container.qr_signature)
                and hmac.compare_digest(signature, container.qr_signature))

    def resolve(self, token_or_url: str) -> tuple[str, int]:
        """Verifica el HMAC con el secreto de ESTE proceso (sólo sirve en la
        estación/usuario que emitió). Para validar etiquetas usar `matches`."""
        container_id, version, signature = self.parse(token_or_url)
        firmado = f"{container_id}.{version}"
        esperado = (self._sign(firmado) if self.is_compact_signature(signature)
                    else self._legacy_sign(firmado))
        if not hmac.compare_digest(esperado, signature):
            raise LogisticsDomainError("Firma QR inválida")
        return container_id, version

    def validate(self, token_or_url: str, container: PhysicalContainer) -> bool:
        return self.matches(token_or_url, container)
