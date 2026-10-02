"""Composición de Logística para la app de escritorio.

El servicio canónico de Logística se armaba en `core/events/wiring.py`
(`_wire_logistics_pipeline`), que se borró con el shell legado. Desde entonces
NADA lo construía en producción: la composición de Compras sólo creaba «Compra en
origen» si recibía un servicio de Logística, y nunca lo recibía. Aquí se arma,
con autorización real sobre la sesión y el secreto de firma de QR persistido.
"""

from __future__ import annotations

import secrets
import sqlite3

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


def qr_signing_secret(connection) -> bytes:
    """Secreto HMAC de los QR permanentes. Se genera una sola vez por instalación
    y se guarda en `configuraciones`: cambiarlo invalidaría todas las etiquetas
    ya impresas."""
    try:
        row = connection.execute("SELECT valor FROM configuraciones WHERE clave=?",
                                 (QR_SECRET_KEY,)).fetchone()
    except sqlite3.OperationalError:
        row = None
    if row and row[0] and len(str(row[0])) >= 64:
        return bytes.fromhex(str(row[0]))
    value = secrets.token_hex(32)
    try:
        connection.execute(
            "INSERT INTO configuraciones (clave, valor, tipo, grupo, descripcion)"
            " VALUES (?, ?, 'texto', 'logistica', 'Secreto de firma de QR de contenedores')"
            " ON CONFLICT(clave) DO UPDATE SET valor=excluded.valor", (QR_SECRET_KEY, value))
        connection.commit()
    except sqlite3.OperationalError:
        pass
    return bytes.fromhex(value)


def build_logistics_services(connection, session_context):
    """``(servicio de aplicación, consultas)`` de Logística listos para usar."""
    from backend.application.logistics.authorization import LogisticsAuthorizationPolicy
    from backend.application.logistics.queries import LogisticsShipmentQueryService
    from backend.application.logistics.service import LogisticsApplicationService
    from backend.domain.logistics.qr_identity import PermanentContainerQrService
    from backend.infrastructure.db.repositories.logistics_repository import LogisticsRepository

    service = LogisticsApplicationService(
        connection,
        LogisticsAuthorizationPolicy(SessionLogisticsPermissionChecker(session_context)),
        PermanentContainerQrService(qr_signing_secret(connection)))
    queries = LogisticsShipmentQueryService(connection, LogisticsRepository(connection))
    return service, queries
