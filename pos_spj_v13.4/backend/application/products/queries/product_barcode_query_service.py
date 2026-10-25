"""ProductBarcodeQueryService (PROD-22) — códigos de barras y alternos de UN producto.

Read side del diálogo «Códigos de barras» (§17). Los casos de uso de asignación
existían desde PROD-7 pero ninguna pantalla los alcanzaba ni podía listar lo
asignado. Read-only.
"""

from __future__ import annotations


class ProductBarcodeQueryService:
    def __init__(self, connection) -> None:
        self._conn = connection

    def list_barcodes(self, product_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT id, barcode_value, barcode_type, is_primary, active FROM product_barcodes "
            "WHERE product_id=? ORDER BY active DESC, is_primary DESC, created_at",
            (product_id,)).fetchall()
        return [{"id": r[0], "value": r[1], "barcode_type": r[2],
                 "is_primary": bool(r[3]), "active": bool(r[4])} for r in rows]

    def list_alternate_codes(self, product_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT id, code, code_type, supplier_id, active FROM product_alternate_codes "
            "WHERE product_id=? ORDER BY active DESC, created_at", (product_id,)).fetchall()
        return [{"id": r[0], "code": r[1], "code_type": r[2], "supplier_id": r[3],
                 "active": bool(r[4])} for r in rows]

    def preview_internal_barcode(self) -> str:
        """Siguiente EAN-13 interno libre (PROD-23), sin consumirlo."""
        from backend.application.products.queries.internal_barcode import (
            preview_internal_barcode,
        )
        return preview_internal_barcode(self._conn)
