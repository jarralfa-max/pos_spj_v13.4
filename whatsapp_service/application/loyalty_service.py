# application/loyalty_service.py — WA-15 (§8/§52 del prompt maestro)
"""
LoyaltyService — capa fina sobre `LoyaltyApiClient` (WA-15). Cubre lectura
(consultar puntos/nivel, `Intent.CHECK_LOYALTY`, ya en `_RULE_KEYWORDS`
desde WA-8: "mis puntos"/"puntos acumulados").

**Redención explícitamente fuera de alcance**: el único caso de uso real
y wireado de "canjear puntos" en el repo
(`backend/application/sales/use_cases/loyalty_use_cases.py::RedeemLoyaltyPointsUseCase`,
usado por el checkout POS y por el módulo Fidelidad) está acoplado a una
venta EN CURSO del lado escritorio (`sale_id`) — no es una acción
conversacional independiente que WhatsApp pueda disparar por su cuenta.
(El otro `RedeemLoyaltyPointsUseCase`, en
`backend/application/use_cases/redeem_loyalty_points_use_case.py`, es un
`DelegatingUseCase` sin handler inyectado — un scaffold, no una
implementación real; confirmado antes de decidir este alcance.) Construir
una redención por WhatsApp habría significado inventar una tercera vía de
descontar puntos sin sale_id, duplicando lógica de negocio real en vez de
reutilizarla — mismo criterio que WA-12 con `pago_flow.py`: se documenta
el corte de alcance, no se fuerza.
"""
from __future__ import annotations

from domain.whatsapp.erp_ports import LoyaltySummaryRef


class LoyaltyService:
    def __init__(self, root) -> None:
        self._root = root

    async def get_summary(self, *, customer_external_id: str) -> LoyaltySummaryRef:
        return await self._root.loyalty.get_summary(customer_external_id)
