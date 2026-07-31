"""Resolve invoice tolerances from canonical configuration, never UI constants."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from backend.domain.procurement.value_objects import Tolerance


@dataclass(frozen=True, slots=True)
class InvoiceTolerances:
    quantity: Tolerance
    price: Tolerance
    tax: Tolerance


class ProcurementToleranceSettingsQueryService:
    def __init__(self, connection) -> None:
        self._connection = connection

    def invoice_tolerances(self, *, supplier_id: str | None = None,
                           nature: str | None = None) -> InvoiceTolerances:
        return InvoiceTolerances(
            quantity=Tolerance(self._value("quantity", supplier_id, nature)),
            price=Tolerance(self._value("price", supplier_id, nature)),
            tax=Tolerance(self._value("tax", supplier_id, nature)),
        )

    def _value(self, kind: str, supplier_id: str | None,
               nature: str | None) -> Decimal:
        keys = []
        if supplier_id:
            keys.append(f"procurement.tolerance.{kind}.supplier.{supplier_id}")
        if nature:
            keys.append(f"procurement.tolerance.{kind}.nature.{nature}")
        keys.append(f"procurement.tolerance.{kind}.default")
        for key in keys:
            row = self._connection.execute(
                "SELECT valor FROM configuraciones WHERE clave=?", (key,)).fetchone()
            if row is not None:
                return Decimal(str(row[0]))
        raise LookupError(f"Falta configuración canónica de tolerancia: {kind}")
