"""Verificador para el AUTORIZADOR de una autorización en caliente.

Estándar ÚNICO para todos los módulos (2026-09-18). Nació en Precios
(`PricingAuthorizerPermissionChecker`, 2026-09-17) y se movió aquí cuando la
Fase 5 encontró el mismo defecto en el mostrador: el descuento grande —y ahora
el descuento bajo el precio mínimo— exige a OTRO usuario, y el verificador de
sesión de Ventas lo denegaba siempre. Una copia por módulo es justo lo que no
debe existir.

POR QUÉ NO SIRVE EL VERIFICADOR DE SESIÓN
------------------------------------------
`PricingSessionPermissionChecker` —como los de Compras y Transferencias— sólo
concede si el usuario consultado ES el de la sesión. Es lo correcto para las
operaciones normales: quien opera es quien tiene la sesión abierta.

Pero la autorización en caliente es justo lo contrario: vender bajo el mínimo
exige que **otra persona** (el gerente) autorice sobre el terminal de quien
vende. Con el verificador de sesión, `authorize_exception` consultaba al
autorizador contra una sesión que no es suya y denegaba SIEMPRE — la capacidad
existía en el dominio y era inalcanzable en la práctica.

Este verificador resuelve permisos de CUALQUIER usuario contra `rol_permisos`
(vía `PermissionQueryService`, que ya aplica las tres capas: rol → usuario →
sucursal, donde `permitido=0` revoca). Aplica las mismas reglas de comodín que
`PermissionEvaluator`, que es quien decide en el resto del sistema:

    bypass admin (`{"*"}`)  →  código exacto  →  `MODULO.*`

Se usa SÓLO para autorizar excepciones. Las operaciones normales siguen con el
verificador de sesión: si este se usara para todo, cualquiera con permisos en la
base podría operar sin tener sesión abierta.
"""

from __future__ import annotations

from backend.application.security.permission_query_service import PermissionQueryService
from backend.infrastructure.db.repositories.security.permission_repository import (
    SqlitePermissionRepository,
)
from backend.security.permissions.codes import normalize_permission

_GLOBAL_WILDCARD = "*"


class AuthorizerPermissionChecker:
    """`PermissionChecker` que valida a un usuario ARBITRARIO.

    `branch_id` acota las excepciones por sucursal: un gerente autorizado en una
    sucursal no autoriza en otra si sus overrides así lo dicen.
    """

    def __init__(self, connection, *, branch_id: str | None = None) -> None:
        self._conn = connection
        self._branch_id = branch_id

    def has_permission(self, user_id: str, permission_code: str) -> bool:
        user_id = str(user_id or "").strip()
        if not user_id:
            return False
        codes = PermissionQueryService(
            SqlitePermissionRepository(self._conn)
        ).permission_codes_for_user(user_id, self._branch_id)
        if not codes:
            return False
        if _GLOBAL_WILDCARD in codes:
            return True
        normalized = normalize_permission(permission_code)
        if normalized in codes:
            return True
        # `MODULO.*` — mismas reglas que `PermissionEvaluator`. Sólo aplica a
        # códigos punteados; los planos no tienen módulo del que colgar.
        module = normalized.split(".", 1)[0] if "." in normalized else ""
        return bool(module) and f"{module}.{_GLOBAL_WILDCARD}" in codes
