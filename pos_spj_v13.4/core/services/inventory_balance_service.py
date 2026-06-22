"""Canonical read-only inventory balance service.

Wraps InventoryBalanceQueryService (the authoritative stock reader that lives in
backend/application/queries/) behind a simple interface that:
  - enforces required arguments (product_id, branch_id)
  - returns a typed InventoryBalanceDTO dataclass
  - provides get_available_stock() for point-in-time checks

This module is the single import target for any code that needs to CHECK stock
(as opposed to WRITE stock).  It intentionally contains no write logic.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

logger = logging.getLogger("spj.inventory.balance")


@dataclass(frozen=True)
class InventoryBalanceDTO:
    product_id: str
    branch_id: str
    physical_stock: Decimal
    reserved_stock: Decimal
    available_stock: Decimal
    base_unit: str


class InventoryBalanceService:
    """
    Single source of truth for inventory reads.
    Always filters by product_id + branch_id.

    Delegates to InventoryBalanceQueryService when available;
    falls back gracefully to direct SQL on older schema versions.
    """

    def __init__(self, db) -> None:
        self.db = db
        self._query_svc = self._build_query_svc()

    # ── Public API ─────────────────────────────────────────────────────────────

    def get_balance(self, product_id: Any, branch_id: Any) -> InventoryBalanceDTO:
        if not product_id:
            raise ValueError("product_id requerido")
        if not branch_id:
            raise ValueError("branch_id requerido")

        pid = str(product_id)
        bid = str(branch_id)

        if self._query_svc is not None:
            try:
                bal = self._query_svc.get_product_balance(pid, bid)
                return InventoryBalanceDTO(
                    product_id=str(pid),
                    branch_id=str(bid),
                    physical_stock=bal["stock_fisico"],
                    reserved_stock=bal["stock_reservado"],
                    available_stock=bal["stock_disponible"],
                    base_unit=bal.get("unidad_base", "u"),
                )
            except Exception as exc:
                logger.warning(
                    "InventoryBalanceQueryService.get_product_balance failed "
                    "product_id=%s branch_id=%s — falling back to direct SQL: %s",
                    pid, bid, exc,
                )

        # Fallback: direct SQL (handles schemas without inventario_actual)
        raw = self._query_stock(str(pid), str(bid))
        physical = Decimal(str(raw.get("physical_stock") or 0))
        reserved = Decimal(str(raw.get("reserved_stock") or 0))
        available = max(physical - reserved, Decimal("0"))
        return InventoryBalanceDTO(
            product_id=str(pid),
            branch_id=str(bid),
            physical_stock=physical,
            reserved_stock=reserved,
            available_stock=available,
            base_unit=raw.get("base_unit") or "u",
        )

    def get_available_stock(self, product_id: Any, branch_id: Any) -> Decimal:
        return self.get_balance(product_id, branch_id).available_stock

    # ── Private helpers ────────────────────────────────────────────────────────

    def _build_query_svc(self):
        try:
            from backend.application.queries.inventory_balance_service import (
                InventoryBalanceQueryService,
            )
            return InventoryBalanceQueryService(self.db)
        except Exception:
            return None

    def _query_stock(self, product_id: str, branch_id: str) -> dict:
        """Direct SQL fallback — tries inventario_actual then productos.existencia."""
        # inventario_actual is the canonical branch-aware table
        try:
            row = self.db.execute(
                "SELECT COALESCE(cantidad, 0) AS physical_stock, 0 AS reserved_stock, "
                "'' AS base_unit FROM inventario_actual "
                "WHERE producto_id=? AND sucursal_id=?",
                (product_id, branch_id),
            ).fetchone()
            if row:
                r = dict(row) if hasattr(row, "keys") else {
                    "physical_stock": row[0],
                    "reserved_stock": row[1],
                    "base_unit": row[2],
                }
                # also fetch unit
                unit_row = self.db.execute(
                    "SELECT COALESCE(unidad,'u') FROM productos WHERE id=?", (product_id,)
                ).fetchone()
                r["base_unit"] = unit_row[0] if unit_row else "u"
                return r
        except Exception:
            pass

        # Fall back to productos.existencia (global, no branch isolation)
        try:
            row = self.db.execute(
                "SELECT COALESCE(existencia, 0) AS physical_stock, 0 AS reserved_stock, "
                "COALESCE(unidad,'u') AS base_unit FROM productos WHERE id=?",
                (product_id,),
            ).fetchone()
            if row:
                d = dict(row) if hasattr(row, "keys") else {
                    "physical_stock": row[0],
                    "reserved_stock": row[1],
                    "base_unit": row[2],
                }
                logger.warning(
                    "get_balance: usando productos.existencia global para product_id=%s "
                    "(sin aislamiento de sucursal branch_id=%s)",
                    product_id, branch_id,
                )
                return d
        except Exception:
            pass

        return {"physical_stock": 0, "reserved_stock": 0, "base_unit": "u"}
