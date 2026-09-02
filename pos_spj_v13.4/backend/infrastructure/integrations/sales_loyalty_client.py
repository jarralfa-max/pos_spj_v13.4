"""SalesLoyaltyClient — Sales' integration point onto the real Loyalty
program (master prompt §6/§23/§24). No `backend/domain/loyalty/`/
`backend/application/loyalty/` bounded context exists yet (confirmed by
research) — the only real, side-effect-free evaluation is the legacy
`core/services/loyalty_service.py::LoyaltyService.preview_redemption`, whose
own docstring already states its exact intended purpose: "Seguro para
llamar antes de confirmar el pago — no registra ni decrementa puntos. La UI
debe usar este método para poblar el diálogo de canje en lugar de calcular
los valores localmente." Wrapping it here (instead of a UI dialog computing
it) is this exact requirement, just for the new stack.

Two boundary crossings this client makes explicit rather than hiding:
1. **Identity**: `Sale.customer_id` holds a Customer Master `customers.id`
   (per SALES-10), but `LoyaltyService` only understands legacy `clientes.id`
   — bridged via `EnsureLegacyCustomerBridgeUseCase` (CRM-21's new→legacy
   direction), the reverse of the bridge `ScanLoyaltyCardForSaleUseCase`
   (SALES-10) already uses for the legacy→new direction.
2. **Decimal → float**: `LoyaltyService.preview_redemption` takes/returns
   `float`. This is the only place in this call path that conversion
   happens — never inside `SaleBenefitEvaluationService` or any domain code.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from backend.domain.document_output.value_objects.loyalty_summary import LoyaltySummary


class SalesLoyaltyClient:
    def __init__(self, connection) -> None:
        self._connection = connection

    def peek_loyalty_summary(self, *, customer_id: str) -> LoyaltySummary:
        """SET-13 cutover: a real, side-effect-free balance/tier lookup for
        ticket display — reuses `preview_redemption` exactly as intended by
        its own docstring ("Seguro para llamar... la UI debe usar este
        método"), never earns or redeems anything. `points_earned` stays
        `None` — `sales_pos` checkout has no points-earning pipeline yet,
        unlike the legacy `SalesService._execute_sale_core` path; this
        summary never fabricates that number."""
        from backend.application.customers.use_cases.legacy_customer_bridge_use_cases import (
            EnsureLegacyCustomerBridgeUseCase,
        )
        from core.services.loyalty_service import LoyaltyService

        legacy_customer_id = EnsureLegacyCustomerBridgeUseCase().execute(
            self._connection, customer_id=customer_id)
        service = LoyaltyService(self._connection)
        preview = service.preview_redemption(legacy_customer_id, 0.0)
        return LoyaltySummary.create(
            points_balance=int(preview.get("puntos_disponibles") or 0),
            tier=str(preview.get("nivel") or ""),
            available=bool(preview.get("enabled")),
        )

    def preview_redemption(self, *, customer_id: str, subtotal: Decimal) -> dict[str, Any]:
        from backend.application.customers.use_cases.legacy_customer_bridge_use_cases import (
            EnsureLegacyCustomerBridgeUseCase,
        )
        from core.services.loyalty_service import LoyaltyService

        legacy_customer_id = EnsureLegacyCustomerBridgeUseCase().execute(
            self._connection, customer_id=customer_id)
        service = LoyaltyService(self._connection)
        return service.preview_redemption(legacy_customer_id, float(subtotal))

    def redeem(
        self, *, customer_id: str, sale_id: str, subtotal: Decimal, points: int,
        actor_user_id: str,
    ) -> dict[str, Any]:
        """POS-14/§38-41: the REAL redemption (`preview_redemption`'s own
        docstring: "no registra ni decrementa puntos" — this is the
        counterpart that does). Re-previews first to get the
        already-clamped/capped point count and discount amount
        (`LoyaltyService` owns the min-points/50%-of-subtotal/balance caps,
        never re-derived here — §6), then commits via `apply_redemption`
        using that SAME clamped point count, never the raw caller-requested
        one — closes a real race where a naive caller-supplied amount could
        bypass the cap `preview_redemption` already enforced.

        Returns ``{"approved": bool, "points_redeemed": int,
        "discount_amount": Decimal, "reason": str}``. Idempotent by
        (customer, sale) — `LoyaltyService.apply_redemption` is a no-op
        (still ``approved=True``) if this sale's redemption was already
        recorded."""
        from backend.application.customers.use_cases.legacy_customer_bridge_use_cases import (
            EnsureLegacyCustomerBridgeUseCase,
        )
        from core.services.loyalty_service import LoyaltyService

        legacy_customer_id = EnsureLegacyCustomerBridgeUseCase().execute(
            self._connection, customer_id=customer_id)
        service = LoyaltyService(self._connection)
        preview = service.preview_redemption(
            legacy_customer_id, float(subtotal), puntos_solicitados=int(points))
        approved_points = int(preview.get("puntos_solicitados", 0) or 0)
        if not preview.get("enabled") or approved_points <= 0:
            return {
                "approved": False, "points_redeemed": 0, "discount_amount": Decimal("0"),
                "reason": preview.get("mensaje") or "Canje de fidelidad no disponible",
            }
        result = service.apply_redemption(
            legacy_customer_id, sale_id, actor_user_id, float(subtotal), approved_points)
        if not result.get("ok"):
            return {
                "approved": False, "points_redeemed": 0, "discount_amount": Decimal("0"),
                "reason": result.get("error") or "Canje rechazado",
            }
        return {
            "approved": True, "points_redeemed": approved_points,
            "discount_amount": Decimal(str(preview["descuento"])),
            "reason": "",
        }
