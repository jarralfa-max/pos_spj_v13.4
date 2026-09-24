"""¿Se puede contabilizar un pago de contado de Compras? — adaptador a Finanzas.

Implementa `PaymentSourceBookingPort` delegando en la MISMA función que usa el
puente contable al asentar (`purchase_posting_problem`). Así la pantalla que
ofrece fuentes, la confirmación que las valida y el asiento que se genera no
pueden discrepar: si la confirmación acepta una fuente, el puente sabe
asentarla.

Nunca lanza: si Finanzas no se puede consultar (base sin su esquema), responde
con el motivo, y la confirmación se niega — que es fallar cerrado sobre dinero.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("spj.procurement.payment_source_booking")


class ProcurementPaymentSourceBookingAdapter:
    def __init__(self, connection) -> None:
        self._connection = connection

    def booking_problem(self, payment_source: str, branch_id: str | None) -> str | None:
        from backend.application.event_handlers.finance.procurement_immediate_payment_bridge import (
            purchase_posting_problem,
        )
        try:
            return purchase_posting_problem(
                self._connection, payment_source=str(payment_source or ""),
                branch_id=branch_id or None)
        except Exception:
            logger.exception("No se pudo verificar la fuente de pago %r", payment_source)
            return "no se pudo verificar la contabilidad de la fuente de pago"
