"""Tolerancias de factura: parámetros gobernados de Configuración.

`procurement.tolerance.{quantity,price,tax}`, afinables por proveedor
(ámbito SUPPLIER) y resueltos con la regla única del gobierno: proveedor →
global → omisión (0). Antes eran claves sueltas en `configuraciones`
(`...default`, `...supplier.<id>`, `...nature.<x>`); sin ellas la conciliación
reventaba (migración 266). Con valor de omisión en el catálogo eso ya no puede
pasar. El nivel por "naturaleza" se retiró: ningún llamador lo mandaba nunca.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.application.settings.configuration_reader import ConfigurationReader
from backend.domain.procurement.value_objects import Tolerance
from backend.domain.settings.enums import ScopeType


@dataclass(frozen=True, slots=True)
class InvoiceTolerances:
    quantity: Tolerance
    price: Tolerance
    tax: Tolerance


class ProcurementToleranceSettingsQueryService:
    def __init__(self, connection) -> None:
        self._reader = ConfigurationReader(connection)

    def invoice_tolerances(self, *, supplier_id: str | None = None) -> InvoiceTolerances:
        context = {ScopeType.SUPPLIER: supplier_id} if supplier_id else None
        return InvoiceTolerances(**{
            kind: Tolerance(self._reader.get(f"procurement.tolerance.{kind}", context=context))
            for kind in ("quantity", "price", "tax")})
