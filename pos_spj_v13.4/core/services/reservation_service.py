"""ReservationService — manages temporary stock reservations for delivery orders.

Reservation lifecycle:
  1. reserve()         — lock qty at order creation (no inventory deduction)
  2. commit()          — convert reservation to real movement (at preparation/delivery)
  3. release()         — free lock (on cancellation or expiry)

Stock availability:
  available = physical_stock - active_reserved_qty

Thread-safety: all writes use a module-level RLock so concurrent order creation
from multiple workers does not double-reserve the same stock.
"""
from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timedelta
from threading import RLock
from typing import List, Optional

logger = logging.getLogger("spj.services.reservation")

_LOCK = RLock()

# Weight units treated as variable (must go through prepared_qty adjustment)
VARIABLE_WEIGHT_UNITS = frozenset({"kg", "g", "lb", "oz", "gr"})

# Tolerance by units, not percentage. Default business rule: +-0.2 units.
TOLERANCE_UNITS = float(os.environ.get("DELIVERY_WEIGHT_TOLERANCE_UNITS", "0.2"))


class ReservationService:
    """Manages inventory_reservations table to support soft-lock of stock."""

    # ── Public API ────────────────────────────────────────────────────────────

    def reserve(
        self,
        db,
        product_id: int,
        qty: float,
        operation_id: str,
        branch_id: int = 1,
        operation_type: str = "delivery",
        expires_hours: int = 24,
    ) -> str:
        """Reserve *qty* units for *operation_id*.

        Returns the reservation UUID. Raises ValueError if available stock < qty.
        """
        reservation_id = uuid.uuid4().hex
        expires_at = (datetime.utcnow() + timedelta(hours=expires_hours)).isoformat()

        with _LOCK:
            available = self.get_available_stock(db, product_id, branch_id)
            if available < qty:
                raise ValueError(
                    f"Stock insuficiente para reservar: disponible={available:.3f}, "
                    f"solicitado={qty:.3f}, producto_id={product_id}"
                )
            db.execute(
                """INSERT INTO inventory_reservations
                   (id, branch_id, product_id, reserved_qty, operation_id,
                    operation_type, expires_at, released)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 0)""",
                (reservation_id, branch_id, product_id, qty,
                 operation_id, operation_type, expires_at),
            )
            try:
                db.commit()
            except Exception:
                pass

        logger.info(
            "Reserved product_id=%d qty=%.3f op=%s branch=%d expires=%s",
            product_id, qty, operation_id, branch_id, expires_at,
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
            try:
                db.commit()
            except Exception:
                pass
        if count:
            logger.info("Released %d reservation(s) for op=%s", count, operation_id)
        return count

    def commit_reservation(
        self,
        db,
        operation_id: str,
        product_id: int,
        actual_qty: float,
        branch_id: int = 1,
    ) -> None:
        """Convert a reservation to a confirmed inventory movement.

        Releases the reservation lock and (via InventoryService) deducts
        the actual_qty from physical stock — not the reserved amount.
        """
        released = self.release_by_operation(db, operation_id)
        if released == 0:
            logger.warning("commit_reservation: no active reservation for op=%s", operation_id)

        try:
            from core.services.inventory_service import InventoryService as InvSvc
            inv = InvSvc(db)
            inv.deduct_stock(
                product_id=product_id,
                branch_id=branch_id,
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

    def get_reserved_qty(self, db, product_id: int, branch_id: int) -> float:
        """Sum of active, non-expired reservations for this product/branch."""
        try:
            row = db.execute(
                """SELECT COALESCE(SUM(reserved_qty), 0)
                   FROM inventory_reservations
                   WHERE product_id=? AND branch_id=?
                     AND released=0
                     AND expires_at > datetime('now')""",
                (product_id, branch_id),
            ).fetchone()
            return float(row[0]) if row else 0.0
        except Exception as exc:
            logger.debug("get_reserved_qty error: %s", exc)
            return 0.0

    def get_available_stock(self, db, product_id: int, branch_id: int) -> float:
        """Physical stock minus active reservations."""
        try:
            row = db.execute(
                "SELECT COALESCE(cantidad, 0) FROM inventario_actual "
                "WHERE producto_id=? AND sucursal_id=?",
                (product_id, branch_id),
            ).fetchone()
            physical = float(row[0]) if row else 0.0
        except Exception as exc:
            logger.debug("get_available_stock physical query error: %s", exc)
            physical = 0.0

        reserved = self.get_reserved_qty(db, product_id, branch_id)
        available = max(0.0, physical - reserved)
        logger.debug(
            "available_stock product=%d branch=%d physical=%.3f reserved=%.3f available=%.3f",
            product_id, branch_id, physical, reserved, available,
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