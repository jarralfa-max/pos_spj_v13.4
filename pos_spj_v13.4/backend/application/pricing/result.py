"""Resultado estructurado de los casos de uso de Precios.

Misma forma que `SupplierResult` / `InventoryResult`: los casos de uso NO lanzan
para los fallos esperados (permiso, estado inválido, precio bajo mínimo) — los
devuelven, para que la pantalla pueda explicarlos. Las excepciones quedan para
lo inesperado.

Precios era el único de estos contextos sin tipo de resultado, sencillamente
porque no tenía capa de escritura: el dominio, la autorización y el repositorio
estaban completos, pero no había ni un caso de uso que los usara.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class PricingResult:
    success: bool
    message: str = ""
    operation_id: str | None = None
    entity_id: str | None = None
    error_code: str | None = None
    data: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def ok(cls, message: str = "", *, entity_id: str | None = None,
           operation_id: str | None = None, **data) -> "PricingResult":
        return cls(True, message, operation_id, entity_id, None, dict(data))

    @classmethod
    def fail(cls, message: str, error_code: str, *,
             operation_id: str | None = None, **data) -> "PricingResult":
        return cls(False, message, operation_id, None, error_code, dict(data))
