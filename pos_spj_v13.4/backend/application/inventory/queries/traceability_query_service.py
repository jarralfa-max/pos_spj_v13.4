"""TraceabilityQueryService — upstream/downstream lot trace + recall (§32).

Traceability is read-only and derived from what is already recorded: the ledger
(every movement carries its lot) plus the explicit genealogy links that bridge
lot-identity breaks (production/slaughter/repack). This service answers three
questions a food/meat ERP must answer on demand:

- **Upstream** (``trace_upstream``): where did this lot come from? Its origin
  (supplier/production/slaughter, from ``inventory_lots``), its explicit parent
  lots, and the INCREASE ledger movements that brought it in.
- **Downstream** (``trace_downstream``): where did this lot go? The DECREASE
  ledger movements (sales, transfers, consumption, waste) and its explicit child
  lots.
- **Recall** (``recall_report``): walking downstream recursively through child
  lots, the full distribution footprint — every branch/warehouse/document that
  received affected stock, so a recall can reach all of it.

Read-only; Decimal throughout; never mutates the ledger or balances.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from backend.domain.inventory.enums import (
    MOVEMENT_DIRECTION,
    MovementDirection,
    MovementType,
    TraceabilityDirection,
)
from backend.infrastructure.db.repositories.inventory.base import to_decimal
from backend.infrastructure.db.repositories.inventory.inventory_lot_repository import (
    InventoryLotRepository,
)
from backend.infrastructure.db.repositories.inventory.traceability_repository import (
    TraceabilityRepository,
)


def _direction_of(movement_type: str) -> MovementDirection | None:
    try:
        return MOVEMENT_DIRECTION[MovementType(movement_type)]
    except (ValueError, KeyError):
        return None


@dataclass(frozen=True, slots=True)
class TraceEvent:
    movement_id: str
    movement_type: str
    direction: str            # INCREASE | DECREASE | STATUS_TRANSFER | ...
    source_module: str
    source_document_type: str
    source_document_id: str
    branch_id: str
    warehouse_id: str
    quantity: Decimal
    weight: Decimal
    occurred_at: str


@dataclass(frozen=True, slots=True)
class GenealogyEdge:
    parent_lot_id: str
    child_lot_id: str
    link_type: str
    quantity: Decimal
    weight: Decimal
    source_document_type: str | None
    source_document_id: str | None


@dataclass(frozen=True, slots=True)
class LotTraceDTO:
    lot_id: str
    direction: str
    product_id: str | None = None
    origin: dict = field(default_factory=dict)
    events: tuple[TraceEvent, ...] = ()
    links: tuple[GenealogyEdge, ...] = ()


@dataclass(frozen=True, slots=True)
class RecallReportDTO:
    root_lot_id: str
    affected_lot_ids: tuple[str, ...] = ()
    distribution: tuple[TraceEvent, ...] = ()
    origin: dict = field(default_factory=dict)

    @property
    def reaches_customers(self) -> bool:
        return any(e.movement_type == MovementType.SALE_ISSUE.value
                   for e in self.distribution)

    @property
    def branches_touched(self) -> tuple[str, ...]:
        return tuple(sorted({e.branch_id for e in self.distribution if e.branch_id}))


class TraceabilityQueryService:
    def __init__(self, connection) -> None:
        self._trace = TraceabilityRepository(connection)
        self._lots = InventoryLotRepository(connection)

    # ── public API ──────────────────────────────────────────────────────────
    def trace_upstream(self, lot_id: str) -> LotTraceDTO:
        events = tuple(e for e in self._events_for(lot_id)
                       if e.direction == MovementDirection.INCREASE.value)
        links = tuple(_edge(r) for r in self._trace.parents_of(lot_id))
        return LotTraceDTO(
            lot_id=lot_id, direction=TraceabilityDirection.UPSTREAM.value,
            product_id=self._product_of(lot_id), origin=self._origin_of(lot_id),
            events=events, links=links)

    def trace_downstream(self, lot_id: str) -> LotTraceDTO:
        events = tuple(e for e in self._events_for(lot_id)
                       if e.direction == MovementDirection.DECREASE.value)
        links = tuple(_edge(r) for r in self._trace.children_of(lot_id))
        return LotTraceDTO(
            lot_id=lot_id, direction=TraceabilityDirection.DOWNSTREAM.value,
            product_id=self._product_of(lot_id), events=events, links=links)

    def recall_report(self, lot_id: str) -> RecallReportDTO:
        """Walk downstream recursively (ledger DECREASE + child genealogy),
        collecting every distribution event across all affected lots."""
        affected: list[str] = []
        seen: set[str] = set()
        distribution: list[TraceEvent] = []
        stack = [lot_id]
        while stack:
            current = stack.pop()
            if current in seen:
                continue
            seen.add(current)
            affected.append(current)
            distribution.extend(
                e for e in self._events_for(current)
                if e.direction == MovementDirection.DECREASE.value)
            for row in self._trace.children_of(current):
                child = row["child_lot_id"]
                if child not in seen:
                    stack.append(child)
        distribution.sort(key=lambda e: e.occurred_at)
        return RecallReportDTO(
            root_lot_id=lot_id, affected_lot_ids=tuple(affected),
            distribution=tuple(distribution), origin=self._origin_of(lot_id))

    # ── internals ─────────────────────────────────────────────────────────
    def _events_for(self, lot_id: str) -> list[TraceEvent]:
        events: list[TraceEvent] = []
        for row in self._trace.ledger_movements_for_lot(lot_id):
            direction = _direction_of(row["movement_type"])
            events.append(TraceEvent(
                movement_id=row["movement_id"], movement_type=row["movement_type"],
                direction=direction.value if direction else "UNKNOWN",
                source_module=row["source_module"],
                source_document_type=row["source_document_type"],
                source_document_id=row["source_document_id"],
                branch_id=row["branch_id"], warehouse_id=row["warehouse_id"],
                quantity=to_decimal(row["quantity"]), weight=to_decimal(row["weight"]),
                occurred_at=row["occurred_at"]))
        return events

    def _origin_of(self, lot_id: str) -> dict:
        lot = self._lots.get(lot_id)
        if lot is None:
            return {}
        return {
            "lot_code": lot.lot_code,
            "origin_type": lot.origin_type.value,
            "origin_document_id": lot.origin_document_id,
            "supplier_lot_code": lot.supplier_lot_code,
            "production_lot_code": lot.production_lot_code,
            "slaughter_lot_code": lot.slaughter_lot_code,
            "production_date": lot.production_date,
            "slaughter_date": lot.slaughter_date,
            "expiration_date": lot.expiration_date,
            "received_at": lot.received_at,
            "branch_id": lot.branch_id,
        }

    def _product_of(self, lot_id: str) -> str | None:
        lot = self._lots.get(lot_id)
        return lot.product_id if lot else None


def _edge(row: dict) -> GenealogyEdge:
    return GenealogyEdge(
        parent_lot_id=row["parent_lot_id"], child_lot_id=row["child_lot_id"],
        link_type=row["link_type"], quantity=to_decimal(row["quantity"]),
        weight=to_decimal(row["weight"]),
        source_document_type=row["source_document_type"],
        source_document_id=row["source_document_id"])
