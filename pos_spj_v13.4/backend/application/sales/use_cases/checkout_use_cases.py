"""CheckoutSaleUseCase — POS-14's "Atomic operation" (Cash, Card, Transfer,
Mixed, Credit, Mercado Pago already recorded via SALES-13's
`RecordSalePaymentUseCase`; Loyalty already settled, if requested, via
`RedeemLoyaltyPointsUseCase`; this is the single all-or-nothing finalize
step a "Cobrar" button triggers once).

**Atomicity, and why the ordering here is not arbitrary**: everything that
must succeed together — confirming the inventory hold and completing the
sale — happens inside ONE `SalesUnitOfWork`. To make that a genuine
guarantee rather than a hopeful one, the two domain checks that can still
fail (`SaleLifecyclePolicy.ensure_transition`, `SalePaymentPolicy.
ensure_fully_paid`) run FIRST, before any I/O mutation — so if checkout
can't legally complete, nothing is touched and the transaction commits an
unchanged no-op. Only once completion is already guaranteed to succeed does
the (harder to cleanly undo) inventory-reservation confirmation run, then
`Sale.complete()` itself (a cheap, guaranteed-to-pass re-check).

**Outbox**: `PAYMENT_CONFIRMED`/`COMPLETED` are enqueued to `sales_outbox`
inside that SAME transaction — if anything above fails, no event survives.

**Cash effects, and the one part of "atomic" this use case cannot deliver
honestly**: `SalesCashEffectsClient` wraps Caja's real
`CashSalesIntegrationService.record_completed_sale` — but `Cash Register`'s
own `CashRegisterUnitOfWork` has no `owns_transaction=False` mode (unlike
Sales'/Inventory's), so it cannot be composed into the same SAVEPOINT
without prematurely committing it. This step therefore runs AFTER the
sale's own transaction has already committed, as a best-effort, logged,
idempotent side effect — a genuine architectural limit found by this
phase's own research, not an oversight papered over. A failure here never
un-completes the sale (the cashier already collected real payment by this
point); it is recorded for reconciliation instead.

FASE 6 (2026-09-18) — lo que el cobro NO hacía, medido con la sesión real
-------------------------------------------------------------------------
Una venta normal de 2 Pollos quedaba COMPLETED por $200 y:

1. **El inventario no se movía.** Sólo se confirmaba una reserva si la venta
   ya la traía, y sólo SUSPENDER la creaba. Ahora el cobro reserva y descuenta
   en la misma transacción. Si la existencia no alcanza, pide autorización en
   caliente (`POS.venta.sin_existencia`, otro usuario + motivo) y la salida
   queda negativa y auditada — decisión del usuario.
2. **Caja no la veía** si el cajero no tenía turno: el efecto de caja corre
   después del commit y sólo dejaba un aviso en el log. Ahora se exige turno
   abierto ANTES de completar (decisión del usuario).
3. **Finanzas no se enteraba.** `SALE_COMPLETED` llevaba sólo el total y nadie
   lo despachaba. Ahora lleva totales, pagos y costo de venta, y
   `backend/application/sales/integrations/` lo entrega a `SaleCompletedHandler`.

`settle_inventory`/`require_cash_shift` existen para Pedidos/Delivery, que
descuenta por su propio cliente de inventario (ORD-8) y liquida el efectivo con
el repartidor, no con un turno de mostrador. El mostrador usa ambos en True.
"""

from __future__ import annotations

import logging
from decimal import Decimal

from backend.application.sales.dto import SaleDTO
from backend.application.sales.permissions import SalesPermissions
from backend.application.sales.result import SaleResult, fail_from_domain_error
from backend.application.sales.use_cases._base import _SalesBaseUseCase
from backend.domain.sales.enums import SaleStatus
from backend.domain.sales.events import SaleEvents
from backend.domain.sales.exceptions import (
    InventoryShortageError,
    SalesDomainError,
    SaleNotFoundError,
)
from backend.domain.sales.policies.lifecycle_policies import SaleLifecyclePolicy
from backend.domain.sales.policies.payment_policy import SalePaymentPolicy
from backend.infrastructure.db.repositories.sales.unit_of_work import SalesUnitOfWork
from backend.infrastructure.integrations.sales_cash_effects_client import SalesCashEffectsClient
from backend.infrastructure.integrations.sales_folio_client import SalesFolioClient
from backend.infrastructure.integrations.sales_sweepstakes_client import SalesSweepstakesClient

logger = logging.getLogger("spj.sales.checkout")


class CheckoutSaleUseCase(_SalesBaseUseCase):
    def __init__(self, authorization=None, inventory_authorization=None,
                 customer_authorization=None, *, authorizer_authorization=None,
                 costs=None, settle_inventory: bool = True,
                 require_cash_shift: bool = True) -> None:
        super().__init__(authorization, inventory_authorization, customer_authorization)
        #: Política para el AUTORIZADOR de vender sin existencia (otro usuario;
        #: en producción, `AuthorizerPermissionChecker`).
        self._authorizer_auth = authorizer_authorization or self._auth
        #: Puerto de costos: `unit_cost(product_id, *, branch_id)` → Decimal | None.
        self._costs = costs
        self._settle_inventory = settle_inventory
        self._require_cash_shift = require_cash_shift

    def execute(self, connection, *, sale_id: str, actor_user_id: str,
                operation_id: str, authorizer_user_id: str | None = None,
                reason: str | None = None) -> SaleResult:
        try:
            self._auth.require(actor_user_id, SalesPermissions.SALE_COMPLETE)
        except SalesDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)

        with SalesUnitOfWork(connection) as uow:
            sale = uow.sales.get(sale_id)
            if sale is None:
                return fail_from_domain_error(
                    SaleNotFoundError(f"Venta {sale_id} no existe"), operation_id=operation_id)

            try:
                SaleLifecyclePolicy.ensure_transition(
                    current=sale.status, target=SaleStatus.COMPLETED)
                SalePaymentPolicy.ensure_fully_paid(
                    total_paid=sale.total_paid, sale_total=sale.totals.total)
            except SalesDomainError as exc:
                return fail_from_domain_error(exc, operation_id=operation_id)

            if self._require_cash_shift:
                problema = self._open_shift_problem(connection, sale)
                if problema:
                    return SaleResult.fail(problema, "NO_OPEN_CASH_SHIFT",
                                           operation_id=operation_id)

            inventario = "NOT_SETTLED"
            if self._settle_inventory:
                resultado = self._settle(
                    connection, sale, actor_user_id=actor_user_id, operation_id=operation_id,
                    authorizer_user_id=authorizer_user_id, reason=reason)
                if isinstance(resultado, SaleResult):
                    return resultado
                inventario, costos, sin_costo = resultado
            else:
                costos, sin_costo = self._unit_costs(connection, sale)

            if not sale.sale_number:
                # Folio comercial (§6), en la MISMA transacción: si el cobro no
                # se confirma, el consecutivo tampoco avanza.
                folio = SalesFolioClient(connection).next_folio(sale.branch_id)
                if folio:
                    sale.assign_number(folio)
            sale.complete()
            uow.sales.save(sale)
            self._emit(uow, SaleEvents.PAYMENT_CONFIRMED, entity_id=sale.id,
                       operation_id=operation_id, branch_id=sale.branch_id,
                       actor_user_id=actor_user_id)
            self._emit(uow, SaleEvents.COMPLETED, entity_id=sale.id, operation_id=operation_id,
                       branch_id=sale.branch_id, actor_user_id=actor_user_id,
                       **_completed_payload(sale, costos, sin_costo, inventario,
                                            authorizer_user_id=authorizer_user_id,
                                            reason=reason))

        cash_effects_error: str | None = None
        if sale.payments:
            change = max(Decimal("0"), sale.total_paid - sale.totals.total)
            try:
                SalesCashEffectsClient().record_completed_sale(
                    connection, sale_id=sale.id, branch_id=sale.branch_id,
                    cashier_user_id=sale.cashier_user_id, operation_id=operation_id,
                    payments=sale.payments, change=change)
            except Exception as exc:  # noqa: BLE001 - never un-complete a sale over a ledger side effect
                cash_effects_error = str(exc)
                logger.warning("Efecto de caja no registrado para venta %s: %s", sale.id, exc)

        raffle_issue_error: str | None = None
        try:
            SalesSweepstakesClient(connection).issue_tickets_for_sale(sale=SaleDTO.from_entity(sale))
        except Exception as exc:  # noqa: BLE001 - never un-complete a sale over raffle issuance
            raffle_issue_error = str(exc)
            logger.warning("Boletos de rifa no emitidos para venta %s: %s", sale.id, exc)

        return SaleResult.ok(
            "Venta finalizada", entity_id=sale.id, operation_id=operation_id,
            sale=SaleDTO.from_entity(sale), cash_effects_error=cash_effects_error,
            raffle_issue_error=raffle_issue_error)


    # ── cobro: turno, inventario y costo ─────────────────────────────────
    @staticmethod
    def _open_shift_problem(connection, sale) -> str | None:
        import sqlite3

        from backend.domain.cash_register.exceptions import CashRegisterError
        try:
            SalesCashEffectsClient().require_open_shift(
                connection, branch_id=sale.branch_id, cashier_user_id=sale.cashier_user_id)
        except (CashRegisterError, sqlite3.OperationalError):
            # Sin esquema de Caja no puede haber turno: se falla cerrado.
            return ("No tienes un turno de caja abierto. Abre tu turno en Caja antes de "
                    "cobrar: sin turno, el dinero de la venta no entra a ningún corte.")
        return None

    def _unit_costs(self, connection, sale) -> tuple[dict, list[str]]:
        """Costo unitario por producto para la salida de inventario y el costo
        de venta. Un producto nunca costeado queda fuera y se informa: el costo
        no se inventa (§18).

        Un COMPUESTO (receta de venta o combo de Productos) cuesta lo que
        cuestan sus componentes; si a uno le falta costo, al compuesto también.
        Los costos de los componentes van en el mismo mapa: son los que lleva la
        salida de inventario."""
        from backend.application.products.queries.sales_fulfillment_query_service import (
            CompositeDefinitionError,
            SalesFulfillmentQueryService,
        )

        costs = self._costs
        if costs is None:
            from backend.infrastructure.integrations.sales_pricing_client import (
                SalesPricingClient,
            )
            costs = SalesPricingClient(connection)
        composicion = SalesFulfillmentQueryService(connection)

        def costo_de(product_id):
            try:
                costo = costs.unit_cost(product_id, branch_id=sale.branch_id)
            except Exception:
                logger.exception("costo de %s no disponible", product_id)
                return None
            return None if costo is None else Decimal(str(costo))

        costos: dict[str, Decimal] = {}
        sin_costo: set[str] = set()
        for product_id in {line.product_id for line in sale.goods_lines}:
            try:
                partes = composicion.explode(product_id, Decimal("1"))
            except CompositeDefinitionError:
                # Composición inválida en Productos: sin costo, no inventado.
                sin_costo.add(product_id)
                continue
            if set(partes) == {product_id}:
                costo = costo_de(product_id)
                if costo is None:
                    sin_costo.add(product_id)
                else:
                    costos[product_id] = costo
                continue
            total = Decimal("0")
            completo = True
            for componente, cantidad in partes.items():
                costo = costo_de(componente)
                if costo is None:
                    sin_costo.add(componente)
                    completo = False
                    continue
                costos[componente] = costo
                total += cantidad * costo
            if completo:
                costos[product_id] = total
            else:
                sin_costo.add(product_id)
        return costos, sorted(sin_costo)

    def _settle(self, connection, sale, *, actor_user_id, operation_id,
                authorizer_user_id, reason):
        """Descuenta el inventario de la venta. Devuelve (cómo se asentó,
        costos, productos sin costo), o un `SaleResult` de fallo que el
        llamador devuelve sin tocar nada más.

        El costo se lee DESPUÉS de reservar (Fase 7): reservar es lo que arma
        un producto reconstruible desde sus partes, y ese armado es lo que le
        da costo. Leído antes, un pollo que sólo se arma se vendía sin costo."""
        if not sale.goods_lines:
            # Sólo vales prepagados: nada sale del inventario (2026-10-03).
            return "NO_GOODS", {}, []
        inv_client = self._inventory_client(
            connection, branch_id=sale.branch_id, actor_user_id=actor_user_id)
        creada = False
        faltante = None
        if sale.inventory_reservation_id and not inv_client.covers(
                sale.inventory_reservation_id, sale):
            # Una venta suspendida con faltante apartó sólo lo que había: se
            # suelta y se resuelve como cualquier cobro (reserva completa o
            # autorización de venta sin existencia).
            inv_client.release(sale.inventory_reservation_id, reason="reserva parcial")
            sale.inventory_reservation_id = None
        try:
            if not sale.inventory_reservation_id:
                sale.inventory_reservation_id = inv_client.reserve_for_sale(sale)
                creada = True
        except InventoryShortageError as exc:
            faltante = str(exc)
        except SalesDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)

        costos, sin_costo = self._unit_costs(connection, sale)
        if faltante is None:
            try:
                inv_client.confirm(sale.inventory_reservation_id, sale_id=sale.id,
                                   folio=sale.sale_number or sale.id, unit_costs=costos)
            except SalesDomainError as exc:
                # La venta no se guarda: una reserva recién creada no puede
                # quedarse reteniendo mercancía de una venta que no se cobró.
                if creada:
                    inv_client.release(sale.id, reason="cobro fallido")
                return fail_from_domain_error(exc, operation_id=operation_id)
            return "RESERVED", costos, sin_costo

        # No alcanza la existencia: sólo con autorización en caliente.
        if not authorizer_user_id:
            return SaleResult.fail(
                f"Sin existencia suficiente: {faltante}. Para cobrar, otro usuario con "
                "permiso debe autorizar la venta sin existencia.",
                "STOCK_AUTHORIZATION_REQUIRED", operation_id=operation_id)
        if not (reason or "").strip():
            return SaleResult.fail("Vender sin existencia requiere un motivo",
                                   "STOCK_AUTHORIZATION_REQUIRED", operation_id=operation_id)
        try:
            self._authorizer_auth.authorize_exception(
                authorizer_user_id=authorizer_user_id, requested_by=actor_user_id,
                permission_code=SalesPermissions.SALE_WITHOUT_STOCK,
                operation_id=operation_id, reason=reason, amount=sale.totals.total,
                sale_id=sale.id)
            inv_client.issue_without_stock(sale, unit_costs=costos)
        except SalesDomainError as exc:
            return fail_from_domain_error(exc, operation_id=operation_id)
        return "WITHOUT_STOCK_AUTHORIZED", costos, sin_costo


def _completed_payload(sale, costos: dict, sin_costo: list[str], inventario: str, *,
                       authorizer_user_id, reason) -> dict:
    """El contrato de `SALE_COMPLETED` (Fase 6). Antes llevaba sólo `total`, y
    Finanzas necesita totales, pagos y costo para asentar la venta. Se publica
    en el vocabulario de Ventas (métodos de pago, totales de la venta); la
    traducción al de Finanzas vive en `backend/application/sales/integrations/`."""
    t = sale.totals
    pagos: dict[str, Decimal] = {}
    for pago in sale.payments:
        metodo = getattr(pago.method, "value", pago.method)
        pagos[metodo] = pagos.get(metodo, Decimal("0")) + pago.amount
    cambio = max(Decimal("0"), sale.total_paid - t.total)
    cogs = sum((line.quantity.value * costos[line.product_id]
                for line in sale.lines if line.product_id in costos), Decimal("0"))
    return {
        "sale_id": sale.id,
        # Sin folio asignado, el FINAL del UUIDv7: el principio es marca de
        # tiempo y se repite entre ventas del mismo momento.
        "folio": sale.sale_number or sale.id[-8:],
        "customer_id": sale.customer_id,
        "currency_code": getattr(sale, "currency_code", None) or "MXN",
        "gross_subtotal": str(t.gross_subtotal),
        "discount_total": str(t.discount_total),
        "promotion_total": str(t.promotion_total),
        "coupon_total": str(t.coupon_total),
        "loyalty_total": str(t.loyalty_total),
        "tax_total": str(t.tax_total),
        "rounding_adjustment": str(t.rounding_adjustment),
        "total": str(t.total),
        "payments": [{"method": m, "amount": str(a)} for m, a in sorted(pagos.items())],
        "change": str(cambio),
        # Para las reglas de Fidelidad (§13, 2026-10-03): por producto (multiplicadores
        # por categoría/producto, puntos por unidad) y canal.
        "channel": str(getattr(getattr(sale, "channel", None), "value",
                               getattr(sale, "channel", None)) or "POS"),
        "lines": [{"product_id": line.product_id, "quantity": str(line.quantity.value),
                   "amount": str(line.line_total)} for line in sale.goods_lines],
        # Vales prepagados vendidos: Finanzas los asienta como pasivo (no ingreso),
        # Fidelidad los activa y no acumulan puntos.
        "prepaid_vouchers": [{**v, "amount": str(v["amount"])} for v in sale.prepaid_vouchers()],
        # Cupones y vales (2026-10-03): Fidelidad confirma su canje al completar;
        # Finanzas liquida el vale contra su pasivo.
        "coupons": [{"coupon_instance_id": c.coupon_instance_id, "code": c.code,
                     "amount": str(c.amount)} for c in sale.coupons],
        "voucher_payments": [{**p, "amount": str(p["amount"])} for p in sale.voucher_payments()],
        "cogs_total": str(cogs.quantize(Decimal("0.01"))),
        "cogs_missing_products": sin_costo,
        "inventory_settlement": inventario,
        "stock_authorized_by": (authorizer_user_id
                                if inventario == "WITHOUT_STOCK_AUTHORIZED" else None),
        "stock_authorization_reason": (reason
                                       if inventario == "WITHOUT_STOCK_AUTHORIZED" else None),
    }
