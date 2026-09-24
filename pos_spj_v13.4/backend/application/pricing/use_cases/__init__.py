"""Casos de uso de escritura de Precios y Costos.

Este paquete NO existía. El contexto tenía dominio completo (ciclo de vida de
listas con transiciones explícitas, `Money` Decimal-only, política de margen),
autorización completa (permisos granulares, segregación de funciones, alcance
por sucursal, autorización en caliente) y repositorio completo con sus
`save_*` — pero ni un solo caso de uso los usaba: los `save_*` no tenían
llamadores fuera del propio repositorio, y la UI era de sólo lectura.

Es decir, el módulo se podía abrir y no se podía ejecutar nada.
"""

from backend.application.pricing.use_cases.price_list_use_cases import (
    ActivatePriceListUseCase,
    ApprovePriceListUseCase,
    CreatePriceListUseCase,
    DeactivatePriceListUseCase,
    DuplicatePriceListUseCase,
    SubmitPriceListUseCase,
)
from backend.application.pricing.use_cases.product_price_use_cases import (
    ApplyPriceToSelectionUseCase,
    SetProductPriceUseCase,
    SetVolumePriceUseCase,
)

__all__ = [
    "ActivatePriceListUseCase",
    "ApprovePriceListUseCase",
    "CreatePriceListUseCase",
    "DeactivatePriceListUseCase",
    "DuplicatePriceListUseCase",
    "SubmitPriceListUseCase",
    "ApplyPriceToSelectionUseCase",
    "SetProductPriceUseCase",
    "SetVolumePriceUseCase",
]
