"""SaleQueryService — read-side access to Sale/POS data, gated by the same
`SalesAuthorizationPolicy` the write-side use cases use. Mirrors
backend/application/cash_register/shift_query_service.py::CashShiftQueryService
(constructor takes `connection` + `authorization`, each method re-checks
permission before querying, own SQL via the repository, returns frozen
DTOs — never the mock-free-for-all of handing a raw sqlite3.Row back).

`list_suspended` is the direct implementation of master prompt §40's
`ListSuspendedSalesQuery`.
"""

from __future__ import annotations

from backend.application.sales.dto import SaleDTO
from backend.application.sales.permissions import SalesPermissions
from backend.application.sales.authorization import SalesAuthorizationPolicy
from backend.infrastructure.db.repositories.sales.sale_repository import SaleRepository


class SaleQueryService:
    def __init__(self, connection, authorization: SalesAuthorizationPolicy | None = None) -> None:
        self._repo = SaleRepository(connection)
        self._auth = authorization or SalesAuthorizationPolicy()

    def get(self, sale_id: str, *, requester_user_id: str) -> SaleDTO | None:
        self._auth.require(requester_user_id, SalesPermissions.VIEW)
        sale = self._repo.get(sale_id)
        return None if sale is None else SaleDTO.from_entity(sale)

    def list_suspended(self, *, branch_id: str, requester_user_id: str,
                        workstation_id: str | None = None) -> tuple[SaleDTO, ...]:
        self._auth.require(requester_user_id, SalesPermissions.VIEW)
        sales = self._repo.list_suspended(branch_id=branch_id, workstation_id=workstation_id)
        return tuple(SaleDTO.from_entity(sale) for sale in sales)

    def count_suspended(self, *, branch_id: str, requester_user_id: str,
                         workstation_id: str | None = None) -> int:
        """POS-15/§41 "Counter": a lightweight badge count — real legacy
        precedent is `modulos/ventas.py`'s own Reanudar button label,
        `f"Reanudar ({len(self.ventas_en_espera)})"`. Deliberately a
        separate method from `list_suspended()`: a UI badge has no reason
        to hydrate every suspended `Sale`/`SaleLine` just to show a number."""
        self._auth.require(requester_user_id, SalesPermissions.VIEW)
        return self._repo.count_suspended(branch_id=branch_id, workstation_id=workstation_id)
