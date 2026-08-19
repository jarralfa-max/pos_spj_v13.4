"""SalesCashDrawerGateway — Sales' integration point onto the real Cash
Register bounded context for opening the money drawer (POS-12/§49-51).

Master prompt §6: Sales is not the owner of cash-register hardware — Caja
is. Research for this phase confirmed `backend/application/cash_register/
hardware_use_cases.py::OpenCashDrawerUseCase` is a real, audited,
permission-gated (`CashPermissions.DRAWER_OPEN` /
`DRAWER_OPEN_WITHOUT_SALE`), event-emitting (`CashEvents.DRAWER_OPENED`)
implementation — not the simpler `core.services.hardware_service.
HardwareService.open_cash_drawer()` boolean `modulos/ventas.py` calls today
(SALES-0's own audit note). This client wraps the Caja use case, the more
complete target architecture, rather than duplicating drawer-opening logic
or wrapping the legacy boolean path a second time.

Mirrors `sales_inventory_client.py`'s shape: thin, delegates entirely to the
real owning context, translates nothing except the failure boundary
(`CashHardwareError` -> whatever the caller wants to do with it — Sales has
no domain concept of a hardware failure code of its own to translate into,
unlike inventory reservation).
"""

from __future__ import annotations

from backend.application.cash_register.authorization import CashAuthorizationPolicy
from backend.application.cash_register.hardware import CashDrawerGateway
from backend.application.cash_register.hardware_use_cases import OpenCashDrawerUseCase


class SalesCashDrawerGateway:
    def __init__(self, authorization: CashAuthorizationPolicy, gateway: CashDrawerGateway) -> None:
        self._use_case = OpenCashDrawerUseCase(authorization, gateway)

    def open(
        self, connection, *, drawer_id: str, branch_id: str, actor_user_id: str,
        operation_id: str, sale_id: str | None = None, reason: str = "",
    ) -> None:
        self._use_case.execute(
            connection, drawer_id=drawer_id, branch_id=branch_id,
            actor_user_id=actor_user_id, operation_id=operation_id,
            sale_id=sale_id, reason=reason)
