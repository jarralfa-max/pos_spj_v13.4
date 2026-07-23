"""BarcodeRepository — persistence for product barcodes and alternate codes (PROD-7).

Enforces active-barcode uniqueness at assignment time via the uniqueness policy
(the DB also has a partial UNIQUE index as a backstop). Parametrized queries only;
never commits (the caller owns the transaction boundary).
"""

from __future__ import annotations

from backend.domain.products.barcode_enums import BarcodeType
from backend.domain.products.entities.product_alternate_code import (
    ProductAlternateCode,
)
from backend.domain.products.entities.product_barcode import ProductBarcode
from backend.domain.products.policies.barcode_uniqueness_policy import (
    ensure_barcode_assignable,
)
from backend.domain.products.value_objects.barcode import Barcode


class BarcodeRepository:
    def __init__(self, connection) -> None:
        self._conn = connection

    # ── barcodes ──────────────────────────────────────────────────────────
    def active_owner(self, barcode_value: str) -> str | None:
        row = self._conn.execute(
            "SELECT product_id FROM product_barcodes "
            "WHERE barcode_value=? AND active=1", (barcode_value,)).fetchone()
        return row["product_id"] if row else None

    def assign(self, barcode: ProductBarcode) -> None:
        """Assign a barcode after checking active-uniqueness (§17)."""
        ensure_barcode_assignable(
            barcode_value=barcode.value,
            product_id=barcode.product_id,
            current_owner_product_id=self.active_owner(barcode.value))
        self._conn.execute(
            """INSERT INTO product_barcodes
               (id, product_id, variant_id, barcode_value, barcode_type,
                is_primary, active)
               VALUES (?,?,?,?,?,?,?)""",
            (barcode.id, barcode.product_id, barcode.variant_id, barcode.value,
             barcode.barcode.barcode_type.value, int(barcode.is_primary),
             int(barcode.active)))

    def list_for_product(self, product_id: str) -> list[ProductBarcode]:
        rows = self._conn.execute(
            "SELECT * FROM product_barcodes WHERE product_id=? ORDER BY is_primary DESC",
            (product_id,)).fetchall()
        return [self._row_to_barcode(r) for r in rows]

    def find_by_value(self, barcode_value: str) -> ProductBarcode | None:
        row = self._conn.execute(
            "SELECT * FROM product_barcodes WHERE barcode_value=? AND active=1",
            (barcode_value,)).fetchone()
        return self._row_to_barcode(row) if row else None

    @staticmethod
    def _row_to_barcode(row) -> ProductBarcode:
        return ProductBarcode(
            id=row["id"], product_id=row["product_id"], variant_id=row["variant_id"],
            barcode=Barcode(value=row["barcode_value"],
                            barcode_type=BarcodeType(row["barcode_type"])),
            is_primary=bool(row["is_primary"]), active=bool(row["active"]))

    # ── alternate codes ───────────────────────────────────────────────────
    def add_alternate_code(self, code: ProductAlternateCode) -> None:
        self._conn.execute(
            """INSERT INTO product_alternate_codes
               (id, product_id, code, code_type, supplier_id, active)
               VALUES (?,?,?,?,?,?)""",
            (code.id, code.product_id, code.code, code.code_type,
             code.supplier_id, int(code.active)))

    def list_alternate_codes(self, product_id: str) -> list[ProductAlternateCode]:
        rows = self._conn.execute(
            "SELECT * FROM product_alternate_codes WHERE product_id=?",
            (product_id,)).fetchall()
        return [ProductAlternateCode(
            id=r["id"], product_id=r["product_id"], code=r["code"],
            code_type=r["code_type"], supplier_id=r["supplier_id"],
            active=bool(r["active"])) for r in rows]
