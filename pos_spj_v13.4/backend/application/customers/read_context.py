"""CrmReadContext (CRM-43) — lo que una lectura de Clientes/CRM sabe de la
sesión que la pide, en un solo objeto.

Las pantallas no construyen contextos de alcance a mano: el presentador arma
UN ``CrmReadContext`` con el usuario y la sucursal activa, y cada lector de la
raíz de composición deriva de él el contexto que su servicio necesita
(``CustomerScopeContext`` o ``CRMScopeContext``). Antes cada directorio armaba
el suyo y ninguno pasaba la sucursal, por eso el eje BRANCH nunca resolvía.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.application.crm.data_scope import CRMScopeContext
from backend.application.customers.data_scope import CustomerScopeContext


@dataclass(frozen=True)
class CrmReadContext:
    user_id: str
    branch_id: str | None = None
    team_member_ids: tuple[str, ...] = field(default_factory=tuple)

    def crm(self) -> CRMScopeContext:
        return CRMScopeContext(
            user_id=self.user_id, team_member_ids=self.team_member_ids,
            branch_ids=(self.branch_id,) if self.branch_id else ())

    def customers(self) -> CustomerScopeContext:
        return CustomerScopeContext(
            user_id=self.user_id, branch_id=self.branch_id,
            team_member_ids=self.team_member_ids)
