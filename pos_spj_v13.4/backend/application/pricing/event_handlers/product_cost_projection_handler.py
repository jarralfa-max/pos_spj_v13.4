"""ProductCostProjectionHandler (Pricing/Costing context, PRC-6).

Keeps the canonical ``product_cost`` fresh from operational events, so the 44
consumers read cost from ``ProductCostQueryService`` instead of
``productos.precio_compra`` / ``inventario_actual.costo_promedio``.

Consumes cost-carrying events whose lines expose ``product_id``, ``quantity`` and
``unit_cost``:
- ``PURCHASE_STOCK_ENTRY_REGISTERED`` — procurement receipt (weighted-average in);
- ``PRODUCTION_OUTPUT_COSTED``        — production output real cost (same shape).

Rules:
- Moving weighted-average via ``AverageCostingService`` (Decimal/Money-only).
- La cantidad previa es la EXISTENCIA REAL antes de la entrada (Inventario,
  ``CostingStockQueryService``), no ``tracked_quantity``: ese contador sólo sumaba
  entradas y nunca restaba salidas (100 @ $40, salen 90, entran 10 @ $60 daba
  $41.82 en vez de $50). ``tracked_quantity`` queda sólo como respaldo para bases
  sin inventario canónico.
- Se proyectan SIEMPRE el costo de empresa (branch '') y, si el evento trae
  sucursal, el de esa sucursal (§32); la política de costo decide cuál se lee.
- Idempotent per (product_id, event_id) via ``price_change_log`` (field='cost'),
  which doubles as the audit trail; a replay short-circuits.
- Atomic: all lines of an event apply in one transaction or none.
- Emits ``PRODUCT_COST_UPDATED`` to ``pricing_outbox`` per changed product.
- Never raises on a single bad line; logs and continues (a receipt must not fail
  because one line lacked a cost).
"""

from __future__ import annotations

import json
import logging
from decimal import Decimal, InvalidOperation

from backend.domain.pricing.events import PricingEvents, build_pricing_event_payload
from backend.domain.pricing.exceptions import PricingDomainError
from backend.domain.pricing.services.average_costing_service import AverageCostingService
from backend.domain.pricing.value_objects.money import Money
from backend.infrastructure.db.repositories.pricing.pricing_repository import (
    PricingRepository,
)

logger = logging.getLogger("spj.pricing.cost_projection")

COST_EVENTS = ("PURCHASE_STOCK_ENTRY_REGISTERED", "PRODUCTION_OUTPUT_COSTED")

_BRANCH_ALL = ""  # el costo canónico es global (como el backfill PRC-5)


def _dec(value) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _consolidated(lines) -> list[dict]:
    """Una línea por producto: cantidad total y costo ponderado.

    La idempotencia es por (producto, operación); con dos líneas del mismo
    producto en un evento la segunda se tomaba por "ya aplicada" y se perdía
    (cantidad y costo). Las líneas inválidas pasan tal cual para que
    `_apply_line` las descarte como antes."""
    merged: dict[str, dict] = {}
    others: list[dict] = []
    for line in lines:
        product_id = str(line.get("product_id") or "").strip()
        qty, cost = _dec(line.get("quantity")), _dec(line.get("unit_cost"))
        if not product_id or qty is None or cost is None or qty <= 0 or cost < 0:
            others.append(line)
            continue
        entry = merged.setdefault(product_id, {"qty": Decimal("0"), "value": Decimal("0")})
        entry["qty"] += qty
        entry["value"] += qty * cost
    return [{"product_id": pid, "quantity": e["qty"], "unit_cost": e["value"] / e["qty"]}
            for pid, e in merged.items()] + others


class ProductCostProjectionHandler:
    def __init__(self, connection, *, currency: str = "MXN", stock=None) -> None:
        self._conn = connection
        self._repo = PricingRepository(connection)
        self._costing = AverageCostingService()
        self._currency = currency
        if stock is None:
            from backend.application.inventory.queries.costing_stock_query_service import (
                CostingStockQueryService,
            )
            stock = CostingStockQueryService(connection)
        self._stock = stock

    def handle(self, payload: dict) -> None:
        event_id = str(payload.get("event_id") or "").strip()
        if not event_id:
            logger.warning("cost projection: evento sin event_id; se ignora")
            return
        lines = payload.get("lines") or []
        if not lines:
            return
        operation_id = str(payload.get("operation_id") or event_id)
        user_id = payload.get("user_id")
        branch_id = str(payload.get("branch_id") or "").strip()
        changed: list[tuple[str, Money]] = []
        try:
            for line in _consolidated(lines):
                result = self._apply_line(line, operation_id=operation_id, user_id=user_id,
                                          branch_id=branch_id)
                if result is not None:
                    changed.append(result)
            for product_id, new_avg in changed:
                self._emit(product_id, new_avg, operation_id=operation_id)
            self._conn.commit()
        except Exception:
            rollback = getattr(self._conn, "rollback", None)
            if rollback is not None:
                rollback()
            raise

    # ── internals ──────────────────────────────────────────────────────────
    def _apply_line(self, line: dict, *, operation_id: str, user_id,
                    branch_id: str = "") -> tuple[str, Money] | None:
        product_id = str(line.get("product_id") or "").strip()
        qty = _dec(line.get("quantity"))
        unit_cost = _dec(line.get("unit_cost"))
        if not product_id or qty is None or unit_cost is None or qty <= 0 or unit_cost < 0:
            return None
        if self._repo.cost_change_applied(product_id, operation_id):
            return None  # ya aplicado (idempotente)

        # §32: siempre las DOS vistas — empresa y sucursal, cada una con su propia
        # existencia. La política de costo sólo decide cuál se lee.
        company = self._project(product_id, qty, unit_cost, operation_id=operation_id,
                                user_id=user_id, branch_id="")
        if company is None:
            return None
        if branch_id:
            self._project(product_id, qty, unit_cost, operation_id=operation_id,
                          user_id=user_id, branch_id=branch_id)
        return product_id, company

    def _project(self, product_id: str, qty: Decimal, unit_cost: Decimal, *,
                 operation_id: str, user_id, branch_id: str) -> Money | None:
        prior_avg, tracked_qty = self._repo.cost_basis(product_id, branch_id or _BRANCH_ALL)
        on_hand = self._stock.on_hand_before(product_id, operation_id=operation_id,
                                             branch_id=branch_id or None)
        prior_qty = tracked_qty if on_hand is None else on_hand
        try:
            update = self._costing.apply_receipt(
                prior_average=prior_avg, prior_quantity=prior_qty,
                unit_cost=Money(unit_cost, self._currency), incoming_quantity=qty)
        except PricingDomainError as exc:
            logger.warning("cost projection: línea inválida producto=%s: %s", product_id, exc)
            return None
        self._repo.upsert_cost_basis(
            product_id=product_id, branch_id=branch_id or _BRANCH_ALL,
            average=update.average_cost, last=update.last_cost,
            tracked_quantity=update.tracked_quantity)
        self._repo.log_cost_change(
            product_id=product_id, branch_id=branch_id or None, old_value=prior_avg,
            new_value=update.average_cost, operation_id=operation_id, user_id=user_id)
        return update.average_cost

    def _emit(self, product_id: str, new_avg: Money, *, operation_id: str) -> None:
        evt = build_pricing_event_payload(
            PricingEvents.PRODUCT_COST_UPDATED, operation_id=operation_id,
            entity_id=product_id, product_id=product_id, branch_id=None,
            average_cost=str(new_avg.amount), currency=new_avg.currency)
        self._repo.enqueue_event(
            event_id=evt["event_id"], event_name=evt["event_name"],
            operation_id=operation_id, entity_id=product_id, payload=json.dumps(evt))
