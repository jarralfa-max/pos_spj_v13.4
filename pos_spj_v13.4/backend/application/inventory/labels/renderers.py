"""Label renderers (INV-26) — pure functions: inventory data → LabelDocument.

No SQL, no I/O, no float. Each renderer maps a small primitive/DTO input to an
immutable ``LabelDocument`` with es-MX body lines and an optional barcode/QR. The
gateway later turns the document into ZPL / ESC-POS.
"""

from __future__ import annotations

from decimal import Decimal

from backend.domain.inventory.enums import LabelType
from backend.domain.inventory.value_objects.label_document import LabelDocument


def _num(value) -> Decimal:
    if value in (None, ""):
        return Decimal("0")
    return value if isinstance(value, Decimal) else Decimal(str(value))


def render_lot_label(*, product_id: str, product_name: str, lot_code: str,
                     expiration_date: str | None = None,
                     origin_type: str | None = None, branch_id: str | None = None,
                     lot_id: str | None = None, copies: int = 1) -> LabelDocument:
    lines = [f"Producto: {product_name}", f"Lote: {lot_code}"]
    if origin_type:
        lines.append(f"Origen: {origin_type}")
    if expiration_date:
        lines.append(f"Caduca: {expiration_date}")
    return LabelDocument(
        label_type=LabelType.LOT, title=product_name or product_id, lines=tuple(lines),
        barcode=lot_code, qr_payload=f"lot:{lot_id or lot_code}",
        entity_ref=lot_id or lot_code, copies=copies)


def render_weight_label(*, product_id: str, product_name: str, net_weight,
                        unit: str = "kg", tare=None, lot_code: str | None = None,
                        unit_price=None, branch_id: str | None = None,
                        copies: int = 1) -> LabelDocument:
    net = _num(net_weight)
    lines = [f"Producto: {product_name}", f"Peso neto: {net} {unit}"]
    if tare not in (None, ""):
        lines.append(f"Tara: {_num(tare)} {unit}")
    if lot_code:
        lines.append(f"Lote: {lot_code}")
    if unit_price not in (None, ""):
        importe = (_num(unit_price) * net)
        lines.append(f"Precio/{unit}: {_num(unit_price)}")
        lines.append(f"Importe: {importe}")
    return LabelDocument(
        label_type=LabelType.WEIGHT, title=product_name or product_id,
        lines=tuple(lines), barcode=lot_code or product_id,
        entity_ref=product_id, copies=copies)


def render_transfer_label(*, transfer_id: str, folio: str, origin_branch: str,
                          dest_branch: str, items: int, copies: int = 1) -> LabelDocument:
    lines = [f"Folio: {folio}", f"Origen: {origin_branch}",
             f"Destino: {dest_branch}", f"Ítems: {int(items)}"]
    return LabelDocument(
        label_type=LabelType.TRANSFER, title=f"Transferencia {folio}",
        lines=tuple(lines), barcode=folio, qr_payload=f"transfer:{transfer_id}",
        entity_ref=transfer_id, copies=copies)


def render_count_label(*, count_id: str, folio: str, warehouse: str,
                       location: str | None = None, copies: int = 1) -> LabelDocument:
    lines = [f"Folio: {folio}", f"Almacén: {warehouse}"]
    if location:
        lines.append(f"Ubicación: {location}")
    return LabelDocument(
        label_type=LabelType.COUNT, title=f"Conteo {folio}", lines=tuple(lines),
        barcode=folio, qr_payload=f"count:{count_id}", entity_ref=count_id,
        copies=copies)
