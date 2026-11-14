"""Búsqueda de sucursales ACOTADA al alcance del usuario.

EL ORDEN IMPORTA Y ES EL PUNTO DE TODO ESTE ARCHIVO:

    usuario → sucursales permitidas → consulta → resultados

y NUNCA `todas las sucursales → frontend → ocultar las no permitidas`. Lo
segundo es una fuga de información: un cajero no debe poder DESCUBRIR, buscando
por nombre, sucursales a las que sus permisos no le dan acceso. Por eso el
filtro vive en el SQL, sobre un conjunto resuelto antes de consultar, y nunca en
la pantalla.

CÓMO SE RESUELVE EL ALCANCE

    1. ¿tiene el permiso de alcance global que le pasa el llamador? → TODAS.
    2. ¿algún rol suyo vale en toda la empresa?                     → TODAS.
    3. si no → los sitios que cubren sus roles: sucursal propia, asignadas
       (`usuarios_sucursales`) y las unidades de `user_role_assignments`, con
       herencia por jerarquía.
    4. nada de lo anterior                                          → NINGUNA.

Los pasos 2 y 3 son `AccessScopeResolver`, el mismo que decide los permisos de
la sesión (SDLC-ARQ-PERM-003): antes este servicio leía por su cuenta
`usuarios_sucursales` con respaldo en la sucursal propia e ignoraba las
asignaciones de rol y la jerarquía, así que el mismo usuario alcanzaba sucursales
distintas según qué módulo preguntara. Un solo resolvedor; aquí sólo se le agrega
el escape global del llamador.

POR QUÉ EL PERMISO GLOBAL SE INYECTA Y NO SE INVENTA AQUÍ

No existe un módulo `SUCURSALES` en el catálogo, y crear un `SUCURSALES.ver_todas`
sería fabricar vocabulario. El ERP ya declara el escape bajo el módulo que
CONSUME (`CAJA.ver.todas_sucursales`, `INVENTARIO.ver.todas_sucursales`,
`COMPRAS...`, `DELIVERY...`, `PRODUCCION...`), así que cada llamador pasa el
suyo. Sin código inyectado no hay ese escape: sólo cuenta el alcance de los roles.

COMODINES: se aplican las MISMAS reglas que `PermissionEvaluator`
(`{"*"}` → código exacto → `MODULO.*`). No hacerlo fue exactamente el fallo de
`InventoryScopePolicy`, que comparaba por pertenencia literal y por eso denegaba
a los administradores, cuyos permisos llegan como `{"*"}` sin expandir.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.application.security.access_scope import AccessScopeResolver, SiteReach
from backend.application.security.permission_query_service import PermissionQueryService
from backend.infrastructure.db.repositories.security.permission_repository import (
    SqlitePermissionRepository,
)
from backend.infrastructure.db.repositories.settings.branch_directory_repository import (
    SqliteBranchDirectoryRepository,
)
from backend.security.permissions.codes import normalize_permission

_GLOBAL_WILDCARD = "*"


@dataclass(frozen=True)
class BranchSearchQuery:
    """Contrato único de búsqueda de sucursales.

    `code` se declara porque es parte del contrato pedido, pero el esquema base
    de `sucursales` NO tiene esa columna (id, nombre, direccion, telefono,
    rfc_empresa, activa, fecha_alta). El repositorio se degrada de forma
    EXPLÍCITA: si la columna no existe, un filtro por código devuelve CERO
    resultados en vez de ignorarse. Ignorarlo devolvería filas que nadie pidió.
    """

    text: str | None = None
    code: str | None = None
    active_only: bool = True
    #: Identidad contra la que se resuelve el alcance. `None` NO significa
    #: "todas": significa que no hay usuario, y entonces no hay resultados.
    allowed_for_user: str | None = None
    page: int = 1
    page_size: int = 50

    def __post_init__(self) -> None:
        if int(self.page) < 1:
            raise ValueError("page empieza en 1")
        if int(self.page_size) < 1:
            raise ValueError("page_size debe ser positivo")

    @property
    def limit(self) -> int:
        return int(self.page_size)

    @property
    def offset(self) -> int:
        return (int(self.page) - 1) * int(self.page_size)


@dataclass(frozen=True)
class BranchOption:
    branch_id: str
    name: str
    is_active: bool = True


@dataclass(frozen=True)
class EmptyBranchReason:
    code: str
    message: str


class BranchScopeQueryService:
    def __init__(self, connection, *, global_scope_permission: str | None = None) -> None:
        self._conn = connection
        self._global_permission = global_scope_permission
        self._branches = SqliteBranchDirectoryRepository(connection)

    # ── alcance ───────────────────────────────────────────────────────────
    def _has_global_scope(self, user_id: str) -> bool:
        if not self._global_permission:
            return False
        try:
            codes = PermissionQueryService(
                SqlitePermissionRepository(self._conn)
            ).permission_codes_for_user(user_id, None)
        except Exception:
            # Sin esquema de seguridad (bases mínimas, fixtures acotados) no se
            # puede afirmar que alguien tenga alcance global. Negarlo es fallar
            # cerrado; propagar el error tumbaría al llamador por una tabla que
            # ni siquiera es la que se está consultando.
            return False
        if not codes:
            return False
        if _GLOBAL_WILDCARD in codes:
            return True
        normalized = normalize_permission(self._global_permission)
        if normalized in codes:
            return True
        module = normalized.split(".", 1)[0] if "." in normalized else ""
        return bool(module) and f"{module}.{_GLOBAL_WILDCARD}" in codes

    def _reach(self, user_id: str) -> SiteReach:
        try:
            return AccessScopeResolver(SqlitePermissionRepository(self._conn)).reach(user_id)
        except Exception:
            # Mismo criterio que `_has_global_scope`: sin esquema de seguridad no
            # se puede afirmar que alcance nada, y negarlo es fallar cerrado.
            return SiteReach(False, frozenset())

    def allowed_branch_ids(self, user_id: str | None) -> tuple[str, ...] | None:
        """Sucursales permitidas. `None` = TODAS (alcance global concedido).

        La tupla VACÍA es significativa y distinta de `None`: quiere decir
        "ninguna", y el buscador devolverá cero resultados en vez de todo.
        """
        user_id = str(user_id or "").strip()
        if not user_id:
            return ()
        if self._has_global_scope(user_id):
            return None
        reach = self._reach(user_id)
        return None if reach.company_wide else tuple(sorted(reach.site_ids))

    # ── búsqueda ──────────────────────────────────────────────────────────
    def search(self, criteria: BranchSearchQuery) -> list[BranchOption]:
        permitidas = self.allowed_branch_ids(criteria.allowed_for_user)
        filas = self._branches.search(
            branch_ids=permitidas, text=criteria.text, code=criteria.code,
            active_only=criteria.active_only,
            limit=criteria.limit, offset=criteria.offset)
        return [BranchOption(branch_id=str(f["id"]), name=str(f["nombre"] or ""),
                             is_active=bool(f["activa"]))
                for f in filas]

    def explain_empty(self, criteria: BranchSearchQuery) -> EmptyBranchReason | None:
        """POR QUÉ no hubo resultados. Sin esto, "no tienes acceso" y "no existe"
        se ven iguales, y el usuario concluye que el buscador está roto."""
        if self.search(criteria):
            return None
        permitidas = self.allowed_branch_ids(criteria.allowed_for_user)
        if permitidas is not None and not permitidas:
            return EmptyBranchReason(
                "SIN_ALCANCE",
                "No tienes sucursales asignadas. Contacta al administrador.")
        if criteria.code and not self._branches.supports_branch_code():
            return EmptyBranchReason(
                "SIN_CODIGO",
                "Esta instalación no registra códigos de sucursal; busca por nombre.")
        sin_texto = BranchSearchQuery(
            active_only=criteria.active_only,
            allowed_for_user=criteria.allowed_for_user,
            page_size=criteria.page_size)
        if self.search(sin_texto):
            return EmptyBranchReason(
                "NO_COINCIDE",
                "Ninguna de tus sucursales coincide con esa búsqueda.")
        if criteria.active_only:
            todas = BranchSearchQuery(
                active_only=False, allowed_for_user=criteria.allowed_for_user,
                page_size=criteria.page_size)
            if self.search(todas):
                return EmptyBranchReason(
                    "SIN_ACTIVAS", "Tus sucursales están inactivas.")
        return None
