"""ReservationService — manages temporary stock reservations for delivery orders.

Reservation lifecycle:
  1. reserve()         — lock qty at order creation (no inventory deduction)
  2. commit()          — convert reservation to real movement (at preparation/delivery)
  3. release()         — free lock (on cancellation or expiry)

Stock availability:
  available = physical_stock - active_reserved_qty

Thread-safety: all writes use a module-level RLock so concurrent order creation
from multiple workers does not double-reserve the same stock.

Identity contract: product_id and branch_id MUST be UUIDv7 strings.
Any digit-only string is rejected immediately with an explicit error.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from threading import RLock
from typing import List

from backend.shared.ids import new_uuid

logger = logging.getLogger("spj.services.reservation")

_LOCK = RLock()

# Weight units treated as variable (must go through prepared_qty adjustment)
VARIABLE_WEIGHT_UNITS = frozenset({"kg", "g", "lb", "oz", "gr"})

# Tolerance by units, not percentage. Default business rule: +-0.2 units.
TOLERANCE_UNITS = float(os.environ.get("DELIVERY_WEIGHT_TOLERANCE_UNITS", "0.2"))


def _require_uuid(value: str | None, field: str) -> str:
    """Validate that *value* looks like a UUID (not a bare integer). Returns str."""
    s = str(value or "").strip()
    if not s:
        raise ValueError(f"Legacy identity rejected: {field} is empty. Expected UUIDv7.")
    if s.isdigit():
        raise ValueError(
            f"Legacy identity rejected: {field}={s}. Expected UUIDv7, got integer. "
            "Delete the DB and reseed with UUID-only schema."
        )
    return s


class ReservationService:
    """Manages inventory_reservations table to support soft-lock of stock."""

    # ── Public API ────────────────────────────────────────────────────────────

    def reserve(
        self,
        db,
        product_id: str,
        qty: float,
        operation_id: str,
        branch_id: str,
        operation_type: str = "delivery",
        expires_hours: int = 24,
    ) -> str:
        """Reserve *qty* units for *operation_id*.

        Returns the reservation UUID. Raises ValueError if available stock < qty.
        product_id and branch_id must be UUIDv7 strings — integer IDs are rejected.
        """
        pid = _require_uuid(product_id, "product_id")
        bid = _require_uuid(branch_id, "branch_id")
        reservation_id = new_uuid()
        expires_at = (datetime.utcnow() + timedelta(hours=expires_hours)).isoformat()

        with _LOCK:
            available = self.get_available_stock(db, pid, bid)
            if available < qty:
                raise ValueError(
                    f"Stock insuficiente para reservar: disponible={available:.3f}, "
                    f"solicitado={qty:.3f}, product_id={pid}"
                )
            db.execute(
                """INSERT INTO inventory_reservations
                   (id, branch_id, product_id, reserved_qty, operation_id,
                    operation_type, expires_at, released)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 0)""",
                (reservation_id, bid, pid, qty,
                 operation_id, operation_type, expires_at),
            )

        logger.info(
            "Reserved product_id=%s qty=%.3f op=%s branch=%s expires=%s",
            pid, qty, operation_id, bid, expires_at,
        )
        return reservation_id

    def release_by_operation(self, db, operation_id: str) -> int:
        """Mark all active reservations for *operation_id* as released.

        Returns number of rows released.
        """
        with _LOCK:
            cur = db.execute(
                "UPDATE inventory_reservations SET released=1 "
                "WHERE operation_id=? AND released=0",
                (operation_id,),
            )
            count = cur.rowcount
        if count:
            logger.info("Released %d reservation(s) for op=%s", count, operation_id)
        return count

    def adjust_reservation(
        self,
        db,
        operation_id: str,
        product_id: str,
        new_qty: float,
        branch_id: str,
    ) -> int:
        """Re-set the active reservation for *operation_id*+*product_id* to *new_qty*.

        Called after a weight/quantity adjustment so the soft-lock reflects the
        real prepared quantity instead of the original requested quantity.

        Idempotent by construction: it writes an ABSOLUTE value, so replaying the
        same adjustment yields the same row state. Returns rows updated (0 or 1).
        """
        pid = _require_uuid(product_id, "product_id")
        with _LOCK:
            cur = db.execute(
                "UPDATE inventory_reservations SET reserved_qty=? "
                "WHERE operation_id=? AND product_id=? AND released=0",
                (new_qty, operation_id, pid),
            )
            count = cur.rowcount
        logger.info(
            "Adjusted reservation op=%s product_id=%s new_qty=%.3f rows=%d",
            operation_id, pid, new_qty, count,
        )
        return count

    def commit_reservation(
        self,
        db,
        operation_id: str,
        product_id: str,
        actual_qty: float,
        branch_id: str,
    ) -> None:
        """Convert a reservation to a confirmed inventory movement.

        Releases the reservation lock and (via InventoryService) deducts
        the actual_qty from physical stock — not the reserved amount.
        """
        pid = _require_uuid(product_id, "product_id")
        bid = _require_uuid(branch_id, "branch_id")
        released = self.release_by_operation(db, operation_id)
        if released == 0:
            logger.warning("commit_reservation: no active reservation for op=%s", operation_id)

        try:
            from core.services.inventory_service import InventoryService as InvSvc
            inv = InvSvc(db)
            inv.deduct_stock(
                product_id=pid,
                branch_id=bid,
                qty=actual_qty,
                reference_type="delivery_prepared",
                reference_id=operation_id,
                operation_id=operation_id,
                user="sistema",
                notes=f"delivery prepared qty={actual_qty:.3f}",
            )
        except Exception as exc:
            logger.error("commit_reservation: inventory deduct failed op=%s: %s", operation_id, exc)
            raise

    def get_reserved_qty(self, db, product_id: str, branch_id: str) -> float:
        """Sum of active, non-expired reservations for this product/branch."""
        pid = _require_uuid(product_id, "product_id")
        bid = _require_uuid(branch_id, "branch_id")
        try:
            row = db.execute(
                """SELECT COALESCE(SUM(reserved_qty), 0)
                   FROM inventory_reservations
                   WHERE product_id=? AND branch_id=?
                     AND released=0
                     AND expires_at > datetime('now')""",
                (pid, bid),
            ).fetchone()
            return float(row[0]) if row else 0.0
        except Exception as exc:
            logger.debug("get_reserved_qty error: %s", exc)
            return 0.0

    def get_available_stock(self, db, product_id: str, branch_id: str) -> float:
        """Physical stock minus active reservations.

        Reads from inventory_stock (canonical) — never from the legacy integer-keyed table.
        """
        pid = _require_uuid(product_id, "product_id")
        bid = _require_uuid(branch_id, "branch_id")
        try:
            row = db.execute(
                "SELECT COALESCE(quantity, 0) FROM inventory_stock "
                "WHERE product_id=? AND branch_id=?",
                (pid, bid),
            ).fetchone()
            physical = float(row[0]) if row else 0.0
        except Exception as exc:
            logger.debug("get_available_stock physical query error: %s", exc)
            physical = 0.0

        reserved = self.get_reserved_qty(db, pid, bid)
        available = max(0.0, physical - reserved)
        logger.debug(
            "available_stock product=%s branch=%s physical=%.3f reserved=%.3f available=%.3f",
            pid, bid, physical, reserved, available,
        )
        return available

    def get_reservations_for_operation(self, db, operation_id: str) -> List[dict]:
        """Return all active reservation rows for an operation."""
        try:
            rows = db.execute(
                """SELECT id, product_id, reserved_qty, branch_id, expires_at
                   FROM inventory_reservations
                   WHERE operation_id=? AND released=0""",
                (operation_id,),
            ).fetchall()
            return [
                {
                    "id": r[0],
                    "product_id": r[1],
                    "reserved_qty": r[2],
                    "branch_id": r[3],
                    "expires_at": r[4],
                }
                for r in rows
            ]
        except Exception as exc:
            logger.debug("get_reservations_for_operation error: %s", exc)
            return []

    # ── Weight helpers ────────────────────────────────────────────────────────

    @staticmethod
    def is_variable_weight(unit: str) -> bool:
        return (unit or "").lower().strip() in VARIABLE_WEIGHT_UNITS

    @staticmethod
    def compute_adjustment(
        requested_qty: float,
        prepared_qty: float,
        unit_price: float,
        tolerance_units: float = TOLERANCE_UNITS,
    ) -> dict:
        """Return adjustment metadata for a single item.

        Tolerance is measured in absolute units, not percentage.
        Example: requested=2.0 kg, prepared=2.25 kg, tolerance=0.2 → exceeded.
        """
        diff_qty = prepared_qty - requested_qty
        diff_abs = abs(diff_qty)
        diff_pct = abs(diff_qty / requested_qty) if requested_qty else 0.0
        new_subtotal = round(prepared_qty * unit_price, 4)
        return {
            "diff_qty": round(diff_qty, 4),
            "diff_abs": round(diff_abs, 4),
            "diff_pct": round(diff_pct * 100, 2),
            "new_subtotal": new_subtotal,
            "tolerance_units": float(tolerance_units),
            "tolerance_exceeded": diff_abs > float(tolerance_units),
        }
