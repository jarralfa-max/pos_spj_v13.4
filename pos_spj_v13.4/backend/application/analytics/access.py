"""Qué puede ver una sesión en BI: permisos y sucursales (SDLC-BI-001).

Antes cualquiera con acceso al módulo veía las cifras de toda la empresa: las rutas
descartaban la sucursal y el servicio permitía todo si nadie le pasaba verificador.

El alcance sale del estándar `BranchScopeQueryService`, más el sitio de la sesión:
éste ya se validó al iniciar sesión y puede venir de un rol con ámbito que la
consulta de asignaciones no ve. `allowed_branch_ids=None` significa TODAS y sólo lo
da `AnalyticsPermissions.ALL_BRANCHES_VIEW`; una tupla vacía significa NINGUNA.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Callable

from backend.application.analytics.dto.bi_dashboard_dto import DashboardFilters
from backend.application.analytics.permissions import AnalyticsPermissions as P
from backend.application.security.branch_scope_query_service import BranchScopeQueryService
from backend.domain.analytics.exceptions import AnalyticsPermissionDeniedError

#: El menú interno pide códigos granulares; `SECTION_PERMISSION`, los planos que
#: siguen otorgados en instalaciones existentes. Vale cualquiera de los dos: quien
#: ve la entrada del menú debe ver su contenido.
_GRANULAR_SECTION_CODE = {
    "INTELIGENCIA_BI.VER_VENTAS": P.SALES_VIEW,
    "INTELIGENCIA_BI.VER_INVENTARIO": P.INVENTORY_VIEW,
    "INTELIGENCIA_BI.VER_COMPRAS": P.PURCHASES_VIEW,
    "INTELIGENCIA_BI.VER_CAJA": P.FINANCE_CASHFLOW_VIEW,
    "INTELIGENCIA_BI.VER_CLIENTES": P.FINANCE_VIEW,
    "INTELIGENCIA_BI.VER_PROVEEDORES": P.PURCHASES_VIEW,
    "INTELIGENCIA_BI.VER_FINANZAS": P.FINANCE_VIEW,
    "INTELIGENCIA_BI.VER_MERMA": P.INVENTORY_VIEW,
}


def _deny(_code: str) -> bool:
    return False


@dataclass(frozen=True)
class BiAccess:
    can: Callable[[str], bool] = _deny
    allowed_branch_ids: tuple[str, ...] | None = ()
    default_branch_id: str = ""

    @classmethod
    def permissive_for_tests(cls) -> "BiAccess":
        return cls(can=lambda _code: True, allowed_branch_ids=None)

    @property
    def company_wide(self) -> bool:
        return self.allowed_branch_ids is None

    def covers(self, branch_id: str) -> bool:
        return self.company_wide or branch_id in self.allowed_branch_ids

    def require_branch(self, branch_id: str) -> None:
        if not self.covers(branch_id):
            raise AnalyticsPermissionDeniedError("No tiene acceso a esa sucursal.")

    def resolve_branch(self, branch_id: str = "") -> str:
        """La sucursal que se consulta; `""` (todas) sólo con alcance global."""
        if branch_id:
            self.require_branch(branch_id)
            return branch_id
        if self.company_wide:
            return ""
        if not self.allowed_branch_ids:
            raise AnalyticsPermissionDeniedError(
                "Su usuario no tiene sucursales asignadas. Contacte al administrador.")
        if self.default_branch_id in self.allowed_branch_ids:
            return self.default_branch_id
        return self.allowed_branch_ids[0]

    def scope(self, filters: DashboardFilters) -> DashboardFilters:
        return replace(filters, branch_id=self.resolve_branch(filters.branch_id))

    def scoped_branches(self, query_service) -> list[dict]:
        """Sucursales que este acceso puede ver, ya acotadas para los selectores."""
        return [b for b in query_service.filter_options().get("branches", [])
                if self.covers(b["id"])]


def build_bi_access(connection, session) -> BiAccess:
    """El acceso de una sesión viva. Sin sesión no concede nada."""
    user_id = str(getattr(session, "user_id", None) or "")
    if not user_id:
        return BiAccess()

    def can(code: str) -> bool:
        if session.tiene_permiso(code):
            return True
        granular = _GRANULAR_SECTION_CODE.get(str(code).upper())
        return bool(granular) and session.tiene_permiso(granular)

    permitidas = BranchScopeQueryService(
        connection, global_scope_permission=P.ALL_BRANCHES_VIEW).allowed_branch_ids(user_id)
    sitio = str(getattr(session, "active_branch_id", None) or "")
    if permitidas is not None and sitio and sitio not in permitidas:
        permitidas = (*permitidas, sitio)
    return BiAccess(can=can, allowed_branch_ids=permitidas, default_branch_id=sitio)
