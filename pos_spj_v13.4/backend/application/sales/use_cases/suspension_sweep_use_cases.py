"""ExpireSuspendedSalesUseCase (POS-15/§41: "Expire").

SALES-9 already built `ExpireOrphanedInventoryReservationsUseCase`, but it
only releases a stale INVENTORY hold (`stock_reservas.expires_at`, a 30-
minute TTL) — it never touches the SALE itself. A suspended sale whose
reservation already expired that way is left exactly where it was:
`status=SUSPENDED`, still holding a now-stale `inventory_reservation_id`
that Inventory has already silently released underneath it. This is the
real gap POS-15 closes: a system sweep for the SALE aggregate's own
suspension age, not just its inventory side-effect.

No real precedent in this repository names a specific expiry threshold for
a suspended sale (the legacy `modulos/ventas.py::ventas_en_espera` in-memory
dict never expires suspended sales by time at all — only a resume/cancel/
app-restart clears it) — `max_age_hours` is therefore a caller-supplied
parameter, not a hardcoded business rule Sales has no real precedent to
invent (same restraint this pipeline has applied to Promotions/Coupons/
Vouchers, SALES-11).

A system sweep, not a per-cashier action — no `SalesPermissions` gate,
same reasoning as `ExpireOrphanedInventoryReservationsUseCase` and CRM's
own time-based automation trigger sweep.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from backend.application.sales.use_cases._base import SYSTEM_ACTOR, _SalesBaseUseCase
from backend.domain.sales.events import SaleEvents, sale_event_payload
from backend.infrastructure.db.repositories.sales.unit_of_work import SalesUnitOfWork
from backend.shared.ids import new_uuid

_DEFAULT_REASON = "Expiración automática por tiempo de suspensión"


class ExpireSuspendedSalesUseCase(_SalesBaseUseCase):
    """Barrido de sistema: no lleva permiso por cajero.

    Hereda de `_SalesBaseUseCase` sólo por la fontanería —el cliente de
    inventario con su política inyectada—, no para añadir una puerta de
    permisos que este barrido no tiene por diseño.
    """

    def execute(self, connection, *, max_age_hours: int, reason: str = _DEFAULT_REASON) -> int:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=max_age_hours)).isoformat(
            timespec="seconds")
        with SalesUnitOfWork(connection) as uow:
            expired = uow.sales.list_suspended_before(cutoff)
            for sale in expired:
                sale.cancel(reason)
                if sale.inventory_reservation_id:
                    client = self._inventory_client(
                        connection, branch_id=sale.branch_id,
                        actor_user_id=SYSTEM_ACTOR)
                    client.release(sale.inventory_reservation_id, reason="expirada")
                    sale.inventory_reservation_id = None
                uow.sales.save(sale)
                sweep_operation_id = new_uuid()
                payload = sale_event_payload(
                    SaleEvents.CANCELLED, operation_id=sweep_operation_id, entity_id=sale.id,
                    branch_id=sale.branch_id, user_id=sale.cashier_user_id, reason=reason,
                    expired=True)
                uow.outbox.enqueue(
                    event_id=payload["event_id"], event_name=SaleEvents.CANCELLED,
                    payload_json=json.dumps(payload, ensure_ascii=False, default=str),
                    operation_id=sweep_operation_id)
        return len(expired)
