"""Barcode uniqueness policy (§17) — an active barcode belongs to one product.

"Los códigos activos deben ser únicos según policy." Given the barcode value's
current owner (looked up by the repository), assigning it to a different product
is rejected. Re-assigning to the same product (idempotent) is allowed. Inactive
duplicates do not block (a retired code may be reused).
"""

from __future__ import annotations

from backend.domain.products.exceptions import BarcodeAlreadyAssignedError


def ensure_barcode_assignable(
    *,
    barcode_value: str,
    product_id: str,
    current_owner_product_id: str | None,
) -> None:
    """Raise if ``barcode_value`` is already active on a different product."""
    if current_owner_product_id is None:
        return
    if current_owner_product_id != product_id:
        raise BarcodeAlreadyAssignedError(
            f"El código {barcode_value} ya está asignado a otro producto "
            f"({current_owner_product_id})")
