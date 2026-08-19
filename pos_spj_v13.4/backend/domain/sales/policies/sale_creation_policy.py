"""Sale creation gate (master prompt §13: 'No permitir completar venta sin
caja abierta cuando la política lo requiera'). Pure decision — the caller
already resolved whether a cash shift is open (`CashSessionQuery`,
application layer)."""

from __future__ import annotations

from backend.domain.sales.exceptions import SaleInvalidStateError


class SaleCreationPolicy:
    @staticmethod
    def ensure_can_start(*, requires_open_cash_session: bool, has_open_cash_session: bool) -> None:
        if requires_open_cash_session and not has_open_cash_session:
            raise SaleInvalidStateError(
                "No se puede iniciar una venta sin una sesión de caja abierta")
