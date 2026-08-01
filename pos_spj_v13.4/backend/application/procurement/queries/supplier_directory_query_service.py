"""Procurement read contract over the canonical ``proveedores`` master."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SupplierEligibility:
    supplier_id: str
    active: bool
    purchasing_enabled: bool
    financially_blocked: bool


class SupplierDirectoryQueryService:
    """Read supplier eligibility without creating a second supplier aggregate."""

    def __init__(self, connection) -> None:
        self._connection = connection

    def get_eligibility(self, supplier_id: str) -> SupplierEligibility | None:
        cursor = self._connection.execute(
            "SELECT id, activo FROM proveedores WHERE id=?", (supplier_id,))
        row = cursor.fetchone()
        if row is None:
            return None
        return SupplierEligibility(
            supplier_id=str(row[0]), active=bool(row[1]),
            purchasing_enabled=True, financially_blocked=False)

    def require_eligible(self, supplier_id: str) -> None:
        from backend.domain.procurement.exceptions import SupplierNotEligibleError

        eligibility = self.get_eligibility(supplier_id)
        if eligibility is None:
            raise SupplierNotEligibleError("El proveedor canónico no existe")
        if (not eligibility.active or not eligibility.purchasing_enabled
                or eligibility.financially_blocked):
            raise SupplierNotEligibleError("El proveedor no está habilitado para compras")
