"""Rebuild & validate the balance projection from the ledger (§6.3).

The ledger (``inventory_ledger`` + ``inventory_ledger_lines``) is the source of
truth; ``inventory_balances`` is a reconstructable projection. These read-only use
cases replay the whole ledger into a scratch in-memory projection (never touching
the real ledger or balances) and:

- ``RebuildInventoryBalancesUseCase`` returns the reconstructed balance map;
- ``ValidateInventoryProjectionUseCase`` diffs it against the live projection and
  reports per-dimension drift, so a cutover can abort on any difference.

Only physical quantity/weight are ledger-derived; ``reserved_*`` comes from the
reservation projection (not the ledger) and is out of scope for this check.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from backend.application.inventory.services.inventory_projection_service import (
    InventoryProjectionService,
    _line_from_row,
)
from backend.domain.inventory.entities.inventory_balance import InventoryBalance
from backend.domain.inventory.enums import InventoryStatus, MovementType
from backend.infrastructure.db.repositories.inventory.base import (
    InventoryRepositoryBase,
    to_decimal,
)
from backend.infrastructure.db.repositories.inventory.inventory_ledger_repository import (
    InventoryLedgerRepository,
)

# Dimension key = full balance identity (None normalised to '').
_Key = tuple[str, str, str, str, str, str, str]


def _key(*, product_id, branch_id, warehouse_id, inventory_status,
         location_id, lot_id, serial_id) -> _Key:
    status = inventory_status.value if hasattr(inventory_status, "value") \
        else str(inventory_status)
    return (str(product_id), str(branch_id), str(warehouse_id), status,
            location_id or "", lot_id or "", serial_id or "")


class _ScratchBalances:
    """In-memory balance store mirroring the projection's get/upsert contract."""

    def __init__(self) -> None:
        self._by_key: dict[_Key, InventoryBalance] = {}

    def get(self, *, product_id, branch_id, warehouse_id,
            inventory_status=InventoryStatus.AVAILABLE,
            location_id=None, lot_id=None, serial_id=None):
        return self._by_key.get(_key(
            product_id=product_id, branch_id=branch_id, warehouse_id=warehouse_id,
            inventory_status=inventory_status, location_id=location_id,
            lot_id=lot_id, serial_id=serial_id))

    def upsert(self, balance: InventoryBalance) -> None:
        self._by_key[_key(
            product_id=balance.product_id, branch_id=balance.branch_id,
            warehouse_id=balance.warehouse_id,
            inventory_status=balance.inventory_status,
            location_id=balance.location_id, lot_id=balance.lot_id,
            serial_id=balance.serial_id)] = balance

    def values(self):
        return self._by_key.values()


class _ScratchUoW:
    def __init__(self) -> None:
        self.balances = _ScratchBalances()


class _ReplayMovement:
    """Minimal movement for replaying a non-reversal row through the projection."""

    def __init__(self, movement_type, branch_id, warehouse_id, lines) -> None:
        self.movement_type = movement_type
        self.branch_id = branch_id
        self.warehouse_id = warehouse_id
        self.lines = lines


class RebuildInventoryBalancesUseCase:
    """Replay the ledger into a scratch projection (read-only; never mutates)."""

    def rebuild(self, connection) -> dict[_Key, InventoryBalance]:
        ledger = InventoryLedgerRepository(connection)
        movements = ledger.list_all_ordered()
        by_id = {m["id"]: m for m in movements}
        scratch = _ScratchUoW()
        projection = InventoryProjectionService(scratch)

        for row in movements:
            mtype = MovementType(row["movement_type"])
            line_rows = ledger.get_lines(row["id"])
            if mtype is MovementType.REVERSAL:
                original = by_id.get(row.get("reversal_of_id"))
                if original is None:
                    continue  # orphan reversal — cannot attribute an effect
                projection.project_reversal(
                    branch_id=row["branch_id"], warehouse_id=row["warehouse_id"],
                    original_movement_type=MovementType(original["movement_type"]),
                    original_line_rows=line_rows)
            else:
                lines = [_line_from_row(r) for r in line_rows]
                projection.project_movement(
                    _ReplayMovement(mtype, row["branch_id"], row["warehouse_id"], lines),
                    negative_allowed=True, authorized=True)
        return {_key(
            product_id=b.product_id, branch_id=b.branch_id,
            warehouse_id=b.warehouse_id, inventory_status=b.inventory_status,
            location_id=b.location_id, lot_id=b.lot_id, serial_id=b.serial_id): b
            for b in scratch.balances.values()}


@dataclass(frozen=True, slots=True)
class BalanceDriftRow:
    key: _Key
    projected_quantity: Decimal
    rebuilt_quantity: Decimal
    projected_weight: Decimal
    rebuilt_weight: Decimal

    @property
    def quantity_drift(self) -> Decimal:
        return self.projected_quantity - self.rebuilt_quantity

    @property
    def weight_drift(self) -> Decimal:
        return self.projected_weight - self.rebuilt_weight


class ValidateInventoryProjectionUseCase(InventoryRepositoryBase):
    """Diff the live balance projection against a ledger rebuild (§6.3)."""

    def _live_balances(self) -> dict[_Key, tuple[Decimal, Decimal]]:
        rows = self._query(
            "SELECT product_id, branch_id, warehouse_id, inventory_status,"
            " location_id, lot_id, serial_id, quantity, weight FROM inventory_balances")
        out: dict[_Key, tuple[Decimal, Decimal]] = {}
        for r in rows:
            out[_key(
                product_id=r["product_id"], branch_id=r["branch_id"],
                warehouse_id=r["warehouse_id"], inventory_status=r["inventory_status"],
                location_id=r["location_id"], lot_id=r["lot_id"],
                serial_id=r["serial_id"])] = (
                    to_decimal(r["quantity"]), to_decimal(r["weight"]))
        return out

    def validate(self) -> list[BalanceDriftRow]:
        rebuilt = RebuildInventoryBalancesUseCase().rebuild(self._conn)
        live = self._live_balances()
        drifts: list[BalanceDriftRow] = []
        for key in sorted(set(live) | set(rebuilt)):
            lq, lw = live.get(key, (Decimal("0"), Decimal("0")))
            rb = rebuilt.get(key)
            rq = rb.quantity if rb else Decimal("0")
            rw = rb.weight if rb else Decimal("0")
            if lq != rq or lw != rw:
                drifts.append(BalanceDriftRow(
                    key=key, projected_quantity=lq, rebuilt_quantity=rq,
                    projected_weight=lw, rebuilt_weight=rw))
        return drifts

    def has_drift(self) -> bool:
        return bool(self.validate())
