# infrastructure/erp_clients/loyalty_client.py — WA-15
"""
LoyaltySnapshotApiClient — primera implementación real de
`LoyaltyApiClient` (WA-9 lo dejó como contrato sin envoltorio, `erp_ports.py`).

Lee `loyalty_snapshots` — la misma tabla precomputada que ya lee
`LoyaltyCustomerSummaryQuery` (`backend/application/customers/queries/
loyalty_customer_summary_query.py`, CRM-21) — MISMA forma de SQL, no
reinventada. No se reutiliza esa clase directamente porque exige
`actor_user_id` y pasa por `CustomerAuthorizationPolicy.require(...,
LOYALTY_VIEW)` — un chequeo de permisos de EMPLEADO (¿puede este usuario
del ERP ver los puntos de este cliente?) que no aplica aquí: por WhatsApp
es el propio cliente consultando su propio saldo, no un tercero. Envolver
esa clase con un `actor_user_id` de sistema inventado habría sido fingir
una autorización que no existe; leer la misma tabla, sola, es la
reutilización honesta.

`cliente_id` en `loyalty_snapshots` es el `clientes.id` LEGACY (documentado
en `loyalty_customer_summary_query.py`) — el mismo id que ya devuelven
`CustomersApiClient.find_by_phone`/`create_minimal` (WA-9). A diferencia
de WA-14 (consentimiento), aquí NO hace falta ningún puente hacia
`customers.id` — Fidelidad nunca migró a ese esquema.
"""
from __future__ import annotations

from domain.whatsapp.erp_ports import LoyaltySummaryRef


class LoyaltySnapshotApiClient:
    def __init__(self, conn) -> None:
        self._conn = conn

    async def get_summary(self, customer_id: str) -> LoyaltySummaryRef:
        row = self._conn.execute(
            "SELECT puntos_actuales, nivel, visitas FROM loyalty_snapshots WHERE cliente_id=?",
            (customer_id,),
        ).fetchone()
        if row is None:
            return LoyaltySummaryRef(customer_id=customer_id, enrolled=False, points=0, tier="", visits=0)
        puntos, nivel, visitas = row
        return LoyaltySummaryRef(
            customer_id=customer_id, enrolled=True, points=puntos or 0, tier=nivel or "", visits=visitas or 0,
        )
