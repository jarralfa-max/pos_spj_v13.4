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
- Costing is global (branch ''), matching the PRC-5 backfill dimension.
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


class ProductCostProjectionHandler:
    def __init__(self, connection, *, currency: str = "MXN") -> None:
        self._conn = connection
        self._repo = PricingRepository(connection)
        self._costing = AverageCostingService()
        self._currency = currency

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
        changed: list[tuple[str, Money]] = []
        try:
            for line in lines:
                result = self._apply_line(line, operation_id=operation_id, user_id=user_id)
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
    def _apply_line(self, line: dict, *, operation_id: str, user_id) -> tuple[str, Money] | None:
        product_id = str(line.get("product_id") or "").strip()
        qty = _dec(line.get("quantity"))
        unit_cost = _dec(line.get("unit_cost"))
        if not product_id or qty is None or unit_cost is None or qty <= 0 or unit_cost < 0:
            return None
        if self._repo.cost_change_applied(product_id, operation_id):
            return None  # ya aplicado (idempotente)

        prior_avg, prior_qty = self._repo.cost_basis(product_id, _BRANCH_ALL)
        try:
            update = self._costing.apply_receipt(
                prior_average=prior_avg, prior_quantity=prior_qty,
                unit_cost=Money(unit_cost, self._currency), incoming_quantity=qty)
        except PricingDomainError as exc:
            logger.warning("cost projection: línea inválida producto=%s: %s", product_id, exc)
            return None

        self._repo.upsert_cost_basis(
            product_id=product_id, branch_id=_BRANCH_ALL, average=update.average_cost,
            last=update.last_cost, tracked_quantity=update.tracked_quantity)
        self._repo.log_cost_change(
            product_id=product_id, branch_id=None, old_value=prior_avg,
            new_value=update.average_cost, operation_id=operation_id, user_id=user_id)
        return product_id, update.average_cost

    def _emit(self, product_id: str, new_avg: Money, *, operation_id: str) -> None:
        evt = build_pricing_event_payload(
            PricingEvents.PRODUCT_COST_UPDATED, operation_id=operation_id,
            entity_id=product_id, product_id=product_id, branch_id=None,
            average_cost=str(new_avg.amount), currency=new_avg.currency)
        self._repo.enqueue_event(
            event_id=evt["event_id"], event_name=evt["event_name"],
            operation_id=operation_id, entity_id=product_id, payload=json.dumps(evt))
