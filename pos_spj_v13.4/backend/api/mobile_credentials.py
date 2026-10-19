"""Login móvil contra los usuarios reales (integración Logística 32cfbf).

La API móvil sólo tenía dobles de prueba como `CredentialVerifier`: en producción
nadie podía iniciar sesión. Este verificador usa las MISMAS piezas que el login
de escritorio (hash Argon2/Bcrypt y bloqueo por intentos) y los permisos por rol
de `rol_permisos`. Sin `LOGISTICA.embarque.ver` no hay sesión móvil.
"""

from __future__ import annotations

import logging
import sqlite3

from backend.api.mobile_session import MobileIdentity

logger = logging.getLogger("spj.api.mobile_credentials")

MOBILE_REQUIRED_PERMISSION = "LOGISTICA.embarque.ver"


class DatabaseMobileCredentialVerifier:
    def __init__(self, connection) -> None:
        self._conn = connection

    def authenticate_mobile(self, username: str, password: str,
                            device_id: str) -> MobileIdentity | None:
        from backend.application.security.authorizer_permission_checker import (
            AuthorizerPermissionChecker,
        )
        from backend.security.authentication.errors import AuthenticationFailedError
        from backend.security.authentication.verify_authorizer_credentials_use_case import (
            build_authorizer_credentials_verifier,
        )
        from backend.security.sessions.errors import AccountLockedError
        try:
            user_id = build_authorizer_credentials_verifier(self._conn).execute(
                username=username, password=password)
        except (AuthenticationFailedError, AccountLockedError):
            return None
        branch_id, branch_name = self._branch(user_id)
        checker = AuthorizerPermissionChecker(self._conn, branch_id=branch_id or None)
        if not checker.has_permission(user_id, MOBILE_REQUIRED_PERMISSION):
            return None
        warehouse_id, warehouse_name = self._warehouse(branch_id)
        return MobileIdentity(
            user_id=user_id, display_name=self._name(user_id), branch_id=branch_id,
            branch_name=branch_name, warehouse_id=warehouse_id, warehouse_name=warehouse_name,
            device_id=device_id, permissions=self._permissions(user_id, branch_id))

    def _name(self, user_id: str) -> str:
        try:
            fila = self._conn.execute(
                "SELECT COALESCE(NULLIF(trim(nombre),''), usuario) FROM usuarios WHERE id=?",
                (user_id,)).fetchone()
        except sqlite3.OperationalError:
            return ""
        return str(fila[0]) if fila and fila[0] else ""

    def _branch(self, user_id: str) -> tuple[str, str]:
        for consulta in ("SELECT sucursal_id FROM usuarios_sucursales WHERE usuario_id=?"
                         " ORDER BY COALESCE(es_principal, 0) DESC, rowid LIMIT 1",
                         "SELECT sucursal_id FROM usuarios WHERE id=?"):
            try:
                fila = self._conn.execute(consulta, (user_id,)).fetchone()
            except sqlite3.OperationalError:
                continue
            if fila and fila[0]:
                branch_id = str(fila[0])
                nombre = self._conn.execute("SELECT nombre FROM sucursales WHERE id=?",
                                            (branch_id,)).fetchone()
                return branch_id, str(nombre[0]) if nombre else ""
        return "", ""

    def _warehouse(self, branch_id: str) -> tuple[str, str]:
        if not branch_id:
            return "", ""
        from backend.application.logistics.warehouse_directory import (
            WarehouseDirectoryQueryService,
        )
        almacenes = WarehouseDirectoryQueryService(self._conn).warehouses_for_purpose(
            branch_id, "PURCHASE")
        if len(almacenes) != 1:
            return "", ""
        fila = self._conn.execute("SELECT name FROM warehouses WHERE id=?",
                                  (almacenes[0],)).fetchone()
        return almacenes[0], str(fila[0]) if fila else ""

    def _permissions(self, user_id: str, branch_id: str) -> tuple[str, ...]:
        from backend.application.security.permission_query_service import (
            PermissionQueryService,
        )
        from backend.infrastructure.db.repositories.security.permission_repository import (
            SqlitePermissionRepository,
        )
        try:
            codes = PermissionQueryService(SqlitePermissionRepository(self._conn)) \
                .permission_codes_for_user(user_id, branch_id or None)
        except Exception:  # noqa: BLE001 - sin permisos legibles, la sesión no ve nada extra
            logger.exception("permisos móviles no disponibles")
            return ()
        # `permission_codes_for_user` normaliza a MAYÚSCULAS y el flujo móvil
        # compara contra la grafía canónica (`LOGISTICA.embarque.crear`): sin
        # traducirlas, toda acción del teléfono respondía 403.
        from backend.application.logistics.permissions import ALL_LOGISTICS_PERMISSIONS
        canonical = {code.upper(): code for code in ALL_LOGISTICS_PERMISSIONS}
        return tuple(sorted({canonical.get(str(c).upper(), str(c)) for c in codes
                             if str(c).upper().startswith("LOGISTICA")}))
