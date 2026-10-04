"""Composición de Logística para la app de escritorio.

El servicio canónico de Logística se armaba en `core/events/wiring.py`
(`_wire_logistics_pipeline`), que se borró con el shell legado. Desde entonces
NADA lo construía en producción: la composición de Compras sólo creaba «Compra en
origen» si recibía un servicio de Logística, y nunca lo recibía. Aquí se arma,
con autorización real sobre la sesión y el secreto de firma de QR guardado
en el almacén de secretos.
"""

from __future__ import annotations

import secrets

QR_SECRET_KEY = "logistics.qr_signing_secret"


class SessionLogisticsPermissionChecker:
    """Mismo criterio que Compras: sesión activa, identidad coincidente y permiso."""

    def __init__(self, session) -> None:
        self._session = session

    def has_permission(self, user_id: str, permission_code: str) -> bool:
        session = self._session
        if session is None or not bool(getattr(session, "is_active", False)):
            return False
        if str(getattr(session, "user_id", "") or "").strip() != str(user_id or "").strip():
            return False
        check = getattr(session, "tiene_permiso", None)
        return bool(callable(check) and check(permission_code))


def qr_signing_secret(secret_store) -> bytes:
    """Secreto HMAC de los QR permanentes, en el almacén de secretos (§46).

    Se genera una sola vez por instalación: cambiarlo invalidaría todas las
    etiquetas ya impresas. Antes vivía en texto plano en `configuraciones` y,
    si la lectura fallaba, se generaba OTRO en silencio — exactamente el
    cambio que invalida las etiquetas. Ahora un almacén que no responde es un
    error visible, no un secreto nuevo.
    """
    value = secret_store.get_secret(QR_SECRET_KEY)
    if value and len(value) >= 64:
        return bytes.fromhex(value)
    value = secrets.token_hex(32)
    secret_store.set_secret(QR_SECRET_KEY, value)
    return bytes.fromhex(value)


def build_logistics_services(connection, session_context, *, secret_store=None):
    """``(servicio de aplicación, consultas)`` de Logística listos para usar."""
    if secret_store is None:
        from backend.security.secrets.default_secret_store import build_default_secret_store
        secret_store = build_default_secret_store()
    from backend.application.logistics.authorization import LogisticsAuthorizationPolicy
    from backend.application.logistics.queries import LogisticsShipmentQueryService
    from backend.application.logistics.service import LogisticsApplicationService
    from backend.domain.logistics.qr_identity import PermanentContainerQrService
    from backend.infrastructure.db.repositories.logistics_repository import LogisticsRepository

    service = LogisticsApplicationService(
        connection,
        LogisticsAuthorizationPolicy(SessionLogisticsPermissionChecker(session_context)),
        PermanentContainerQrService(qr_signing_secret(secret_store)))
    queries = LogisticsShipmentQueryService(connection, LogisticsRepository(connection))
    return service, queries
